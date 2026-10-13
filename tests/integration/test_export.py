import json
import zipfile

import pandas as pd
import pytest

from afp import config
from afp.cli import main as cli_main
from afp.export.exporter import export_run, select_candidates, zip_export
from afp.io.fasta import InputError, parse_fasta
from afp.pipeline import execute_run, load_candidates
from afp.runner import launcher

pytestmark = pytest.mark.integration

PARAMS = {"seed_id": "type3_hplc12", "n_candidates": 15, "max_mutations": 4, "backend": "mock", "mcmc_steps": 40,
          "random_patches": 30, "rng_seed": 4}


@pytest.fixture
def run_dir(isolated_dirs):
    d = launcher.create_run(PARAMS)
    assert execute_run(d) == 0
    return d


def test_export_top_n_package_contents(run_dir):
    out = export_run(run_dir, "pkg", top=5)
    assert out == config.EXPORTS_DIR / "pkg"
    recs = parse_fasta((out / "candidates.fasta").read_text(encoding="utf-8"))
    assert recs[0][0] == "seed|wildtype" and len(recs) == 6                  # 시드 원본 + 5개
    seed = json.loads((run_dir / "seed.json").read_text(encoding="utf-8"))
    assert recs[0][1] == seed["sequence"]
    ranking = pd.read_csv(out / "ranking.csv")
    assert len(ranking) == 5 and list(ranking["rank"]) == sorted(ranking["rank"])
    assert recs[1][0].startswith(ranking.loc[0, "cand_id"])                   # FASTA 순서 = 순위 순서
    assert "rank=1" in recs[1][0] and "score=" in recs[1][0]
    for cid in ranking["cand_id"]:
        assert (out / "structures" / f"{cid}.pdb").exists()
    assert (out / "structures" / "seed_wildtype.pdb").exists()
    readme = (out / "README.txt").read_text(encoding="utf-8")
    assert config.DISCLAIMER in readme and run_dir.name in readme and "python -m afp.cli rerun" in readme
    for name in ("seed.json", "params.json", "versions.json", "scoring.json", "manifest.json"):
        assert (out / name).exists(), name
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["n_candidates"] == 5


def test_export_selected_ids_and_errors(run_dir):
    ids = list(load_candidates(run_dir)["cand_id"])[:3]
    out = export_run(run_dir, "picked", cand_ids=ids)
    assert set(pd.read_csv(out / "ranking.csv")["cand_id"]) == set(ids)
    with pytest.raises(InputError, match="실행에 없는 후보"):
        export_run(run_dir, "bad", cand_ids=["c9999"])


def test_export_refuses_overwrite_unless_asked(run_dir):
    export_run(run_dir, "twice", top=2)
    with pytest.raises(InputError, match="이미 내용이 있는 폴더"):
        export_run(run_dir, "twice", top=2)
    out = export_run(run_dir, "twice", top=3, overwrite=True)
    assert len(pd.read_csv(out / "ranking.csv")) == 3


def test_export_thresholds_can_empty_the_selection(run_dir):
    with pytest.raises(InputError, match="내보낼 후보가 없습니다"):
        export_run(run_dir, "none", top=5, min_plddt=99.9)
    df = load_candidates(run_dir)
    sel = select_candidates(df, 100, None, min_plddt=0, max_rmsd=1e9)
    assert len(sel) == len(df)


def test_export_works_without_evaluation(isolated_dirs):
    d = launcher.create_run({**PARAMS, "evaluate": False})
    assert execute_run(d) == 0
    out = export_run(d, "noeval", top=4)
    recs = parse_fasta((out / "candidates.fasta").read_text(encoding="utf-8"))
    assert len(recs) == 5 and "score=" not in recs[1][0]
    assert not (out / "scoring.json").exists()


def test_cli_export_and_zip(run_dir):
    assert cli_main(["export", "--run", run_dir.name, "--top", "3", "--out", "cli-pkg"]) == 0
    out = config.EXPORTS_DIR / "cli-pkg"
    z = zip_export(out)
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
    assert {"candidates.fasta", "ranking.csv", "README.txt"} <= names
    assert any(n.startswith("structures/") for n in names)


def test_cli_seeds_and_validate_smoke(isolated_dirs, tmp_path, capsys):
    assert cli_main(["seeds"]) == 0
    assert "type3_hplc12" in capsys.readouterr().out
    out = tmp_path / "val.md"
    assert cli_main(["validate", "--patches", "10", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "양성 대조 검증 보고서" in text and "사후 탐색" in text
    summary = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))["summary"]
    assert summary["verdict"] in ("합격", "부분 합격", "불합격") and summary["seeds_total"] >= 3

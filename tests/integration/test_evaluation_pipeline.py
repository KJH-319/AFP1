import json
import math

import numpy as np
import pytest

from afp import config
from afp.evaluate.scoring import apply_weights, flag_set, load_scoring
from afp.pipeline import execute_run, load_candidates, run_evaluate_only
from afp.runner import launcher
from afp.runner.status import read_status

pytestmark = pytest.mark.integration


def _run(params):
    base = {"seed_id": "type3_hplc12", "n_candidates": 12, "max_mutations": 4, "backend": "mock", "mcmc_steps": 40,
            "random_patches": 30, "rng_seed": 2, "evaluate": True}
    run_dir = launcher.create_run({**base, **params})
    assert execute_run(run_dir) == 0, launcher.tail_log(run_dir)
    return run_dir


def test_full_pipeline_fills_all_columns(isolated_dirs):
    run_dir = _run({})
    st = read_status(run_dir)
    assert st["state"] == "done"
    df = load_candidates(run_dir)
    for col in ("ibs_planarity", "ibs_area", "ibs_lattice_dev", "ibs_hydrophobic_frac", "esm_llr", "seq_identity",
                "net_charge", "pI", "flags", "score", "rank", "g_structure", "g_ibs", "g_afp", "g_dev"):
        assert col in df.columns, col
    assert sorted(df["rank"]) == list(range(1, len(df) + 1))
    assert df["score"].is_monotonic_decreasing                         # 순위순 정렬
    assert df["score"].between(0, 1.2).all()
    assert df["seq_identity"].between(0.9, 1.0).all()
    sc = load_scoring(run_dir)
    assert sc["disclaimer"] == config.DISCLAIMER
    assert sum(sc["weights"].values()) == pytest.approx(1.0)
    assert set(sc["anchors"]) == {"ibs_planarity", "ibs_area", "ibs_lattice_dev", "ibs_hydrophobic_frac"}
    assert sc["reference_structure"] == "predicted"


def test_evaluate_only_reproduces_scores(isolated_dirs):
    run_dir = _run({})
    before = load_candidates(run_dir)[["cand_id", "score", "rank"]]
    run_evaluate_only(run_dir)
    after = load_candidates(run_dir)[["cand_id", "score", "rank"]]
    assert list(before["cand_id"]) == list(after["cand_id"])
    assert np.allclose(before["score"], after["score"])


def test_reweighting_changes_ranking_without_recomputation(isolated_dirs):
    run_dir = _run({"n_candidates": 20})
    df = load_candidates(run_dir)
    a = apply_weights(df, {"structure": 1, "ibs": 0, "afp": 0, "dev": 0})
    b = apply_weights(df, {"structure": 0, "ibs": 0, "afp": 1, "dev": 0})
    assert list(a["cand_id"]) != list(b["cand_id"])
    top_by_structure = df.loc[df["g_structure"].idxmax(), "cand_id"]
    assert a.iloc[0]["cand_id"] == top_by_structure


def test_low_plddt_marks_low_ibs_confidence(isolated_dirs):
    run_dir = _run({"mock_plddt": 60.0})
    df = load_candidates(run_dir)
    assert all("low_ibs_confidence" in flag_set(f) for f in df["flags"])


@pytest.mark.parametrize("seed_id", ["type1_hplc6", "tmafp_beetle"])
def test_other_seeds_run_end_to_end(isolated_dirs, seed_id):
    run_dir = _run({"seed_id": seed_id, "n_candidates": 6})
    df = load_candidates(run_dir)
    assert len(df) == 6 and df["score"].notna().all()
    anchors = json.loads((run_dir / "scoring.json").read_text(encoding="utf-8"))["anchors"]
    for name in ("ibs_planarity", "ibs_area", "ibs_hydrophobic_frac"):
        assert not math.isnan(anchors[name]["x_seed"]) and not anchors[name]["degenerate"], name
    # 격자 지표: 쌍이 범위(3~10 Å) 안에 없으면(예: Type I의 Thr 간격 약 16 Å) NaN이고 점수에서 제외된다
    lat = anchors["ibs_lattice_dev"]
    assert lat["degenerate"] or not math.isnan(lat["x_seed"])

"""후보 내보내기 (F-15, M3-3): FASTA, PDB, CSV 순위표와 안내 파일. 실험팀 전달 패키지 형식."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from afp import config
from afp.io.fasta import InputError, format_fasta

README = """\
AFP Designer 내보내기 패키지
============================
생성: {created}
실행(run): {run_id}
시드: {seed_name} ({seed_id}), {n} 개 후보 선택

[중요] {disclaimer}
순위와 점수는 실험 후보를 고르는 우선순위 보조 지표입니다. 열이력(TH)이나 얼음 재결정 억제(IRI) 활성을
예측하지 않으며, 점수가 높아도 활성이 없을 수 있고 낮아도 활성이 있을 수 있습니다.

파일
----
candidates.fasta   첫 항목은 시드 원본(>seed|wildtype)이며 실험 양성 대조군으로 함께 발현할 것을 권장합니다.
                   나머지 헤더 형식: >후보ID|변이|score=점수|rank=순위 (변이 번호는 시드 서열의 1-based 인덱스)
ranking.csv        선택한 후보의 모든 지표 (열 설명은 docs/dev/00-conventions.md)
structures/        예측 구조(PDB, B-factor 열 = pLDDT 0~100)와 시드 실험 구조(seed_wildtype.pdb)
seed.json          사용한 시드와 IBS 잔기, 근거 수준({evidence_level})
params.json        실행 파라미터 (재현에 사용)
versions.json      도구·모델 버전과 하드웨어
scoring.json       점수 정의, 가중치, 정규화 기준값 (있는 경우)

재현
----
python -m afp.cli rerun --run {run_id}

실험 설계 제안 (최종 결정은 실험팀)
----------------------------------
- 대조군: 시드 원본(양성) + 활성이 없다고 알려진 단백질 또는 IBS 잔기를 치환한 변이체(음성)
- 측정: IRI(splat assay), 열이력(nanoliter osmometer)
- 결과 기록: 후보 ID(cand_id)를 그대로 유지한 CSV (v1.x 결과 업로드와 점수 보정에서 같은 ID를 사용)
- 개발성 플래그(n_glyc, odd_cys, hydrophobic_patch)는 발현 숙주와 정제 계획을 세울 때 참고하세요.
"""


def resolve_out(out: str | Path) -> Path:
    p = Path(out)
    if p.is_absolute() or p.parent != Path("."):
        return p
    return config.EXPORTS_DIR / p


def select_candidates(df: pd.DataFrame, top: int | None, cand_ids: list[str] | None,
                      min_plddt: float = 0.0, max_rmsd: float = 1e9) -> pd.DataFrame:
    if "rank" in df.columns:
        df = df.sort_values("rank")
    if cand_ids:
        missing = [c for c in cand_ids if c not in set(df["cand_id"])]
        if missing:
            raise InputError(f"실행에 없는 후보 ID: {missing}")
        return df[df["cand_id"].isin(cand_ids)]
    ok = df[(df["qc_status"] == "ok") & (df["plddt_mean"] >= min_plddt) & (df["rmsd_seed"] <= max_rmsd)]
    if "score" in ok.columns:
        ok = ok[ok["score"].notna()]
    return ok.head(top) if top else ok


def export_run(run_dir: Path, out: str | Path, *, top: int | None = 10, cand_ids: list[str] | None = None,
               min_plddt: float = 0.0, max_rmsd: float = 1e9, overwrite: bool = False) -> Path:
    from afp.pipeline import load_candidates

    run_dir = Path(run_dir)
    df = load_candidates(run_dir)
    sel = select_candidates(df, top, cand_ids, min_plddt, max_rmsd)
    if sel.empty:
        raise InputError("내보낼 후보가 없습니다(임계값을 확인하세요).")
    seed = json.loads((run_dir / "seed.json").read_text(encoding="utf-8"))
    out_dir = resolve_out(out)
    if out_dir.exists() and any(out_dir.iterdir()):
        if not overwrite:
            raise InputError(f"이미 내용이 있는 폴더입니다: {out_dir}")
        shutil.rmtree(out_dir)
    (out_dir / "structures").mkdir(parents=True, exist_ok=True)

    records = [("seed|wildtype", seed["sequence"])]
    for _, r in sel.iterrows():
        tag = f"{r['cand_id']}|{r['mutations'] or '-'}"
        if "score" in sel.columns and pd.notna(r.get("score")):
            tag += f"|score={r['score']:.3f}|rank={int(r['rank'])}"
        records.append((tag, r["sequence"]))
        src = run_dir / r["structure_path"] if r.get("structure_path") else None
        if src is not None and src.exists():
            shutil.copy2(src, out_dir / "structures" / f"{r['cand_id']}.pdb")
    (out_dir / "candidates.fasta").write_text(format_fasta(records), encoding="utf-8")
    sel.to_csv(out_dir / "ranking.csv", index=False)

    seed_pdb = config.SEEDS_DIR / seed["id"] / "structure.pdb"
    if seed_pdb.exists():
        shutil.copy2(seed_pdb, out_dir / "structures" / "seed_wildtype.pdb")
    for name in ("seed.json", "params.json", "versions.json", "scoring.json"):
        if (run_dir / name).exists():
            shutil.copy2(run_dir / name, out_dir / name)
    (out_dir / "README.txt").write_text(README.format(
        created=datetime.now().astimezone().isoformat(timespec="seconds"), run_id=run_dir.name,
        seed_name=seed["name"], seed_id=seed["id"], n=len(sel), disclaimer=config.DISCLAIMER,
        evidence_level=seed.get("ibs_evidence_level", "?")), encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps({
        "run_id": run_dir.name, "seed_id": seed["id"], "n_candidates": len(sel),
        "cand_ids": list(sel["cand_id"]), "disclaimer": config.DISCLAIMER,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


def zip_export(out_dir: Path) -> Path:
    """UI 다운로드용 ZIP. 폴더 옆에 <이름>.zip을 만든다."""
    return Path(shutil.make_archive(str(out_dir), "zip", root_dir=out_dir))

"""구조 품질 검사 (F-7): 구조 예측, pLDDT, 시드 대비 RMSD. 예측 결과는 서열 해시로 캐시한다."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

import numpy as np

from afp import config
from afp.io.pdb import bfactor_per_residue, ca_coords, kabsch_rmsd, parse_pdb
from afp.io.seeds import Seed
from afp.models import Prediction


def cache_key(sequence: str, model_name: str) -> str:
    return hashlib.sha1(f"{model_name}|{sequence}".encode()).hexdigest()[:20]


def predict_cached(predictor, sequence: str, cache_dir: Path | None = None) -> tuple[Prediction, bool]:
    """(예측, 캐시 적중 여부). 캐시 파일은 B-factor 열에 pLDDT를 가진 PDB다."""
    cache_dir = Path(cache_dir or config.CACHE_DIR) / "structures"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{cache_key(sequence, getattr(predictor, 'model_name', config.STRUCTURE_MODEL))}.pdb"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        return Prediction(pdb_text=text, plddt=bfactor_per_residue(parse_pdb(text, "A"))), True
    pred = predictor.predict(sequence)
    path.write_text(pred.pdb_text, encoding="utf-8")
    return pred, False


def qc_metrics(seed: Seed, pred: Prediction) -> dict:
    """pLDDT(전체/IBS)와 시드 대비 Cα RMSD."""
    residues = parse_pdb(pred.pdb_text, "A")
    if len(residues) != seed.length:
        raise ValueError(f"예측 구조의 잔기 수 {len(residues)} != 시드 {seed.length}")
    ibs = seed.ibs_indices
    return {
        "plddt_mean": float(np.mean(pred.plddt)),
        "plddt_ibs": float(np.mean(pred.plddt[ibs])),
        "rmsd_seed": kabsch_rmsd(ca_coords(residues), ca_coords(seed.residues())),
    }


def run_structure_qc(
    df,
    seed: Seed,
    predictor,
    run_dir: Path,
    *,
    cache_dir: Path | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> None:
    """df(candidates)에 plddt_mean, plddt_ibs, rmsd_seed, qc_status, structure_path 열을 채운다."""
    run_dir = Path(run_dir)
    (run_dir / "structures").mkdir(parents=True, exist_ok=True)
    for col in ("plddt_mean", "plddt_ibs", "rmsd_seed"):
        df[col] = np.nan
    df["qc_status"] = ""
    df["structure_path"] = ""
    total = len(df)
    for n, idx in enumerate(df.index, start=1):
        cand_id, seq = df.at[idx, "cand_id"], df.at[idx, "sequence"]
        try:
            pred, hit = predict_cached(predictor, seq, cache_dir)
            m = qc_metrics(seed, pred)
            rel = f"structures/{cand_id}.pdb"
            (run_dir / rel).write_text(pred.pdb_text, encoding="utf-8")
            for k, v in m.items():
                df.at[idx, k] = v
            df.at[idx, "structure_path"] = rel
            df.at[idx, "qc_status"] = "ok"
        except Exception as exc:  # noqa: BLE001  개별 실패는 기록하고 계속 진행
            df.at[idx, "qc_status"] = f"failed: {type(exc).__name__}: {str(exc)[:120]}"
        if progress:
            progress(n / total, f"구조 예측 {n}/{total}")


def apply_thresholds(df, plddt_min: float = config.PLDDT_MIN, rmsd_max: float = config.RMSD_MAX):
    """임계값 통과 여부(bool 시리즈). 실패 후보는 False."""
    return (df["qc_status"] == "ok") & (df["plddt_mean"] >= plddt_min) & (df["rmsd_seed"] <= rmsd_max)


def baseline(seed: Seed, predictor, cache_dir: Path | None = None) -> dict:
    """M0-8: 시드 서열을 예측해 실험 구조와 비교한다 (임계값 근거 자료)."""
    pred, _ = predict_cached(predictor, seed.sequence, cache_dir)
    m = qc_metrics(seed, pred)
    m["seed_id"] = seed.id
    m["length"] = seed.length
    return m

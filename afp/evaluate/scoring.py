"""종합 점수와 순위 (F-11) 및 평가 단계 실행 (IBS 지표, AFP 유사도, 개발성).

점수는 4개 그룹(구조 신뢰도, IBS, AFP 유사도, 개발성)의 가중합이다. 그룹 값은 후보 표에
(`g_structure`, `g_ibs`, `g_afp`, `g_dev`) 저장하므로, UI의 가중치 슬라이더는 재계산만 하면 된다.

IBS 지표는 시드의 실제 IBS 값(양성 앵커)과 같은 크기 무작위 표면 패치의 중앙값(음성 앵커) 사이로
정규화한다. 시드와 음성 앵커가 같은 지표(변별력 없음)는 점수에서 제외하고 scoring.json에 표시한다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from afp import config
from afp.evaluate import ibs_metrics as ibs
from afp.evaluate.developability import DEV_FLAGS, developability, seq_identity
from afp.evaluate.structure_qc import predict_cached
from afp.io.pdb import parse_pdb, residue_sasa
from afp.io.seeds import Seed
from afp.runner.launcher import load_params
from afp.runner.status import write_json_atomic

GROUPS = ("structure", "ibs", "afp", "dev")
DEFINITION_VERSION = 1


# ---------------------------------------------------------------- 순수 함수 (UI에서도 사용)

def flag_set(text) -> set[str]:
    return {f for f in str(text or "").split(";") if f}


def flag_str(flags) -> str:
    return ";".join(sorted(flags))


def normalize_ibs_metric(name: str, x: float, anchor: dict) -> float:
    """IBS 지표 하나를 0~IBS_NORM_CAP로. 변별력 없는(degenerate) 지표나 NaN은 NaN."""
    if x is None or (isinstance(x, float) and math.isnan(x)) or anchor.get("degenerate"):
        return float("nan")
    x_seed, x_neg = anchor["x_seed"], anchor["x_neg"]
    span = x_seed - x_neg
    if name == "ibs_hydrophobic_frac":                       # 시드와 가까울수록 좋음
        return float(np.clip(1.0 - abs(x - x_seed) / abs(span), 0.0, 1.0))
    return float(np.clip((x - x_neg) / span, 0.0, config.IBS_NORM_CAP))


def structure_group(plddt_mean, rmsd) -> float:
    if pd.isna(plddt_mean) or pd.isna(rmsd):
        return float("nan")
    p = np.clip((plddt_mean - config.PLDDT_NORM_LO) / (config.PLDDT_NORM_HI - config.PLDDT_NORM_LO), 0, 1)
    r = np.clip(1.0 - rmsd / config.RMSD_NORM_MAX, 0, 1)
    return float((p + r) / 2)


def afp_group(esm_llr, n_mut, identity) -> float:
    if pd.isna(esm_llr) or pd.isna(identity) or n_mut < 1:
        return float("nan")
    llr = np.clip(0.5 + (esm_llr / n_mut) / config.LLR_PER_MUTATION_SCALE, 0, 1)
    return float((llr + identity) / 2)


def dev_group(flags: set[str]) -> float:
    return float(max(0.0, 1.0 - config.DEV_FLAG_PENALTY * len(flags & set(DEV_FLAGS))))


def compute_groups(df: pd.DataFrame, anchors: dict) -> pd.DataFrame:
    df = df.copy()
    df["g_structure"] = [structure_group(p, r) for p, r in zip(df["plddt_mean"], df["rmsd_seed"])]
    ibs_vals = []
    for _, row in df.iterrows():
        norms = [normalize_ibs_metric(m, row.get(m), anchors[m]) for m in ibs.METRIC_NAMES]
        norms = [v for v in norms if not math.isnan(v)]
        ibs_vals.append(float(np.mean(norms)) if norms else float("nan"))
    df["g_ibs"] = ibs_vals
    df["g_afp"] = [afp_group(e, n, i) for e, n, i in zip(df["esm_llr"], df["n_mut"], df["seq_identity"])]
    df["g_dev"] = [dev_group(flag_set(f)) for f in df["flags"]]
    return df


def normalize_weights(weights: dict | None) -> dict:
    w = {g: float((weights or {}).get(g, config.DEFAULT_WEIGHTS[g])) for g in GROUPS}
    total = sum(w.values())
    if total <= 0:
        raise ValueError("가중치 합이 0 이하입니다.")
    return {g: v / total for g, v in w.items()}


def apply_weights(df: pd.DataFrame, weights: dict | None, plddt_min: float = config.PLDDT_MIN) -> pd.DataFrame:
    """가중합 점수와 순위, near_duplicate 플래그를 다시 계산한다 (UI 슬라이더용)."""
    df = df.copy()
    w = normalize_weights(weights)
    scores = []
    for _, row in df.iterrows():
        parts = {g: row[f"g_{g}"] for g in GROUPS}
        if row["qc_status"] != "ok" or any(pd.isna(parts[g]) for g in ("structure", "afp", "dev")):
            scores.append(float("nan"))
            continue
        # IBS 그룹만 비어 있으면(모든 지표가 제외됨) 그 그룹을 빼고 나머지 가중치로 재정규화한다
        usable = {g: v for g, v in parts.items() if not pd.isna(v)}
        total = sum(w[g] for g in usable)
        scores.append(sum(w[g] * v for g, v in usable.items()) / total)
    df["score"] = scores
    order = df["score"].rank(method="first", ascending=False, na_option="bottom")
    df["rank"] = order.astype(int)
    df = mark_near_duplicates(df)
    return df.sort_values("rank").reset_index(drop=True)


def mark_near_duplicates(df: pd.DataFrame, identity: float = config.DUPLICATE_IDENTITY) -> pd.DataFrame:
    """순위가 높은 후보와 서열 동일도가 기준 이상이면 near_duplicate 플래그 (점수에는 영향 없음)."""
    df = df.copy()
    flags = [flag_set(f) - {"near_duplicate"} for f in df["flags"]]
    kept: list[str] = []
    for pos in df.sort_values("rank").index:
        seq = df.at[pos, "sequence"]
        if any(len(seq) == len(k) and np.mean([a == b for a, b in zip(seq, k)]) >= identity for k in kept):
            flags[df.index.get_loc(pos)].add("near_duplicate")
        else:
            kept.append(seq)
    df["flags"] = [flag_str(f) for f in flags]
    return df


# ---------------------------------------------------------------- 평가 단계

def _reference_structure(seed: Seed, predictor, cache_dir) -> tuple[list, str, str]:
    """앵커 계산에 쓸 기준 구조. 예측기가 있으면 시드 서열의 예측 구조(후보와 같은 방식), 없으면 실험 구조."""
    if predictor is not None:
        pred, _ = predict_cached(predictor, seed.sequence, cache_dir)
        return parse_pdb(pred.pdb_text, "A"), pred.pdb_text, "predicted"
    return seed.residues(), seed.structure_text(), "experimental"


def build_anchors(seed: Seed, residues, pdb_text: str, n_patches: int, rng_seed: int) -> tuple[dict, dict]:
    sasa = residue_sasa(pdb_text)
    indices = seed.ibs_indices
    x_seed = ibs.metrics_for_indices(residues, seed.sequence, indices, sasa)
    rng = np.random.default_rng([rng_seed, 4242])
    patches = ibs.random_patch_metrics(residues, seed.sequence, pdb_text, len(indices), n_patches, rng, sasa)
    summary = ibs.summarize_patches(patches)
    anchors = {}
    for name in ibs.METRIC_NAMES:
        xs, xn = x_seed[name], summary[name]["median"]
        degenerate = (math.isnan(xs) or math.isnan(xn) or abs(xs - xn) < 1e-6)
        anchors[name] = {"x_seed": xs, "x_neg": xn, "neg_p10": summary[name]["p10"], "neg_p90": summary[name]["p90"],
                         "n_patches": summary[name]["n"], "degenerate": bool(degenerate)}
    seed_hydro = sum(sasa[r.number] for r, aa in zip(residues, seed.sequence) if aa in "AVLIMFW") / sum(sasa.values())
    return anchors, {"seed_exposed_hydrophobic_frac": float(seed_hydro)}


def run_evaluation(run_dir: Path, *, seed: Seed, scorer=None, predictor=None, progress=None, status=None) -> pd.DataFrame:
    """candidates.csv에 IBS 지표, AFP 유사도, 개발성, 점수, 순위를 채우고 scoring.json을 쓴다."""
    from afp.pipeline import load_candidates, save_candidates

    run_dir = Path(run_dir)
    params = load_params(run_dir)
    df = load_candidates(run_dir)
    if "qc_status" not in df.columns:
        raise RuntimeError("구조 QC 결과가 없습니다. 먼저 design(구조 QC까지)을 실행하세요.")
    plddt_min = float(params.get("plddt_min", config.PLDDT_MIN))

    def report(frac, msg):
        if progress:
            progress(frac, msg)

    if status:
        status.stage("ibs_metrics", None, "IBS 기준선 계산 중")
    ref_res, ref_text, ref_kind = _reference_structure(seed, predictor, config.CACHE_DIR)
    n_patches = int(params.get("random_patches", config.RANDOM_PATCH_COUNT))
    anchors, extra = build_anchors(seed, ref_res, ref_text, n_patches, int(params.get("rng_seed", 1)))
    report(0.15, "IBS 기준선 완료")

    indices = seed.ibs_indices
    cols = {k: [] for k in (*ibs.METRIC_NAMES, "seq_identity", "net_charge", "pI", "exposed_hydrophobic_frac")}
    flags_out = []
    total = len(df)
    for n, (_, row) in enumerate(df.iterrows(), start=1):
        flags = flag_set(row.get("flags", ""))
        seq = row["sequence"]
        cols["seq_identity"].append(seq_identity(seq, seed.sequence))
        if row["qc_status"] == "ok" and row["structure_path"]:
            text = (run_dir / row["structure_path"]).read_text(encoding="utf-8")
            residues = parse_pdb(text, "A")
            sasa = residue_sasa(text)
            m = ibs.metrics_for_indices(residues, seq, indices, sasa)
            dev = developability(seq, seed.sequence, residues, sasa, extra["seed_exposed_hydrophobic_frac"])
            if row["plddt_ibs"] < plddt_min:
                flags.add("low_ibs_confidence")
        else:
            m = {k: float("nan") for k in ibs.METRIC_NAMES}
            dev = developability(seq, seed.sequence)
            flags.add("qc_failed")
        for k in ibs.METRIC_NAMES:
            cols[k].append(m[k])
        for k in ("net_charge", "pI", "exposed_hydrophobic_frac"):
            cols[k].append(dev[k])
        flags |= set(dev["dev_flags"])
        flags_out.append(flag_str(flags))
        if n % 5 == 0 or n == total:
            report(0.15 + 0.75 * n / total, f"IBS 지표·개발성 {n}/{total}")
    for k, v in cols.items():
        df[k] = v
    df["flags"] = flags_out

    if status:
        status.stage("scoring", None, "점수 계산 중")
    weights = params.get("weights") or config.DEFAULT_WEIGHTS
    df = apply_weights(compute_groups(df, anchors), weights, plddt_min)
    save_candidates(df, run_dir)
    write_json_atomic(run_dir / "scoring.json", {
        "definition_version": DEFINITION_VERSION,
        "weights": normalize_weights(weights),
        "reference_structure": ref_kind,
        "anchors": anchors,
        "seed_exposed_hydrophobic_frac": extra["seed_exposed_hydrophobic_frac"],
        "constants": {k: getattr(config, k) for k in (
            "PLDDT_NORM_LO", "PLDDT_NORM_HI", "RMSD_NORM_MAX", "IBS_NORM_CAP", "LLR_PER_MUTATION_SCALE",
            "DEV_FLAG_PENALTY", "HYDROPHOBIC_PATCH_DELTA", "DUPLICATE_IDENTITY")},
        "lattice": {"spacings": list(config.ICE_LATTICE_SPACINGS), "max_multiple": config.LATTICE_MAX_MULTIPLE,
                    "pair_range": [config.LATTICE_PAIR_MIN, config.LATTICE_PAIR_MAX]},
        "n_random_patches": n_patches,
        "disclaimer": config.DISCLAIMER,
    })
    report(1.0, "평가 완료")
    return df


def load_scoring(run_dir: Path) -> dict | None:
    p = Path(run_dir) / "scoring.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

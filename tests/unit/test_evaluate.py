import math

import numpy as np
import pandas as pd
import pytest

from afp import config
from afp.evaluate import ibs_metrics as ibs
from afp.evaluate.developability import charge_and_pi, developability, seq_identity, sequon_count
from afp.evaluate.scoring import (
    afp_group, apply_weights, dev_group, flag_set, mark_near_duplicates, normalize_ibs_metric,
    normalize_weights, structure_group,
)
from afp.io.pdb import residue_sasa

pytestmark = pytest.mark.unit


# ------------------------------------------------------------ 기하 지표

def test_planarity_zero_for_coplanar_points_and_positive_otherwise():
    rng = np.random.default_rng(0)
    flat = np.c_[rng.normal(size=(8, 2)) * 5, np.zeros(8)]
    assert ibs.planarity(flat) == pytest.approx(0.0, abs=1e-9)
    bumpy = flat + np.c_[np.zeros((8, 2)), rng.normal(0, 1.0, 8)]
    assert ibs.planarity(bumpy) > 0.3
    assert math.isnan(ibs.planarity(flat[:2]))


def test_planarity_known_value():
    # 5 Å 간격 4x4 격자에 z를 체스판 무늬로 +-0.8 Å 어긋나게 둔다 -> 최적 평면은 z=0, RMS 0.8
    pts = np.array([[5.0 * i, 5.0 * j, 0.8 * (-1) ** (i + j)] for i in range(4) for j in range(4)])
    assert ibs.planarity(pts) == pytest.approx(0.8, abs=1e-9)


def test_lattice_deviation_zero_for_ideal_spacing():
    ideal = np.array([[0, 0, 0], [4.52, 0, 0], [9.04, 0, 0]], dtype=float)   # 거리 4.52, 4.52, 9.04
    assert ibs.lattice_deviation(ideal) == pytest.approx(0.0, abs=1e-9)
    off = np.array([[0, 0, 0], [5.6, 0, 0]], dtype=float)                     # 5.6는 4.52 또는 7.35에서 1.08
    assert ibs.lattice_deviation(off) == pytest.approx(min(5.6 - 4.52, 7.35 - 5.6), abs=1e-9)
    assert math.isnan(ibs.lattice_deviation(ideal[:1]))
    assert math.isnan(ibs.lattice_deviation(np.array([[0, 0, 0], [1.0, 0, 0]])))     # 너무 가까움


def test_metrics_for_seed_ibs(seed):
    sasa = residue_sasa(seed.structure_text())
    m = ibs.metrics_for_indices(seed.residues(), seed.sequence, seed.ibs_indices, sasa)
    assert set(m) == set(ibs.METRIC_NAMES)
    assert m["ibs_area"] > 20
    expected_hydro = np.mean([seed.sequence[i] in config.HYDROPHOBIC for i in seed.ibs_indices])
    assert m["ibs_hydrophobic_frac"] == pytest.approx(expected_hydro)
    assert not math.isnan(m["ibs_planarity"])


def test_functional_point_uses_polar_atom_for_threonine(type3):
    thr = next(r for r in type3.residues() if r.aa == "T")
    xyz, polar = ibs.functional_point(thr)
    assert polar and np.allclose(xyz, thr.atoms["OG1"])
    ala = next(r for r in type3.residues() if r.aa == "A")
    xyz, polar = ibs.functional_point(ala)
    assert not polar and np.allclose(xyz, ala.atoms["CB"])


def test_random_patches_have_requested_size_and_are_deterministic(type3):
    text = type3.structure_text()
    sasa = residue_sasa(text)
    surface = ibs.surface_indices(type3.residues(), sasa)
    k = len(type3.ibs_indices)
    a = ibs.random_patch_indices(type3.residues(), surface, k, np.random.default_rng(5))
    b = ibs.random_patch_indices(type3.residues(), surface, k, np.random.default_rng(5))
    assert a == b and len(a) == k and set(a) <= set(surface)
    patches = ibs.random_patch_metrics(type3.residues(), type3.sequence, text, k, 20, np.random.default_rng(1), sasa)
    assert len(patches) == 20
    summary = ibs.summarize_patches(patches)
    assert summary["ibs_area"]["p10"] <= summary["ibs_area"]["median"] <= summary["ibs_area"]["p90"]
    with pytest.raises(ValueError):
        ibs.random_patch_indices(type3.residues(), surface[:3], k, np.random.default_rng(0))


# ------------------------------------------------------------ 점수

ANCHOR = {"x_seed": 2.0, "x_neg": 6.0, "degenerate": False}        # 낮을수록 좋은 지표(예: 평면성 유사)


def test_normalize_ibs_metric_linear_between_anchors():
    assert normalize_ibs_metric("ibs_planarity", 2.0, ANCHOR) == pytest.approx(1.0)
    assert normalize_ibs_metric("ibs_planarity", 6.0, ANCHOR) == pytest.approx(0.0)
    assert normalize_ibs_metric("ibs_planarity", 4.0, ANCHOR) == pytest.approx(0.5)
    assert normalize_ibs_metric("ibs_planarity", -10.0, ANCHOR) == pytest.approx(config.IBS_NORM_CAP)
    assert normalize_ibs_metric("ibs_planarity", 50.0, ANCHOR) == pytest.approx(0.0)
    up = {"x_seed": 200.0, "x_neg": 100.0, "degenerate": False}    # 높을수록 좋은 지표(넓이)
    assert normalize_ibs_metric("ibs_area", 150.0, up) == pytest.approx(0.5)


def test_normalize_hydrophobic_is_closeness_to_seed():
    a = {"x_seed": 0.5, "x_neg": 0.25, "degenerate": False}
    assert normalize_ibs_metric("ibs_hydrophobic_frac", 0.5, a) == pytest.approx(1.0)
    assert normalize_ibs_metric("ibs_hydrophobic_frac", 0.75, a) == pytest.approx(0.0)
    assert normalize_ibs_metric("ibs_hydrophobic_frac", 0.375, a) == pytest.approx(0.5)


def test_degenerate_anchor_and_nan_are_excluded():
    bad = {"x_seed": 1.0, "x_neg": 1.0, "degenerate": True}
    assert math.isnan(normalize_ibs_metric("ibs_area", 3.0, bad))
    assert math.isnan(normalize_ibs_metric("ibs_area", float("nan"), ANCHOR))


def test_group_functions_bounds():
    assert structure_group(90, 0) == pytest.approx(1.0)
    assert structure_group(50, 4.0) == pytest.approx(0.0)
    assert structure_group(70, 2.0) == pytest.approx(0.5)
    assert math.isnan(structure_group(float("nan"), 1.0))
    assert afp_group(0.0, 4, 1.0) == pytest.approx(0.75)           # 로그비 0 -> 0.5, 동일도 1 -> 평균 0.75
    assert afp_group(8.0, 4, 0.9) == pytest.approx((1.0 + 0.9) / 2)
    assert dev_group(set()) == 1.0
    assert dev_group({"n_glyc", "odd_cys"}) == pytest.approx(0.5)
    assert dev_group({"near_duplicate", "low_ibs_confidence"}) == 1.0   # 개발성 그룹에 속하지 않는 플래그


def test_normalize_weights():
    w = normalize_weights({"structure": 2, "ibs": 2, "afp": 0, "dev": 0})
    assert w["structure"] == pytest.approx(0.5) and sum(w.values()) == pytest.approx(1.0)
    assert normalize_weights(None) == pytest.approx(normalize_weights(config.DEFAULT_WEIGHTS))
    with pytest.raises(ValueError):
        normalize_weights({"structure": 0, "ibs": 0, "afp": 0, "dev": 0})


def _frame(rows):
    df = pd.DataFrame(rows)
    for col, default in (("qc_status", "ok"), ("flags", ""), ("sequence", None)):
        if col not in df:
            df[col] = default
    df["qc_status"] = df["qc_status"].fillna("ok")
    if df["sequence"].isna().all():
        df["sequence"] = ["A" * 10 + chr(65 + i) * 1 for i in range(len(df))]
    return df


def test_dominating_candidate_always_ranks_first_for_any_weights():
    df = _frame([
        {"cand_id": "a", "g_structure": 0.9, "g_ibs": 0.9, "g_afp": 0.9, "g_dev": 1.0},
        {"cand_id": "b", "g_structure": 0.5, "g_ibs": 0.4, "g_afp": 0.6, "g_dev": 0.75},
        {"cand_id": "c", "g_structure": 0.2, "g_ibs": 0.8, "g_afp": 0.1, "g_dev": 0.5},
    ])
    rng = np.random.default_rng(0)
    for _ in range(30):
        w = dict(zip(("structure", "ibs", "afp", "dev"), rng.random(4) + 1e-3))
        out = apply_weights(df, w)
        order = list(out["cand_id"])
        assert order.index("a") < order.index("b")


def test_raising_a_weight_never_lowers_the_leader_in_that_group():
    df = _frame([
        {"cand_id": "s", "g_structure": 0.95, "g_ibs": 0.3, "g_afp": 0.5, "g_dev": 1.0},
        {"cand_id": "i", "g_structure": 0.40, "g_ibs": 0.95, "g_afp": 0.5, "g_dev": 1.0},
    ])
    base = {"structure": 1, "ibs": 1, "afp": 1, "dev": 1}
    r0 = apply_weights(df, base).set_index("cand_id")["rank"]["i"]
    r1 = apply_weights(df, {**base, "ibs": 10}).set_index("cand_id")["rank"]["i"]
    assert r1 <= r0 and r1 == 1


def test_failed_and_missing_groups_rank_last_and_ibs_missing_is_renormalized():
    df = _frame([
        {"cand_id": "ok", "g_structure": 0.8, "g_ibs": 0.8, "g_afp": 0.8, "g_dev": 1.0},
        {"cand_id": "noibs", "g_structure": 0.8, "g_ibs": float("nan"), "g_afp": 0.8, "g_dev": 1.0},
        {"cand_id": "bad", "g_structure": float("nan"), "g_ibs": float("nan"), "g_afp": 0.8, "g_dev": 1.0, "qc_status": "failed: x"},
    ])
    out = apply_weights(df, None).set_index("cand_id")
    assert out.loc["bad", "rank"] == 3 and math.isnan(out.loc["bad", "score"])
    assert out.loc["noibs", "score"] == pytest.approx((0.3 * 0.8 + 0.2 * 0.8 + 0.1 * 1.0) / 0.6)


def test_near_duplicate_flag_goes_to_lower_ranked_one():
    base = "ACDEFGHIKLMNPQRSTVWY" * 5                 # 100 aa
    near = base[:-1] + "A"                             # 동일도 0.99 (마지막 Y -> A)
    far = "A" * 60 + base[60:]
    df = pd.DataFrame({"cand_id": ["x", "y", "z"], "sequence": [base, near, far], "rank": [1, 2, 3], "flags": ["", "", ""]})
    out = mark_near_duplicates(df).set_index("cand_id")
    assert "near_duplicate" not in flag_set(out.loc["x", "flags"])
    assert "near_duplicate" in flag_set(out.loc["y", "flags"])
    assert "near_duplicate" not in flag_set(out.loc["z", "flags"])


# ------------------------------------------------------------ 개발성

def test_sequon_detection():
    assert sequon_count("AAANASAA") == 1
    assert sequon_count("AAANPSAA") == 0       # N-P-S는 제외
    assert sequon_count("AAANATAANGT") == 2


def test_developability_flags(type3):
    s = type3.sequence
    clean = developability(s, s)
    assert clean["dev_flags"] == []
    glyc = s[:30] + "NAS" + s[33:]
    assert "n_glyc" in developability(glyc, s)["dev_flags"]
    cys = s[:30] + "C" + s[31:]
    assert "odd_cys" in developability(cys, s)["dev_flags"]


def test_hydrophobic_patch_flag_needs_structure(type3):
    sasa = residue_sasa(type3.structure_text())
    res = type3.residues()
    base = developability(type3.sequence, type3.sequence, res, sasa, seed_hydro_fraction=0.0)
    assert not math.isnan(base["exposed_hydrophobic_frac"])
    assert "hydrophobic_patch" in base["dev_flags"] or base["exposed_hydrophobic_frac"] <= config.HYDROPHOBIC_PATCH_DELTA
    same = developability(type3.sequence, type3.sequence, res, sasa, seed_hydro_fraction=base["exposed_hydrophobic_frac"])
    assert "hydrophobic_patch" not in same["dev_flags"]


def test_charge_direction_and_identity():
    pos, _ = charge_and_pi("K" * 10 + "A" * 10)
    neg, _ = charge_and_pi("D" * 10 + "A" * 10)
    assert pos > 5 > -5 > neg
    assert charge_and_pi("KKKKRRRR")[1] > 9
    assert seq_identity("AAAA", "AAAB") == 0.75
    with pytest.raises(ValueError):
        seq_identity("AA", "AAA")

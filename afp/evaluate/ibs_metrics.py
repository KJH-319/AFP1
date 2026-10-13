"""IBS 지표 4종과 무작위 패치 기준선 (F-8).

모든 지표는 구조(예측 또는 실험)와 IBS 잔기의 0-based 인덱스로 계산한다. 정의는 출발점이며
M3 양성 대조 검증에서 변별력을 확인한다(docs/dev/validation-report.md).

- ibs_planarity   : IBS 대표 원자들의 최소제곱 평면으로부터의 RMS 거리 (Å, 낮을수록 평평)
- ibs_area        : IBS 잔기의 용매 접근 표면적 합 (Å^2)
- ibs_lattice_dev : IBS 극성 원자 쌍 거리가 얼음 격자 간격(4.52, 7.35 Å와 그 배수)에서 벗어난 평균 (Å)
- ibs_hydrophobic_frac : IBS 잔기 중 소수성 잔기의 비율
"""
from __future__ import annotations

import numpy as np

from afp import config
from afp.io.pdb import MAX_SASA, Residue, residue_sasa

FUNCTIONAL_ATOM = {"T": "OG1", "S": "OG", "N": "OD1", "Q": "OE1", "Y": "OH", "D": "OD1", "E": "OE1", "K": "NZ", "R": "NH1", "H": "NE2"}
METRIC_NAMES = ("ibs_planarity", "ibs_area", "ibs_lattice_dev", "ibs_hydrophobic_frac")


def functional_point(res: Residue) -> tuple[np.ndarray, bool]:
    """(좌표, 극성 원자 여부). 극성 잔기는 말단 극성 원자, 그 외는 Cβ(Gly는 Cα)."""
    name = FUNCTIONAL_ATOM.get(res.aa)
    if name and name in res.atoms:
        return res.atoms[name], True
    if "CB" in res.atoms:
        return res.atoms["CB"], False
    return res.atoms["CA"], False


def planarity(points: np.ndarray) -> float:
    """평면 맞춤 RMS 거리 (Å). 점이 3개 미만이면 NaN."""
    if len(points) < 3:
        return float("nan")
    centered = points - points.mean(axis=0)
    _, s, _ = np.linalg.svd(centered, full_matrices=False)
    return float(s[-1] / np.sqrt(len(points)))


def lattice_deviation(polar_points: np.ndarray) -> float:
    """극성 원자 쌍 거리가 가장 가까운 격자 허용 거리에서 벗어난 평균(Å). 쌍이 없으면 NaN."""
    if len(polar_points) < 2:
        return float("nan")
    allowed = sorted({n * s for s in config.ICE_LATTICE_SPACINGS for n in range(1, config.LATTICE_MAX_MULTIPLE + 1)
                      if n * s <= config.LATTICE_PAIR_MAX})
    dist = np.sqrt(((polar_points[:, None, :] - polar_points[None, :, :]) ** 2).sum(-1))
    iu = np.triu_indices(len(polar_points), k=1)
    d = dist[iu]
    d = d[(d >= config.LATTICE_PAIR_MIN) & (d <= config.LATTICE_PAIR_MAX)]
    if len(d) == 0:
        return float("nan")
    return float(np.mean([min(abs(x - a) for a in allowed) for x in d]))


def metrics_for_indices(residues: list[Residue], sequence: str, indices: list[int], sasa: dict[int, float]) -> dict:
    pts, polar = [], []
    for i in indices:
        xyz, is_polar = functional_point(residues[i])
        pts.append(xyz)
        if is_polar:
            polar.append(xyz)
    pts_arr = np.array(pts)
    return {
        "ibs_planarity": planarity(pts_arr),
        "ibs_area": float(sum(sasa[residues[i].number] for i in indices)),
        "ibs_lattice_dev": lattice_deviation(np.array(polar)) if polar else float("nan"),
        "ibs_hydrophobic_frac": float(np.mean([sequence[i] in config.HYDROPHOBIC for i in indices])),
    }


def compute_ibs_metrics(residues: list[Residue], sequence: str, indices: list[int], pdb_text: str,
                        sasa: dict[int, float] | None = None) -> dict:
    return metrics_for_indices(residues, sequence, indices, sasa or residue_sasa(pdb_text))


# ---------------------------------------------------------------- 무작위 패치 기준선

def surface_indices(residues: list[Residue], sasa: dict[int, float], rel_cut: float = config.SURFACE_REL_SASA) -> list[int]:
    return [i for i, r in enumerate(residues) if sasa[r.number] / MAX_SASA[r.aa] >= rel_cut]


def random_patch_indices(residues: list[Residue], surface: list[int], k: int, rng: np.random.Generator) -> list[int]:
    """표면 잔기 하나를 중심으로 가장 가까운 표면 잔기 k개 (Cα 거리) = 같은 크기의 무작위 표면 패치."""
    if len(surface) < k:
        raise ValueError(f"표면 잔기({len(surface)})가 패치 크기({k})보다 적습니다.")
    cas = np.array([residues[i].ca for i in surface])
    center = cas[int(rng.integers(len(surface)))]
    order = np.argsort(((cas - center) ** 2).sum(axis=1))[:k]
    return sorted(surface[int(j)] for j in order)


def random_patch_metrics(residues: list[Residue], sequence: str, pdb_text: str, k: int, n: int,
                         rng: np.random.Generator, sasa: dict[int, float] | None = None) -> list[dict]:
    """같은 구조에서 크기 k의 무작위 표면 패치 n개의 지표. 중복 패치는 허용한다."""
    sasa = sasa or residue_sasa(pdb_text)
    surface = surface_indices(residues, sasa)
    return [metrics_for_indices(residues, sequence, random_patch_indices(residues, surface, k, rng), sasa) for _ in range(n)]


def summarize_patches(patch_metrics: list[dict]) -> dict[str, dict]:
    out = {}
    for name in METRIC_NAMES:
        vals = np.array([m[name] for m in patch_metrics], dtype=float)
        vals = vals[~np.isnan(vals)]
        out[name] = {
            "median": float(np.median(vals)) if len(vals) else float("nan"),
            "p10": float(np.percentile(vals, 10)) if len(vals) else float("nan"),
            "p90": float(np.percentile(vals, 90)) if len(vals) else float("nan"),
            "n": int(len(vals)),
        }
    return out

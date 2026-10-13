"""개발성 플래그와 AFP 유사도 보조 값 (F-9, F-10). 후보를 자동 삭제하지 않고 플래그만 붙인다."""
from __future__ import annotations

import re

import numpy as np

from afp import config

SEQUON = re.compile(r"N(?=[^P][ST])")
DEV_FLAGS = ("n_glyc", "odd_cys", "hydrophobic_patch")


def charge_and_pi(seq: str) -> tuple[float, float]:
    from Bio.SeqUtils.ProtParam import ProteinAnalysis

    pa = ProteinAnalysis(seq)
    return float(pa.charge_at_pH(7.0)), float(pa.isoelectric_point())


def sequon_count(seq: str) -> int:
    return len(SEQUON.findall(seq))


def exposed_hydrophobic_fraction(sequence: str, residues, sasa: dict[int, float]) -> float:
    total = sum(sasa[r.number] for r in residues)
    if total <= 0:
        return 0.0
    hydro = sum(sasa[r.number] for r, aa in zip(residues, sequence) if aa in "AVLIMFW")
    return float(hydro / total)


def developability(sequence: str, seed_sequence: str, residues=None, sasa: dict[int, float] | None = None,
                   seed_hydro_fraction: float | None = None) -> dict:
    """net_charge, pI와 플래그 목록. 구조(잔기, SASA)가 있으면 노출 소수성 패치도 본다."""
    charge, pi = charge_and_pi(sequence)
    flags: list[str] = []
    if sequon_count(sequence) > sequon_count(seed_sequence):
        flags.append("n_glyc")
    if sequence.count("C") != seed_sequence.count("C"):
        flags.append("odd_cys")
    hydro = float("nan")
    if residues is not None and sasa is not None and seed_hydro_fraction is not None:
        hydro = exposed_hydrophobic_fraction(sequence, residues, sasa)
        if hydro > seed_hydro_fraction + config.HYDROPHOBIC_PATCH_DELTA:
            flags.append("hydrophobic_patch")
    return {"net_charge": charge, "pI": pi, "exposed_hydrophobic_frac": hydro, "dev_flags": flags}


def seq_identity(sequence: str, seed_sequence: str) -> float:
    if len(sequence) != len(seed_sequence):
        raise ValueError("서열 길이가 다릅니다.")
    return float(np.mean([a == b for a, b in zip(sequence, seed_sequence)]))

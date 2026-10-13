"""가벼운 PDB 파서/작성기와 구조 계산 유틸리티.

표준 아미노산 ATOM 레코드만 다루고 첫 모델, 첫 altloc만 쓴다.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from afp.io.fasta import InputError

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E", "GLY": "G",
    "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P", "SER": "S",
    "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}
ONE_TO_THREE = {v: k for k, v in THREE_TO_ONE.items()}


@dataclass
class Residue:
    number: int
    name3: str
    atoms: dict[str, np.ndarray] = field(default_factory=dict)
    bfactors: dict[str, float] = field(default_factory=dict)

    @property
    def aa(self) -> str:
        return THREE_TO_ONE[self.name3]

    @property
    def ca(self) -> np.ndarray:
        return self.atoms["CA"]


def parse_pdb(text: str, chain: str | None = None) -> list[Residue]:
    """첫 모델의 지정 체인(없으면 첫 체인)에서 CA가 있는 표준 잔기 목록을 읽는다."""
    residues: dict[tuple[int, str], Residue] = {}
    order: list[tuple[int, str]] = []
    use_chain = chain
    for line in text.splitlines():
        if line.startswith("ENDMDL"):
            break
        if not line.startswith("ATOM") or len(line) < 54:
            continue
        altloc = line[16]
        if altloc not in (" ", "A", "1"):
            continue
        name3 = line[17:20].strip()
        if name3 not in THREE_TO_ONE:
            continue
        ch = line[21]
        if use_chain is None:
            use_chain = ch
        if ch != use_chain:
            continue
        element = line[76:78].strip() if len(line) >= 78 else ""
        atom_name = line[12:16].strip()
        if element == "H" or (not element and atom_name.lstrip("0123456789").startswith("H")):
            continue
        try:
            number = int(line[22:26])
            xyz = np.array([float(line[30:38]), float(line[38:46]), float(line[46:54])])
        except ValueError as exc:
            raise InputError(f"PDB 좌표를 읽을 수 없습니다: {line[:30]!r}") from exc
        icode = line[26]
        key = (number, icode)
        if key not in residues:
            residues[key] = Residue(number=number, name3=name3)
            order.append(key)
        res = residues[key]
        if atom_name not in res.atoms:
            res.atoms[atom_name] = xyz
            try:
                res.bfactors[atom_name] = float(line[60:66])
            except ValueError:
                res.bfactors[atom_name] = 0.0
    out = [residues[k] for k in order if "CA" in residues[k].atoms]
    if not out:
        raise InputError("PDB에서 아미노산 잔기(CA 원자)를 찾지 못했습니다.")
    return out


def read_pdb(path: str | Path, chain: str | None = None) -> list[Residue]:
    return parse_pdb(Path(path).read_text(encoding="utf-8", errors="replace"), chain)


def sequence_of(residues: list[Residue]) -> str:
    return "".join(r.aa for r in residues)


def ca_coords(residues: list[Residue]) -> np.ndarray:
    return np.array([r.ca for r in residues], dtype=float)


def write_pdb(residues: list[Residue], chain: str = "A", renumber: bool = False, bfactor_per_residue=None) -> str:
    """잔기 목록을 PDB 텍스트로. bfactor_per_residue가 있으면 B-factor 열에 쓴다."""
    lines = []
    serial = 1
    for idx, res in enumerate(residues):
        number = idx + 1 if renumber else res.number
        for name, xyz in res.atoms.items():
            bf = float(bfactor_per_residue[idx]) if bfactor_per_residue is not None else res.bfactors.get(name, 0.0)
            atom_field = f" {name:<3}" if len(name) < 4 else name
            element = name[0]
            lines.append(
                f"ATOM  {serial:5d} {atom_field} {res.name3:>3} {chain}{number:4d}    "
                f"{xyz[0]:8.3f}{xyz[1]:8.3f}{xyz[2]:8.3f}{1.0:6.2f}{bf:6.2f}          {element:>2}"
            )
            serial += 1
    lines.append("TER")
    lines.append("END")
    return "\n".join(lines) + "\n"


def bfactor_per_residue(residues: list[Residue]) -> np.ndarray:
    return np.array([r.bfactors.get("CA", 0.0) for r in residues], dtype=float)


# ---------------------------------------------------------------- 구조 계산

def kabsch_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    """두 (N,3) 좌표를 최적 겹침한 뒤의 RMSD."""
    if a.shape != b.shape or a.shape[0] < 3:
        raise ValueError("RMSD 계산에는 같은 길이의 좌표 3개 이상이 필요합니다.")
    ac = a - a.mean(axis=0)
    bc = b - b.mean(axis=0)
    h = ac.T @ bc
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    rot = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    diff = (rot @ ac.T).T - bc
    return float(np.sqrt((diff ** 2).sum() / a.shape[0]))


def kabsch_transform(mobile: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """mobile을 ref에 겹치는 회전 R과 이동 t: aligned = mobile @ R.T + t."""
    mc, rc = mobile.mean(axis=0), ref.mean(axis=0)
    h = (mobile - mc).T @ (ref - rc)
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    rot = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    return rot, rc - mc @ rot.T


def align_to_reference(mobile: list[Residue], ref_ca: np.ndarray) -> list[Residue]:
    """mobile 잔기(Cα 수 = len(ref_ca))를 ref_ca에 겹친 새 잔기 목록 (3D 비교용)."""
    rot, t = kabsch_transform(ca_coords(mobile), ref_ca)
    out = []
    for r in mobile:
        out.append(Residue(number=r.number, name3=r.name3, bfactors=dict(r.bfactors),
                           atoms={k: v @ rot.T + t for k, v in r.atoms.items()}))
    return out


def residue_sasa(pdb_text: str) -> dict[int, float]:
    """잔기별 SASA(Å^2). 키는 PDB 잔기 번호. Biopython Shrake-Rupley를 쓴다."""
    from Bio.PDB import PDBParser
    from Bio.PDB.SASA import ShrakeRupley

    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        structure = PDBParser(QUIET=True).get_structure("s", io.StringIO(pdb_text))
    ShrakeRupley(probe_radius=1.4, n_points=100).compute(structure[0], level="R")
    out: dict[int, float] = {}
    for res in structure[0].get_residues():
        if res.id[0] == " ":
            out[res.id[1]] = float(res.sasa)
    return out


# 최대 SASA (Tien et al. 2013, 이론값 Å^2) — 상대 SASA 계산용
MAX_SASA = {
    "A": 129.0, "R": 274.0, "N": 195.0, "D": 193.0, "C": 167.0, "Q": 225.0, "E": 223.0, "G": 104.0,
    "H": 224.0, "I": 197.0, "L": 201.0, "K": 236.0, "M": 224.0, "F": 240.0, "P": 159.0, "S": 155.0,
    "T": 172.0, "W": 285.0, "Y": 263.0, "V": 174.0,
}

"""data/_raw/*.pdb(RCSB 원본)에서 시드와 음성 대조 폴더를 만든다 (M0-5, M0-6).

IBS 잔기와 근거 수준은 아래 SEEDS에 사람이 기록한 값이다. 이 스크립트는 그 값이 구조의 서열과
맞는지(예: 문헌이 말한 잔기 종류와 일치하는지) 검증하고, 맞지 않으면 중단한다.

    python scripts/prepare_seeds.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from afp.io.pdb import parse_pdb, sequence_of, write_pdb  # noqa: E402

RAW = ROOT / "data" / "_raw"

SEEDS = [
    {
        "id": "type3_hplc12",
        "name": "Type III AFP (HPLC-12, ocean pout)",
        "afp_type": "type3",
        "pdb_id": "1HG7",
        "chain": "A",
        "residue_offset": 1000,  # 1HG7은 번호가 1000부터(Met0 = 1000). 문헌 번호 = PDB 번호 - 1000
        "ibs_residues": [9, 14, 15, 18, 44],
        "expect": {9: "Q", 14: "N", 15: "T", 18: "T", 44: "Q"},
        "ibs_evidence_level": "literature",
        "ibs_evidence": [
            "Sonnichsen et al. 1996, Structure 4:1325-1337 (RCSB 1KDE 초록): 추정 얼음 결합 잔기 Gln9, Asn14, Thr15, Thr18, Gln44",
            "구조 서열에서 Q9, N14, T15, T18, Q44를 확인함 (문헌 번호 = 1HG7 PDB 번호 - 1000)",
            "구조 출처: Antson et al. 2001, J Mol Biol 305:875 (1HG7, 1.15 A)",
        ],
        "notes": "Type III 복합 IBS(프리즘/피라미드 면)의 일부만 포함한 핵심 잔기 집합이다. A16, L19, V20, V41 등은 확인한 출처가 없어 넣지 않았다.",
    },
    {
        "id": "tmafp_beetle",
        "name": "TmAFP (Tenebrio molitor, beta-helix)",
        "afp_type": "insect_beta_helix",
        "pdb_id": "1EZG",
        "chain": "A",
        "residue_offset": 1,  # 문헌(성숙 단백질) 번호 + 1 = 1EZG PDB 번호
        "ibs_residues": [16, 26, 28, 38, 40, 50, 52, 62, 64],
        "expect": {n: "T" for n in (16, 26, 28, 38, 40, 50, 52, 62, 64)},
        "ibs_evidence_level": "literature_partial",
        "ibs_evidence": [
            "PMC5991737 (AFP의 TIP4P/Ice 시뮬레이션) Table 1: TmAFP의 IBS Thr 변이 대상 T16, T26, T28, T38, T40, T50, T52, T62, T64",
            "같은 논문: TmAFP IBS는 Thr 11개로 이루어지며 전체 목록은 본문에 없음 (이 9개는 그중 일부)",
            "Liou et al. 2000, Nature 406:322 (1EZG, 1.4 A): TCT 모티프가 평평한 β-시트 얼음 결합면을 이룸",
        ],
        "notes": "IBS Thr 11개 중 9개만 문헌에서 확인했다. 나머지 2개는 번호를 확인하지 못해 제외했다.",
    },
    {
        "id": "type1_hplc6",
        "name": "Type I AFP (HPLC-6, winter flounder)",
        "afp_type": "type1",
        "pdb_id": "1WFA",
        "chain": "A",
        "residue_offset": 0,
        "ibs_residues": [2, 13, 24, 35],
        "expect": {2: "T", 13: "T", 24: "T", 35: "T"},
        "ibs_evidence_level": "derived",
        "ibs_evidence": [
            "Sicheri & Yang 1995, Nature 375:427-431 (1WFA): 반복되는 얼음 결합 모티프 4개가 평평한 결합면을 이룸",
            "잔기 번호는 서열의 11잔기 주기 Thr(T2, T13, T24, T35)에서 유도했다. 열어본 출처에서 번호를 직접 확인하지는 못했다",
        ],
        "notes": "근거 수준 derived: 번호가 문헌으로 확인되지 않았다. 전문가 확인 후 literature로 올린다.",
    },
]

CONTROLS = [
    {"id": "ubiquitin", "name": "Ubiquitin", "pdb_id": "1UBQ", "chain": "A", "paired_seeds": ["type3_hplc12"]},
    {"id": "bpti", "name": "BPTI (aprotinin)", "pdb_id": "5PTI", "chain": "A", "paired_seeds": ["tmafp_beetle"]},
    {"id": "gcn4_zipper", "name": "GCN4 leucine zipper", "pdb_id": "2ZTA", "chain": "A", "paired_seeds": ["type1_hplc6"]},
]


def main() -> None:
    for spec in SEEDS:
        residues = parse_pdb((RAW / f"{spec['pdb_id']}.pdb").read_text(encoding="utf-8"), spec["chain"])
        numbers = {r.number: r.aa for r in residues}
        for lit, aa in spec["expect"].items():
            got = numbers.get(lit + spec["residue_offset"])
            if got != aa:
                raise SystemExit(f"[{spec['id']}] 문헌 번호 {lit}: 기대 {aa}, 구조 {got}")
        out = ROOT / "data" / "seeds" / spec["id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "structure.pdb").write_text(write_pdb(residues, chain=spec["chain"]), encoding="utf-8")
        data = {k: v for k, v in spec.items() if k != "expect"}
        data["sequence"] = sequence_of(residues)
        data["structure_source"] = "experimental"
        data["uniprot"] = ""
        (out / "seed.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"seed {spec['id']}: {len(residues)} residues, IBS {spec['ibs_residues']}")

    for spec in CONTROLS:
        residues = parse_pdb((RAW / f"{spec['pdb_id']}.pdb").read_text(encoding="utf-8"), spec["chain"])
        out = ROOT / "data" / "controls" / spec["id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "structure.pdb").write_text(write_pdb(residues, chain=spec["chain"]), encoding="utf-8")
        data = dict(spec)
        data["sequence"] = sequence_of(residues)
        (out / "control.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"control {spec['id']}: {len(residues)} residues")


if __name__ == "__main__":
    main()

"""시드 AFP 라이브러리와 대조군 (F-2, F-3).

seed.json의 `ibs_residues`는 문헌 번호 기준이고, PDB 잔기 번호는 `문헌 번호 + residue_offset`이다.
후보의 변이 위치는 시드 서열의 1-based 인덱스로 쓴다 (문헌 번호와 다를 수 있음).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from afp.config import CONTROLS_DIR, EVIDENCE_LEVELS, SEEDS_DIR
from afp.io.fasta import InputError, validate_sequence
from afp.io.pdb import Residue, parse_pdb, sequence_of, write_pdb

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{1,40}$")


def parse_residue_spec(text: str) -> list[int]:
    """'9, 14, 15-18' 같은 입력을 번호 목록으로."""
    out: list[int] = []
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(-?\d+)-(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b < a:
                raise InputError(f"잔기 범위가 잘못되었습니다: {part}")
            out.extend(range(a, b + 1))
        elif re.fullmatch(r"-?\d+", part):
            out.append(int(part))
        else:
            raise InputError(f"잔기 번호 형식이 잘못되었습니다: {part!r} (예: 9, 14, 15-18)")
    return sorted(set(out))


@dataclass
class Seed:
    id: str
    name: str
    afp_type: str
    pdb_id: str
    chain: str
    sequence: str
    ibs_residues: list[int]
    residue_offset: int = 0
    ibs_evidence_level: str = "unverified"
    ibs_evidence: list[str] = field(default_factory=list)
    uniprot: str = ""
    notes: str = ""
    structure_source: str = "experimental"   # experimental | predicted | uploaded
    directory: Path | None = None
    _residues: list[Residue] | None = field(default=None, repr=False, compare=False)

    @property
    def structure_path(self) -> Path:
        assert self.directory is not None
        return self.directory / "structure.pdb"

    def residues(self) -> list[Residue]:
        if self._residues is None:
            self._residues = parse_pdb(self.structure_path.read_text(encoding="utf-8"), self.chain)
        return self._residues

    def structure_text(self) -> str:
        return self.structure_path.read_text(encoding="utf-8")

    @property
    def length(self) -> int:
        return len(self.sequence)

    @property
    def residue_numbers(self) -> list[int]:
        return [r.number for r in self.residues()]

    @property
    def ibs_pdb_numbers(self) -> list[int]:
        return [n + self.residue_offset for n in self.ibs_residues]

    @property
    def ibs_indices(self) -> list[int]:
        """IBS 잔기의 0-based 시드 서열 인덱스."""
        index_of = {n: i for i, n in enumerate(self.residue_numbers)}
        try:
            return sorted(index_of[n] for n in self.ibs_pdb_numbers)
        except KeyError as exc:
            raise InputError(f"IBS 잔기 번호 {exc.args[0]}가 구조에 없습니다.") from exc

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "afp_type": self.afp_type,
            "pdb_id": self.pdb_id,
            "uniprot": self.uniprot,
            "chain": self.chain,
            "sequence": self.sequence,
            "residue_offset": self.residue_offset,
            "ibs_residues": self.ibs_residues,
            "ibs_evidence_level": self.ibs_evidence_level,
            "ibs_evidence": self.ibs_evidence,
            "structure_source": self.structure_source,
            "notes": self.notes,
        }


def validate_seed(seed: Seed) -> list[str]:
    """문제 목록 (비어 있으면 통과)."""
    problems: list[str] = []
    if seed.ibs_evidence_level not in EVIDENCE_LEVELS:
        problems.append(f"알 수 없는 IBS 근거 수준: {seed.ibs_evidence_level}")
    if not seed.structure_path.exists():
        return problems + ["structure.pdb가 없습니다."]
    try:
        structure_seq = sequence_of(seed.residues())
    except InputError as exc:
        return problems + [str(exc)]
    if structure_seq != seed.sequence:
        problems.append("seed.json의 서열이 구조(체인)의 서열과 다릅니다.")
    try:
        validate_sequence(seed.sequence)
    except InputError as exc:
        problems.append(str(exc))
    if len(seed.ibs_residues) < 2:
        problems.append("IBS 잔기는 2개 이상이어야 합니다.")
    if len(set(seed.ibs_residues)) != len(seed.ibs_residues):
        problems.append("IBS 잔기 번호가 중복되었습니다.")
    numbers = set(seed.residue_numbers)
    missing = [n for n in seed.ibs_pdb_numbers if n not in numbers]
    if missing:
        problems.append(f"구조에 없는 IBS 잔기 번호: {missing}")
    if seed.ibs_evidence_level in ("literature", "literature_partial", "derived") and not seed.ibs_evidence:
        problems.append("IBS 근거(ibs_evidence)가 비어 있습니다.")
    return problems


def _seed_from_json(data: dict, directory: Path) -> Seed:
    return Seed(
        id=data["id"], name=data["name"], afp_type=data.get("afp_type", ""), pdb_id=data.get("pdb_id", ""),
        chain=data.get("chain", "A"), sequence=data["sequence"], ibs_residues=list(data["ibs_residues"]),
        residue_offset=int(data.get("residue_offset", 0)),
        ibs_evidence_level=data.get("ibs_evidence_level", "unverified"),
        ibs_evidence=list(data.get("ibs_evidence", [])), uniprot=data.get("uniprot", ""),
        notes=data.get("notes", ""), structure_source=data.get("structure_source", "experimental"),
        directory=directory,
    )


def list_seed_ids(root: Path = SEEDS_DIR) -> list[str]:
    if not root.exists():
        return []
    return sorted(p.parent.name for p in root.glob("*/seed.json"))


def load_seed(seed_id: str, allow_unverified: bool = False, root: Path = SEEDS_DIR) -> Seed:
    directory = root / seed_id
    path = directory / "seed.json"
    if not path.exists():
        raise InputError(f"시드를 찾을 수 없습니다: {seed_id}")
    seed = _seed_from_json(json.loads(path.read_text(encoding="utf-8")), directory)
    if seed.ibs_evidence_level == "unverified" and not allow_unverified:
        raise InputError(f"시드 {seed_id}는 IBS 근거가 확인되지 않아(unverified) 사용할 수 없습니다.")
    return seed


def load_all_seeds(root: Path = SEEDS_DIR, allow_unverified: bool = False) -> list[Seed]:
    return [load_seed(i, allow_unverified, root) for i in list_seed_ids(root)]


def create_seed(
    seed_id: str,
    name: str,
    ibs_numbers: list[int],
    *,
    pdb_text: str | None = None,
    chain: str | None = None,
    fasta_sequence: str | None = None,
    predictor=None,
    afp_type: str = "user",
    residue_offset: int = 0,
    evidence: list[str] | None = None,
    root: Path = SEEDS_DIR,
) -> Seed:
    """사용자가 입력한 PDB 또는 FASTA(+구조 예측)로 새 시드를 저장한다 (시나리오 2)."""
    if not ID_PATTERN.match(seed_id):
        raise InputError("시드 ID는 영문·숫자·_·-만 쓰고 2자 이상이어야 합니다.")
    directory = root / seed_id
    if (directory / "seed.json").exists():
        raise InputError(f"이미 있는 시드 ID입니다: {seed_id}")
    source = "uploaded"
    if pdb_text is not None:
        residues = parse_pdb(pdb_text, chain)
        use_chain = chain or "A"
    elif fasta_sequence is not None:
        if predictor is None:
            raise InputError("FASTA만 입력하면 구조 예측기가 필요합니다.")
        seq = validate_sequence(fasta_sequence)
        pred = predictor.predict(seq)
        residues = parse_pdb(pred.pdb_text, "A")
        use_chain, source = "A", "predicted"
    else:
        raise InputError("PDB 또는 FASTA 중 하나가 필요합니다.")
    sequence = sequence_of(residues)
    pdb_numbers = {r.number for r in residues}
    missing = [n for n in ibs_numbers if n + residue_offset not in pdb_numbers]
    if missing:
        raise InputError(f"구조에 없는 IBS 잔기 번호: {missing}")
    if len(ibs_numbers) < 2:
        raise InputError("IBS 잔기는 2개 이상 입력해야 합니다.")
    seed = Seed(
        id=seed_id, name=name, afp_type=afp_type, pdb_id="", chain=use_chain, sequence=sequence,
        ibs_residues=sorted(set(ibs_numbers)), residue_offset=residue_offset,
        ibs_evidence_level="user_provided", ibs_evidence=evidence or ["사용자 입력"],
        structure_source=source, directory=directory,
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "structure.pdb").write_text(write_pdb(residues, chain=use_chain), encoding="utf-8")
    (directory / "seed.json").write_text(json.dumps(seed.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return seed


# ---------------------------------------------------------------- 음성 대조

@dataclass
class Control:
    id: str
    name: str
    pdb_id: str
    chain: str
    sequence: str
    paired_seeds: list[str]
    directory: Path
    _residues: list[Residue] | None = field(default=None, repr=False, compare=False)

    @property
    def structure_path(self) -> Path:
        return self.directory / "structure.pdb"

    def residues(self) -> list[Residue]:
        if self._residues is None:
            self._residues = parse_pdb(self.structure_path.read_text(encoding="utf-8"), self.chain)
        return self._residues

    def structure_text(self) -> str:
        return self.structure_path.read_text(encoding="utf-8")


def load_controls(root: Path = CONTROLS_DIR) -> list[Control]:
    out = []
    for path in sorted(root.glob("*/control.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        out.append(Control(
            id=d["id"], name=d["name"], pdb_id=d.get("pdb_id", ""), chain=d.get("chain", "A"),
            sequence=d["sequence"], paired_seeds=list(d.get("paired_seeds", [])), directory=path.parent,
        ))
    return out

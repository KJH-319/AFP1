"""FASTA 읽기/쓰기와 서열 검증 (F-3)."""
from __future__ import annotations

from pathlib import Path

from afp.config import AMINO_ACIDS, MAX_SEQUENCE_LENGTH


class InputError(ValueError):
    """사용자 입력이 잘못되었을 때. 메시지는 UI에 그대로 보여준다."""


def clean_sequence(seq: str) -> str:
    return "".join(seq.split()).upper()


def validate_sequence(seq: str) -> str:
    seq = clean_sequence(seq)
    if not seq:
        raise InputError("서열이 비어 있습니다.")
    bad = sorted(set(seq) - set(AMINO_ACIDS))
    if bad:
        raise InputError(f"표준 20개 아미노산이 아닌 문자가 있습니다: {''.join(bad)}")
    if len(seq) > MAX_SEQUENCE_LENGTH:
        raise InputError(f"서열이 너무 깁니다({len(seq)} > {MAX_SEQUENCE_LENGTH}).")
    return seq


def parse_fasta(text: str) -> list[tuple[str, str]]:
    """(id, sequence) 목록. 헤더가 없는 단일 서열도 허용한다."""
    records: list[tuple[str, list[str]]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            records.append((line[1:].split()[0] if line[1:].strip() else f"seq{len(records) + 1}", []))
        else:
            if not records:
                records.append(("seq1", []))
            records[-1][1].append(line)
    if not records:
        raise InputError("FASTA에서 서열을 찾지 못했습니다.")
    return [(rid, validate_sequence("".join(parts))) for rid, parts in records]


def read_fasta(path: str | Path) -> list[tuple[str, str]]:
    return parse_fasta(Path(path).read_text(encoding="utf-8"))


def format_fasta(records: list[tuple[str, str]], width: int = 60) -> str:
    out = []
    for rid, seq in records:
        out.append(f">{rid}")
        out.extend(seq[i : i + width] for i in range(0, len(seq), width))
    return "\n".join(out) + "\n"


def write_fasta(path: str | Path, records: list[tuple[str, str]]) -> None:
    Path(path).write_text(format_fasta(records), encoding="utf-8")

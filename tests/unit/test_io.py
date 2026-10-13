import numpy as np
import pytest

from afp.io.fasta import InputError, format_fasta, parse_fasta, validate_sequence
from afp.io.pdb import kabsch_rmsd, parse_pdb, residue_sasa, sequence_of, write_pdb
from afp.io.seeds import (
    create_seed,
    load_all_seeds,
    load_controls,
    load_seed,
    parse_residue_spec,
    validate_seed,
)

pytestmark = pytest.mark.unit


def test_parse_fasta_multi_and_headerless():
    recs = parse_fasta(">a desc\nACDE\nFGH\n>b\nKLM")
    assert recs == [("a", "ACDEFGH"), ("b", "KLM")]
    assert parse_fasta("acd ef") == [("seq1", "ACDEF")]


@pytest.mark.parametrize("text", ["", ">x\n", ">x\nAC1D", ">x\nACBZ"])
def test_parse_fasta_rejects_bad_input(text):
    with pytest.raises(InputError):
        parse_fasta(text)


def test_sequence_too_long():
    with pytest.raises(InputError):
        validate_sequence("A" * 500)


def test_fasta_roundtrip():
    recs = [("c1", "ACDEFGHIKLMNPQRSTVWY" * 5)]
    assert parse_fasta(format_fasta(recs)) == recs


def test_all_seeds_valid_and_controls_load():
    seeds = load_all_seeds()
    assert len(seeds) >= 3
    for s in seeds:
        assert validate_seed(s) == [], s.id
        assert s.ibs_indices and max(s.ibs_indices) < s.length
    assert len(load_controls()) >= 3


def test_type3_literature_numbering_maps_to_residue_types():
    s = load_seed("type3_hplc12")
    seq = s.sequence
    assert [seq[i] for i in s.ibs_indices] == ["Q", "N", "T", "T", "Q"]   # Q9 N14 T15 T18 Q44


def test_tmafp_ibs_are_all_threonine():
    s = load_seed("tmafp_beetle")
    assert {s.sequence[i] for i in s.ibs_indices} == {"T"}


def test_pdb_roundtrip_and_renumber():
    s = load_seed("type1_hplc6")
    text = write_pdb(s.residues(), "A", renumber=True)
    back = parse_pdb(text, "A")
    assert sequence_of(back) == s.sequence
    assert [r.number for r in back] == list(range(1, s.length + 1))
    assert np.allclose(back[5].ca, s.residues()[5].ca, atol=1e-3)


def test_kabsch_rmsd_invariant_to_rotation_translation():
    rng = np.random.default_rng(0)
    a = rng.normal(size=(30, 3)) * 5
    theta = 0.7
    rot = np.array([[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
    b = a @ rot.T + np.array([3.0, -2.0, 9.0])
    assert kabsch_rmsd(a, b) == pytest.approx(0.0, abs=1e-6)
    noisy = b + rng.normal(0, 0.5, b.shape)
    assert 0.3 < kabsch_rmsd(a, noisy) < 1.2


def test_kabsch_handles_reflection_without_flipping():
    rng = np.random.default_rng(1)
    a = rng.normal(size=(20, 3)) * 4
    mirrored = a * np.array([1, 1, -1])
    assert kabsch_rmsd(a, mirrored) > 1.0   # 거울상은 회전만으로 겹치지 않는다


def test_residue_sasa_buried_vs_exposed():
    s = load_seed("type3_hplc12")
    sasa = residue_sasa(s.structure_text())
    assert len(sasa) == s.length
    assert all(v >= 0 for v in sasa.values())
    assert sum(sasa.values()) > 2000


@pytest.mark.parametrize("text,expected", [("9, 14,15-17", [9, 14, 15, 16, 17]), ("3 1 2", [1, 2, 3])])
def test_parse_residue_spec(text, expected):
    assert parse_residue_spec(text) == expected


@pytest.mark.parametrize("text", ["a", "5-2", "1..3"])
def test_parse_residue_spec_errors(text):
    with pytest.raises(InputError):
        parse_residue_spec(text)


def test_create_seed_from_pdb_upload(tmp_path):
    s = load_seed("type1_hplc6")
    created = create_seed("my_seed", "내 시드", [2, 13, 24], pdb_text=s.structure_text(), chain="A", root=tmp_path)
    assert created.sequence == s.sequence
    assert created.ibs_evidence_level == "user_provided"
    again = load_seed("my_seed", root=tmp_path)
    assert validate_seed(again) == []
    with pytest.raises(InputError):   # 중복 ID
        create_seed("my_seed", "x", [2, 13], pdb_text=s.structure_text(), chain="A", root=tmp_path)
    with pytest.raises(InputError):   # 구조에 없는 잔기
        create_seed("other", "x", [2, 999], pdb_text=s.structure_text(), chain="A", root=tmp_path)
    with pytest.raises(InputError):   # 잘못된 ID
        create_seed("bad id!", "x", [2, 13], pdb_text=s.structure_text(), chain="A", root=tmp_path)


def test_unverified_seed_is_refused(tmp_path):
    s = load_seed("type1_hplc6")
    created = create_seed("tmp_seed", "t", [2, 13], pdb_text=s.structure_text(), chain="A", root=tmp_path)
    p = created.directory / "seed.json"
    p.write_text(p.read_text(encoding="utf-8").replace("user_provided", "unverified"), encoding="utf-8")
    with pytest.raises(InputError):
        load_seed("tmp_seed", root=tmp_path)
    assert load_seed("tmp_seed", allow_unverified=True, root=tmp_path).ibs_evidence_level == "unverified"

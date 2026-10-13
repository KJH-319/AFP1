import pytest

from afp import config
from afp.design.mode_a import allowed_targets, conservative_group, generate_candidates, variable_sites

pytestmark = pytest.mark.unit


def _gen(seed, scorer, **kw):
    args = dict(n=30, max_mutations=6, rng_seed=3, mcmc_steps=60)
    args.update(kw)
    cands, sites, _ = generate_candidates(seed, scorer, **args)
    return cands, sites


def test_invariants_hold_for_every_seed(seed, mock_scorer):
    cands, sites = _gen(seed, mock_scorer)
    assert len(cands) >= 1
    ibs = set(seed.ibs_indices)
    cons = set(sites.conservative)
    assert len({c.sequence for c in cands}) == len(cands)
    for c in cands:
        assert len(c.sequence) == seed.length                       # 치환만, 길이 동일
        assert 1 <= c.n_mut <= 6
        for i in ibs:                                               # IBS 고정
            assert c.sequence[i] == seed.sequence[i]
        for pos, wt, new in c.mutations:
            assert seed.sequence[pos] == wt and c.sequence[pos] == new and new != wt
            assert wt not in config.FROZEN_WILDTYPE                 # G/P/C 위치는 그대로
            assert new not in config.FORBIDDEN_TARGETS              # 새 Cys 없음
            if pos in cons:                                         # IBS 근처는 보수적 치환만
                assert new in conservative_group(wt)
        diffs = [i for i, (a, b) in enumerate(zip(seed.sequence, c.sequence)) if a != b]
        assert sorted(diffs) == sorted(p for p, _, _ in c.mutations)


def test_deterministic_given_rng_seed(type3, mock_scorer):
    a, _ = _gen(type3, mock_scorer, rng_seed=7)
    b, _ = _gen(type3, mock_scorer, rng_seed=7)
    c, _ = _gen(type3, mock_scorer, rng_seed=8)
    assert [x.sequence for x in a] == [x.sequence for x in b]
    assert [x.sequence for x in a] != [x.sequence for x in c]


def test_mutation_count_follows_max_mutations(type3, mock_scorer):
    cands, _ = _gen(type3, mock_scorer, n=40, max_mutations=2)
    assert {c.n_mut for c in cands} <= {1, 2}
    cands, _ = _gen(type3, mock_scorer, n=40, max_mutations=8)
    assert max(c.n_mut for c in cands) > 2


def test_mutation_string_is_one_based(type3, mock_scorer):
    cands, _ = _gen(type3, mock_scorer, n=5)
    for c in cands:
        for token in c.mutation_string.split(";"):
            wt, pos, new = token[0], int(token[1:-1]), token[-1]
            assert type3.sequence[pos - 1] == wt and c.sequence[pos - 1] == new


def test_variable_sites_exclude_ibs_and_frozen(seed):
    sites = variable_sites(seed, 5.0)
    ibs = set(seed.ibs_indices)
    assert not ibs & set(sites.free + sites.conservative)
    assert all(seed.sequence[i] in config.FROZEN_WILDTYPE for i in sites.frozen)
    assert set(sites.fixed_ibs) == ibs
    # 반경을 키우면 보수적 위치가 늘어난다
    assert len(variable_sites(seed, 9.0).conservative) >= len(sites.conservative)


def test_extra_fixed_positions_are_respected(type3, mock_scorer):
    sites = variable_sites(type3, 5.0)
    pick = (sites.free + sites.conservative)[:10]
    cands, s2 = _gen(type3, mock_scorer, extra_fixed=pick)
    for c in cands:
        assert not {p for p, _, _ in c.mutations} & set(pick)
    assert set(pick) <= set(s2.frozen)


def test_allowed_targets_rules():
    assert "C" not in allowed_targets("A", False)
    assert "A" not in allowed_targets("A", False)
    assert set(allowed_targets("A", True)) == set("VILM")
    assert allowed_targets("H", True) == ["K", "R"]


def test_mcmc_prefers_higher_scoring_mutations(type3):
    """점수가 높은 아미노산이 낮은 것보다 더 자주 뽑힌다."""
    from afp.models import MockEsmScorer

    class Biased(MockEsmScorer):
        def masked_marginals(self, seq, positions):
            import numpy as np
            out = np.full((len(positions), 20), -3.0, dtype=np.float32)
            out[:, config.AMINO_ACIDS.index("A")] = 0.0     # 모든 위치에서 Ala가 선호됨
            return out

    cands, _, _ = generate_candidates(type3, Biased(), n=40, max_mutations=3, rng_seed=1, mcmc_steps=300, temperature=0.5)
    ala = sum(1 for c in cands for _, _, new in c.mutations if new == "A")
    total = sum(c.n_mut for c in cands)
    assert ala / total > 0.5


def test_raises_when_no_variable_positions(type3, mock_scorer):
    with pytest.raises(ValueError):
        generate_candidates(type3, mock_scorer, n=3, max_mutations=2, extra_fixed=list(range(type3.length)))

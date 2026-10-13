"""모드 A: 시드 기반 서열 최적화 (F-5).

치환만 지원한다(삽입·결실 없음). IBS 잔기는 고정하고, IBS 근처는 보수적 치환만 허용한다.
후보는 "정확히 k개 변이" 상태 공간 위의 Metropolis MCMC로 뽑으며, 에너지는 ESM-2 masked marginal
로그비(변이 아미노산 - 시드 아미노산)의 합이다. IBS 지표와 AFP 점수는 루프 밖(생성 후)에서 평가한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from afp import config
from afp.io.seeds import Seed

AA = config.AMINO_ACIDS
AA_INDEX = {a: i for i, a in enumerate(AA)}


@dataclass
class Candidate:
    cand_id: str
    sequence: str
    mutations: list[tuple[int, str, str]] = field(default_factory=list)   # (0-based 위치, 시드 aa, 새 aa)
    esm_llr: float = 0.0

    @property
    def n_mut(self) -> int:
        return len(self.mutations)

    @property
    def mutation_string(self) -> str:
        """1-based 시드 서열 인덱스 기준, 예: 'A12T;K30R'."""
        return ";".join(f"{wt}{pos + 1}{new}" for pos, wt, new in sorted(self.mutations))


@dataclass
class VariableSites:
    free: list[int]
    conservative: list[int]
    fixed_ibs: list[int]
    frozen: list[int]


def variable_sites(seed: Seed, near_ibs_angstrom: float, extra_fixed: list[int] | None = None) -> VariableSites:
    """변이 가능한 위치(0-based). IBS와 Gly/Pro/Cys, 사용자 고정 위치는 제외한다."""
    ibs = set(seed.ibs_indices)
    extra = set(extra_fixed or [])
    residues = seed.residues()
    ibs_atoms = np.array([xyz for i in ibs for xyz in residues[i].atoms.values()])
    free, conservative, frozen = [], [], []
    for i, res in enumerate(residues):
        if i in ibs:
            continue
        if i in extra or seed.sequence[i] in config.FROZEN_WILDTYPE:
            frozen.append(i)
            continue
        atoms = np.array(list(res.atoms.values()))
        d = np.sqrt(((atoms[:, None, :] - ibs_atoms[None, :, :]) ** 2).sum(-1)).min()
        (conservative if d <= near_ibs_angstrom else free).append(i)
    return VariableSites(free=free, conservative=conservative, fixed_ibs=sorted(ibs), frozen=frozen)


def conservative_group(aa: str) -> str:
    for g in config.CONSERVATIVE_GROUPS:
        if aa in g:
            return g
    return ""


def allowed_targets(wt: str, conservative: bool) -> list[str]:
    pool = conservative_group(wt) if conservative else AA
    return [a for a in pool if a != wt and a not in config.FORBIDDEN_TARGETS]


def generate_candidates(
    seed: Seed,
    scorer,
    *,
    n: int,
    max_mutations: int,
    near_ibs_angstrom: float = config.NEAR_IBS_ANGSTROM,
    temperature: float = 1.0,
    mcmc_steps: int = config.MCMC_STEPS,
    rng_seed: int = 1,
    extra_fixed: list[int] | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[list[Candidate], VariableSites, dict]:
    """후보 n개(가능하면)를 만든다. (후보, 변이 가능 위치, 위치별 점수 행렬 정보)를 돌려준다."""
    if n < 1 or max_mutations < 1:
        raise ValueError("n과 max_mutations는 1 이상이어야 합니다.")
    sites = variable_sites(seed, near_ibs_angstrom, extra_fixed)
    positions = sorted(sites.free + sites.conservative)
    cons = set(sites.conservative)
    targets = {p: allowed_targets(seed.sequence[p], p in cons) for p in positions}
    positions = [p for p in positions if targets[p]]
    if not positions:
        raise ValueError("변이 가능한 위치가 없습니다. IBS 근처 거리나 고정 위치를 확인하세요.")

    wt = seed.sequence
    mm = scorer.masked_marginals(wt, positions)                       # (P, 20) 로그확률
    delta = {p: {a: float(mm[r, AA_INDEX[a]] - mm[r, AA_INDEX[wt[p]]]) for a in targets[p]} for r, p in enumerate(positions)}
    if progress:
        progress(0.2, f"ESM-2 점수 계산 완료 (변이 가능 위치 {len(positions)}개)")

    seen: set[str] = set()
    out: list[Candidate] = []
    attempts, max_attempts = 0, max(50, 30 * n)
    while len(out) < n and attempts < max_attempts:
        rng = np.random.default_rng([rng_seed, attempts])
        attempts += 1
        k = int(rng.integers(1, min(max_mutations, len(positions)) + 1))
        state = _run_chain(positions, targets, delta, k, temperature, mcmc_steps, rng)
        seq = list(wt)
        for p, a in state.items():
            seq[p] = a
        seq = "".join(seq)
        if seq in seen:
            continue
        seen.add(seq)
        muts = [(p, wt[p], a) for p, a in sorted(state.items())]
        out.append(Candidate(
            cand_id=f"c{len(out) + 1:04d}", sequence=seq, mutations=muts,
            esm_llr=float(sum(delta[p][a] for p, a in state.items())),
        ))
        if progress and (len(out) % 10 == 0 or len(out) == n):
            progress(0.2 + 0.8 * len(out) / n, f"후보 {len(out)}/{n} 생성")
    return out, sites, {"positions": positions, "attempts": attempts}


def _run_chain(positions, targets, delta, k, temperature, steps, rng) -> dict[int, str]:
    """정확히 k개 변이를 갖는 상태 위에서의 Metropolis MCMC. 제안 분포는 대칭이다."""
    chosen = rng.choice(len(positions), size=k, replace=False)
    state = {positions[i]: targets[positions[i]][int(rng.integers(len(targets[positions[i]])))] for i in chosen}
    for _ in range(steps):
        p = list(state)[int(rng.integers(len(state)))]
        if rng.random() < 0.5:                                   # 같은 위치에서 아미노산 교체
            new = targets[p][int(rng.integers(len(targets[p])))]
            d_e = delta[p][new] - delta[p][state[p]]
            if d_e >= 0 or rng.random() < np.exp(d_e / temperature):
                state[p] = new
        else:                                                    # 변이 위치 이동
            q = positions[int(rng.integers(len(positions)))]
            if q in state:
                continue
            new = targets[q][int(rng.integers(len(targets[q])))]
            d_e = delta[q][new] - delta[p][state[p]]
            if d_e >= 0 or rng.random() < np.exp(d_e / temperature):
                del state[p]
                state[q] = new
    return state

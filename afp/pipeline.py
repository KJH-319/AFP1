"""실행 하나(run)의 전체 흐름: 설계 -> 구조 QC -> 평가(IBS 지표, 점수)."""
from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path

import pandas as pd

from afp import config
from afp.design.mode_a import Candidate, generate_candidates
from afp.io.fasta import write_fasta
from afp.io.seeds import load_seed
from afp.models import get_backends, versions
from afp.runner.launcher import load_params
from afp.runner.status import StatusWriter, now_iso, write_json_atomic

BASE_COLUMNS = ["cand_id", "sequence", "n_mut", "mutations", "esm_llr"]


def candidates_dataframe(cands: list[Candidate]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"cand_id": c.cand_id, "sequence": c.sequence, "n_mut": c.n_mut, "mutations": c.mutation_string,
          "esm_llr": c.esm_llr} for c in cands],
        columns=BASE_COLUMNS,
    )


def save_candidates(df: pd.DataFrame, run_dir: Path) -> None:
    df.to_csv(Path(run_dir) / "candidates.csv", index=False)


def load_candidates(run_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(Path(run_dir) / "candidates.csv", keep_default_na=False, na_values=[""])
    for col in ("mutations", "flags", "qc_status", "structure_path"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
    return df


def _stage_progress(status: StatusWriter, lo: float, hi: float):
    def cb(frac: float, message: str = "") -> None:
        status.progress(lo + (hi - lo) * float(frac), message)
    return cb


def execute_run(run_dir: Path, backends=None) -> int:
    """작업 폴더의 params.json대로 실행한다. 서브프로세스(afp.cli run)와 CLI/테스트가 공통으로 쓴다."""
    run_dir = Path(run_dir)
    status = StatusWriter(run_dir)
    try:
        params = load_params(run_dir)
        status.update(state="running", pid=os.getpid(), started_at=status.data.get("started_at") or now_iso(), error=None)
        write_json_atomic(run_dir / "versions.json", versions(params))
        seed = load_seed(params["seed_id"], allow_unverified=bool(params.get("allow_unverified", False)))
        write_json_atomic(run_dir / "seed.json", seed.to_json())
        scorer, predictor = backends or get_backends(params, seed)

        # 1) 설계
        status.stage("design", 0.0, "ESM-2로 변이 점수 계산 중")
        cands, sites, info = generate_candidates(
            seed, scorer, n=int(params["n_candidates"]), max_mutations=int(params["max_mutations"]),
            near_ibs_angstrom=float(params["near_ibs_angstrom"]), temperature=float(params["temperature"]),
            mcmc_steps=int(params["mcmc_steps"]), rng_seed=int(params["rng_seed"]),
            extra_fixed=params.get("extra_fixed") or [], progress=_stage_progress(status, 0.0, 0.15),
        )
        df = candidates_dataframe(cands)
        save_candidates(df, run_dir)
        write_fasta(run_dir / "sequences.fasta", [(c.cand_id, c.sequence) for c in cands])
        write_json_atomic(run_dir / "design_info.json", {
            "n_generated": len(cands), "n_requested": int(params["n_candidates"]), "attempts": info["attempts"],
            "variable_positions": len(info["positions"]), "free": sites.free, "conservative": sites.conservative,
            "fixed_ibs": sites.fixed_ibs, "frozen": sites.frozen,
        })
        if len(cands) < int(params["n_candidates"]):
            print(f"[경고] 요청한 {params['n_candidates']}개 중 {len(cands)}개만 생성되었습니다(변이 공간이 작음).", flush=True)

        # 2) 구조 QC
        from afp.evaluate.structure_qc import run_structure_qc

        status.stage("structure_qc", 0.15, "구조 예측 시작")
        run_structure_qc(df, seed, predictor, run_dir, cache_dir=config.CACHE_DIR, progress=_stage_progress(status, 0.15, 0.8))
        save_candidates(df, run_dir)

        # 3) IBS 지표와 점수 (M2)
        if params.get("evaluate", True):
            from afp.evaluate.scoring import run_evaluation

            run_evaluation(run_dir, seed=seed, scorer=scorer, predictor=predictor,
                           progress=_stage_progress(status, 0.8, 1.0), status=status)

        status.update(state="done", stage=None, progress=1.0, message="완료")
        return 0
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        status.update(state="failed", error=f"{type(exc).__name__}: {exc}", message="실패")
        return 1
    finally:
        status.update(finished_at=now_iso())


def run_evaluate_only(run_dir: Path, backends=None) -> None:
    """저장된 후보와 구조에서 평가 단계만 다시 실행한다 (CLI evaluate)."""
    from afp.evaluate.scoring import run_evaluation

    params = load_params(run_dir)
    seed = load_seed(params["seed_id"], allow_unverified=bool(params.get("allow_unverified", False)))
    scorer, predictor = backends or get_backends(params, seed)
    run_evaluation(run_dir, seed=seed, scorer=scorer, predictor=predictor, progress=None, status=None)

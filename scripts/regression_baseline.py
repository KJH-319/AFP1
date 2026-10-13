"""M3-2: 고정 시드·파라미터로 실제 모델 설계를 돌려 후보 품질 비율의 기준선을 기록한다.

    python scripts/regression_baseline.py [--n 20] [--seeds type3_hplc12 tmafp_beetle type1_hplc6]

결과: tests/regression/baseline.json 과 docs/dev/regression-baseline.md
품질 비율 = (pLDDT >= 80 이고 시드 대비 RMSD <= 2 Å) 인 후보 / 생성된 후보
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from afp import config  # noqa: E402
from afp.evaluate.structure_qc import apply_thresholds  # noqa: E402
from afp.io.seeds import list_seed_ids  # noqa: E402
from afp.models import versions  # noqa: E402
from afp.pipeline import execute_run, load_candidates  # noqa: E402
from afp.runner.launcher import create_run  # noqa: E402

FIXED = {"max_mutations": 8, "rng_seed": 1, "temperature": 1.0, "near_ibs_angstrom": config.NEAR_IBS_ANGSTROM,
         "backend": "real", "evaluate": False}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seeds", nargs="*", default=list_seed_ids())
    args = ap.parse_args()

    results = {}
    for sid in args.seeds:
        t0 = time.time()
        run_dir = create_run({**FIXED, "seed_id": sid, "n_candidates": args.n})
        code = execute_run(run_dir)
        df = load_candidates(run_dir)
        ok = apply_thresholds(df, config.PLDDT_MIN, config.RMSD_MAX)
        results[sid] = {
            "n_generated": int(len(df)), "n_ok_qc": int((df["qc_status"] == "ok").sum()), "n_pass": int(ok.sum()),
            "pass_rate": float(ok.mean()) if len(df) else 0.0,
            "plddt_mean_median": float(df["plddt_mean"].median()), "rmsd_median": float(df["rmsd_seed"].median()),
            "seconds": round(time.time() - t0), "exit_code": code, "run": run_dir.name,
        }
        print(f"{sid}: {results[sid]}", flush=True)

    out = {"params": {**FIXED, "n_candidates": args.n}, "thresholds": {"plddt_min": config.PLDDT_MIN, "rmsd_max": config.RMSD_MAX},
           "versions": versions(FIXED), "seeds": results}
    (ROOT / "tests" / "regression").mkdir(parents=True, exist_ok=True)
    (ROOT / "tests" / "regression" / "baseline.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 설계 후보 품질 회귀 기준선 (M3-2)", "",
             f"고정 파라미터(후보 {args.n}개, 최대 변이 {FIXED['max_mutations']}, 난수 시드 {FIXED['rng_seed']})로 실제 모델(ESM-2, ESMFold)을 돌린 결과다. "
             f"품질 후보 = pLDDT ≥ {config.PLDDT_MIN:g} 이고 시드 대비 RMSD ≤ {config.RMSD_MAX:g} Å.", "",
             "| 시드 | 생성 | 구조 예측 성공 | 품질 후보 | 비율 | 중앙값 pLDDT | 중앙값 RMSD (Å) | 소요(s) |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for sid, r in results.items():
        lines.append(f"| {sid} | {r['n_generated']} | {r['n_ok_qc']} | {r['n_pass']} | {r['pass_rate']:.0%} | {r['plddt_mean_median']:.1f} | {r['rmsd_median']:.2f} | {r['seconds']} |")
    lines += ["", "PRD 성공 지표: 품질 후보 비율 30% 이상. 회귀 테스트는 이 기준선에서 ±5%p(제안값) 이상 벗어나면 실패한다 "
              "(`pytest -m regression`)."]
    (ROOT / "docs" / "dev" / "regression-baseline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("저장 완료")


if __name__ == "__main__":
    main()

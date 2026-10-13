"""명령줄 인터페이스.

    python -m afp.cli seeds
    python -m afp.cli design --seed type3_hplc12 --n 100 --max-mut 8 --rng-seed 1
    python -m afp.cli evaluate --run <run_id>
    python -m afp.cli rerun --run <run_id>
    python -m afp.cli export --run <run_id> --top 10 --out my_batch
    python -m afp.cli validate
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from afp import config  # noqa: E402


def _resolve_run(arg: str) -> Path:
    p = Path(arg)
    if p.is_dir() and (p / "params.json").exists():
        return p
    cand = config.RUNS_DIR / arg
    if cand.is_dir():
        return cand
    raise SystemExit(f"실행 폴더를 찾을 수 없습니다: {arg}")


def cmd_seeds(args) -> int:
    from afp.io.seeds import load_all_seeds, validate_seed

    for s in load_all_seeds(allow_unverified=True):
        problems = validate_seed(s)
        print(f"{s.id:<16} {s.length:>3}aa  IBS {len(s.ibs_residues)}개  근거={s.ibs_evidence_level:<18} {'OK' if not problems else problems}")
    return 0


def cmd_design(args) -> int:
    from afp.pipeline import execute_run
    from afp.runner.launcher import create_run

    params = {
        "seed_id": args.seed, "n_candidates": args.n, "max_mutations": args.max_mut, "rng_seed": args.rng_seed,
        "temperature": args.temperature, "near_ibs_angstrom": args.near_ibs, "backend": args.backend,
        "device": args.device, "evaluate": not args.no_evaluate, "plddt_min": args.plddt_min, "rmsd_max": args.rmsd_max,
    }
    run_dir = create_run(params, Path(args.runs_dir) if args.runs_dir else None)
    print(f"실행 폴더: {run_dir}", flush=True)
    code = execute_run(run_dir)
    print("완료" if code == 0 else "실패 (log 또는 status.json 참고)")
    return code


def cmd_run(args) -> int:
    from afp.pipeline import execute_run

    return execute_run(Path(args.run_dir))


def cmd_evaluate(args) -> int:
    from afp.pipeline import run_evaluate_only

    run_evaluate_only(_resolve_run(args.run))
    print("평가 완료")
    return 0


def cmd_rerun(args) -> int:
    from afp.pipeline import execute_run
    from afp.runner.launcher import create_run, load_params, start_run

    params = load_params(_resolve_run(args.run))
    if args.background:
        print(start_run(params))
        return 0
    run_dir = create_run(params)
    print(f"실행 폴더: {run_dir}", flush=True)
    return execute_run(run_dir)


def cmd_export(args) -> int:
    from afp.export.exporter import export_run

    out = export_run(_resolve_run(args.run), args.out, top=args.top, cand_ids=args.ids.split(",") if args.ids else None,
                     min_plddt=args.plddt_min, max_rmsd=args.rmsd_max)
    print(f"내보내기 완료: {out}")
    return 0


def cmd_validate(args) -> int:
    from afp.validation import run_validation, write_report

    predictor = None
    if args.predicted:
        from afp.models import EsmFoldPredictor

        predictor = EsmFoldPredictor(device=args.device)
    result = run_validation(n_patches=args.patches, rng_seed=args.rng_seed, predictor=predictor)
    out = write_report(result, Path(args.out))
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"보고서: {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="afp", description="AFP Designer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("seeds", help="시드 목록과 검증").set_defaults(fn=cmd_seeds)

    d = sub.add_parser("design", help="설계 + 구조 QC (+ 평가)를 실행")
    d.add_argument("--seed", default=config.DEFAULT_PARAMS["seed_id"])
    d.add_argument("--n", type=int, default=config.DEFAULT_PARAMS["n_candidates"])
    d.add_argument("--max-mut", type=int, default=config.DEFAULT_PARAMS["max_mutations"])
    d.add_argument("--rng-seed", type=int, default=config.DEFAULT_PARAMS["rng_seed"])
    d.add_argument("--temperature", type=float, default=config.DEFAULT_PARAMS["temperature"])
    d.add_argument("--near-ibs", type=float, default=config.NEAR_IBS_ANGSTROM)
    d.add_argument("--backend", choices=["real", "mock"], default="real")
    d.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    d.add_argument("--no-evaluate", action="store_true", help="IBS 지표·점수 단계를 건너뜀")
    d.add_argument("--plddt-min", type=float, default=config.PLDDT_MIN)
    d.add_argument("--rmsd-max", type=float, default=config.RMSD_MAX)
    d.add_argument("--runs-dir")
    d.set_defaults(fn=cmd_design)

    r = sub.add_parser("run", help="(내부용) 기존 작업 폴더를 실행")
    r.add_argument("--run-dir", required=True)
    r.set_defaults(fn=cmd_run)

    e = sub.add_parser("evaluate", help="저장된 구조에서 평가 단계만 재실행")
    e.add_argument("--run", required=True)
    e.set_defaults(fn=cmd_evaluate)

    rr = sub.add_parser("rerun", help="params.json으로 새 작업 폴더를 만들어 재실행")
    rr.add_argument("--run", required=True)
    rr.add_argument("--background", action="store_true")
    rr.set_defaults(fn=cmd_rerun)

    x = sub.add_parser("export", help="상위 후보를 FASTA/PDB/CSV로 내보내기")
    x.add_argument("--run", required=True)
    x.add_argument("--top", type=int, default=10)
    x.add_argument("--ids", help="쉼표로 구분한 cand_id 목록 (지정하면 --top 무시)")
    x.add_argument("--out", required=True, help="exports/ 아래 폴더 이름 또는 경로")
    x.add_argument("--plddt-min", type=float, default=0.0)
    x.add_argument("--rmsd-max", type=float, default=1e9)
    x.set_defaults(fn=cmd_export)

    v = sub.add_parser("validate", help="양성 대조 검증 (M3)")
    v.add_argument("--patches", type=int, default=config.RANDOM_PATCH_COUNT)
    v.add_argument("--rng-seed", type=int, default=1)
    v.add_argument("--out", default="docs/dev/validation-report.md")
    v.add_argument("--predicted", action="store_true", help="실험 구조 대신 ESMFold 예측 구조로 검증")
    v.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    v.set_defaults(fn=cmd_validate)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main())

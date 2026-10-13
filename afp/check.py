"""도구 설치 검증 (smoke test). 한 명령으로 실행한다.

    python -m afp.check                  # 전체 (모델 포함)
    python -m afp.check --quick          # 모델 로딩은 건너뜀
    python -m afp.check --report docs/dev/env-report.md
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Result:
    name: str
    status: str   # ok | fail | skip
    detail: str
    seconds: float = 0.0


def _run(name, fn) -> Result:
    t0 = time.time()
    try:
        detail = fn()
        return Result(name, "ok", str(detail), time.time() - t0)
    except Exception as exc:  # noqa: BLE001
        return Result(name, "fail", f"{type(exc).__name__}: {exc}", time.time() - t0)


def check_python():
    if sys.version_info < (3, 10):
        raise RuntimeError(f"Python 3.10 이상이 필요합니다 (현재 {sys.version.split()[0]})")
    return sys.version.split()[0]


def check_imports():
    from afp.models import versions

    v = versions()
    missing = [k for k in ("numpy", "pandas", "scipy", "Bio", "transformers", "torch", "streamlit") if not v.get(k)]
    if missing:
        raise RuntimeError(f"설치되지 않은 패키지: {missing}")
    return ", ".join(f"{k} {v[k]}" for k in ("torch", "transformers", "Bio", "numpy", "streamlit"))


def check_gpu():
    import torch

    if not torch.cuda.is_available():
        return "CUDA 사용 불가 (cpu로 실행)"
    p = torch.cuda.get_device_properties(0)
    return f"{p.name}, VRAM {p.total_memory / 1024 ** 3:.1f} GB, CUDA {torch.version.cuda}"


def check_seeds():
    from afp.io.seeds import load_all_seeds, load_controls, validate_seed

    seeds = load_all_seeds()
    if len(seeds) < 3:
        raise RuntimeError(f"시드가 3개 미만입니다 ({len(seeds)})")
    problems = {s.id: validate_seed(s) for s in seeds}
    bad = {k: v for k, v in problems.items() if v}
    if bad:
        raise RuntimeError(f"시드 검증 실패: {bad}")
    controls = load_controls()
    return f"시드 {len(seeds)}개({', '.join(s.id for s in seeds)}), 음성 대조 {len(controls)}개"


def check_io():
    from afp.io.fasta import format_fasta, parse_fasta
    from afp.io.pdb import parse_pdb, write_pdb
    from afp.io.seeds import load_seed

    seed = load_seed("type1_hplc6")
    again = parse_pdb(write_pdb(seed.residues(), "A"), "A")
    assert [r.aa for r in again] == [r.aa for r in seed.residues()]
    assert parse_fasta(format_fasta([("x", seed.sequence)]))[0][1] == seed.sequence
    return "FASTA/PDB 왕복 일치"


def check_sasa():
    from afp.io.pdb import residue_sasa
    from afp.io.seeds import load_seed

    seed = load_seed("type1_hplc6")
    sasa = residue_sasa(seed.structure_text())
    total = sum(sasa.values())
    if not (500 < total < 6000):
        raise RuntimeError(f"SASA 합이 비정상입니다: {total:.0f}")
    return f"SASA 합 {total:.0f} Å^2 (Shrake-Rupley)"


def check_esm(device: str):
    from afp.io.seeds import load_seed
    from afp.models import EsmScorer

    seed = load_seed("type1_hplc6")
    scorer = EsmScorer(device=device)
    t0 = time.time()
    mm = scorer.masked_marginals(seed.sequence, [3, 10, 20])
    if mm.shape != (3, 20) or not np.isfinite(mm).all():
        raise RuntimeError(f"비정상 출력: {mm.shape}")
    return f"ESM-2 650M on {scorer.device}, masked marginal 3위치 {time.time() - t0:.2f}s"


def check_esmfold(device: str):
    import torch

    from afp.io.seeds import load_seed
    from afp.models import EsmFoldPredictor

    seed = load_seed("type1_hplc6")
    t_load = time.time()
    pred = EsmFoldPredictor(device=device)
    load_s = time.time() - t_load
    if pred.device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    out = pred.predict(seed.sequence)
    dt = time.time() - t0
    if len(out.plddt) != seed.length:
        raise RuntimeError("pLDDT 길이가 서열과 다릅니다")
    if not (0 <= out.plddt.min() and out.plddt.max() <= 100):
        raise RuntimeError(f"pLDDT 범위 이상: {out.plddt.min():.1f}~{out.plddt.max():.1f}")
    peak = f", 최대 VRAM {torch.cuda.max_memory_allocated() / 1024 ** 3:.1f}GB" if pred.device == "cuda" else ""
    note = f" ({pred.note})" if pred.note else ""
    return (f"ESMFold on {pred.device}{note}: 로딩 {load_s:.0f}s, {seed.length}잔기 예측 {dt:.1f}s, "
            f"평균 pLDDT {out.plddt.mean():.1f}{peak}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AFP Designer 설치 검증")
    ap.add_argument("--quick", action="store_true", help="모델 로딩 검사를 건너뜀")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--report", help="결과를 마크다운 파일로 저장")
    args = ap.parse_args(argv)

    results = [
        _run("Python", check_python),
        _run("패키지", check_imports),
        _run("GPU", check_gpu),
        _run("시드·대조군", check_seeds),
        _run("FASTA/PDB 입출력", check_io),
        _run("SASA", check_sasa),
    ]
    if args.quick:
        results += [Result("ESM-2", "skip", "--quick"), Result("ESMFold", "skip", "--quick")]
    else:
        results += [_run("ESM-2", lambda: check_esm(args.device)), _run("ESMFold", lambda: check_esmfold(args.device))]

    width = max(len(r.name) for r in results)
    for r in results:
        mark = {"ok": "OK  ", "fail": "FAIL", "skip": "SKIP"}[r.status]
        print(f"[{mark}] {r.name:<{width}}  {r.detail}  ({r.seconds:.1f}s)")
    failed = [r for r in results if r.status == "fail"]
    print(f"\n{len(results) - len(failed)}/{len(results)} 통과" + (f", 실패 {len(failed)}" if failed else ""))

    if args.report:
        from afp.models import versions

        v = versions()
        lines = ["# 환경 보고서 (python -m afp.check)", "", f"- Python {v['python']} · {v['platform']}",
                 f"- torch {v['torch']} · transformers {v['transformers']} · biopython {v['Bio']}",
                 f"- GPU: {v.get('gpu', '없음')} ({v.get('gpu_vram_gb', '-')} GB)", "",
                 "| 항목 | 결과 | 내용 | 시간(s) |", "| --- | --- | --- | --- |"]
        lines += [f"| {r.name} | {r.status} | {r.detail} | {r.seconds:.1f} |" for r in results]
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

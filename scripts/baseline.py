"""M0-8 기준선: 시드 서열을 ESMFold로 예측해 실험 구조와 비교하고 docs/dev/baseline.md를 쓴다.

    python scripts/baseline.py [--device auto|cuda|cpu]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from afp import config  # noqa: E402
from afp.evaluate.structure_qc import baseline  # noqa: E402
from afp.io.seeds import load_all_seeds  # noqa: E402
from afp.models import EsmFoldPredictor, versions  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="auto")
    ap.add_argument("--out", default=str(ROOT / "docs" / "dev" / "baseline.md"))
    args = ap.parse_args()

    pred = EsmFoldPredictor(device=args.device)
    rows = []
    for seed in load_all_seeds():
        t0 = time.time()
        m = baseline(seed, pred, cache_dir=config.CACHE_DIR)
        m["seconds"] = time.time() - t0
        rows.append((seed, m))
        print(f"{seed.id}: pLDDT {m['plddt_mean']:.1f} (IBS {m['plddt_ibs']:.1f}) RMSD {m['rmsd_seed']:.2f} Å, {m['seconds']:.0f}s", flush=True)

    v = versions()
    lines = [
        "# 시드 기준선 (M0-8)", "",
        f"시드 서열을 ESMFold(`{config.STRUCTURE_MODEL}`, {pred.device})로 예측해 실험 구조와 비교한 값이다. "
        "이 값은 M1의 pLDDT·RMSD 임계값을 시드별로 조정할 때의 근거 자료다.", "",
        f"- 환경: {v['platform']}, torch {v['torch']}, transformers {v['transformers']}",
        f"- 장치: {pred.device}" + (f" ({pred.note})" if pred.note else ""), "",
        "| 시드 | 길이 | 근거 수준 | 평균 pLDDT | IBS 영역 pLDDT | 실험 구조 대비 RMSD (Å) | 예측 시간 (s) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for seed, m in rows:
        lines.append(f"| {seed.id} | {seed.length} | {seed.ibs_evidence_level} | {m['plddt_mean']:.1f} | {m['plddt_ibs']:.1f} | {m['rmsd_seed']:.2f} | {m['seconds']:.0f} |")
    lines += ["", "임계값(pLDDT ≥ 80, RMSD ≤ 2 Å)과 비교해 시드 자체가 통과하는지 확인한다. 통과하지 못하는 시드는 시드별 임계값을 따로 둔다."]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"저장: {args.out}")


if __name__ == "__main__":
    main()

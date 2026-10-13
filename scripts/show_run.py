"""실행 결과 요약을 터미널에 출력한다.  python scripts/show_run.py <run_id|경로> [--top 10]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from afp import config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()
    d = Path(args.run) if Path(args.run).is_dir() else config.RUNS_DIR / args.run
    sc_path = d / "scoring.json"
    if sc_path.exists():
        sc = json.loads(sc_path.read_text(encoding="utf-8"))
        print("가중치", {k: round(v, 3) for k, v in sc["weights"].items()}, "| 기준 구조:", sc["reference_structure"])
        for k, a in sc["anchors"].items():
            print(f"  {k:22s} 시드={a['x_seed']:.3f}  음성중앙값={a['x_neg']:.3f}  음성 p10~p90={a['neg_p10']:.3f}~{a['neg_p90']:.3f}  degenerate={a['degenerate']}")
    df = pd.read_csv(d / "candidates.csv", keep_default_na=False, na_values=[""])
    cols = [c for c in ("cand_id", "mutations", "plddt_mean", "rmsd_seed", "ibs_planarity", "ibs_area", "ibs_lattice_dev",
                        "g_structure", "g_ibs", "g_afp", "g_dev", "score", "rank", "flags") if c in df.columns]
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 40)
    print(df[cols].head(args.top).round(3).to_string(index=False))
    print(f"... 총 {len(df)}개 후보")


if __name__ == "__main__":
    main()

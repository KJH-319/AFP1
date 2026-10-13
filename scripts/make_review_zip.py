"""검토용 ZIP(코드, 데이터, 문서, 테스트)을 만든다. 실행 결과·캐시·모델 가중치·원본 PDB는 제외한다.

    python scripts/make_review_zip.py [--out afp-designer-review.zip]
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = ("afp", "app", "data", "docs", "scripts", "tests")
INCLUDE_FILES = ("README.md", "pyproject.toml", "requirements.txt", ".gitignore")
SKIP_PARTS = {"__pycache__", ".pytest_cache", "_raw"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "afp-designer-review.zip"))
    args = ap.parse_args()
    out = Path(args.out)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in INCLUDE_DIRS:
            for p in sorted((ROOT / d).rglob("*")):
                if p.is_file() and not (SKIP_PARTS & set(p.parts)) and p.suffix != ".pyc":
                    zf.write(p, Path("afp-designer") / p.relative_to(ROOT))
                    n += 1
        for f in INCLUDE_FILES:
            zf.write(ROOT / f, Path("afp-designer") / f)
            n += 1
    print(f"{out.name}: {n}개 파일, {out.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()

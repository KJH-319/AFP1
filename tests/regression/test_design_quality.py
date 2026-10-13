"""고정 시드 설계 결과의 품질 비율이 기준선(baseline.json)에서 크게 벗어나지 않는지 확인한다. 느림(실제 모델).

    python scripts/regression_baseline.py     # 기준선 생성/갱신
    pytest -m regression                      # 비교
"""
import json
from pathlib import Path

import pytest

from afp import config
from afp.evaluate.structure_qc import apply_thresholds
from afp.pipeline import execute_run, load_candidates
from afp.runner.launcher import create_run

pytestmark = pytest.mark.regression

BASELINE = Path(__file__).with_name("baseline.json")
TOLERANCE = 0.05            # +-5%p (제안값)
PRD_MIN_RATE = 0.30         # PRD 성공 지표


@pytest.fixture(scope="module")
def baseline():
    if not BASELINE.exists():
        pytest.skip("baseline.json이 없습니다. scripts/regression_baseline.py를 먼저 실행하세요.")
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _seed_ids():
    if not BASELINE.exists():
        return []
    return list(json.loads(BASELINE.read_text(encoding="utf-8"))["seeds"])


@pytest.mark.parametrize("seed_id", _seed_ids())
def test_pass_rate_matches_baseline(baseline, isolated_dirs, seed_id):
    params = {**baseline["params"], "seed_id": seed_id}
    run_dir = create_run(params)
    assert execute_run(run_dir) == 0
    df = load_candidates(run_dir)
    rate = float(apply_thresholds(df, config.PLDDT_MIN, config.RMSD_MAX).mean())
    expected = baseline["seeds"][seed_id]["pass_rate"]
    # 후보 20개 기준 1개 = 5%p 이므로 경계(정확히 5%p 차이)는 허용한다 (부동소수점 오차 보정)
    assert abs(rate - expected) <= TOLERANCE + 1e-9, f"{seed_id}: {rate:.0%} vs 기준선 {expected:.0%}"


@pytest.mark.parametrize("seed_id", _seed_ids())
def test_baseline_meets_prd_target(baseline, seed_id):
    assert baseline["seeds"][seed_id]["pass_rate"] >= PRD_MIN_RATE

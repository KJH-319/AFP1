import math

import numpy as np
import pytest

from afp.validation import DIRECTION, percentile_better, run_validation

pytestmark = pytest.mark.unit


def test_percentile_better_respects_direction_and_nan():
    ctrl = np.arange(1.0, 11.0)                                   # 1..10
    assert percentile_better(0.5, ctrl, -1) == 1.0                # 낮을수록 좋음: 모든 대조보다 낮음
    assert percentile_better(5.5, ctrl, -1) == 0.5
    assert percentile_better(5.5, ctrl, +1) == 0.5
    assert percentile_better(11.0, ctrl, +1) == 1.0
    assert math.isnan(percentile_better(5.0, ctrl, 0))            # 방향 가정이 없는 지표
    assert math.isnan(percentile_better(float("nan"), ctrl, -1))
    assert math.isnan(percentile_better(5.0, np.array([np.nan]), -1))


def test_direction_table_is_the_preregistered_one():
    assert DIRECTION == {"ibs_planarity": -1, "ibs_lattice_dev": -1, "ibs_area": +1, "ibs_hydrophobic_frac": 0}


def test_run_validation_structure_and_determinism():
    a = run_validation(n_patches=15, rng_seed=3)
    b = run_validation(n_patches=15, rng_seed=3)
    assert a == b or str(a) == str(b)                              # 같은 난수 시드면 같은 결과 (NaN 비교 때문에 문자열도 허용)
    assert a["summary"]["seeds_total"] >= 3
    assert a["summary"]["verdict"] in ("합격", "부분 합격", "불합격")
    for row in a["seeds"]:
        assert set(row["metrics"]) == set(DIRECTION)
        assert row["passed"] == (len(row["hits"]) >= 2)
        assert set(row["hits"]) <= set(row["hits_either_direction"])    # 사후 탐색은 판정을 포함한다
        for name, m in row["metrics"].items():
            if DIRECTION[name] == 0:
                assert math.isnan(m["better_than_control_patches"])


def test_verdict_rule():
    from afp.validation import PARTIAL_FRACTION

    assert PARTIAL_FRACTION == 0.5

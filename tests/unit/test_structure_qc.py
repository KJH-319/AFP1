import pandas as pd
import pytest

from afp.evaluate.structure_qc import apply_thresholds, predict_cached, qc_metrics, run_structure_qc

pytestmark = pytest.mark.unit


class Counting:
    def __init__(self, inner):
        self.inner, self.calls = inner, 0
        self.model_name = inner.model_name

    def predict(self, seq):
        self.calls += 1
        return self.inner.predict(seq)


def test_qc_metrics_for_unmutated_seed(seed, mock_predictor_for):
    m = qc_metrics(seed, mock_predictor_for(seed).predict(seed.sequence))
    assert 80 < m["plddt_mean"] < 95
    assert 0.0 < m["rmsd_seed"] < 1.5
    assert 80 < m["plddt_ibs"] < 95


def test_cache_prevents_repeat_prediction(type3, mock_predictor_for, tmp_path):
    pred = Counting(mock_predictor_for(type3))
    a, hit1 = predict_cached(pred, type3.sequence, tmp_path)
    b, hit2 = predict_cached(pred, type3.sequence, tmp_path)
    assert (hit1, hit2) == (False, True) and pred.calls == 1
    assert list(a.plddt) == pytest.approx(list(b.plddt), abs=0.01)


def test_run_structure_qc_fills_columns_and_survives_failures(type3, mock_predictor_for, tmp_path):
    inner = mock_predictor_for(type3)
    good = type3.sequence
    mutated = good[:20] + ("A" if good[20] != "A" else "V") + good[21:]

    class Flaky(Counting):
        def predict(self, seq):
            if seq == mutated:
                raise RuntimeError("CUDA out of memory (가짜)")
            return super().predict(seq)

    df = pd.DataFrame({"cand_id": ["c0001", "c0002"], "sequence": [good, mutated]})
    seen = []
    run_structure_qc(df, type3, Flaky(inner), tmp_path / "run", cache_dir=tmp_path / "cache", progress=lambda f, m: seen.append(f))
    assert df.loc[0, "qc_status"] == "ok" and (tmp_path / "run" / "structures" / "c0001.pdb").exists()
    assert df.loc[1, "qc_status"].startswith("failed") and pd.isna(df.loc[1, "plddt_mean"])
    assert seen[-1] == 1.0
    ok = apply_thresholds(df, plddt_min=80, rmsd_max=2.0)
    assert list(ok) == [True, False]
    assert list(apply_thresholds(df, plddt_min=99, rmsd_max=2.0)) == [False, False]

"""실제 ESM-2 / ESMFold 가중치를 쓰는 테스트.  pytest -m gpu"""
import numpy as np
import pytest

from afp import config
from afp.evaluate.structure_qc import qc_metrics
from afp.io.seeds import load_seed
from afp.models import EsmFoldPredictor, EsmScorer
from afp.pipeline import execute_run, load_candidates
from afp.runner import launcher

pytestmark = pytest.mark.gpu


@pytest.fixture(scope="module")
def scorer():
    return EsmScorer()


@pytest.fixture(scope="module")
def predictor():
    return EsmFoldPredictor()


def test_masked_marginals_are_normalized_and_prefer_wildtype(scorer):
    seed = load_seed("type3_hplc12")
    positions = list(range(0, seed.length, 4))
    mm = scorer.masked_marginals(seed.sequence, positions)
    assert mm.shape == (len(positions), 20) and np.isfinite(mm).all()
    assert np.allclose(np.exp(mm).sum(axis=1), 1.0, atol=1e-3)
    wt_idx = [config.AMINO_ACIDS.index(seed.sequence[p]) for p in positions]
    wt_prob = np.exp(mm[np.arange(len(positions)), wt_idx])
    assert wt_prob.mean() > 1 / 20 * 3          # 야생형이 무작위(1/20)보다 확실히 선호됨


def test_esmfold_reproduces_type1_seed(predictor):
    seed = load_seed("type1_hplc6")
    pred = predictor.predict(seed.sequence)
    m = qc_metrics(seed, pred)
    assert 0 <= pred.plddt.min() and pred.plddt.max() <= 100
    assert m["plddt_mean"] > 80 and m["rmsd_seed"] < 2.0


def test_real_end_to_end_small_run(isolated_dirs):
    run_dir = launcher.create_run({"seed_id": "type1_hplc6", "n_candidates": 3, "max_mutations": 3, "rng_seed": 1})
    assert execute_run(run_dir) == 0, launcher.tail_log(run_dir)
    df = load_candidates(run_dir)
    assert len(df) == 3 and (df["qc_status"] == "ok").all() and df["score"].notna().all()

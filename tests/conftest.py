import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from afp import config  # noqa: E402
from afp.io.seeds import load_all_seeds, load_seed  # noqa: E402
from afp.models import MockEsmScorer, MockStructurePredictor  # noqa: E402

SEED_IDS = [s.id for s in load_all_seeds()]


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """runs/, cache/를 임시 폴더로 돌린다 (서브프로세스에도 환경변수로 전달)."""
    runs, cache, exports = tmp_path / "runs", tmp_path / "cache", tmp_path / "exports"
    for d in (runs, cache, exports):
        d.mkdir()
    monkeypatch.setattr(config, "RUNS_DIR", runs)
    monkeypatch.setattr(config, "CACHE_DIR", cache)
    monkeypatch.setattr(config, "EXPORTS_DIR", exports)
    monkeypatch.setenv("AFP_RUNS_DIR", str(runs))
    monkeypatch.setenv("AFP_CACHE_DIR", str(cache))
    monkeypatch.setenv("AFP_EXPORTS_DIR", str(exports))
    return runs, cache


@pytest.fixture(params=SEED_IDS)
def seed(request):
    return load_seed(request.param)


@pytest.fixture
def type3():
    return load_seed("type3_hplc12")


@pytest.fixture
def mock_scorer():
    return MockEsmScorer()


@pytest.fixture
def mock_predictor_for():
    def make(seed, **kw):
        return MockStructurePredictor(seed.residues(), seed.sequence, **kw)
    return make

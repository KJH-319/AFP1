import json
import subprocess
import sys
import time

import pytest

from afp.models import MockEsmScorer, MockStructurePredictor
from afp.pipeline import execute_run, load_candidates
from afp.runner import launcher
from afp.runner.status import StatusWriter, read_status

pytestmark = pytest.mark.integration

PARAMS = {"seed_id": "type1_hplc6", "n_candidates": 6, "max_mutations": 3, "backend": "mock", "mcmc_steps": 40,
          "evaluate": False, "rng_seed": 5}


def _wait(run_dir, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = launcher.refresh_status(run_dir)
        if st and st["state"] in ("done", "failed", "cancelled"):
            return st
        time.sleep(0.3)
    raise AssertionError("실행이 제한 시간 안에 끝나지 않았습니다")


def test_execute_run_writes_expected_files(isolated_dirs):
    run_dir = launcher.create_run(PARAMS)
    assert read_status(run_dir)["state"] == "queued"
    assert execute_run(run_dir) == 0
    st = read_status(run_dir)
    assert st["state"] == "done" and st["progress"] == 1.0 and st["error"] is None
    for name in ("params.json", "versions.json", "status.json", "candidates.csv", "sequences.fasta", "seed.json", "design_info.json"):
        assert (run_dir / name).exists(), name
    df = load_candidates(run_dir)
    assert len(df) == 6 and (df["qc_status"] == "ok").all()
    assert df["plddt_mean"].between(0, 100).all()
    assert len(list((run_dir / "structures").glob("*.pdb"))) == 6
    versions = json.loads((run_dir / "versions.json").read_text(encoding="utf-8"))
    assert versions["backend"] == "mock" and "torch" in versions


def test_rerun_reproduces_sequences(isolated_dirs):
    a = launcher.create_run(PARAMS)
    execute_run(a)
    b = launcher.create_run(launcher.load_params(a))
    assert a != b
    execute_run(b)
    assert (a / "sequences.fasta").read_text() == (b / "sequences.fasta").read_text()


def test_failure_is_recorded(isolated_dirs):
    run_dir = launcher.create_run({**PARAMS, "seed_id": "does_not_exist"})
    assert execute_run(run_dir) == 1
    st = read_status(run_dir)
    assert st["state"] == "failed" and "does_not_exist" in st["error"]


def test_subprocess_run_to_completion(isolated_dirs):
    run_dir = launcher.start_run(PARAMS)
    st = _wait(run_dir)
    assert st["state"] == "done", launcher.tail_log(run_dir)
    assert (run_dir / "log.txt").exists()
    runs = launcher.list_runs()
    assert runs and runs[0]["state"] == "done" and runs[0]["seed_id"] == "type1_hplc6"


def test_concurrency_limit(isolated_dirs, monkeypatch):
    monkeypatch.setattr(launcher, "MAX_CONCURRENT", 1)
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        run_dir = launcher.create_run(PARAMS)
        StatusWriter(run_dir).update(state="running", pid=sleeper.pid)
        with pytest.raises(RuntimeError, match="동시 실행"):
            launcher.start_run(PARAMS)
    finally:
        sleeper.kill()


def test_cancel_kills_process_and_marks_cancelled(isolated_dirs):
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    run_dir = launcher.create_run(PARAMS)
    StatusWriter(run_dir).update(state="running", pid=sleeper.pid)
    assert launcher.cancel_run(run_dir) is True
    assert read_status(run_dir)["state"] == "cancelled"
    sleeper.wait(timeout=10)
    assert sleeper.poll() is not None
    assert launcher.cancel_run(run_dir) is False       # 이미 끝난 작업


def test_dead_process_is_marked_failed(isolated_dirs):
    run_dir = launcher.create_run(PARAMS)
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    StatusWriter(run_dir).update(state="running", pid=p.pid)
    st = launcher.refresh_status(run_dir)
    assert st["state"] == "failed" and "비정상 종료" in st["error"]


def test_status_file_is_never_half_written(isolated_dirs):
    run_dir = launcher.create_run(PARAMS)
    w = StatusWriter(run_dir)
    for i in range(200):
        w.progress(i / 200, "x" * 50)
        assert 0 <= read_status(run_dir)["progress"] <= 1


def test_mock_backend_reused_in_process(isolated_dirs, type3=None):
    from afp.io.seeds import load_seed

    seed = load_seed("type1_hplc6")
    run_dir = launcher.create_run(PARAMS)
    assert execute_run(run_dir, backends=(MockEsmScorer(), MockStructurePredictor(seed.residues(), seed.sequence))) == 0

"""실행(run) 폴더 생성, 서브프로세스 시작, 취소, 목록 (F-1, F-13, F-17)."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from afp import config
from afp.runner.status import StatusWriter, now_iso, read_status, write_json_atomic

MAX_CONCURRENT = int(os.environ.get("AFP_MAX_CONCURRENT", "1"))


def merge_params(params: dict | None) -> dict:
    merged = copy.deepcopy(config.DEFAULT_PARAMS)
    merged.update(params or {})
    return merged


def new_run_id(seed_id: str, params: dict) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha1((json.dumps(params, sort_keys=True) + str(time.time_ns())).encode()).hexdigest()[:6]
    return f"{stamp}-{seed_id}-{digest}"


def create_run(params: dict | None, runs_dir: Path | None = None) -> Path:
    """params.json과 status.json(queued)을 가진 새 작업 폴더를 만든다."""
    runs_dir = Path(runs_dir or config.RUNS_DIR)
    merged = merge_params(params)
    run_dir = runs_dir / new_run_id(merged["seed_id"], merged)
    (run_dir / "structures").mkdir(parents=True, exist_ok=True)
    write_json_atomic(run_dir / "params.json", merged)
    StatusWriter(run_dir).update(state="queued", stage=None, progress=0.0)
    return run_dir


def load_params(run_dir: Path) -> dict:
    return json.loads((Path(run_dir) / "params.json").read_text(encoding="utf-8"))


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def refresh_status(run_dir: Path) -> dict | None:
    """상태를 읽되, running인데 프로세스가 죽었으면 failed로 바로잡는다."""
    status = read_status(run_dir)
    if status and status.get("state") in ("running", "queued") and status.get("pid") and not pid_alive(status["pid"]):
        StatusWriter(run_dir).update(state="failed", error=status.get("error") or "작업 프로세스가 비정상 종료되었습니다. log.txt를 확인하세요.")
        status = read_status(run_dir)
    return status


def running_count(runs_dir: Path | None = None) -> int:
    runs_dir = Path(runs_dir or config.RUNS_DIR)
    if not runs_dir.exists():
        return 0
    n = 0
    for d in runs_dir.iterdir():
        st = refresh_status(d) if d.is_dir() else None
        if st and st.get("state") == "running":
            n += 1
    return n


def start_run(params: dict | None, runs_dir: Path | None = None, python: str | None = None) -> Path:
    """서브프로세스로 실행을 시작한다. UI를 막지 않는다."""
    if running_count(runs_dir) >= MAX_CONCURRENT:
        raise RuntimeError(f"동시 실행 한도({MAX_CONCURRENT}개)에 도달했습니다. 실행 중인 작업이 끝난 뒤 다시 시도하세요.")
    run_dir = create_run(params, runs_dir)
    log = open(run_dir / "log.txt", "ab")
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(
        [python or sys.executable, "-m", "afp.cli", "run", "--run-dir", str(run_dir)],
        stdout=log, stderr=subprocess.STDOUT, cwd=str(config.ROOT), creationflags=flags, env=env,
    )
    StatusWriter(run_dir).update(pid=proc.pid, state="running", started_at=now_iso(), message="시작 중")
    return run_dir


def cancel_run(run_dir: Path) -> bool:
    """프로세스 트리를 종료하고 cancelled로 표시한다. 부분 결과는 폴더에 남긴다."""
    status = read_status(run_dir)
    if not status or status.get("state") not in ("running", "queued"):
        return False
    pid = status.get("pid")
    if pid_alive(pid):
        try:
            import psutil

            parent = psutil.Process(pid)
            procs = parent.children(recursive=True) + [parent]
            for p in procs:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(procs, timeout=10)
        except ImportError:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            else:
                os.kill(pid, 9)
    StatusWriter(run_dir).update(state="cancelled", message="사용자가 취소했습니다.")
    return True


def list_runs(runs_dir: Path | None = None) -> list[dict]:
    """최근 실행부터. UI의 실행 이력 표에 쓴다."""
    runs_dir = Path(runs_dir or config.RUNS_DIR)
    out = []
    if not runs_dir.exists():
        return out
    for d in sorted((p for p in runs_dir.iterdir() if p.is_dir()), reverse=True):
        try:
            params = load_params(d)
        except (OSError, json.JSONDecodeError):
            continue
        st = refresh_status(d) or {}
        out.append({
            "run_id": d.name, "path": d, "seed_id": params.get("seed_id"),
            "n_candidates": params.get("n_candidates"), "backend": params.get("backend"),
            "state": st.get("state"), "stage": st.get("stage"), "progress": st.get("progress", 0.0),
            "started_at": st.get("started_at"), "updated_at": st.get("updated_at"), "error": st.get("error"),
        })
    return out


def tail_log(run_dir: Path, lines: int = 40) -> str:
    path = Path(run_dir) / "log.txt"
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])

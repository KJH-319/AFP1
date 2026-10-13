"""작업 폴더의 status.json 읽기/쓰기 (F-13). UI는 이 파일을 폴링한다."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

STATES = ("queued", "running", "done", "failed", "cancelled")
STAGES = ("design", "structure_qc", "ibs_metrics", "scoring", "export")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json_atomic(path: Path, data: dict) -> None:
    """임시 파일에 쓰고 rename하여 UI가 반쯤 쓰인 파일을 읽지 않게 한다."""
    path = Path(path)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_status(run_dir: Path) -> dict | None:
    path = Path(run_dir) / "status.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


class StatusWriter:
    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / "status.json"
        self.data = read_status(run_dir) or {
            "state": "queued", "stage": None, "progress": 0.0, "pid": None,
            "started_at": None, "updated_at": now_iso(), "error": None, "message": "",
        }

    def update(self, **fields) -> None:
        self.data.update(fields)
        self.data["updated_at"] = now_iso()
        write_json_atomic(self.path, self.data)

    def stage(self, stage: str, progress: float | None = None, message: str = "") -> None:
        fields = {"stage": stage, "message": message}
        if progress is not None:
            fields["progress"] = round(float(progress), 4)
        self.update(**fields)

    def progress(self, progress: float, message: str = "") -> None:
        self.update(progress=round(float(progress), 4), message=message)

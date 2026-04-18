from __future__ import annotations

from datetime import datetime
from pathlib import Path


def append_plan_log(task_dir: Path, line: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    log_path = task_dir / "plan.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {line}\n")

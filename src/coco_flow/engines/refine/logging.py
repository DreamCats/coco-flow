from __future__ import annotations

from datetime import datetime
from pathlib import Path


def append_refine_log(task_dir: Path, message: str) -> None:
    log_path = task_dir / "refine.log"
    with log_path.open("a", encoding="utf-8") as file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file.write(f"{timestamp} {message}\n")

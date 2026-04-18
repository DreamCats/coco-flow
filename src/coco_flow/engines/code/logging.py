from __future__ import annotations

from datetime import datetime
from pathlib import Path


def append_code_log(task_dir: Path, line: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with (task_dir / "code.log").open("a", encoding="utf-8") as file:
        file.write(f"{timestamp} {line}\n")

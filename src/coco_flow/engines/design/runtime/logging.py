"""Design 日志写入工具。

服务层和引擎共用该函数向 task 目录追加 design.log，保持阶段推进过程可追踪。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def append_design_log(task_dir: Path, message: str) -> None:
    log_path = task_dir / "design.log"
    with log_path.open("a", encoding="utf-8") as file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file.write(f"{timestamp} {message}\n")

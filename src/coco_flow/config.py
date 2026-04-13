from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    config_root: Path
    task_root: Path
    refine_executor: str
    plan_executor: str
    code_executor: str
    coco_bin: str
    native_query_timeout: str
    native_code_timeout: str


def load_settings() -> Settings:
    home = Path.home()
    config_root = Path(
        os.getenv("COCO_FLOW_CONFIG_DIR", home / ".config" / "coco-flow")
    ).expanduser()
    task_root = Path(
        os.getenv("COCO_FLOW_TASK_ROOT", config_root / "tasks")
    ).expanduser()
    refine_executor = os.getenv("COCO_FLOW_REFINE_EXECUTOR", "native").strip() or "native"
    plan_executor = os.getenv("COCO_FLOW_PLAN_EXECUTOR", "native").strip() or "native"
    code_executor = os.getenv("COCO_FLOW_CODE_EXECUTOR", "native").strip() or "native"
    coco_bin = os.getenv("COCO_FLOW_COCO_BIN", "coco").strip() or "coco"
    native_query_timeout = os.getenv("COCO_FLOW_NATIVE_QUERY_TIMEOUT", "90s").strip() or "90s"
    native_code_timeout = os.getenv("COCO_FLOW_NATIVE_CODE_TIMEOUT", "10m").strip() or "10m"
    return Settings(
        config_root=config_root,
        task_root=task_root,
        refine_executor=refine_executor,
        plan_executor=plan_executor,
        code_executor=code_executor,
        coco_bin=coco_bin,
        native_query_timeout=native_query_timeout,
        native_code_timeout=native_code_timeout,
    )

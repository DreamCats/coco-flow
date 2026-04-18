from __future__ import annotations

from coco_flow.config import Settings, load_settings
from coco_flow.engines.input import create_input_task, run_input_engine


def create_task(
    raw_input: str,
    title: str | None,
    repos: list[str],
    settings: Settings | None = None,
    supplement: str | None = None,
    defer_lark_resolution: bool = False,
) -> tuple[str, str]:
    cfg = settings or load_settings()
    result = create_input_task(
        raw_input=raw_input,
        title=title,
        supplement=supplement,
        repos=repos,
        settings=cfg,
        defer_lark_resolution=defer_lark_resolution,
    )
    return result.task_id, result.status


def input_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    return run_input_engine(task_id, cfg)

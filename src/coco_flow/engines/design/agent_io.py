from __future__ import annotations

import json
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings

from .models import DesignInputBundle


def run_agent_json(
    prepared: DesignInputBundle,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
) -> dict[str, object]:
    raw = _run_agent_template(prepared, settings, template, prompt_builder, prefix, ".json")
    if "__FILL__" in raw or not raw.strip():
        raise ValueError("design_agent_template_unfilled")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("design_agent_payload_not_object")
    return payload


def run_agent_markdown(
    prepared: DesignInputBundle,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
) -> str:
    raw = _run_agent_template(prepared, settings, template, prompt_builder, prefix, ".md")
    if not raw.strip():
        raise ValueError("design_agent_markdown_empty")
    return raw.rstrip() + "\n"


def _run_agent_template(
    prepared: DesignInputBundle,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
    suffix: str,
) -> str:
    path = _write_template(prepared.task_dir, prefix, suffix, template)
    client = CocoACPClient(settings.coco_bin, idle_timeout_seconds=settings.acp_idle_timeout_seconds, settings=settings)
    try:
        client.run_agent(
            prompt_builder(str(path)),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        return path.read_text(encoding="utf-8") if path.exists() else ""
    finally:
        if path.exists():
            path.unlink()


def _write_template(task_dir: Path, prefix: str, suffix: str, content: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=task_dir, prefix=prefix, suffix=suffix, delete=False) as handle:
        handle.write(content)
        handle.flush()
        return Path(handle.name)


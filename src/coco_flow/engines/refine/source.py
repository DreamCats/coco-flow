from __future__ import annotations

# 本文件负责准备 Refine 输入：从 task 目录读取原始 PRD、人工提炼范围、
# input/source 元数据，并统一组装成后续编排使用的 RefinePreparedInput。

from pathlib import Path

from coco_flow.config import Settings
from coco_flow.engines.shared.manual_extract import split_source_and_manual_extract
from coco_flow.services.queries.task_detail import read_json_file

from .models import RefinePreparedInput


def locate_task_dir(task_id: str, settings: Settings) -> Path | None:
    primary = settings.task_root / task_id
    if primary.is_dir():
        return primary
    return None


def prepare_refine_input(task_dir: Path, task_meta: dict[str, object]) -> RefinePreparedInput:
    input_meta = read_json_file(task_dir / "input.json")
    source_meta = read_json_file(task_dir / "source.json")
    source_markdown = (task_dir / "prd.source.md").read_text(encoding="utf-8") if (task_dir / "prd.source.md").exists() else ""
    source_content, supplement = extract_source_sections(source_markdown)
    if input_meta.get("supplement") and not supplement:
        supplement = str(input_meta.get("supplement") or "").strip()
    return RefinePreparedInput(
        task_dir=task_dir,
        task_id=task_dir.name,
        title=str(task_meta.get("title") or input_meta.get("title") or task_dir.name),
        source_type=str((source_meta or {}).get("type") or task_meta.get("source_type") or ""),
        source_meta=source_meta or {},
        source_markdown=source_markdown,
        source_content=source_content.strip(),
        supplement=supplement.strip(),
        input_meta=input_meta or {},
    )


def extract_source_sections(markdown: str) -> tuple[str, str]:
    separator = "\n---\n"
    content = markdown.split(separator, 1)[1] if separator in markdown else markdown
    source, supplement = split_source_and_manual_extract(content)
    return source.strip(), supplement.strip()


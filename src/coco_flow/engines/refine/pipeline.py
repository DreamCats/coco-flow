from __future__ import annotations

# 本文件负责 Refine 阶段的主编排：读取输入、整理人工提炼范围、调用生成器产出
# `prd-refined.md`。这里不持久化中间 schema，所有临时结构只服务于本次生成。

import json
import tempfile

from coco_flow.config import Settings

from .brief import (
    build_refine_brief,
    build_source_excerpt,
    merge_brief_with_refined_markdown,
    parse_manual_extract,
)
from .generate import generate_refined_markdown
from .models import RefineEngineResult
from .source import prepare_refine_input


def run_refine_engine(
    task_dir,
    task_meta: dict[str, object],
    settings: Settings,
    on_log,
) -> RefineEngineResult:
    # Refine 的第一版主流程保持“文档流”：
    # 1. 读取 Input 阶段已经确认的人工提炼范围。
    # 2. 在内存中整理成适合渲染的需求要点。
    # 3. local 直接生成 Markdown；native 只负责在模板基础上润色。
    # 4. 所有中间对象只服务于本次生成，不作为阶段 schema 持久化。
    prepared = prepare_refine_input(task_dir, task_meta)
    if not prepared.source_content.strip():
        raise ValueError("prd.source.md 为空，无法执行 refine")

    # 人工提炼范围是事实入口；后面的 brief 只是生成辅助，不落盘、不交给下游消费。
    manual_extract = parse_manual_extract(prepared.supplement)
    brief = build_refine_brief(prepared, manual_extract)
    source_excerpt = build_source_excerpt(prepared, brief)

    manual_extract_payload = manual_extract.to_payload()
    brief_draft_payload = brief.to_payload()
    # native agent 仍需要读取文件路径；这里使用临时目录，避免 task 目录出现 schema 产物。
    with tempfile.TemporaryDirectory(prefix="coco-flow-refine-") as temp_dir:
        manual_extract_path = _write_temp_file(temp_dir, "manual-extract.json", manual_extract_payload)
        brief_draft_path = _write_temp_file(temp_dir, "brief-draft.json", brief_draft_payload)
        source_excerpt_path = _write_temp_file(temp_dir, "source-excerpt.md", source_excerpt)

        refined_markdown, verify = generate_refined_markdown(
            prepared=prepared,
            brief=brief,
            manual_extract_path=manual_extract_path,
            brief_draft_path=brief_draft_path,
            source_excerpt_path=source_excerpt_path,
            settings=settings,
            on_log=on_log,
        )
    finalized_brief = merge_brief_with_refined_markdown(brief, refined_markdown)

    on_log("refine_strategy: manual_first_doc_only")
    on_log(f"scope_count: {len(manual_extract.scope)}")
    on_log(f"change_point_count: {len(manual_extract.change_points)}")
    on_log(f"target_surface: {brief.target_surface}")
    on_log(f"goal: {brief.goal}")
    on_log(f"confirmed_changes: {_join_log_items(brief.in_scope[:4])}")
    on_log(f"out_of_scope: {_join_log_items(finalized_brief.out_of_scope[:4])}")
    on_log(f"refine_check: {'passed' if verify.ok else 'failed'}")
    if verify.failure_type:
        on_log(f"refine_check_failure: {verify.failure_type}")
    on_log(f"local_repair_count: {verify.repair_attempts}")

    return RefineEngineResult(
        status="refined",
        refined_markdown=refined_markdown,
    )


def _write_temp_file(temp_dir: str, name: str, payload: str | dict[str, object]):
    from pathlib import Path

    path = Path(temp_dir) / name
    if isinstance(payload, dict):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(payload.rstrip() + "\n", encoding="utf-8")
    return path


def _join_log_items(items: list[str]) -> str:
    return ", ".join(items) if items else "无"

from __future__ import annotations

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
    # refine 新主流程：
    # 1. 读取 Input 产物
    # 2. 解析“人工提炼范围”模板
    # 3. 生成规则版 brief draft + source excerpt
    # 4. local 直接渲染，native 交给 AGENT_MODE 读写模板
    # 5. 产出最终 markdown 与 verify 结果
    prepared = prepare_refine_input(task_dir, task_meta)
    if not prepared.source_content.strip():
        raise ValueError("prd.source.md 为空，无法执行 refine")

    manual_extract = parse_manual_extract(prepared.supplement)
    brief = build_refine_brief(prepared, manual_extract)
    source_excerpt = build_source_excerpt(prepared, brief)

    manual_extract_payload = manual_extract.to_payload()
    brief_draft_payload = brief.to_payload()
    # 这三个中间产物就是 agent 的全部输入，便于复现和排查。
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
    diagnosis_payload = {
        "severity": "passed" if verify.ok else "failed",
        "failure_type": verify.failure_type,
        "next_action": "",
    }

    on_log("refine_mode: manual_first")
    on_log(f"manual_scope_count: {len(manual_extract.scope)}")
    on_log(f"manual_change_points_count: {len(manual_extract.change_points)}")
    on_log(f"brief_target_surface: {brief.target_surface}")
    on_log(f"brief_goal: {brief.goal}")
    on_log(f"brief_in_scope: {', '.join(brief.in_scope[:4]) if brief.in_scope else '无'}")
    on_log(f"brief_out_of_scope: {', '.join(finalized_brief.out_of_scope[:4]) if finalized_brief.out_of_scope else '无'}")
    on_log(f"verify_ok: {'true' if verify.ok else 'false'}")
    on_log(f"repair_attempts: {verify.repair_attempts}")
    on_log(f"diagnosis: severity={diagnosis_payload.get('severity') or ''} failure_type={diagnosis_payload.get('failure_type') or '-'} next_action={diagnosis_payload.get('next_action') or ''}")

    return RefineEngineResult(
        status="refined",
        refined_markdown=refined_markdown,
        skills_used=settings.refine_executor.strip().lower() == "native",
        selected_skill_ids=["agent_refine"] if settings.refine_executor.strip().lower() == "native" else [],
        intermediate_artifacts={},
    )


def _write_temp_file(temp_dir: str, name: str, payload: str | dict[str, object]):
    from pathlib import Path

    path = Path(temp_dir) / name
    if isinstance(payload, dict):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(payload.rstrip() + "\n", encoding="utf-8")
    return path

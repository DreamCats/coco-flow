from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.engines.shared.diagnostics import diagnosis_payload_from_verify, enrich_verify_payload

from .brief import (
    build_compat_intent_payload,
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
    artifacts: dict[str, str | dict[str, object]] = {
        "refine-manual-extract.json": manual_extract_payload,
        "refine-brief.draft.json": brief_draft_payload,
        "refine-source.excerpt.md": source_excerpt,
        "refine-brief.json": brief_draft_payload,
        "refine-intent.json": build_compat_intent_payload(prepared, brief),
    }

    manual_extract_path = prepared.task_dir / "refine-manual-extract.json"
    brief_draft_path = prepared.task_dir / "refine-brief.draft.json"
    source_excerpt_path = prepared.task_dir / "refine-source.excerpt.md"
    manual_extract_path.write_text(_json_dump(manual_extract_payload), encoding="utf-8")
    brief_draft_path.write_text(_json_dump(brief_draft_payload), encoding="utf-8")
    source_excerpt_path.write_text(source_excerpt.rstrip() + "\n", encoding="utf-8")

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
    verify_payload = enrich_verify_payload(stage="refine", verify_payload=verify.to_payload(), artifact="prd-refined.md")
    artifacts["refine-verify.json"] = verify_payload
    diagnosis_payload = diagnosis_payload_from_verify(
        stage="refine",
        verify_payload=verify_payload,
        artifact="prd-refined.md",
    )
    artifacts["refine-diagnosis.json"] = diagnosis_payload
    artifacts["refine-brief.json"] = finalized_brief.to_payload()
    artifacts["refine-intent.json"] = build_compat_intent_payload(prepared, finalized_brief)

    on_log("refine_mode: manual_first")
    on_log(f"manual_scope_count: {len(manual_extract.scope)}")
    on_log(f"manual_change_points_count: {len(manual_extract.change_points)}")
    on_log(f"brief_target_surface: {brief.target_surface}")
    on_log(f"brief_goal: {brief.goal}")
    on_log(f"brief_in_scope: {', '.join(brief.in_scope[:4]) if brief.in_scope else '无'}")
    on_log(f"brief_out_of_scope: {', '.join(finalized_brief.out_of_scope[:4]) if finalized_brief.out_of_scope else '无'}")
    on_log(f"verify_ok: {'true' if verify.ok else 'false'}")
    on_log(f"diagnosis: severity={diagnosis_payload.get('severity') or ''} failure_type={diagnosis_payload.get('failure_type') or '-'} next_action={diagnosis_payload.get('next_action') or ''}")

    return RefineEngineResult(
        status="refined",
        refined_markdown=refined_markdown,
        skills_used=settings.refine_executor.strip().lower() == "native",
        selected_skill_ids=["agent_refine"] if settings.refine_executor.strip().lower() == "native" else [],
        intermediate_artifacts=artifacts,
    )


def _json_dump(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

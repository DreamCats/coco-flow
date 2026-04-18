from __future__ import annotations

from coco_flow.config import Settings

from .generate import generate_refine
from .intent import extract_native_refine_intent, extract_refine_intent
from .knowledge import build_refine_query, read_selected_knowledge, shortlist_refine_knowledge
from .models import EXECUTOR_NATIVE, RefineEngineResult, RefineIntent, RefinePreparedInput
from .source import prepare_refine_input


def run_refine_engine(
    task_dir,
    task_meta: dict[str, object],
    settings: Settings,
    on_log,
) -> RefineEngineResult:
    prepared = prepare_refine_input(task_dir, task_meta)
    if not prepared.source_content.strip():
        raise ValueError("prd.source.md 为空，无法执行 refine")

    intent = extract_refine_intent(prepared)
    intent_payload = intent.to_payload() | {"extraction_mode": "rule"}
    if settings.refine_executor.strip().lower() == EXECUTOR_NATIVE:
        intent, intent_payload = maybe_extract_native_intent(prepared, settings, on_log, fallback=intent)
    on_log(f"intent_goal: {intent.goal}")
    on_log(f"intent_terms: {', '.join(intent.terms[:8]) if intent.terms else '无'}")

    artifacts: dict[str, str | dict[str, object]] = {
        "refine-intent.json": intent_payload,
    }

    query_payload = build_refine_query(prepared, intent)
    artifacts["refine-query.json"] = query_payload
    on_log(f"query_terms: {', '.join([str(item) for item in query_payload.get('terms', [])][:8]) if query_payload.get('terms') else '无'}")

    selected_documents, selection = shortlist_refine_knowledge(
        prepared=prepared,
        intent=intent,
        settings=settings,
        on_log=on_log,
    )
    artifacts["refine-knowledge-selection.json"] = selection.to_payload()
    on_log(f"knowledge_candidates: {len(selection.candidates)}")
    on_log(f"selected_knowledge_ids: {', '.join(selection.selected_ids) if selection.selected_ids else '无'}")

    knowledge_read = read_selected_knowledge(
        prepared=prepared,
        intent=intent,
        selected_documents=selected_documents,
        settings=settings,
        on_log=on_log,
    )
    if knowledge_read.markdown.strip():
        artifacts["refine-knowledge-read.md"] = knowledge_read.markdown

    result = generate_refine(
        prepared=prepared,
        intent=intent,
        knowledge_read=knowledge_read,
        settings=settings,
        artifacts=artifacts,
        on_log=on_log,
    )
    return result


def maybe_extract_native_intent(
    prepared: RefinePreparedInput,
    settings: Settings,
    on_log,
    *,
    fallback: RefineIntent,
) -> tuple[RefineIntent, dict[str, object]]:
    try:
        intent = extract_native_refine_intent(prepared, settings)
        on_log("intent_extraction_mode: llm")
        return intent, intent.to_payload() | {"extraction_mode": "llm"}
    except ValueError as error:
        on_log(f"native_intent_fallback: {error}")
        on_log("intent_extraction_mode: rule_fallback")
        return fallback, fallback.to_payload() | {"extraction_mode": "rule_fallback", "fallback_reason": str(error)}

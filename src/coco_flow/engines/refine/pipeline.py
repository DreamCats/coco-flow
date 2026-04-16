from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.engines.business_memory import load_business_memory

from .generate import generate_local_refine, generate_native_refine, generate_pending_refine
from .intent import extract_native_refine_intent, extract_refine_intent
from .knowledge import build_refine_knowledge_brief
from .models import EXECUTOR_LOCAL, EXECUTOR_NATIVE, RefineEngineResult, RefineIntent, RefinePreparedInput
from .source import build_pending_refined_content, is_pending_lark_source, prepare_refine_input


def run_refine_engine(
    task_dir,
    task_meta: dict[str, object],
    settings: Settings,
    on_log,
) -> RefineEngineResult:
    prepared = prepare_refine_input(task_dir, task_meta)
    executor = settings.refine_executor.strip().lower()
    memory = load_business_memory(prepared.repo_root)
    on_log(f"context_mode: {memory.mode}")
    on_log(f"business_memory_provider: {memory.provider}")
    on_log(f"business_memory_used: {str(memory.used).lower()}")
    on_log(f"business_memory_documents: {len(memory.documents)}")
    if memory.documents:
        on_log("business_memory_files: " + ", ".join(document.name for document in memory.documents[:6]))
    if memory.risk_flags:
        on_log("business_memory_risk_flags: " + ", ".join(memory.risk_flags))

    intent = extract_refine_intent(prepared)
    intent_payload = intent.to_payload() | {"extraction_mode": "rule"}
    if executor == EXECUTOR_NATIVE and prepared.source_content.strip():
        native_intent, native_payload = maybe_extract_native_intent(prepared, settings, on_log, fallback=intent)
        intent = native_intent
        intent_payload = native_payload
    artifacts: dict[str, str | dict[str, object]] = {
        "refine-intent.json": intent_payload,
    }
    on_log(f"intent_goal: {intent.goal or prepared.title}")
    on_log(f"intent_key_terms: {len(intent.key_terms)}")
    if intent.key_terms:
        on_log("intent_terms: " + ", ".join(intent.key_terms[:8]))

    brief = build_refine_knowledge_brief(memory, intent, prepared, settings)
    if brief.markdown:
        artifacts["refine-knowledge-brief.md"] = brief.markdown
        artifacts["refine-knowledge-selection.json"] = brief.selection_payload
        on_log(f"knowledge_brief_documents: {len(brief.matched_documents)}")
        on_log("knowledge_brief_files: " + ", ".join(brief.matched_documents))
        if brief.selected_knowledge_ids:
            on_log("selected_knowledge_ids: " + ", ".join(brief.selected_knowledge_ids))
    else:
        on_log("knowledge_brief_documents: 0")
    if brief.selection_payload.get("candidates"):
        on_log(f"knowledge_candidates: {len(brief.selection_payload['candidates'])}")

    if prepared.source_type == "lark_doc" and is_pending_lark_source(prepared.source_meta, prepared.source_content):
        on_log("pending_refine: true")
        if prepared.source_meta.get("fetch_error"):
            on_log(f"fetch_error: {prepared.source_meta.get('fetch_error')}")
        on_log("status: initialized")
        return generate_pending_refine(
            prepared,
            memory,
            build_pending_refined_content(
                task_id=prepared.task_id,
                title=prepared.title,
                source_url=str(prepared.source_meta.get("url") or ""),
                doc_token=str(prepared.source_meta.get("doc_token") or ""),
                fetch_error=str(prepared.source_meta.get("fetch_error") or ""),
                fetch_error_code=str(prepared.source_meta.get("fetch_error_code") or ""),
            ),
            artifacts,
        )

    if executor == EXECUTOR_NATIVE:
        try:
            return generate_native_refine(
                prepared,
                settings,
                memory,
                intent,
                brief.markdown,
                artifacts,
                on_log,
            )
        except ValueError as error:
            on_log(f"native_refine_error: {error}")
            return generate_local_refine(prepared, memory, intent, brief.markdown, artifacts, on_log)
    if executor == EXECUTOR_LOCAL:
        return generate_local_refine(prepared, memory, intent, brief.markdown, artifacts, on_log)
    raise ValueError(f"unknown refine executor: {settings.refine_executor}")


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
        on_log(f"native_intent_error: {error}")
        on_log("intent_extraction_mode: rule_fallback")
        return fallback, fallback.to_payload() | {"extraction_mode": "rule_fallback", "fallback_reason": str(error)}

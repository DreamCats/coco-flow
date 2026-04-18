from __future__ import annotations

import json
import re

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.refine import build_refine_generate_prompt, build_refine_verify_prompt

from .models import EXECUTOR_NATIVE, RefineEngineResult, RefineIntent, RefineKnowledgeRead, RefinePreparedInput, STATUS_REFINED

_REQUIRED_SECTIONS = (
    "核心诉求",
    "改动范围",
    "风险提示",
    "讨论点",
    "边界与非目标",
)
_HEADING_RE = re.compile(r"(?m)^#\s+PRD Refined\s*$")


def generate_refine(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    knowledge_read: RefineKnowledgeRead,
    settings: Settings,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> RefineEngineResult:
    if settings.refine_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            return generate_native_refine(
                prepared=prepared,
                intent=intent,
                knowledge_read=knowledge_read,
                settings=settings,
                artifacts=artifacts,
                on_log=on_log,
            )
        except ValueError as error:
            on_log(f"native_refine_fallback: {error}")
    return generate_local_refine(
        prepared=prepared,
        intent=intent,
        knowledge_read=knowledge_read,
        artifacts=artifacts,
        on_log=on_log,
    )


def generate_local_refine(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    knowledge_read: RefineKnowledgeRead,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> RefineEngineResult:
    on_log("generate_mode: local")
    refined = build_local_refined_markdown(prepared=prepared, intent=intent, knowledge_read=knowledge_read)
    on_log(f"status: {STATUS_REFINED}")
    return RefineEngineResult(
        status=STATUS_REFINED,
        refined_markdown=refined,
        knowledge_used=bool(knowledge_read.selected_ids),
        selected_knowledge_ids=knowledge_read.selected_ids,
        intermediate_artifacts=artifacts,
    )


def generate_native_refine(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    knowledge_read: RefineKnowledgeRead,
    settings: Settings,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> RefineEngineResult:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    prompt = build_refine_generate_prompt(
        title=prepared.title,
        source_markdown=prepared.source_markdown,
        supplement=prepared.supplement,
        intent_payload=intent.to_payload(),
        knowledge_read_markdown=knowledge_read.markdown,
    )
    on_log(f"generate_prompt_start: timeout={settings.native_query_timeout}")
    raw = client.run_prompt_only(prompt, settings.native_query_timeout, fresh_session=True)
    refined = extract_refined_content(raw)
    if not refined:
        raise ValueError("native_refine_returned_empty_content")
    on_log(f"generate_prompt_ok: {len(raw)} bytes")

    verify_raw = client.run_prompt_only(
        build_refine_verify_prompt(
            title=prepared.title,
            source_markdown=prepared.source_markdown,
            supplement=prepared.supplement,
            refined_markdown=refined,
        ),
        settings.native_query_timeout,
        fresh_session=True,
    )
    verify_payload = parse_refine_verify_output(verify_raw)
    artifacts["refine-verify.json"] = verify_payload
    if not bool(verify_payload.get("ok")):
        issues = verify_payload.get("issues") or []
        issue_text = "; ".join(str(item) for item in issues[:3]) if isinstance(issues, list) else "unknown"
        raise ValueError(f"native_refine_verify_failed: {issue_text}")

    on_log(f"status: {STATUS_REFINED}")
    return RefineEngineResult(
        status=STATUS_REFINED,
        refined_markdown=refined.rstrip() + "\n",
        knowledge_used=bool(knowledge_read.selected_ids),
        selected_knowledge_ids=knowledge_read.selected_ids,
        intermediate_artifacts=artifacts,
    )


def extract_refined_content(raw: str) -> str:
    content = raw.strip()
    if not content or not _HEADING_RE.search(content):
        return ""
    return content.rstrip() + "\n"


def parse_refine_verify_output(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid_verify_json: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("verify_output_is_not_object")
    return {
        "ok": bool(payload.get("ok")),
        "issues": [str(item) for item in payload.get("issues", []) if str(item).strip()],
        "missing_sections": [str(item) for item in payload.get("missing_sections", []) if str(item).strip()],
        "reason": str(payload.get("reason") or ""),
    }


def build_local_refined_markdown(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    knowledge_read: RefineKnowledgeRead,
) -> str:
    change_scope = intent.change_points or [intent.goal]
    risks = intent.risks_seed or _extract_hint_lines(knowledge_read.markdown, "风险") or ["当前未识别到明确高风险项，建议人工复核。"]
    discussions = intent.discussion_seed or ["[建议补充] 当前输入信息仍偏少，建议补充业务口径和确认结论。"]
    boundaries = intent.boundary_seed or ["仅围绕当前输入明确提到的需求范围推进，不默认扩展到相邻能力。"]
    return (
        "# PRD Refined\n\n"
        "## 核心诉求\n"
        f"{_render_list([intent.goal])}\n\n"
        "## 改动范围\n"
        f"{_render_list(change_scope)}\n\n"
        "## 风险提示\n"
        f"{_render_list(risks)}\n\n"
        "## 讨论点\n"
        f"{_render_list(_ensure_discussion_tags(discussions))}\n\n"
        "## 边界与非目标\n"
        f"{_render_list(boundaries)}\n"
    )


def _render_list(items: list[str]) -> str:
    normalized = [item.strip() for item in items if item.strip()]
    return "\n".join(f"- {item}" for item in normalized) if normalized else "- 无"


def _ensure_discussion_tags(items: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in items:
        stripped = item.strip()
        if not stripped:
            continue
        if stripped.startswith("[待确认]") or stripped.startswith("[建议补充]"):
            normalized.append(stripped)
        else:
            normalized.append(f"[待确认] {stripped}")
    return normalized


def _extract_hint_lines(markdown: str, title: str) -> list[str]:
    if not markdown.strip():
        return []
    sections = _split_markdown_sections(markdown)
    return [line.strip("- ").strip() for line in sections.get(title, "").splitlines() if line.strip()]


def _split_markdown_sections(content: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = ""
    current_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(current_lines).strip()
            current = line.removeprefix("## ").strip()
            current_lines = []
            continue
        if current:
            current_lines.append(line)
    if current:
        sections[current] = "\n".join(current_lines).strip()
    return sections

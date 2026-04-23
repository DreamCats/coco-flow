from __future__ import annotations

import json
import re
from json import JSONDecodeError, JSONDecoder
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.refine import (
    build_refine_generate_agent_prompt,
    build_refine_template_markdown,
    build_refine_verify_agent_prompt,
    build_refine_verify_template_json,
)

from .models import EXECUTOR_NATIVE, RefineEngineResult, RefineIntent, RefineSkillsRead, RefinePreparedInput, STATUS_REFINED

_REQUIRED_SECTIONS = (
    "需求概述",
    "具体变更点",
    "验收标准",
    "边界与非目标",
    "待确认项",
)
_HEADING_RE = re.compile(r"(?m)^#\s+需求确认书\s*$")


def generate_refine(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    skills_read: RefineSkillsRead,
    settings: Settings,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> RefineEngineResult:
    if settings.refine_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            return generate_native_refine(
                prepared=prepared,
                intent=intent,
                skills_read=skills_read,
                settings=settings,
                artifacts=artifacts,
                on_log=on_log,
            )
        except ValueError as error:
            on_log(f"native_refine_fallback: {error}")
    return generate_local_refine(
        prepared=prepared,
        intent=intent,
        skills_read=skills_read,
        artifacts=artifacts,
        on_log=on_log,
    )


def generate_local_refine(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    skills_read: RefineSkillsRead,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> RefineEngineResult:
    on_log("generate_mode: local")
    refined = build_local_refined_markdown(prepared=prepared, intent=intent, skills_read=skills_read)
    on_log(f"status: {STATUS_REFINED}")
    return RefineEngineResult(
        status=STATUS_REFINED,
        refined_markdown=refined,
        skills_used=bool(skills_read.selected_skill_ids),
        selected_skill_ids=skills_read.selected_skill_ids,
        intermediate_artifacts=artifacts,
    )


def generate_native_refine(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    skills_read: RefineSkillsRead,
    settings: Settings,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> RefineEngineResult:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_refine_template(prepared.task_dir)
    try:
        prompt = build_refine_generate_agent_prompt(
            title=prepared.title,
            source_markdown=prepared.source_markdown,
            supplement=prepared.supplement,
            intent_payload=intent.to_payload(),
            skills_read_markdown=skills_read.markdown,
            template_path=str(template_path),
        )
        on_log(f"generate_agent_start: timeout={settings.native_query_timeout}")
        agent_reply = client.run_agent(
            prompt,
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        on_log(f"generate_agent_reply: {_preview_text(agent_reply)}")
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
    finally:
        if template_path.exists():
            template_path.unlink()

    refined = extract_refined_content(raw)
    if not refined:
        on_log(f"generate_template_preview: {_preview_text(raw)}")
        missing_section = _find_unfilled_template_section(raw)
        if missing_section:
            raise ValueError(f"native_refine_agent_left_placeholder_in_section: {missing_section}")
        raise ValueError("native_refine_agent_did_not_write_valid_template")
    on_log(f"generate_agent_ok: {len(raw)} bytes")

    verify_template_path = _write_verify_template(prepared.task_dir)
    try:
        verify_reply = client.run_agent(
            build_refine_verify_agent_prompt(
                title=prepared.title,
                source_markdown=prepared.source_markdown,
                supplement=prepared.supplement,
                refined_markdown=refined,
                template_path=str(verify_template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        verify_raw = verify_template_path.read_text(encoding="utf-8") if verify_template_path.exists() else ""
        _ = verify_reply
    finally:
        if verify_template_path.exists():
            verify_template_path.unlink()
    on_log(f"verify_raw_preview: {_preview_text(verify_raw)}")
    try:
        verify_payload = parse_refine_verify_output(verify_raw)
    except ValueError as error:
        raise ValueError(f"invalid_verify_json: {error}") from error
    artifacts["refine-verify.json"] = verify_payload
    if not bool(verify_payload.get("ok")):
        issues = verify_payload.get("issues") or []
        issue_text = "; ".join(str(item) for item in issues[:3]) if isinstance(issues, list) else "unknown"
        raise ValueError(f"native_refine_verify_failed: {issue_text}")

    on_log(f"status: {STATUS_REFINED}")
    return RefineEngineResult(
        status=STATUS_REFINED,
        refined_markdown=refined.rstrip() + "\n",
        skills_used=bool(skills_read.selected_skill_ids),
        selected_skill_ids=skills_read.selected_skill_ids,
        intermediate_artifacts=artifacts,
    )


def extract_refined_content(raw: str) -> str:
    content = raw.strip()
    if not content:
        return ""
    if _looks_like_unfilled_template(content):
        return ""
    if _HEADING_RE.search(content):
        return content.rstrip() + "\n"
    if _looks_like_refined_markdown(content):
        return "# PRD Refined\n\n" + content.rstrip() + "\n"
    return ""


def parse_refine_verify_output(raw: str) -> dict[str, object]:
    payload = _parse_json_object_tolerant(raw)
    if not isinstance(payload, dict):
        raise ValueError("verify_output_is_not_object")
    return _normalize_verify_payload(payload)


def _parse_json_object_tolerant(raw: str) -> object:
    normalized = raw.strip()
    if not normalized:
        raise ValueError("verify_output_is_empty")
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", normalized, re.S)
    if fence_match:
        normalized = fence_match.group(1).strip()
    try:
        return json.loads(normalized)
    except JSONDecodeError:
        pass
    decoder = JSONDecoder()
    for index, char in enumerate(normalized):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(normalized[index:])
            return payload
        except JSONDecodeError:
            continue
    raise ValueError("verify_output_has_no_parseable_json_object")


def _normalize_verify_payload(payload: dict[str, object]) -> dict[str, object]:
    if _payload_has_fill_marker(payload):
        raise ValueError("verify_output_contains_fill_marker")
    return {
        "ok": bool(payload.get("ok")),
        "issues": [str(item) for item in payload.get("issues", []) if str(item).strip()],
        "missing_sections": [str(item) for item in payload.get("missing_sections", []) if str(item).strip()],
        "reason": str(payload.get("reason") or ""),
    }


def _preview_text(raw: str, limit: int = 160) -> str:
    normalized = " ".join(raw.strip().split())
    if len(normalized) <= limit:
        return normalized or "(empty)"
    return normalized[:limit] + "..."


def _write_refine_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".refine-template-",
        suffix=".md",
        delete=False,
    ) as handle:
        handle.write(build_refine_template_markdown())
        handle.flush()
        return Path(handle.name)


def _write_verify_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".refine-verify-",
        suffix=".json",
        delete=False,
    ) as handle:
        handle.write(build_refine_verify_template_json())
        handle.flush()
        return Path(handle.name)


def build_local_refined_markdown(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    skills_read: RefineSkillsRead,
) -> str:
    change_scope = intent.change_points or [intent.goal]
    acceptance_criteria = (
        intent.acceptance_criteria
        or _extract_hint_lines(skills_read.markdown, "验收")
        or [f"当需求「{intent.goal}」落地后，应该满足预期业务行为且不引入额外回归。"]
    )
    boundaries = intent.boundary_seed or ["仅围绕当前输入明确提到的需求范围推进，不默认扩展到相邻能力。"]
    open_questions = _build_confirmation_items(
        discussions=intent.discussion_seed,
        risks=intent.risks_seed,
        change_scope=change_scope,
    )
    return (
        "# 需求确认书\n\n"
        "## 需求概述\n"
        f"{_render_paragraph(intent.goal)}\n\n"
        "## 具体变更点\n"
        f"{_render_list(_render_change_points(change_scope))}\n\n"
        "## 验收标准\n"
        f"{_render_list(_render_acceptance_criteria(acceptance_criteria))}\n\n"
        "## 边界与非目标\n"
        f"{_render_list(boundaries)}\n\n"
        "## 待确认项\n"
        f"{_render_list(open_questions)}\n"
    )


def _render_list(items: list[str]) -> str:
    normalized = [item.strip() for item in items if item.strip()]
    return "\n".join(f"- {item}" for item in normalized) if normalized else "- 无"


def _render_paragraph(text: str) -> str:
    normalized = text.strip()
    return normalized or "当前需求目标待进一步补充。"


def _render_change_points(items: list[str]) -> list[str]:
    rendered: list[str] = []
    for item in items:
        current = item.strip()
        if not current:
            continue
        if all(tag in current for tag in ("场景：", "当前行为：", "期望行为：")):
            rendered.append(current)
            continue
        rendered.append(f"场景：{current}；当前行为：待结合现有逻辑进一步确认；期望行为：{current}")
    return rendered


def _render_acceptance_criteria(items: list[str]) -> list[str]:
    rendered: list[str] = []
    for item in items:
        current = item.strip()
        if not current:
            continue
        if "当" in current and "时" in current:
            rendered.append(current)
            continue
        rendered.append(f"当执行本次需求时，应该满足：{current}")
    return rendered


def _build_confirmation_items(*, discussions: list[str], risks: list[str], change_scope: list[str]) -> list[str]:
    seeds = discussions or []
    if not seeds:
        seeds = risks[:2]
    if not seeds:
        seeds = ["当前输入信息仍偏少，需确认业务口径和最终验收边界。"]
    impact_hint = change_scope[0].strip() if change_scope else "本次改动范围与验收口径"
    items: list[str] = []
    for seed in seeds[:4]:
        current = seed.strip()
        if not current:
            continue
        items.append(f"问题：{current}；当前假设：待确认后再锁定最终口径；影响范围：{impact_hint}")
    return items or [f"问题：当前信息不足以完全锁定实现边界；当前假设：先按最小范围推进；影响范围：{impact_hint}"]


def _extract_hint_lines(markdown: str, title: str) -> list[str]:
    if not markdown.strip():
        return []
    sections = _split_markdown_sections(markdown)
    return [line.strip("- ").strip() for line in sections.get(title, "").splitlines() if line.strip()]


def _normalize_risks(items: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in items:
        current = item.strip()
        if not current:
            continue
        if _is_background_like_risk(current):
            continue
        if "可能" not in current and "风险" not in current and "误" not in current and "影响" not in current:
            current = f"{current}，需要确认是否会影响现有状态判断。"
        normalized.append(current)
    return normalized


def _is_background_like_risk(text: str) -> bool:
    background_hints = ("背景", "当前", "现状", "目前", "已有", "有时", "会导致")
    return any(hint in text for hint in background_hints) and "可能" not in text and "误" not in text


def _looks_like_refined_markdown(content: str) -> bool:
    headings = [f"## {section}" for section in _REQUIRED_SECTIONS]
    return all(heading in content for heading in headings)


def _looks_like_unfilled_template(content: str) -> bool:
    placeholders = (
        "\n- 待补充",
        "\n- 问题：待补充；当前假设：待补充；影响范围：待补充",
    )
    return any(marker in content for marker in placeholders)


def _find_unfilled_template_section(content: str) -> str:
    if not content.strip():
        return ""
    sections = _split_markdown_sections(content)
    for section in _REQUIRED_SECTIONS:
        body = sections.get(section, "")
        if "待补充" in body:
            return section
    return ""


def _payload_has_fill_marker(value: object) -> bool:
    if isinstance(value, str):
        return "__FILL__" in value
    if isinstance(value, list):
        return any(_payload_has_fill_marker(item) for item in value)
    if isinstance(value, dict):
        return any(_payload_has_fill_marker(item) for item in value.values())
    return False


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

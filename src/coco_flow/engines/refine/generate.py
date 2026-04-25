from __future__ import annotations

# 本文件负责生成和校验 `prd-refined.md`：local 路径用规则渲染，native 路径
# 让 agent 在模板内润色，并用本地校验/修复保证不偏离人工提炼范围。

from dataclasses import dataclass
import json
import re
import tempfile
from json import JSONDecodeError, JSONDecoder
from pathlib import Path

from coco_flow.clients import AgentSessionHandle, CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.refine import (
    build_refine_bootstrap_prompt,
    build_refine_generate_agent_prompt,
    build_refine_verify_agent_prompt,
)

from .models import EXECUTOR_NATIVE, RefineBrief, RefinePreparedInput, RefineVerifyResult

_REQUIRED_SECTIONS = (
    "需求概述",
    "具体变更点",
    "验收标准",
    "边界与非目标",
    "待确认项",
)
_PLACEHOLDER_HINTS = ("待补充", "如无可写", "请写这里", "[必填]")
_MAX_LOCAL_REPAIR_ATTEMPTS = 2


@dataclass(frozen=True)
class _PathChange:
    raw: str
    group: str
    state: str
    value: str


def generate_refined_markdown(
    *,
    prepared: RefinePreparedInput,
    brief: RefineBrief,
    manual_extract_path: Path,
    brief_draft_path: Path,
    source_excerpt_path: Path,
    settings: Settings,
    on_log,
) -> tuple[str, RefineVerifyResult]:
    # local/native 共用同一份需求要点，区别只在最终 Markdown 的生成方式。
    # local 强调稳定可控；native 只做表达润色，不能扩大人工提炼范围。
    if settings.refine_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            return _generate_native_refined_markdown(
                prepared=prepared,
                brief=brief,
                manual_extract_path=manual_extract_path,
                brief_draft_path=brief_draft_path,
                source_excerpt_path=source_excerpt_path,
                settings=settings,
                on_log=on_log,
            )
        except ValueError as error:
            on_log(f"native_refine_fallback: {error}")
    refined_markdown = render_refined_markdown(brief)
    refined_markdown, verify = _verify_with_local_repair(brief, refined_markdown, on_log)
    on_log("generation_path: local_renderer")
    return refined_markdown, verify


def render_refined_markdown(brief: RefineBrief) -> str:
    overview_lines = [brief.goal]
    if brief.gating_conditions:
        overview_lines.extend(["", "前置条件：", *_render_bullets(brief.gating_conditions).splitlines()])
    boundary_items = _dedupe_boundary_items([*brief.out_of_scope, *[f"边界检查：{item}" for item in brief.edge_cases]])
    open_questions = brief.open_questions or ["当前无额外待确认项。"]
    return (
        "# 需求确认书\n\n"
        "## 需求概述\n"
        f"{_render_paragraph(overview_lines)}\n\n"
        "## 具体变更点\n"
        f"{_render_change_scope(brief)}\n\n"
        "## 验收标准\n"
        f"{_render_acceptance_criteria(brief)}\n\n"
        "## 边界与非目标\n"
        f"{_render_bullets(boundary_items)}\n\n"
        "## 待确认项\n"
        f"{_render_bullets(open_questions)}\n"
    )


def verify_refine_output(brief: RefineBrief, refined_markdown: str) -> RefineVerifyResult:
    issues: list[str] = []
    missing_sections = [section for section in _REQUIRED_SECTIONS if f"## {section}" not in refined_markdown]
    if not brief.in_scope:
        issues.append("refine brief 缺少 in_scope。")
    if not brief.acceptance_criteria:
        issues.append("refine brief 缺少 acceptance_criteria。")
    if not brief.out_of_scope:
        issues.append("refine brief 缺少 out_of_scope。")
    if missing_sections:
        issues.append("refined markdown 缺少必填章节。")
    if any(hint in refined_markdown for hint in _PLACEHOLDER_HINTS):
        issues.append("refined markdown 仍包含模板占位语。")
    acceptance_section = _extract_markdown_section(refined_markdown, "验收标准")
    if "未纳入范围" in acceptance_section or "不扩大到" in acceptance_section:
        issues.append("验收标准混入了边界说明。")
    change_section = _extract_markdown_section(refined_markdown, "具体变更点")
    if _parse_path_changes(brief.in_scope) and "| 状态 | 展示内容 |" not in change_section:
        issues.append("具体变更点应使用分组表格。")
    for condition in brief.gating_conditions:
        if not _contains_condition(change_section, condition):
            issues.append(f"具体变更点缺少适用条件：{condition}")
            break
    if _parse_path_changes(brief.in_scope) and "按上表展示" not in acceptance_section:
        issues.append("验收标准应按分组表格压缩表达。")
    for item in brief.in_scope:
        if not _change_item_present(item, refined_markdown):
            issues.append(f"缺少 in_scope 叶子项：{item}")
            break
    ok = not issues
    reason = "local verify passed" if ok else "local verify failed"
    return RefineVerifyResult(
        ok=ok,
        issues=issues,
        missing_sections=missing_sections,
        reason=reason,
        failure_type=_classify_refine_failure(issues, missing_sections),
    )


def parse_refine_verify_output(raw: str) -> dict[str, object]:
    payload = _parse_json_object_tolerant(raw)
    if not isinstance(payload, dict):
        raise ValueError("verify_output_is_not_object")
    return {
        "ok": bool(payload.get("ok")),
        "issues": [str(item) for item in payload.get("issues", []) if str(item).strip()],
        "missing_sections": [str(item) for item in payload.get("missing_sections", []) if str(item).strip()],
        "reason": str(payload.get("reason") or ""),
        "failure_type": str(payload.get("failure_type") or ""),
    }


def _generate_native_refined_markdown(
    *,
    prepared: RefinePreparedInput,
    brief: RefineBrief,
    manual_extract_path: Path,
    brief_draft_path: Path,
    source_excerpt_path: Path,
    settings: Settings,
    on_log,
) -> tuple[str, RefineVerifyResult]:
    # native 路径不让模型从零总结，而是先写好模板，再让 agent 在模板内润色。
    # 这样可以保留 LLM 的表达能力，同时把范围控制权留在人工提炼和本地规则里。
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_refine_template(prepared.task_dir, render_refined_markdown(brief))
    generated_path: Path | None = None
    generate_session: AgentSessionHandle | None = None
    try:
        on_log("generation_path: native_agent")
        on_log("session_role: refine_generate")
        generate_session = client.new_agent_session(
            query_timeout=settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            role="refine_generate",
        )
        on_log("bootstrap_prompt: true role=refine_generate")
        _prompt_agent_session_logged(
            client,
            generate_session,
            build_refine_bootstrap_prompt(),
            stage="bootstrap",
            on_log=on_log,
        )
        _prompt_agent_session_logged(
            client,
            generate_session,
            build_refine_generate_agent_prompt(
                manual_extract_path=str(manual_extract_path),
                brief_draft_path=str(brief_draft_path),
                source_excerpt_path=str(source_excerpt_path),
                template_path=str(template_path),
            ),
            stage="generate",
            on_log=on_log,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        refined_markdown = _extract_refined_markdown(raw)
        # verify agent 需要读生成稿；用隐藏临时稿承接，结束后立即删除。
        generated_path = prepared.task_dir / ".refine-generated.md"
        generated_path.write_text(refined_markdown, encoding="utf-8")
        repaired_markdown, local_verify = _verify_with_local_repair(brief, refined_markdown, on_log)
        native_verify: RefineVerifyResult | None = None
        try:
            native_verify = _run_native_verify(
                client=client,
                brief_draft_path=brief_draft_path,
                refined_markdown_path=generated_path,
                settings=settings,
                cwd=prepared.task_dir,
                on_log=on_log,
            )
        except ValueError as error:
            on_log(f"native_verify_unavailable: {error}")
        if local_verify.ok:
            if local_verify.repair_attempts:
                on_log(f"local_repair_applied: attempts={local_verify.repair_attempts}")
            return repaired_markdown, local_verify
        _write_native_refine_failure_artifacts(prepared.task_dir, refined_markdown, local_verify)
        if native_verify is not None and not native_verify.ok:
            raise ValueError(f"native_refine_verify_failed: {native_verify.reason or native_verify.issues}; local={local_verify.issues}")
        raise ValueError(f"native_refine_local_verify_failed: {local_verify.issues}")
    finally:
        if generate_session is not None:
            _close_agent_session_quietly(client, generate_session, on_log)
        if template_path.exists():
            template_path.unlink()
        if generated_path and generated_path.exists():
            generated_path.unlink()


def _run_native_verify(
    *,
    client: CocoACPClient,
    brief_draft_path: Path,
    refined_markdown_path: Path,
    settings: Settings,
    cwd: Path,
    on_log,
) -> RefineVerifyResult:
    template_path = _write_verify_template(cwd)
    verify_session: AgentSessionHandle | None = None
    try:
        on_log("session_role: refine_verify")
        verify_session = client.new_agent_session(
            query_timeout=settings.native_query_timeout,
            cwd=str(cwd),
            role="refine_verify",
        )
        on_log("bootstrap_prompt: inline role=refine_verify")
        _prompt_agent_session_logged(
            client,
            verify_session,
            _join_prompts(
                build_refine_bootstrap_prompt(standalone=False),
                build_refine_verify_agent_prompt(
                    brief_draft_path=str(brief_draft_path),
                    refined_markdown_path=str(refined_markdown_path),
                    template_path=str(template_path),
                ),
            ),
            stage="verify",
            on_log=on_log,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        payload = parse_refine_verify_output(raw)
        return RefineVerifyResult(
            ok=bool(payload.get("ok")),
            issues=[str(item) for item in payload.get("issues", [])],
            missing_sections=[str(item) for item in payload.get("missing_sections", [])],
            reason=str(payload.get("reason") or ""),
            failure_type=str(payload.get("failure_type") or ""),
        )
    finally:
        if verify_session is not None:
            _close_agent_session_quietly(client, verify_session, on_log)
        if template_path.exists():
            template_path.unlink()


def _close_agent_session_quietly(client: CocoACPClient, handle: AgentSessionHandle, on_log) -> None:
    try:
        client.close_agent_session(handle)
    except Exception as error:
        on_log(f"session_close_warning: role={handle.role} error={error}")


def _prompt_agent_session_logged(
    client: CocoACPClient,
    handle: AgentSessionHandle,
    prompt: str,
    *,
    stage: str,
    on_log,
) -> str:
    on_log(f"agent_prompt_start: role={handle.role} stage={stage}")
    try:
        content = client.prompt_agent_session(handle, prompt)
    except Exception as error:
        on_log(f"agent_prompt_failed: role={handle.role} stage={stage} error={error}")
        raise
    on_log(f"agent_prompt_done: role={handle.role} stage={stage}")
    return content


def _join_prompts(*parts: str) -> str:
    return "\n\n---\n\n".join(part.strip() for part in parts if part.strip()).rstrip() + "\n"


def _write_native_refine_failure_artifacts(task_dir: Path, refined_markdown: str, verify: RefineVerifyResult) -> None:
    del verify
    (task_dir / "prd-refined.md").write_text(refined_markdown.rstrip() + "\n", encoding="utf-8")


def _verify_with_local_repair(brief: RefineBrief, refined_markdown: str, on_log) -> tuple[str, RefineVerifyResult]:
    verify = verify_refine_output(brief, refined_markdown)
    attempt = 0
    while not verify.ok and attempt < _MAX_LOCAL_REPAIR_ATTEMPTS:
        repaired_markdown, repair_notes = _repair_refined_markdown(brief, refined_markdown, verify)
        if repaired_markdown == refined_markdown:
            break
        attempt += 1
        on_log(f"refine_repair_attempt: {attempt} notes={', '.join(repair_notes) if repair_notes else '-'}")
        refined_markdown = repaired_markdown
        verify = verify_refine_output(brief, refined_markdown)
    verify.repair_attempts = attempt
    return refined_markdown, verify


def _repair_refined_markdown(
    brief: RefineBrief,
    refined_markdown: str,
    verify: RefineVerifyResult,
) -> tuple[str, list[str]]:
    notes: list[str] = []
    canonical = render_refined_markdown(brief)
    repaired = refined_markdown.rstrip() + "\n"

    for section in verify.missing_sections:
        repaired = _append_missing_section(repaired, section, _extract_markdown_section(canonical, section))
        notes.append(f"missing_section:{section}")

    for section in _REQUIRED_SECTIONS:
        section_body = _extract_markdown_section(repaired, section)
        if section_body and any(hint in section_body for hint in _PLACEHOLDER_HINTS):
            repaired = _replace_markdown_section(repaired, section, _extract_markdown_section(canonical, section))
            notes.append(f"placeholder:{section}")

    acceptance_section = _extract_markdown_section(repaired, "验收标准")
    if "未纳入范围" in acceptance_section or "不扩大到" in acceptance_section:
        repaired = _replace_markdown_section(
            repaired,
            "验收标准",
            _strip_boundary_acceptance_items(acceptance_section) or _extract_markdown_section(canonical, "验收标准"),
        )
        notes.append("acceptance_boundary_mixed")
    change_section = _extract_markdown_section(repaired, "具体变更点")
    if _parse_path_changes(brief.in_scope) and "| 状态 | 展示内容 |" not in change_section:
        repaired = _replace_markdown_section(repaired, "具体变更点", _extract_markdown_section(canonical, "具体变更点"))
        repaired = _replace_markdown_section(repaired, "验收标准", _extract_markdown_section(canonical, "验收标准"))
        notes.append("structured_change_scope_format")
        change_section = _extract_markdown_section(repaired, "具体变更点")
    if any(not _contains_condition(change_section, condition) for condition in brief.gating_conditions):
        repaired = _replace_markdown_section(repaired, "具体变更点", _extract_markdown_section(canonical, "具体变更点"))
        notes.append("gating_condition_missing")
    acceptance_section = _extract_markdown_section(repaired, "验收标准")
    if _parse_path_changes(brief.in_scope) and "按上表展示" not in acceptance_section:
        repaired = _replace_markdown_section(repaired, "验收标准", _extract_markdown_section(canonical, "验收标准"))
        notes.append("structured_acceptance_format")

    return repaired.rstrip() + "\n", notes


def _append_missing_section(markdown: str, section: str, body: str) -> str:
    if f"## {section}" in markdown:
        return markdown
    normalized_body = body.strip() or "- 无"
    return markdown.rstrip() + f"\n\n## {section}\n{normalized_body}\n"


def _replace_markdown_section(markdown: str, section: str, body: str) -> str:
    normalized_body = body.strip() or "- 无"
    pattern = rf"(?ms)^## {re.escape(section)}\n.*?(?=^## |\Z)"
    replacement = f"## {section}\n{normalized_body}\n\n"
    if re.search(pattern, markdown):
        return re.sub(pattern, lambda _match: replacement, markdown, count=1).rstrip() + "\n"
    return _append_missing_section(markdown, section, normalized_body)


def _strip_boundary_acceptance_items(section_body: str) -> str:
    lines: list[str] = []
    for line in section_body.splitlines():
        if "未纳入范围" in line or "不扩大到" in line:
            continue
        if line.strip():
            lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _classify_refine_failure(issues: list[str], missing_sections: list[str]) -> str:
    if missing_sections or any("缺少必填章节" in issue for issue in issues):
        return "missing_required_section"
    if any("模板占位" in issue for issue in issues):
        return "template_placeholder"
    if any("acceptance_criteria" in issue for issue in issues):
        return "missing_acceptance_criteria"
    if any("验收标准混入了边界说明" in issue for issue in issues):
        return "acceptance_boundary_mixed"
    if any("分组表格" in issue for issue in issues):
        return "change_scope_format"
    if any("具体变更点缺少适用条件" in issue for issue in issues):
        return "missing_gating_condition"
    if any("in_scope" in issue for issue in issues):
        return "missing_in_scope"
    if any("out_of_scope" in issue for issue in issues):
        return "missing_out_of_scope"
    return "refine_verify_failed" if issues else ""


def _write_refine_template(task_dir: Path, initial_markdown: str | None = None) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".refine-template-",
        suffix=".md",
        delete=False,
    ) as handle:
        handle.write((initial_markdown or _build_refine_template_markdown()).rstrip() + "\n")
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
        handle.write(_build_refine_verify_template_json())
        handle.flush()
        return Path(handle.name)


def _build_refine_template_markdown() -> str:
    return (
        "# 需求确认书\n\n"
        "## 需求概述\n"
        "- 待补充\n\n"
        "## 具体变更点\n"
        "- 待补充\n\n"
        "## 验收标准\n"
        "- 待补充\n\n"
        "## 边界与非目标\n"
        "- 待补充\n\n"
        "## 待确认项\n"
        "- 待补充\n"
    )


def _build_refine_verify_template_json() -> str:
    return (
        '{\n'
        '  "ok": false,\n'
        '  "issues": ["__FILL__"],\n'
        '  "missing_sections": ["__FILL__"],\n'
        '  "reason": "__FILL__"\n'
        '}\n'
    )


def _extract_refined_markdown(raw: str) -> str:
    content = raw.strip()
    if not content:
        raise ValueError("native_refine_template_empty")
    if any(hint in content for hint in _PLACEHOLDER_HINTS):
        raise ValueError("native_refine_template_contains_placeholder")
    missing_sections = [section for section in _REQUIRED_SECTIONS if f"## {section}" not in content]
    if missing_sections:
        raise ValueError(f"native_refine_missing_sections: {', '.join(missing_sections)}")
    return content.rstrip() + "\n"


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


def _render_bullets(items: list[str]) -> str:
    normalized = [item.strip() for item in items if item.strip()]
    return "\n".join(f"- {item}" for item in normalized) if normalized else "- 无"


def _render_change_scope(brief: RefineBrief) -> str:
    structured = _parse_path_changes(brief.in_scope)
    if structured:
        return _render_structured_change_scope(brief, structured)
    items: list[str] = []
    if brief.gating_conditions:
        items.append("适用条件：" + "；".join(brief.gating_conditions))
    items.extend(brief.in_scope)
    return _render_bullets(items)


def _render_structured_change_scope(brief: RefineBrief, changes: list[_PathChange]) -> str:
    lines: list[str] = []
    if brief.gating_conditions:
        lines.extend(["- 适用条件：" + "；".join(brief.gating_conditions), ""])
    for group in _ordered_groups(changes):
        rows = [change for change in changes if change.group == group]
        lines.extend(
            [
                f"### {group}",
                "",
                "| 状态 | 展示内容 |",
                "| --- | --- |",
            ]
        )
        for row in rows:
            lines.append(f"| {_escape_table_cell(row.state)} | {_escape_table_cell(row.value)} |")
        lines.append("")
    return "\n".join(lines).strip() or _render_bullets(brief.in_scope)


def _render_acceptance_criteria(brief: RefineBrief) -> str:
    structured = _parse_path_changes(brief.in_scope)
    if not structured:
        return _render_bullets(brief.acceptance_criteria)
    prefix = f"{_format_condition_prefix(brief.gating_conditions[0])}，" if brief.gating_conditions else ""
    criteria: list[str] = []
    for group in _ordered_groups(structured):
        states = [change.state for change in structured if change.group == group]
        criteria.append(f"{prefix}{group} 的{'、'.join(states)}按上表展示。")
    return _render_bullets(criteria)


def _parse_path_changes(items: list[str]) -> list[_PathChange]:
    changes = [_parse_path_change(item) for item in items]
    if not changes or any(change is None for change in changes):
        return []
    return [change for change in changes if change is not None]


def _parse_path_change(item: str) -> _PathChange | None:
    matched = re.match(r"^(?P<path>.+?)[：:](?P<value>.+)$", item.strip())
    if not matched:
        return None
    path = matched.group("path").strip()
    value = matched.group("value").strip()
    parts = [part.strip() for part in path.split("/") if part.strip()]
    if len(parts) < 2 or not value:
        return None
    group, state = _split_change_path(parts)
    return _PathChange(raw=item, group=group, state=state, value=value)


def _split_change_path(parts: list[str]) -> tuple[str, str]:
    if len(parts) >= 3 and parts[1].strip().lower() in {"temporary listing"}:
        return " / ".join(parts[:2]), " / ".join(parts[2:])
    return parts[0], " / ".join(parts[1:])


def _ordered_groups(changes: list[_PathChange]) -> list[str]:
    groups: list[str] = []
    for change in changes:
        if change.group not in groups:
            groups.append(change.group)
    return groups


def _escape_table_cell(value: str) -> str:
    return value.replace("|", r"\|").strip()


def _format_condition_prefix(condition: str) -> str:
    normalized = condition.strip().rstrip("。")
    if normalized.endswith("时"):
        return normalized
    return f"{normalized}时"


def _dedupe_boundary_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.removeprefix("边界检查：").strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _render_paragraph(lines: list[str]) -> str:
    normalized = [line.rstrip() for line in lines if line.strip()]
    return "\n".join(normalized) if normalized else "当前需求目标待补充。"


def _extract_markdown_section(markdown: str, title: str) -> str:
    pattern = rf"(?ms)^## {re.escape(title)}\n(.*?)(?=^## |\Z)"
    matched = re.search(pattern, markdown)
    return matched.group(1).strip() if matched else ""


def _contains_condition(section_body: str, condition: str) -> bool:
    condition_norm = _normalize_condition_text(condition)
    section_norm = _normalize_condition_text(section_body)
    return bool(condition_norm) and condition_norm in section_norm


def _normalize_condition_text(value: str) -> str:
    return re.sub(r"[\s。.,，:：；;]+", "", value.strip())


def _change_item_present(item: str, refined_markdown: str) -> bool:
    if item in refined_markdown:
        return True
    change = _parse_path_change(item)
    if change is None:
        return False
    section = _extract_markdown_section(refined_markdown, "具体变更点")
    section_norm = _normalize_change_text(section)
    return all(
        _normalize_change_text(part) in section_norm
        for part in (change.group, change.state, change.value)
    )


def _normalize_change_text(value: str) -> str:
    return re.sub(r"[\s|\\。.,，:：；;\"“”'‘’`]+", "", value.strip().lower())

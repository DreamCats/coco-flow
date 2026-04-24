from __future__ import annotations

import json
import re
import tempfile
from json import JSONDecodeError, JSONDecoder
from pathlib import Path

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.engines.shared.diagnostics import diagnosis_payload_from_verify, enrich_verify_payload
from coco_flow.prompts.refine import build_refine_generate_agent_prompt, build_refine_verify_agent_prompt

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
    # local/native 共用同一份 brief；区别只在于最终 markdown 是规则渲染还是 agent 润色。
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
    on_log("generate_mode: local")
    return refined_markdown, verify


def render_refined_markdown(brief: RefineBrief) -> str:
    overview_lines = [brief.goal]
    if brief.gating_conditions:
        overview_lines.extend(["", "前置条件：", *_render_bullets(brief.gating_conditions).splitlines()])
    boundary_items = [*brief.out_of_scope, *[f"边界检查：{item}" for item in brief.edge_cases]]
    open_questions = brief.open_questions or ["当前无额外待确认项。"]
    return (
        "# 需求确认书\n\n"
        "## 需求概述\n"
        f"{_render_paragraph(overview_lines)}\n\n"
        "## 具体变更点\n"
        f"{_render_bullets(brief.in_scope)}\n\n"
        "## 验收标准\n"
        f"{_render_bullets(brief.acceptance_criteria)}\n\n"
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
    for item in brief.in_scope:
        if item not in refined_markdown:
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
    # native 路径不再让模型从零总结，而是让 AGENT_MODE 基于 controller 产出的文件做受控润色。
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_refine_template(prepared.task_dir)
    generated_path: Path | None = None
    try:
        on_log("generate_mode: agent")
        client.run_agent(
            build_refine_generate_agent_prompt(
                manual_extract_path=str(manual_extract_path),
                brief_draft_path=str(brief_draft_path),
                source_excerpt_path=str(source_excerpt_path),
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        refined_markdown = _extract_refined_markdown(raw)
        generated_path = prepared.task_dir / ".refine-generated.md"
        generated_path.write_text(refined_markdown, encoding="utf-8")
        verify = _run_native_verify(
            client=client,
            brief_draft_path=brief_draft_path,
            refined_markdown_path=generated_path,
            settings=settings,
            cwd=prepared.task_dir,
        )
        if not verify.ok:
            repaired_markdown, repaired_verify = _verify_with_local_repair(brief, refined_markdown, on_log)
            if repaired_verify.ok:
                on_log(f"native_refine_local_repair_ok: attempts={repaired_verify.repair_attempts}")
                return repaired_markdown, repaired_verify
            _write_native_refine_failure_artifacts(prepared.task_dir, refined_markdown, verify)
            raise ValueError(f"native_refine_verify_failed: {verify.reason or verify.issues}")
        return refined_markdown, verify
    finally:
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
) -> RefineVerifyResult:
    template_path = _write_verify_template(cwd)
    try:
        client.run_agent(
            build_refine_verify_agent_prompt(
                brief_draft_path=str(brief_draft_path),
                refined_markdown_path=str(refined_markdown_path),
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(cwd),
            fresh_session=True,
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
        if template_path.exists():
            template_path.unlink()


def _write_native_refine_failure_artifacts(task_dir: Path, refined_markdown: str, verify: RefineVerifyResult) -> None:
    verify_payload = enrich_verify_payload(stage="refine", verify_payload=verify.to_payload(), artifact="prd-refined.md")
    diagnosis_payload = diagnosis_payload_from_verify(
        stage="refine",
        verify_payload=verify_payload,
        artifact="prd-refined.md",
    )
    (task_dir / "prd-refined.md").write_text(refined_markdown.rstrip() + "\n", encoding="utf-8")
    (task_dir / "refine-verify.json").write_text(json.dumps(verify_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (task_dir / "refine-diagnosis.json").write_text(json.dumps(diagnosis_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    if any("in_scope" in issue for issue in issues):
        return "missing_in_scope"
    if any("out_of_scope" in issue for issue in issues):
        return "missing_out_of_scope"
    return "refine_verify_failed" if issues else ""


def _write_refine_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".refine-template-",
        suffix=".md",
        delete=False,
    ) as handle:
        handle.write(_build_refine_template_markdown())
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


def _render_paragraph(lines: list[str]) -> str:
    normalized = [line.rstrip() for line in lines if line.strip()]
    return "\n".join(normalized) if normalized else "当前需求目标待补充。"


def _extract_markdown_section(markdown: str, title: str) -> str:
    pattern = rf"(?ms)^## {re.escape(title)}\n(.*?)(?=^## |\Z)"
    matched = re.search(pattern, markdown)
    return matched.group(1).strip() if matched else ""

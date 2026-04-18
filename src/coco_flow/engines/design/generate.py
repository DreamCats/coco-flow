from __future__ import annotations

import json
import re
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.design import (
    build_design_generate_agent_prompt,
    build_design_template_markdown,
    build_design_verify_agent_prompt,
    build_design_verify_template_json,
)

from .models import DesignPreparedInput, EXECUTOR_NATIVE

_HEADING_RE = re.compile(r"(?m)^#\s+Design\s*$")


def build_design_sections_payload(prepared: DesignPreparedInput, repo_binding_payload: dict[str, object], knowledge_brief_markdown: str) -> dict[str, object]:
    repo_bindings = repo_binding_payload.get("repo_bindings")
    binding_items = repo_bindings if isinstance(repo_bindings, list) else []
    system_changes: list[dict[str, object]] = []
    system_dependencies: list[dict[str, object]] = []
    in_scope_repo_ids: list[str] = []
    must_change_repo_ids: list[str] = []
    validate_repos: list[dict[str, object]] = []
    reference_repos: list[dict[str, object]] = []
    for item in binding_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("decision") or "") != "in_scope":
            continue
        repo_id = str(item.get("repo_id") or "")
        scope_tier = str(item.get("scope_tier") or "")
        if repo_id:
            in_scope_repo_ids.append(repo_id)
        if scope_tier in {"must_change", "co_change"}:
            if repo_id:
                must_change_repo_ids.append(repo_id)
            system_changes.append(
                {
                    "system_id": repo_id,
                    "system_name": str(item.get("system_name") or repo_id),
                    "serves_change_points": item.get("serves_change_points") or [1],
                    "responsibility": str(item.get("responsibility") or ""),
                    "planned_changes": item.get("change_summary") or [],
                    "upstream_inputs": item.get("depends_on") or [],
                    "downstream_outputs": [],
                    "touched_repos": [repo_id],
                }
            )
            continue
        target = validate_repos if scope_tier == "validate_only" else reference_repos
        target.append(
            {
                "repo_id": repo_id,
                "system_name": str(item.get("system_name") or repo_id),
                "reason": str(item.get("reason") or ""),
                "scope_tier": scope_tier or "reference_only",
            }
        )
    for item in binding_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("decision") or "") != "in_scope":
            continue
        if str(item.get("scope_tier") or "") not in {"must_change", "co_change"}:
            continue
        downstream_repo_id = str(item.get("repo_id") or "")
        depends_on = [str(value).strip() for value in item.get("depends_on", []) if str(value).strip()]
        for upstream_repo_id in depends_on:
            if upstream_repo_id not in must_change_repo_ids or not downstream_repo_id:
                continue
            system_dependencies.append(
                {
                    "upstream_system_id": upstream_repo_id,
                    "downstream_system_id": downstream_repo_id,
                    "dependency_type": "strong",
                    "reason": f"{downstream_repo_id} 依赖 {upstream_repo_id} 提供前置输入或先行收敛结果。",
                }
            )
    if must_change_repo_ids:
        solution_overview = "优先围绕必须改动仓库 " + "、".join(must_change_repo_ids) + " 收敛设计边界。"
        if validate_repos:
            solution_overview += " 其它仓库仅作为联动验证对象，不默认纳入主改造面。"
    else:
        solution_overview = f"优先围绕 {repo_binding_payload.get('decision_summary') or prepared.title} 收敛设计边界。"
    return {
        "system_change_points": prepared.sections.change_scope[:6] or [prepared.title],
        "solution_overview": solution_overview,
        "system_changes": system_changes,
        "system_dependencies": system_dependencies,
        "validate_repos": validate_repos,
        "reference_repos": reference_repos,
        "critical_flows": [
            {
                "name": "主链路",
                "trigger": prepared.sections.change_scope[0] if prepared.sections.change_scope else prepared.title,
                "steps": prepared.sections.acceptance_criteria[:4] or prepared.sections.change_scope[:4] or [prepared.title],
                "state_changes": prepared.sections.key_constraints[:3],
                "fallback_or_error_handling": prepared.sections.open_questions[:3] or prepared.sections.non_goals[:3],
            }
        ],
        "protocol_changes": [{"boundary_name": "default", "changed": False, "summary": "当前未发现明确协议变更。", "impacted_systems": [], "compatibility_notes": []}],
        "storage_config_changes": [{"category": "config", "changed": False, "summary": "当前未发现明确存储或配置变更。", "affected_items": [], "rollout_notes": []}],
        "experiment_changes": [{"changed": False, "experiment_name": "", "traffic_scope": "", "affected_flows": [], "rollout_notes": [], "rollback_notes": []}],
        "qa_inputs": prepared.sections.acceptance_criteria[:6] or ["建议优先覆盖主链路、边界条件和非目标回归。"],
        "staffing_estimate": {
            "summary": f"当前复杂度：{prepared.assessment.level} ({prepared.assessment.total})。",
            "frontend": "",
            "backend": "",
            "qa": "",
            "coordination_notes": ["当前为初版 Design 产物，详细人力安排后续补齐。"],
        },
        "knowledge_brief_used": bool(knowledge_brief_markdown.strip()),
    }


def generate_design_markdown(
    prepared: DesignPreparedInput,
    repo_binding_payload: dict[str, object],
    sections_payload: dict[str, object],
    knowledge_brief_markdown: str,
    settings: Settings,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> str:
    if settings.plan_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            return generate_native_design_markdown(prepared, repo_binding_payload, sections_payload, knowledge_brief_markdown, settings, artifacts, on_log)
        except ValueError as error:
            on_log(f"native_design_fallback: {error}")
    return generate_local_design_markdown(prepared, repo_binding_payload, sections_payload, knowledge_brief_markdown)


def generate_local_design_markdown(
    prepared: DesignPreparedInput,
    repo_binding_payload: dict[str, object],
    sections_payload: dict[str, object],
    knowledge_brief_markdown: str,
) -> str:
    repo_bindings = [item for item in repo_binding_payload.get("repo_bindings", []) if isinstance(item, dict) and str(item.get("decision") or "") == "in_scope"]
    must_change_bindings = [item for item in repo_bindings if str(item.get("scope_tier") or "") in {"must_change", "co_change"}]
    lines = [
        "# Design",
        "",
        f"- task_id: {prepared.task_id}",
        f"- title: {prepared.title}",
        "",
        "## 系统改造点",
    ]
    lines.extend(f"- {item}" for item in sections_payload.get("system_change_points", []) or [prepared.title])
    lines.extend(["", "## 方案设计", "", "### 总体方案", "", f"- {sections_payload.get('solution_overview') or '当前未形成总体方案。'}", "", "### 分系统改造", ""])
    if must_change_bindings:
        for item in must_change_bindings:
            lines.extend(
                [
                    f"#### {str(item.get('system_name') or item.get('repo_id') or 'system')}",
                    f"- 仓库：{str(item.get('repo_id') or '')}",
                    f"- 角色：{str(item.get('role') or '')}",
                    f"- scope_tier：{str(item.get('scope_tier') or '')}",
                    f"- 职责：{str(item.get('responsibility') or '')}",
                    "- 计划改动：",
                ]
            )
            change_summary = item.get("change_summary") or []
            if isinstance(change_summary, list):
                lines.extend(f"  - {str(value)}" for value in change_summary[:4] if str(value).strip())
            candidate_files = item.get("candidate_files") or []
            if isinstance(candidate_files, list) and candidate_files:
                lines.append("- 候选文件：")
                lines.extend(f"  - {str(value)}" for value in candidate_files[:6] if str(value).strip())
            lines.append("")
    else:
        lines.append("- 当前未识别到明确的必须改动仓库，需要补充设计依据。")
        lines.append("")
    validate_repos = sections_payload.get("validate_repos") or []
    if isinstance(validate_repos, list) and validate_repos:
        lines.extend(["### 联动验证仓库", ""])
        for item in validate_repos:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('repo_id') or ''}：{item.get('reason') or '需要联动验证，但默认不纳入主改造面。'}")
        lines.append("")
    reference_repos = sections_payload.get("reference_repos") or []
    if isinstance(reference_repos, list) and reference_repos:
        lines.extend(["### 参考链路", ""])
        for item in reference_repos:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('repo_id') or ''}：作为背景链路参考，本次默认不改。")
        lines.append("")
    lines.extend(["### 系统依赖关系", ""])
    dependencies = sections_payload.get("system_dependencies") or []
    if isinstance(dependencies, list) and dependencies:
        for item in dependencies:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('upstream_system_id') or ''} -> {item.get('downstream_system_id') or ''}：{item.get('reason') or ''}"
            )
    else:
        lines.append("- 当前未识别到明确的强依赖关系。")
    lines.extend(["", "### 关键链路说明", ""])
    critical_flows = sections_payload.get("critical_flows") or []
    if isinstance(critical_flows, list) and critical_flows:
        first = critical_flows[0] if isinstance(critical_flows[0], dict) else {}
        lines.append(f"- 触发入口：{first.get('trigger') or prepared.title}")
        for step in first.get("steps", [])[:4]:
            lines.append(f"- {step}")
    else:
        lines.append("- 当前未沉淀出额外关键链路。")
    lines.extend(
        [
            "",
            "## 多端协议是否有变更",
            "",
            "- 当前未发现明确的多端协议变更信号。",
            "",
            "## 存储&&配置是否有变更",
            "",
            "- 当前未发现明确的存储或配置变更信号。",
            "",
            "## 是否有实验，实验怎么涉及",
            "",
            "- 当前未发现明确的实验变更信号。",
            "",
            "## 给 QA 的输入",
            "",
        ]
    )
    qa_inputs = sections_payload.get("qa_inputs") or []
    if isinstance(qa_inputs, list) and qa_inputs:
        lines.extend(f"- {str(item)}" for item in qa_inputs[:6] if str(item).strip())
    else:
        lines.append("- 建议优先覆盖主链路、边界条件和非目标回归。")
    lines.extend(["", "## 人力评估", ""])
    staffing = sections_payload.get("staffing_estimate") or {}
    lines.append(f"- {staffing.get('summary') or f'当前复杂度：{prepared.assessment.level} ({prepared.assessment.total})。'}")
    if knowledge_brief_markdown.strip():
        lines.append("- 已参考继承自 Refine 的知识结果。")
    return "\n".join(lines).rstrip() + "\n"


def generate_native_design_markdown(
    prepared: DesignPreparedInput,
    repo_binding_payload: dict[str, object],
    sections_payload: dict[str, object],
    knowledge_brief_markdown: str,
    settings: Settings,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> str:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_design_template(prepared.task_dir)
    try:
        client.run_agent(
            build_design_generate_agent_prompt(
                title=prepared.title,
                refined_markdown=prepared.refined_markdown,
                repo_binding_payload=repo_binding_payload,
                sections_payload=sections_payload,
                knowledge_brief_markdown=knowledge_brief_markdown,
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
    finally:
        if template_path.exists():
            template_path.unlink()
    content = extract_design_content(raw)
    if not content:
        raise ValueError("native_design_agent_did_not_write_valid_template")

    verify_template_path = _write_verify_template(prepared.task_dir)
    try:
        client.run_agent(
            build_design_verify_agent_prompt(
                title=prepared.title,
                design_markdown=content,
                repo_binding_payload=repo_binding_payload,
                sections_payload=sections_payload,
                template_path=str(verify_template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        verify_raw = verify_template_path.read_text(encoding="utf-8") if verify_template_path.exists() else ""
    finally:
        if verify_template_path.exists():
            verify_template_path.unlink()
    verify_payload = parse_design_verify_output(verify_raw)
    artifacts["design-verify.json"] = verify_payload
    if not bool(verify_payload.get("ok")):
        issues = verify_payload.get("issues") or []
        issue_text = "; ".join(str(item) for item in issues[:3]) if isinstance(issues, list) else "unknown"
        raise ValueError(f"native_design_verify_failed: {issue_text}")
    return content


def extract_design_content(raw: str) -> str:
    content = raw.strip()
    if not content:
        return ""
    if "待补充" in content:
        return ""
    if _HEADING_RE.search(content):
        return content.rstrip() + "\n"
    return ""


def parse_design_verify_output(raw: str) -> dict[str, object]:
    normalized = raw.strip()
    if not normalized:
        raise ValueError("design_verify_output_is_empty")
    payload = json.loads(normalized)
    if not isinstance(payload, dict):
        raise ValueError("design_verify_output_is_not_object")
    return {
        "ok": bool(payload.get("ok")),
        "issues": [str(item) for item in payload.get("issues", []) if str(item).strip()],
        "reason": str(payload.get("reason") or ""),
    }


def _write_design_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".design-template-",
        suffix=".md",
        delete=False,
    ) as handle:
        handle.write(build_design_template_markdown())
        handle.flush()
        return Path(handle.name)


def _write_verify_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".design-verify-",
        suffix=".json",
        delete=False,
    ) as handle:
        handle.write(build_design_verify_template_json())
        handle.flush()
        return Path(handle.name)

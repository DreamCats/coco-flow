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
    """组装渲染 design.md 所需的结构化 section 模型。

    这是最后一层纯结构化步骤；有了这些 sections，后面就可以渲染成本地版
    或 native 版 design markdown。
    """
    repo_bindings = repo_binding_payload.get("repo_bindings")
    binding_items = repo_bindings if isinstance(repo_bindings, list) else []
    research_items = prepared.research_payload.get("repos")
    research_by_repo_id = {
        str(item.get("repo_id") or ""): item
        for item in (research_items if isinstance(research_items, list) else [])
        if isinstance(item, dict) and str(item.get("repo_id") or "").strip()
    }
    system_changes: list[dict[str, object]] = []
    system_dependencies: list[dict[str, object]] = []
    in_scope_repo_ids: list[str] = []
    must_change_repo_ids: list[str] = []
    validate_repos: list[dict[str, object]] = []
    reference_repos: list[dict[str, object]] = []
    repo_decisions: list[dict[str, object]] = []
    closure_mode = str(repo_binding_payload.get("closure_mode") or "unresolved")
    selection_basis = str(repo_binding_payload.get("selection_basis") or "unresolved")
    selection_note = str(repo_binding_payload.get("selection_note") or "").strip()
    for item in binding_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("decision") or "") != "in_scope":
            continue
        repo_id = str(item.get("repo_id") or "")
        scope_tier = str(item.get("scope_tier") or "")
        research_entry = research_by_repo_id.get(repo_id, {})
        if repo_id:
            in_scope_repo_ids.append(repo_id)
        repo_decisions.append(
            _build_repo_decision_note(
                item,
                research_entry,
                closure_mode=closure_mode,
                selection_basis=selection_basis,
                selection_note=selection_note,
            )
        )
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
    system_change_points = _build_system_change_points(prepared, repo_decisions, system_changes, validate_repos)
    critical_flows = _build_critical_flows(prepared, repo_decisions, system_change_points)
    return {
        "system_change_points": system_change_points,
        "solution_overview": solution_overview,
        "closure_mode": closure_mode,
        "selection_basis": selection_basis,
        "selection_note": selection_note,
        "system_changes": system_changes,
        "system_dependencies": system_dependencies,
        "repo_decisions": repo_decisions,
        "validate_repos": validate_repos,
        "reference_repos": reference_repos,
        "critical_flows": critical_flows,
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
    """渲染最终 design.md；能走 native 就走 native，否则回退到 local。"""
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
    """基于结构化 payload，渲染一份确定性的本地 design markdown。"""
    repo_bindings = [item for item in repo_binding_payload.get("repo_bindings", []) if isinstance(item, dict) and str(item.get("decision") or "") == "in_scope"]
    must_change_bindings = [item for item in repo_bindings if str(item.get("scope_tier") or "") in {"must_change", "co_change"}]
    repo_decision_notes = {
        str(item.get("repo_id") or ""): item
        for item in (sections_payload.get("repo_decisions") or [])
        if isinstance(item, dict) and str(item.get("repo_id") or "").strip()
    }
    lines = [
        "# Design",
        "",
        f"- task_id: {prepared.task_id}",
        f"- title: {prepared.title}",
        "",
        "## 系统改造点",
    ]
    lines.extend(f"- {item}" for item in sections_payload.get("system_change_points", []) or [prepared.title])
    lines.extend(["", "## 方案设计", "", "### 总体方案", ""])
    lines.extend(_render_solution_overview_lines(sections_payload, prepared.title))
    lines.extend(["", "### 分系统改造", ""])
    if must_change_bindings:
        for item in must_change_bindings:
            note = repo_decision_notes.get(str(item.get("repo_id") or ""), {})
            lines.extend(
                [
                    f"#### {str(item.get('system_name') or item.get('repo_id') or 'system')}",
                    f"- 仓库：{str(item.get('repo_id') or '')}",
                    f"- scope_tier：{str(item.get('scope_tier') or '')}",
                    f"- 职责：{str(item.get('responsibility') or '')}",
                    f"- 选择原因：{str(note.get('decision_reason') or item.get('reason') or '承担本次核心改造，因此纳入主改造面。')}",
                    f"- 仓库现状：{str(note.get('repo_summary') or '当前缺少额外仓库现状摘要。')}",
                    "- 计划改动：",
                ]
            )
            selection_context = str(note.get("selection_context") or "").strip()
            if selection_context:
                lines.append(f"- 仓库选择说明：{selection_context}")
            change_summary = item.get("change_summary") or []
            if isinstance(change_summary, list):
                lines.extend(f"  - {str(value)}" for value in change_summary[:4] if str(value).strip())
            candidate_files = note.get("candidate_files") or item.get("candidate_files") or []
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
            note = repo_decision_notes.get(str(item.get("repo_id") or ""), {})
            detail_parts = [str(note.get("decision_reason") or item.get("reason") or "需要联动验证，但默认不纳入主改造面。").strip()]
            repo_summary = str(note.get("repo_summary") or "").strip()
            if repo_summary:
                detail_parts.append(f"当前仓库现状：{repo_summary}")
            lines.append(f"- {item.get('repo_id') or ''}：{' '.join(part for part in detail_parts if part)}")
        lines.append("")
    reference_repos = sections_payload.get("reference_repos") or []
    if isinstance(reference_repos, list) and reference_repos:
        lines.extend(["### 参考链路", ""])
        for item in reference_repos:
            if not isinstance(item, dict):
                continue
            note = repo_decision_notes.get(str(item.get("repo_id") or ""), {})
            detail = str(note.get("decision_summary") or "作为背景链路参考，本次默认不改。")
            lines.append(f"- {item.get('repo_id') or ''}：{detail}")
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
    """让 agent 生成 design.md，再补契约检查和 verify。"""
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    content = _run_design_generation_once(
        client=client,
        prepared=prepared,
        repo_binding_payload=repo_binding_payload,
        sections_payload=sections_payload,
        knowledge_brief_markdown=knowledge_brief_markdown,
        settings=settings,
    )

    if prepared.is_single_bound_repo:
        artifacts["design-verify.json"] = {"ok": True, "issues": [], "reason": "single bound repo fast path"}
        return content

    verify_payload, retry_source, retry_issues = _evaluate_design_output(
        client=client,
        prepared=prepared,
        content=content,
        repo_binding_payload=repo_binding_payload,
        sections_payload=sections_payload,
        settings=settings,
    )
    if not retry_issues:
        artifacts["design-verify.json"] = verify_payload
        return content

    on_log(f"design_regenerate_start: source={retry_source}, issue_count={len(retry_issues)}")
    logged_failure = False
    try:
        regenerated = _run_design_generation_once(
            client=client,
            prepared=prepared,
            repo_binding_payload=repo_binding_payload,
            sections_payload=sections_payload,
            knowledge_brief_markdown=knowledge_brief_markdown,
            settings=settings,
            regeneration_issues=retry_issues,
            previous_design_markdown=content,
        )
        final_verify_payload, final_source, final_issues = _evaluate_design_output(
            client=client,
            prepared=prepared,
            content=regenerated,
            repo_binding_payload=repo_binding_payload,
            sections_payload=sections_payload,
            settings=settings,
        )
        if final_issues:
            issue_text = "; ".join(final_issues[:3]) if isinstance(final_issues, list) else "unknown"
            on_log(f"design_regenerate_failed: source={final_source}, issues={issue_text}")
            logged_failure = True
            if final_source == "contract":
                raise ValueError(f"native_design_contract_failed: {issue_text}")
            raise ValueError(f"native_design_verify_failed: {issue_text}")
        on_log("design_regenerate_ok: true")
        artifacts["design-verify.json"] = final_verify_payload
        return regenerated
    except ValueError as error:
        if not logged_failure:
            on_log(f"design_regenerate_failed: {error}")
        raise


def _run_design_generation_once(
    *,
    client: CocoACPClient,
    prepared: DesignPreparedInput,
    repo_binding_payload: dict[str, object],
    sections_payload: dict[str, object],
    knowledge_brief_markdown: str,
    settings: Settings,
    regeneration_issues: list[str] | None = None,
    previous_design_markdown: str = "",
) -> str:
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
                regeneration_issues=regeneration_issues,
                previous_design_markdown=previous_design_markdown,
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
    return content


def _evaluate_design_output(
    *,
    client: CocoACPClient,
    prepared: DesignPreparedInput,
    content: str,
    repo_binding_payload: dict[str, object],
    sections_payload: dict[str, object],
    settings: Settings,
) -> tuple[dict[str, object], str, list[str]]:
    contract_issues = collect_design_contract_issues(content, repo_binding_payload, sections_payload)
    if contract_issues:
        return {
            "ok": False,
            "issues": contract_issues,
            "reason": "design contract failed",
        }, "contract", contract_issues
    verify_payload = _run_design_verify_once(
        client=client,
        prepared=prepared,
        content=content,
        repo_binding_payload=repo_binding_payload,
        sections_payload=sections_payload,
        settings=settings,
    )
    if bool(verify_payload.get("ok")):
        return verify_payload, "verify", []
    return verify_payload, "verify", _collect_design_verify_issues(verify_payload)


def _run_design_verify_once(
    *,
    client: CocoACPClient,
    prepared: DesignPreparedInput,
    content: str,
    repo_binding_payload: dict[str, object],
    sections_payload: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
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
    return parse_design_verify_output(verify_raw)


def _collect_design_verify_issues(verify_payload: dict[str, object]) -> list[str]:
    issues = [str(item) for item in (verify_payload.get("issues") or []) if str(item).strip()]
    if issues:
        return issues
    reason = str(verify_payload.get("reason") or "").strip()
    if reason:
        return [reason]
    return ["design verify failed without actionable issues"]


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


def collect_design_contract_issues(
    design_markdown: str,
    repo_binding_payload: dict[str, object],
    sections_payload: dict[str, object],
) -> list[str]:
    normalized = design_markdown.lower()
    issues: list[str] = []
    closure_mode = str(repo_binding_payload.get("closure_mode") or sections_payload.get("closure_mode") or "")
    selection_basis = str(repo_binding_payload.get("selection_basis") or sections_payload.get("selection_basis") or "")
    raw_bindings = repo_binding_payload.get("repo_bindings")
    binding_items = raw_bindings if isinstance(raw_bindings, list) else []
    repo_decisions = {
        str(item.get("repo_id") or ""): item
        for item in (sections_payload.get("repo_decisions") or [])
        if isinstance(item, dict) and str(item.get("repo_id") or "").strip()
    }
    validate_repo_ids: list[str] = []
    for item in binding_items:
        if not isinstance(item, dict) or str(item.get("decision") or "") != "in_scope":
            continue
        repo_id = str(item.get("repo_id") or "").strip()
        if not repo_id:
            continue
        system_name = str(item.get("system_name") or "").strip()
        repo_tokens = [repo_id.lower()]
        if system_name:
            repo_tokens.append(system_name.lower())
        if not any(token and token in normalized for token in repo_tokens):
            issues.append(f"design.md 未明确提及 in_scope 仓库 {repo_id}")
        if str(item.get("scope_tier") or "") == "validate_only":
            validate_repo_ids.append(repo_id)
    if validate_repo_ids and "联动验证仓库" not in design_markdown:
        issues.append("存在 validate_only 仓库，但 design.md 未单独展开联动验证仓库")
    if closure_mode == "single_repo" and selection_basis == "heuristic_tiebreak":
        if "默认选择" not in design_markdown and "默认起始实现仓" not in design_markdown:
            issues.append("selection_basis=heuristic_tiebreak，但 design.md 未说明当前只是默认选择起始实现仓")
        if "单仓" not in design_markdown and "单仓闭合" not in design_markdown:
            issues.append("selection_basis=heuristic_tiebreak，但 design.md 未说明当前判断只是单仓可闭合")
    for repo_id, note in repo_decisions.items():
        if repo_id.lower() not in normalized:
            continue
        candidate_files = note.get("candidate_files") or []
        if not isinstance(candidate_files, list) or not candidate_files:
            continue
        if not any(str(value).strip().lower() in normalized for value in candidate_files[:3]):
            issues.append(f"design.md 提到了 {repo_id}，但未落候选文件或实现落点")
    return issues


def _build_repo_decision_note(
    binding_item: dict[str, object],
    research_entry: dict[str, object],
    *,
    closure_mode: str,
    selection_basis: str,
    selection_note: str,
) -> dict[str, object]:
    repo_id = str(binding_item.get("repo_id") or "")
    scope_tier = str(binding_item.get("scope_tier") or "")
    reason = str(binding_item.get("reason") or "").strip()
    responsibility = str(binding_item.get("responsibility") or "").strip()
    repo_summary = str(research_entry.get("summary") or "").strip()
    evidence = [str(value) for value in research_entry.get("evidence", []) if str(value).strip()] if isinstance(research_entry.get("evidence"), list) else []
    candidate_files = _preferred_note_paths(
        research_entry.get("candidate_files", []),
        binding_item.get("candidate_files", []),
        limit=6,
    )
    candidate_dirs = _preferred_note_paths(
        research_entry.get("candidate_dirs", []),
        binding_item.get("candidate_dirs", []),
        limit=6,
    )
    decision_reason = ""
    if scope_tier in {"must_change", "co_change"}:
        decision_reason = reason or "承担本次核心改造，因此纳入主改造面。"
    elif scope_tier == "validate_only":
        if reason:
            decision_reason = f"{reason} 当前默认仅做联动验证，不作为默认起始实现仓。"
        else:
            decision_reason = "存在相关上下游或算法参考，但当前默认仅做联动验证。"
    else:
        decision_reason = reason or "仅保留背景或参考信息，本次默认不改。"
    selection_context = ""
    if closure_mode == "single_repo" and selection_basis == "heuristic_tiebreak" and selection_note:
        selection_context = selection_note
    return {
        "repo_id": repo_id,
        "system_name": str(binding_item.get("system_name") or repo_id),
        "scope_tier": scope_tier,
        "decision_summary": " ".join(part for part in [decision_reason, f"仓库现状：{repo_summary}" if repo_summary else f"仓库职责：{responsibility}" if responsibility else "", f"仓库选择说明：{selection_context}" if selection_context else ""] if part),
        "decision_reason": decision_reason,
        "selection_context": selection_context,
        "repo_summary": repo_summary,
        "responsibility": responsibility,
        "candidate_files": candidate_files,
        "candidate_dirs": candidate_dirs,
        "evidence": evidence[:4],
    }


def _build_system_change_points(
    prepared: DesignPreparedInput,
    repo_decisions: list[dict[str, object]],
    system_changes: list[dict[str, object]],
    validate_repos: list[dict[str, object]],
) -> list[str]:
    lines: list[str] = []
    if system_changes:
        primary_change = _first_meaningful_line(
            value
            for change in system_changes
            for value in (change.get("planned_changes") or [])
        )
        if primary_change:
            primary_repo = str(system_changes[0].get("system_id") or system_changes[0].get("system_name") or "").strip()
            if primary_repo:
                lines.append(f"以 {primary_repo} 为主改仓，收敛 {primary_change}")
            else:
                lines.append(primary_change)
    focus_files = _collect_focus_files(repo_decisions, limit=3)
    if focus_files:
        lines.append(f"优先统一 {', '.join(focus_files)} 等命中路径的状态判定与讲解卡数据装配逻辑。")
        if len(focus_files) >= 2:
            lines.append("需要同步收敛主路径和兼容返回路径，避免同一竞拍在不同入口下状态表达不一致。")
    elif prepared.sections.acceptance_criteria:
        lines.append(str(prepared.sections.acceptance_criteria[0]).strip())
    if validate_repos:
        repo_text = "、".join(str(item.get("repo_id") or "").strip() for item in validate_repos if str(item.get("repo_id") or "").strip())
        if repo_text:
            lines.append(f"{repo_text} 仅作为联动验证仓库，不纳入本次主改造面。")
    boundary_line = _build_boundary_line(prepared.sections.non_goals[:3])
    if boundary_line:
        lines.append(boundary_line)
    return _dedupe_non_empty(lines)[:6] or [prepared.title]


def _build_critical_flows(
    prepared: DesignPreparedInput,
    repo_decisions: list[dict[str, object]],
    system_change_points: list[str],
) -> list[dict[str, object]]:
    focus_files = _collect_focus_files(repo_decisions, limit=3)
    focus_dirs = _collect_focus_dirs(repo_decisions, limit=2)
    steps: list[str] = []
    if focus_files:
        steps.append(f"先确认 {focus_files[0]} 中的核心状态判定口径。")
    if len(focus_files) >= 2:
        steps.append(f"再同步 {focus_files[1]} 等其它讲解卡返回路径，确保成交态与结束态表达一致。")
    elif focus_dirs:
        steps.append(f"再沿 {focus_dirs[0]} 等命中目录补齐相关返回链路。")
    if prepared.sections.acceptance_criteria:
        acceptance_line = str(prepared.sections.acceptance_criteria[0]).strip()
        if acceptance_line:
            steps.append(f"最后校验 {acceptance_line}。")
    state_changes = _dedupe_non_empty(
        [
            "若只修改单一路径，可能导致同一竞拍在不同入口下状态不一致。" if len(focus_files) >= 2 else "",
            *[str(item).strip() for item in prepared.sections.key_constraints[:2] if str(item).strip()],
        ]
    )
    fallback_or_error_handling = _dedupe_non_empty(
        [
            _build_boundary_line(prepared.sections.non_goals[:3]),
            *[str(item).strip() for item in prepared.sections.open_questions[:2] if str(item).strip()],
        ]
    )
    return [
        {
            "name": "主链路",
            "trigger": system_change_points[0] if system_change_points else prepared.title,
            "steps": _dedupe_non_empty(steps)[:4] or [prepared.title],
            "state_changes": state_changes[:3],
            "fallback_or_error_handling": fallback_or_error_handling[:3],
        }
    ]


def _collect_focus_files(repo_decisions: list[dict[str, object]], *, limit: int) -> list[str]:
    return _dedupe_non_empty(
        str(value).strip()
        for note in repo_decisions
        if isinstance(note, dict) and str(note.get("scope_tier") or "") in {"must_change", "co_change"}
        for value in (note.get("candidate_files") or [])
    )[:limit]


def _collect_focus_dirs(repo_decisions: list[dict[str, object]], *, limit: int) -> list[str]:
    return _dedupe_non_empty(
        str(value).strip()
        for note in repo_decisions
        if isinstance(note, dict) and str(note.get("scope_tier") or "") in {"must_change", "co_change"}
        for value in (note.get("candidate_dirs") or [])
    )[:limit]


def _first_meaningful_line(values) -> str:
    for raw in values:
        text = str(raw).strip()
        if text:
            return text
    return ""


def _build_boundary_line(values) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        return ""
    return "边界保持：" + "；".join(items[:3]) + "。"


def _preferred_note_paths(primary_values, fallback_values, *, limit: int) -> list[str]:
    primary = _dedupe_non_empty(str(value).strip() for value in (primary_values if isinstance(primary_values, list) else []) if str(value).strip())
    if primary:
        return primary[:limit]
    return _dedupe_non_empty(str(value).strip() for value in (fallback_values if isinstance(fallback_values, list) else []) if str(value).strip())[:limit]


def _dedupe_non_empty(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _render_solution_overview_lines(sections_payload: dict[str, object], fallback_title: str) -> list[str]:
    lines = [f"- {sections_payload.get('solution_overview') or fallback_title}"]
    closure_mode = str(sections_payload.get("closure_mode") or "")
    selection_basis = str(sections_payload.get("selection_basis") or "")
    selection_note = str(sections_payload.get("selection_note") or "").strip()
    if closure_mode == "single_repo":
        lines.append("- 当前判断：需求可在单仓内闭合实现，不需要双仓协同改造。")
    elif closure_mode == "multi_repo":
        lines.append("- 当前判断：需求需要多仓协同改造才能闭合。")
    elif closure_mode == "unresolved":
        lines.append("- 当前判断：是否需要多仓协同仍未完全收敛。")
    if selection_basis == "heuristic_tiebreak" and selection_note:
        lines.append(f"- 仓库选择：{selection_note}")
    elif selection_basis == "strong_signal" and selection_note:
        lines.append(f"- 仓库选择依据：{selection_note}")
    elif selection_basis == "unresolved" and selection_note:
        lines.append(f"- 仓库选择仍待确认：{selection_note}")
    return lines


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

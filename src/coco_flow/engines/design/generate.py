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
    must_change_repo_ids: list[str] = []
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
        repo_decisions.append(
            _build_repo_decision_note(
                item,
                research_entry,
                closure_mode=closure_mode,
                selection_basis=selection_basis,
                selection_note=selection_note,
            )
        )
        if scope_tier in {"must_change", "co_change"} and repo_id:
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
                    "dependency_kind": _infer_dependency_kind(upstream_repo_id, downstream_repo_id, repo_decisions),
                    "reason": f"{downstream_repo_id} 依赖 {upstream_repo_id} 提供前置输入或先行收敛结果。",
                }
            )
    if must_change_repo_ids:
        solution_overview = "优先围绕必须改动仓库 " + "、".join(must_change_repo_ids) + " 收敛设计边界。"
        if any(str(item.get("scope_tier") or "") == "validate_only" for item in repo_decisions):
            solution_overview += " 其它仓库仅作为联动验证对象，不默认纳入主改造面。"
    else:
        solution_overview = f"优先围绕 {repo_binding_payload.get('decision_summary') or prepared.title} 收敛设计边界。"
    system_change_points = _build_system_change_points(prepared, repo_decisions, system_changes)
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
        "critical_flows": critical_flows,
        "interface_changes": _build_interface_changes(prepared, repo_decisions),
        "risk_boundaries": _build_risk_boundaries(prepared, repo_decisions),
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
        "## 改造点总览",
    ]
    lines.extend(f"- {item}" for item in sections_payload.get("system_change_points", []) or [prepared.title])
    lines.extend(["", "## 总体方案", ""])
    lines.extend(_render_solution_overview_lines(sections_payload, prepared.title))
    critical_flows = sections_payload.get("critical_flows") or []
    if isinstance(critical_flows, list) and critical_flows:
        first = critical_flows[0] if isinstance(critical_flows[0], dict) else {}
        trigger = str(first.get("trigger") or "").strip()
        if trigger:
            lines.append(f"- 主链路入口：{trigger}")
        for step in first.get("steps", [])[:4]:
            if str(step).strip():
                lines.append(f"- {step}")
    lines.extend(["", "## 分仓库方案", ""])
    if repo_bindings:
        for item in repo_bindings:
            note = repo_decision_notes.get(str(item.get("repo_id") or ""), {})
            lines.extend(
                [
                    f"#### {str(item.get('system_name') or item.get('repo_id') or 'system')}",
                    f"- 仓库：{str(item.get('repo_id') or '')}",
                    f"- scope_tier：{str(item.get('scope_tier') or '')}",
                    f"- 职责：{str(item.get('responsibility') or '')}",
                    f"- 选择原因：{str(note.get('decision_reason') or item.get('reason') or '承担本次核心改造，因此纳入主改造面。')}",
                    f"- 仓库现状：{str(note.get('repo_summary') or '当前缺少额外仓库现状摘要。')}",
                    "- 主要改动：",
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
        lines.append("- 当前未识别到明确的 in_scope 仓库，需要补充设计依据。")
        lines.append("")
    lines.extend(["## 仓库依赖关系", ""])
    dependencies = sections_payload.get("system_dependencies") or []
    if isinstance(dependencies, list) and dependencies:
        for item in dependencies:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('upstream_system_id') or ''} -> {item.get('downstream_system_id') or ''}（{item.get('dependency_kind') or 'interface'}）：{item.get('reason') or ''}"
            )
    else:
        lines.append("- 当前未识别到明确的强依赖关系。")
    lines.extend(["", "## 接口协议变更", ""])
    interface_changes = sections_payload.get("interface_changes") or []
    meaningful_changes = [item for item in interface_changes if isinstance(item, dict) and str(item.get("interface") or "").strip()]
    if meaningful_changes:
        for item in meaningful_changes:
            lines.append(
                f"- 接口：{item.get('interface') or ''}；字段：{item.get('field') or '-'}；变更类型：{item.get('change_type') or 'modify'}；下游：{item.get('consumer') or '-'}；需对齐：{'是' if item.get('need_alignment') else '否'}；说明：{item.get('description') or ''}"
            )
    else:
        lines.append("- 本次需求不涉及对外接口协议变更。")
    lines.extend(["", "## 风险与待确认项", ""])
    risk_boundaries = sections_payload.get("risk_boundaries") or []
    if isinstance(risk_boundaries, list) and risk_boundaries:
        for item in risk_boundaries:
            if not isinstance(item, dict):
                continue
            label = "阻塞项" if bool(item.get("blocking")) else "风险"
            lines.append(f"- {label}（{item.get('level') or '中'}）：{item.get('title') or ''}；建议应对：{item.get('mitigation') or ''}")
    else:
        lines.append("- 当前未沉淀出额外技术风险或待确认项。")
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
    issues.extend(_collect_design_format_issues(design_markdown))
    required_sections = ("## 改造点总览", "## 总体方案", "## 分仓库方案", "## 仓库依赖关系", "## 接口协议变更", "## 风险与待确认项")
    for section in required_sections:
        if section not in design_markdown:
            issues.append(f"design.md 缺少必要章节：{section.removeprefix('## ')}")
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
        scope_tier = str(item.get("scope_tier") or "")
        if scope_tier == "validate_only":
            validate_repo_ids.append(repo_id)
        if scope_tier in {"must_change", "co_change"} and repo_id.lower() in normalized:
            candidate_files = (repo_decisions.get(repo_id, {}).get("candidate_files") or item.get("candidate_files") or [])
            if isinstance(candidate_files, list) and candidate_files and not any(str(value).strip().lower() in normalized for value in candidate_files[:3]):
                issues.append(f"design.md 提到了 {repo_id}，但未落候选文件或实现落点")
    if validate_repo_ids:
        for repo_id in validate_repo_ids:
            if repo_id.lower() in normalized and "验证" not in design_markdown:
                issues.append(f"validate_only 仓库 {repo_id} 缺少验证定位说明")
    if closure_mode == "single_repo" and selection_basis == "heuristic_tiebreak":
        if "默认选择" not in design_markdown and "默认起始实现仓" not in design_markdown:
            issues.append("selection_basis=heuristic_tiebreak，但 design.md 未说明当前只是默认选择起始实现仓")
        if "单仓" not in design_markdown and "单仓闭合" not in design_markdown:
            issues.append("selection_basis=heuristic_tiebreak，但 design.md 未说明当前判断只是单仓可闭合")
    if sections_payload.get("interface_changes") and "接口协议变更" in design_markdown and "不涉及" not in design_markdown:
        meaningful_changes = [
            item for item in (sections_payload.get("interface_changes") or [])
            if isinstance(item, dict) and str(item.get("interface") or "").strip()
        ]
        if meaningful_changes and not any(str(item.get("interface") or "").strip().lower() in normalized for item in meaningful_changes[:2]):
            issues.append("design.md 未体现结构化接口变更信息")
    if sections_payload.get("risk_boundaries") and "风险与待确认项" in design_markdown:
        meaningful_risks = [
            item for item in (sections_payload.get("risk_boundaries") or [])
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ]
        if meaningful_risks and not any(str(item.get("title") or "").strip().lower() in normalized for item in meaningful_risks[:2]):
            issues.append("design.md 未体现结构化风险与待确认项")
    return issues


def _collect_design_format_issues(design_markdown: str) -> list[str]:
    issues: list[str] = []
    for raw_line in design_markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.count("**") % 2 == 1:
            issues.append("design.md 存在未闭合的加粗标记")
            break
    for raw_line in design_markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.count("（") != line.count("）"):
            issues.append("design.md 存在未闭合的中文括号")
            break
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
    validate_repo_ids = [
        str(item.get("repo_id") or "").strip()
        for item in repo_decisions
        if isinstance(item, dict) and str(item.get("scope_tier") or "") == "validate_only"
    ]
    if validate_repo_ids:
        repo_text = "、".join(repo_id for repo_id in validate_repo_ids if repo_id)
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


def _infer_dependency_kind(
    upstream_repo_id: str,
    downstream_repo_id: str,
    repo_decisions: list[dict[str, object]],
) -> str:
    text = " ".join(
        str(value).lower()
        for note in repo_decisions
        if isinstance(note, dict) and str(note.get("repo_id") or "") in {upstream_repo_id, downstream_repo_id}
        for value in (
            note.get("decision_reason"),
            note.get("repo_summary"),
            note.get("responsibility"),
        )
        if str(value).strip()
    )
    if any(keyword in text for keyword in ("config", "配置", "实验", "ab")):
        return "config"
    if any(keyword in text for keyword in ("cache", "db", "数据", "存储", "loader")):
        return "data"
    return "interface"


def _build_interface_changes(prepared: DesignPreparedInput, repo_decisions: list[dict[str, object]]) -> list[dict[str, object]]:
    candidates = _dedupe_non_empty(
        str(value).strip()
        for note in repo_decisions
        if isinstance(note, dict)
        for value in (note.get("candidate_files") or [])
        if any(token in str(value).lower() for token in (".proto", ".thrift", "/handler/", "/api/", "converter", "loader"))
    )
    if not candidates:
        return []
    consumers = "前端 / 其他服务 / 客户端"
    return [
        {
            "interface": candidates[0],
            "field": "",
            "change_type": "modify",
            "consumer": consumers,
            "need_alignment": True,
            "description": f"围绕 {prepared.title} 补齐对外返回口径，具体字段需结合实现确认。",
        }
    ]


def _build_risk_boundaries(prepared: DesignPreparedInput, repo_decisions: list[dict[str, object]]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for question in prepared.sections.open_questions[:3]:
        text = str(question).strip()
        if not text:
            continue
        items.append(
            {
                "title": text,
                "level": "中",
                "mitigation": "先与产品或相关研发确认口径，再进入实现。",
                "blocking": True,
            }
        )
    boundary_line = _build_boundary_line(prepared.sections.non_goals[:3])
    if boundary_line:
        items.append(
            {
                "title": boundary_line,
                "level": "中",
                "mitigation": "实现时严格限制在主改路径内，避免把非目标仓库和场景带入本次改造。",
                "blocking": False,
            }
        )
    if not items and repo_decisions:
        items.append(
            {
                "title": "当前设计已收敛到最小改动范围，但仍需关注实现阶段的联动回归。",
                "level": "低",
                "mitigation": "优先覆盖主链路和非目标回归。",
                "blocking": False,
            }
        )
    return items[:5]


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

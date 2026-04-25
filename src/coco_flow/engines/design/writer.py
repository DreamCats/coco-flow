from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.prompts.design import build_writer_prompt

from .agent_io import run_agent_markdown_with_new_session
from .models import DesignInputBundle
from .utils import as_str_list, dict_list


def write_design_markdown(
    prepared: DesignInputBundle,
    decision_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> str:
    if native_ok:
        try:
            return run_agent_markdown_with_new_session(
                prepared,
                settings,
                build_local_design_markdown(prepared, decision_payload),
                lambda template_path: build_writer_prompt(
                    title=prepared.title,
                    decision_payload=decision_payload,
                    template_path=template_path,
                ),
                ".design-writer-",
                role="design_writer",
                stage="writer",
                on_log=on_log,
            )
        except Exception as error:
            on_log(f"design_v3_writer_degraded: {error}")
    return build_local_design_markdown(prepared, decision_payload)


def write_doc_only_design_markdown(
    prepared: DesignInputBundle,
    research_summary_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> str:
    draft = build_local_doc_only_design_markdown(prepared, research_summary_payload)
    if native_ok:
        try:
            return run_agent_markdown_with_new_session(
                prepared,
                settings,
                draft,
                lambda template_path: _build_doc_only_design_prompt(prepared, research_summary_payload, template_path),
                ".design-writer-",
                role="design_writer",
                stage="writer_doc_only",
                on_log=on_log,
            )
        except Exception as error:
            on_log(f"design_writer_fallback: {error}")
    return draft


def build_local_doc_only_design_markdown(prepared: DesignInputBundle, research_summary_payload: dict[str, object]) -> str:
    candidate_files = _research_candidate_files(research_summary_payload)
    lines = [
        f"# {prepared.title} Design",
        "",
        "## 结论",
        "本设计以 prd-refined.md、绑定仓库代码证据和 Skills/SOP 为事实源，按最小改动范围推进。",
        "",
        "## 核心改造点",
    ]
    for index, item in enumerate(prepared.sections.change_scope or [prepared.title], start=1):
        lines.append(f"{index}. {item}")
    lines.extend(["", "## 分仓库方案"])
    for scope in prepared.repo_scopes:
        files = candidate_files.get(scope.repo_id, [])
        lines.extend(["", f"### {scope.repo_id}", f"- 仓库路径：{scope.repo_path}"])
        if files:
            lines.append("- 代码线索：" + "、".join(files[:8]))
        else:
            lines.append("- 代码线索：以本仓库上下文和 Skills/SOP 继续收敛。")
    if prepared.design_skills_brief_markdown.strip():
        lines.extend(["", "## SOP 与业务规则", prepared.design_skills_brief_markdown.strip()])
    lines.extend(["", "## 风险与待确认"])
    if prepared.sections.open_questions:
        lines.extend(f"- {item}" for item in prepared.sections.open_questions)
    else:
        lines.append("- 若代码证据与本文档判断冲突，以仓库真实职责和 SOP 为准，先修正 design.md 再进入 Plan。")
    if prepared.sections.non_goals:
        lines.extend(["", "## 明确不做"])
        lines.extend(f"- {item}" for item in prepared.sections.non_goals)
    return "\n".join(lines).rstrip() + "\n"


def _build_doc_only_design_prompt(prepared: DesignInputBundle, research_summary_payload: dict[str, object], template_path: str) -> str:
    return (
        "你在做 coco-flow Design 阶段。当前第一版采用文档流，不使用结构化 Design schema。\n\n"
        f"请直接编辑模板文件：{template_path}\n"
        "保留 Markdown 文档形态，输出可给研发评审和后续 Plan 使用的 design.md。\n"
        "只允许依据 prd-refined.md、绑定仓库代码证据、仓库职责和 Skills/SOP；不要输出 JSON，不要发明新需求。\n\n"
        f"## 任务标题\n{prepared.title}\n\n"
        f"## prd-refined.md\n{prepared.refined_markdown.strip()}\n\n"
        f"## 绑定仓库\n{_repo_scope_text(prepared)}\n\n"
        f"## Repo research summary\n{research_summary_payload}\n\n"
        f"## Skills/SOP 摘要\n{prepared.design_skills_brief_markdown.strip() or '当前没有额外 Skills/SOP 摘要。'}\n\n"
        "完成后只需简短回复已完成。"
    )


def _research_candidate_files(payload: dict[str, object]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    raw = payload.get("repos")
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("repo_id") or "").strip()
        files = as_str_list(item.get("candidate_files"))
        if repo_id and files:
            result[repo_id] = files
    return result


def _repo_scope_text(prepared: DesignInputBundle) -> str:
    lines = []
    for scope in prepared.repo_scopes:
        lines.append(f"- {scope.repo_id}: {scope.repo_path}")
    return "\n".join(lines) or "- 未绑定仓库"


def build_local_design_markdown(prepared: DesignInputBundle, decision_payload: dict[str, object]) -> str:
    blocking_count = int(decision_payload.get("review_blocking_count") or 0)
    finalized = bool(decision_payload.get("finalized"))
    parts = [
        f"# {prepared.title} Design",
        "",
        "## 结论",
        _local_design_conclusion(decision_payload, blocking_count, finalized),
        "",
        "## 核心改造点",
    ]
    for index, item in enumerate(as_str_list(decision_payload.get("core_change_points")) or prepared.sections.change_scope or [prepared.title], start=1):
        parts.append(f"{index}. {item}")
    parts.extend(["", "## 分仓库方案"])
    for item in dict_list(decision_payload.get("repo_decisions")):
        repo_id = str(item.get("repo_id") or "")
        work_type = str(item.get("work_type") or "")
        action = "主要代码改造" if work_type in {"must_change", "co_change"} else "联动检查" if work_type == "validate_only" else "参考"
        parts.extend(["", f"### {repo_id}", f"- 主要事项：{action}。{str(item.get('responsibility') or '').strip()}"])
        files = as_str_list(item.get("candidate_files"))
        if files:
            parts.append("- 候选文件：" + "、".join(files[:8]))
        boundaries = as_str_list(item.get("boundaries"))
        if boundaries:
            parts.append("- 边界：" + "；".join(boundaries[:4]))
    dependencies = dict_list(decision_payload.get("repo_dependencies"))
    if dependencies:
        parts.extend(["", "## 仓库依赖与发布顺序"])
        for item in dependencies:
            upstream = str(item.get("upstream_repo_id") or "").strip()
            downstream = str(item.get("downstream_repo_id") or "").strip()
            reason = str(item.get("reason") or "").strip()
            required_for = str(item.get("required_for") or "").strip()
            if not upstream or not downstream:
                continue
            detail = f"{upstream} -> {downstream}"
            if reason:
                detail += f"：{reason}"
            parts.append(f"- {detail}")
            if required_for:
                parts.append(f"  - 前置关系：{required_for}")
    risks = as_str_list(decision_payload.get("risks"))
    unresolved = as_str_list(decision_payload.get("unresolved_questions"))
    parts.extend(["", "## 风险与待确认"])
    if risks or unresolved:
        for item in [*risks, *unresolved]:
            parts.append(f"- {item}")
    else:
        parts.append("- 暂无阻塞性待确认项。")
    if blocking_count > 0 and not finalized:
        parts.extend(["", "## 当前阻断", "- Skeptic review 仍存在阻塞问题，当前 Design 不能进入 Plan。"])
    if prepared.sections.non_goals:
        parts.extend(["", "## 明确不做"])
        parts.extend(f"- {item}" for item in prepared.sections.non_goals)
    return "\n".join(parts).rstrip() + "\n"


def _local_design_conclusion(decision_payload: dict[str, object], blocking_count: int, finalized: bool) -> str:
    summary = str(decision_payload.get("decision_summary") or "本阶段已形成初版设计裁决。").strip()
    if blocking_count > 0 and not finalized:
        return f"当前不能进入 Plan。{summary}"
    return summary

"""Design Markdown 写作器。

本文件只负责生成 doc-only design.md：先构造本地草稿，再在 native 模式下
让 agent 直接编辑 Markdown 模板；失败时回退到本地草稿。
"""

from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.prompts.design import build_doc_only_design_prompt

from coco_flow.engines.design.quality import ensure_inferred_open_questions, infer_design_open_questions, merge_open_questions
from coco_flow.engines.design.runtime import run_agent_markdown_with_new_session
from coco_flow.engines.design.support import as_str_list, dict_list, first_non_empty
from coco_flow.engines.design.types import DesignInputBundle


def write_doc_only_design_markdown(
    prepared: DesignInputBundle,
    research_summary_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> str:
    research_summary_markdown = render_research_summary_markdown(research_summary_payload)
    draft = build_local_doc_only_design_markdown(prepared, research_summary_payload)
    if native_ok:
        try:
            generated = run_agent_markdown_with_new_session(
                prepared,
                settings,
                draft,
                lambda template_path: build_doc_only_design_prompt(
                    title=prepared.title,
                    refined_markdown=prepared.refined_markdown,
                    repo_scope_markdown=_repo_scope_text(prepared),
                    research_summary_markdown=research_summary_markdown,
                    skills_index_markdown=prepared.design_skills_index_markdown,
                    skills_fallback_markdown=prepared.design_skills_fallback_markdown,
                    template_path=template_path,
                ),
                ".design-writer-",
                role="design_writer",
                stage="writer_doc_only",
                on_log=on_log,
            )
            if _design_markdown_is_actionable(generated):
                return _ensure_design_quality(prepared, generated, on_log)
            on_log("design_writer_fallback: shallow_design_markdown")
        except Exception as error:
            on_log(f"design_writer_fallback: {error}")
    return _ensure_design_quality(prepared, draft, on_log)


def build_local_doc_only_design_markdown(prepared: DesignInputBundle, research_summary_payload: dict[str, object]) -> str:
    repos_by_id = _research_repos_by_id(research_summary_payload)
    acceptance = prepared.sections.acceptance_criteria
    non_goals = prepared.sections.non_goals
    open_questions = merge_open_questions(
        prepared.sections.open_questions,
        infer_design_open_questions(prepared.sections),
    )
    lines = [
        f"# {prepared.title} Design",
        "",
        "## 结论",
        "本设计以 prd-refined.md、绑定仓库调研和 Skills/SOP 为事实源，按最小改动范围推进。",
        "",
        "## 核心改造点",
    ]
    for index, item in enumerate(prepared.sections.change_scope or [prepared.title], start=1):
        lines.append(f"{index}. {item}")
    lines.extend(["", "## 方案设计"])
    lines.extend(f"- {item}" for item in _solution_design_points(prepared))
    lines.extend(["", "## 分仓库职责"])
    for scope in prepared.repo_scopes:
        repo_payload = repos_by_id.get(scope.repo_id, {})
        lines.extend(["", f"### {scope.repo_id}", f"- 仓库路径：{scope.repo_path}"])
        work_hypothesis = str(repo_payload.get("work_hypothesis") or "").strip()
        if work_hypothesis:
            lines.append(f"- 职责判断：{_work_hypothesis_label(work_hypothesis)}")
        lines.append("- 改造方案：")
        lines.extend(f"  - {item}" for item in _repo_solution_points(repo_payload, prepared))
        repo_boundaries = as_str_list(repo_payload.get("boundaries"))
        if repo_boundaries or non_goals:
            lines.append("- 边界：")
            lines.extend(f"  - {item}" for item in [*repo_boundaries[:3], *non_goals[:6]])
    lines.extend(["", "## 验收与验证"])
    if acceptance:
        lines.extend(f"- {item}" for item in acceptance[:10])
    else:
        lines.append("- 按 prd-refined.md 的验收标准做最小验证。")
    if prepared.design_skills_fallback_markdown.strip():
        lines.extend(["", "## SOP 与业务规则"])
        lines.append("- 已参考 Design Skills/SOP 做业务边界判断；详细匹配记录见 design-skills.json。")
    lines.extend(["", "## 风险与待确认"])
    if open_questions:
        lines.extend(f"- {item}" for item in open_questions)
    else:
        lines.append("- 若代码证据与本文档判断冲突，以仓库真实职责和 SOP 为准，先修正 design.md 再进入 Plan。")
    if prepared.sections.non_goals:
        lines.extend(["", "## 明确不做"])
        lines.extend(f"- {item}" for item in prepared.sections.non_goals)
    return "\n".join(lines).rstrip() + "\n"


def _ensure_design_quality(prepared: DesignInputBundle, markdown: str, on_log) -> str:
    repaired, added_count = ensure_inferred_open_questions(markdown, prepared.sections)
    if added_count:
        on_log(f"design_quality_repair: inferred_open_questions_added={added_count}")
    return repaired

def render_research_summary_markdown(payload: dict[str, object]) -> str:
    lines: list[str] = []
    for repo in dict_list(payload.get("repos")):
        repo_id = str(repo.get("repo_id") or "").strip() or "unknown"
        work_hypothesis = str(repo.get("work_hypothesis") or "").strip()
        summary = str(repo.get("summary") or "").strip()
        candidates = _candidate_file_items(repo)
        excluded = _excluded_file_items(repo)
        unknowns = as_str_list(repo.get("unknowns"))
        boundaries = as_str_list(repo.get("boundaries"))

        lines.append(f"### {repo_id}")
        if work_hypothesis:
            lines.append(f"- 调研判断：{_work_hypothesis_label(work_hypothesis)}")
        if summary:
            lines.append(f"- 摘要：{summary}")
        if candidates:
            lines.append("- 候选文件：")
            lines.extend(f"  - `{item['path']}`：{item['reason']}" for item in candidates[:8])
        else:
            lines.append("- 候选文件：暂无明确核心文件。")
        if excluded:
            lines.append("- 排除文件：")
            lines.extend(f"  - `{item['path']}`：{item['reason']}" for item in excluded[:8])
        if boundaries:
            lines.append("- 边界：")
            lines.extend(f"  - {item}" for item in boundaries[:5])
        if unknowns:
            lines.append("- 待确认：")
            lines.extend(f"  - {item}" for item in unknowns[:5])
        lines.append("")
    return "\n".join(lines).rstrip()


def _design_markdown_is_actionable(markdown: str) -> bool:
    normalized = markdown.strip()
    if not normalized:
        return False
    has_solution = any(keyword in normalized for keyword in ("改造方案", "技术方案", "方案落点", "实现方案"))
    has_validation = any(keyword in normalized for keyword in ("验收与验证", "验证方案", "验证关注", "验收标准"))
    has_repo_section = any(section in normalized for section in ("## 分仓库职责", "## 分仓库方案", "## 仓库方案"))
    return has_solution and has_validation and has_repo_section


def _research_repos_by_id(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for repo in dict_list(payload.get("repos")):
        repo_id = str(repo.get("repo_id") or "").strip()
        if repo_id:
            result[repo_id] = repo
    return result


def _research_candidate_files(payload: dict[str, object]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    raw = payload.get("repos")
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("repo_id") or "").strip()
        files = _candidate_file_items(item)
        if repo_id and files:
            result[repo_id] = files
    return result


def _candidate_file_items(repo: dict[str, object]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    raw = repo.get("candidate_files")
    dict_items = dict_list(raw)
    for item in dict_items:
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        reason = _candidate_reason(item)
        result.append({"path": path, "reason": reason})
    if not dict_items:
        for path in as_str_list(raw):
            result.append({"path": path, "reason": "代码调研命中该文件。"})
    return result


def _excluded_file_items(repo: dict[str, object]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in dict_list(repo.get("excluded_files")):
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        reason = str(item.get("exclude_reason") or "").strip() or "命中 PRD 明确不做范围。"
        result.append({"path": path, "reason": reason})
    return result


def _candidate_reason(item: dict[str, object]) -> str:
    matched = str(item.get("matched_behavior") or "").strip()
    reason = str(item.get("reason") or "").strip()
    if matched:
        return f"命中 {matched} 相关代码证据。"
    if reason:
        return reason
    return "代码调研命中该文件。"


def _solution_design_points(prepared: DesignInputBundle) -> list[str]:
    change_scope = prepared.sections.change_scope or [prepared.title]
    points: list[str] = []
    visible_change = first_non_empty(change_scope, prepared.title)
    points.append(f"用户可见变化：{visible_change}")
    points.append("服务端策略：在最靠近用户可见表达的数据组装层完成改造，避免扩大到非目标链路。")
    if len(change_scope) > 1:
        points.append("覆盖范围：" + "；".join(change_scope[1:4]) + "。")
    if prepared.sections.acceptance_criteria:
        points.append("实验与回退：命中实验时启用新表现；未命中、取值异常或依赖缺失时保持现有线上逻辑。")
    if prepared.sections.non_goals:
        points.append("隔离边界：不触碰明确不做的链路，相关代码即使被搜索命中也不能作为主改造范围。")
    return points


def _repo_solution_points(repo_payload: dict[str, object], prepared: DesignInputBundle) -> list[str]:
    change_scope = prepared.sections.change_scope or [prepared.title]
    work_hypothesis = str(repo_payload.get("work_hypothesis") or "").strip()
    points: list[str] = []
    normalized = _normalize_work_hypothesis(work_hypothesis)
    if normalized == "required":
        points.append("本仓承担本次需求的核心服务端表达或数据组装改造。")
        points.append("改造层级应收敛在业务表达层或数据转换层，不扩大到无关公共链路。")
    elif normalized == "conditional":
        points.append("本仓属于条件改造：仅当缺少公共字段、配置或协议能力时才需要改动。")
        points.append("进入 Plan 前需要先确认是否已有可复用能力，避免把公共仓误判为必改。")
    elif normalized == "reference_only":
        points.append("本仓仅作为业务规则或公共能力参考，不应默认纳入代码改造。")
    elif normalized == "not_needed":
        points.append("本仓不在本次实现范围内，仅保留为明确边界。")
    elif normalized == "validate_only":
        points.append("本仓主要用于验证边界，不应直接扩大为实现范围。")
    else:
        points.append("当前证据不足以直接判定本仓必须改造，需要在进入 Plan 前确认职责。")
    if prepared.sections.acceptance_criteria:
        points.append("保留验收标准中的实验命中、异常回退、未命中不变等行为约束。")
    return points


def _work_hypothesis_label(value: str) -> str:
    labels = {
        "required": "必改",
        "conditional": "条件改",
        "reference_only": "仅作为参考",
        "not_needed": "不改",
        "unknown": "职责待确认",
        "requires_code_change": "需要代码改造",
        "needs_human_confirmation": "需要人工确认职责或补充搜索术语",
        "validate_only": "仅需验证边界",
    }
    return labels.get(value, value)


def _normalize_work_hypothesis(value: str) -> str:
    aliases = {
        "requires_code_change": "required",
        "needs_human_confirmation": "unknown",
    }
    return aliases.get(value, value)


def _repo_scope_text(prepared: DesignInputBundle) -> str:
    lines = []
    for scope in prepared.repo_scopes:
        lines.append(f"- {scope.repo_id}: {scope.repo_path}")
    return "\n".join(lines) or "- 未绑定仓库"

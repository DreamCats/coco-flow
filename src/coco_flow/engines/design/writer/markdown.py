"""Design Markdown 写作器。

本文件只负责生成 doc-only design.md：先构造本地草稿，再在 native 模式下
让 agent 直接编辑 Markdown 模板；失败时回退到本地草稿。
"""

from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.prompts.design import build_doc_only_design_prompt

from coco_flow.engines.design.runtime import run_agent_markdown_with_new_session
from coco_flow.engines.design.support import as_str_list, dict_list
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
                return generated
            on_log("design_writer_fallback: shallow_design_markdown")
        except Exception as error:
            on_log(f"design_writer_fallback: {error}")
    return draft


def build_local_doc_only_design_markdown(prepared: DesignInputBundle, research_summary_payload: dict[str, object]) -> str:
    candidate_files = _research_candidate_files(research_summary_payload)
    repos_by_id = _research_repos_by_id(research_summary_payload)
    acceptance = prepared.sections.acceptance_criteria
    non_goals = prepared.sections.non_goals
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
        repo_payload = repos_by_id.get(scope.repo_id, {})
        lines.extend(["", f"### {scope.repo_id}", f"- 仓库路径：{scope.repo_path}"])
        work_hypothesis = str(repo_payload.get("work_hypothesis") or "").strip()
        if work_hypothesis:
            lines.append(f"- 职责判断：{_work_hypothesis_label(work_hypothesis)}")
        if files:
            lines.append("- 代码线索：")
            lines.extend(f"  - `{item['path']}`：{item['reason']}" for item in files[:8])
        else:
            lines.append("- 代码线索：以本仓库上下文和 Skills/SOP 继续收敛。")
        lines.append("- 改造方案：")
        lines.extend(f"  - {item}" for item in _repo_solution_points(files, prepared))
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
        lines.extend(["", "## SOP 与业务规则", prepared.design_skills_fallback_markdown.strip()])
    lines.extend(["", "## 风险与待确认"])
    if prepared.sections.open_questions:
        lines.extend(f"- {item}" for item in prepared.sections.open_questions)
    else:
        lines.append("- 若代码证据与本文档判断冲突，以仓库真实职责和 SOP 为准，先修正 design.md 再进入 Plan。")
    if prepared.sections.non_goals:
        lines.extend(["", "## 明确不做"])
        lines.extend(f"- {item}" for item in prepared.sections.non_goals)
    return "\n".join(lines).rstrip() + "\n"

def render_research_summary_markdown(payload: dict[str, object]) -> str:
    lines: list[str] = []
    for repo in dict_list(payload.get("repos")):
        repo_id = str(repo.get("repo_id") or "").strip() or "unknown"
        work_hypothesis = str(repo.get("work_hypothesis") or "").strip()
        summary = str(repo.get("summary") or "").strip()
        candidates = _candidate_file_items(repo)
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
    has_repo_section = "## 分仓库方案" in normalized or "## 仓库方案" in normalized
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


def _candidate_reason(item: dict[str, object]) -> str:
    matched = str(item.get("matched_behavior") or "").strip()
    reason = str(item.get("reason") or "").strip()
    if matched:
        return f"命中 {matched} 相关代码证据。"
    if reason:
        return reason
    return "代码调研命中该文件。"


def _repo_solution_points(files: list[dict[str, str]], prepared: DesignInputBundle) -> list[str]:
    change_scope = prepared.sections.change_scope or [prepared.title]
    points: list[str] = []
    if files:
        file_names = "、".join(f"`{item['path']}`" for item in files[:3])
        points.append(f"以 {file_names} 为优先落点，定位现有标题、文案、配置或 DTO/converter 组装逻辑。")
    else:
        points.append("先按代码调研线索补充定位核心落点；证据不足时不要直接扩大为代码改造。")
    points.extend(f"落实需求点：{item}" for item in change_scope[:4])
    if prepared.sections.acceptance_criteria:
        points.append("实现时保留验收标准中的实验命中、异常回退、未命中不变等行为约束。")
    return points


def _work_hypothesis_label(value: str) -> str:
    labels = {
        "requires_code_change": "需要代码改造",
        "needs_human_confirmation": "需要人工确认职责或补充搜索术语",
        "reference_only": "仅作为参考",
        "validate_only": "仅需验证边界",
    }
    return labels.get(value, value)


def _repo_scope_text(prepared: DesignInputBundle) -> str:
    lines = []
    for scope in prepared.repo_scopes:
        lines.append(f"- {scope.repo_id}: {scope.repo_path}")
    return "\n".join(lines) or "- 未绑定仓库"

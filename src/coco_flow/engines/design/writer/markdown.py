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
            return run_agent_markdown_with_new_session(
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
            lines.append("- 代码线索：")
            lines.extend(f"  - `{item['path']}`：{item['reason']}" for item in files[:8])
        else:
            lines.append("- 代码线索：以本仓库上下文和 Skills/SOP 继续收敛。")
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

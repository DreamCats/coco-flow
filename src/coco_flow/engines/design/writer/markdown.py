"""Design Markdown 写作器。

本文件只负责生成 doc-only design.md：先构造本地草稿，再在 native 模式下
让 agent 直接编辑 Markdown 模板；失败时回退到本地草稿。
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from coco_flow.config import Settings
from coco_flow.prompts.design import build_doc_only_design_prompt, build_doc_only_design_repair_prompt

from coco_flow.engines.design.quality import (
    design_markdown_is_actionable,
    infer_design_open_questions,
    merge_open_questions,
    repair_low_risk_design_quality,
)
from coco_flow.engines.design.runtime import run_agent_markdown_with_new_session
from coco_flow.engines.design.support import as_str_list, dict_list, first_non_empty
from coco_flow.engines.design.types import DesignInputBundle

_FIELD_DEFINITION_PATH_MARKERS = (
    "abtest/struct",
    "config",
    "schema",
    ".proto",
    ".thrift",
)


@dataclass
class DesignWriterDraft:
    markdown: str
    local_draft_markdown: str
    native_markdown: str = ""
    source: str = "local"


def write_doc_only_design_markdown(
    prepared: DesignInputBundle,
    research_summary_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> str:
    result = write_doc_only_design_draft(prepared, research_summary_payload, settings, native_ok=native_ok, on_log=on_log)
    if result.source == "native" and not design_markdown_is_actionable(result.markdown):
        on_log("design_writer_fallback: shallow_design_markdown")
        return _ensure_design_quality(prepared, result.local_draft_markdown, on_log)
    return result.markdown


def write_doc_only_design_draft(
    prepared: DesignInputBundle,
    research_summary_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> DesignWriterDraft:
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
            return DesignWriterDraft(
                markdown=_ensure_design_quality(prepared, generated, on_log),
                local_draft_markdown=draft,
                native_markdown=generated,
                source="native",
            )
        except Exception as error:
            on_log(f"design_writer_fallback: {error}")
    return DesignWriterDraft(
        markdown=_ensure_design_quality(prepared, draft, on_log),
        local_draft_markdown=draft,
        source="local",
    )


def repair_doc_only_design_markdown(
    prepared: DesignInputBundle,
    research_summary_payload: dict[str, object],
    current_markdown: str,
    repair_instructions: list[str],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> str:
    if not native_ok or not repair_instructions:
        return current_markdown
    try:
        research_summary_markdown = render_research_summary_markdown(research_summary_payload)
        repaired = run_agent_markdown_with_new_session(
            prepared,
            settings,
            current_markdown,
            lambda template_path: build_doc_only_design_repair_prompt(
                title=prepared.title,
                refined_markdown=prepared.refined_markdown,
                research_summary_markdown=research_summary_markdown,
                current_design_markdown=current_markdown,
                repair_instructions=repair_instructions,
                template_path=template_path,
            ),
            ".design-writer-repair-",
            role="design_writer",
            stage="writer_repair",
            on_log=on_log,
        )
        on_log("design_writer_repair_ok: true")
        return _ensure_design_quality(prepared, repaired, on_log)
    except Exception as error:
        on_log(f"design_writer_repair_failed: {error}")
        return current_markdown


def build_local_doc_only_design_markdown(prepared: DesignInputBundle, research_summary_payload: dict[str, object]) -> str:
    repos_by_id = _research_repos_by_id(research_summary_payload)
    acceptance = prepared.sections.acceptance_criteria
    non_goals = prepared.sections.non_goals
    open_questions = merge_open_questions(
        merge_open_questions(prepared.sections.open_questions, infer_design_open_questions(prepared.sections)),
        _fallback_open_questions(prepared, research_summary_payload),
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
        focus_files = _repo_focus_files(repo_payload, prepared)
        if focus_files:
            lines.append("- 涉及模块/文件：")
            lines.extend(f"  - `{item['path']}`：{item['purpose']}" for item in focus_files[:4])
        elif dict_list(repo_payload.get("candidate_files")):
            lines.append("- 涉及模块/文件：当前调研只证明存在相关链路，尚不足以确定精准文件落点；进入 Plan 前需要先补充定位。")
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
    return repair_low_risk_design_quality(markdown, prepared.sections, on_log)


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


def _repo_focus_files(repo_payload: dict[str, object], prepared: DesignInputBundle) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in dict_list(repo_payload.get("candidate_files")):
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        matched_terms = _matched_focus_terms(path, item, prepared)
        if not matched_terms and not _is_field_definition_candidate(path, repo_payload, prepared):
            continue
        result.append({"path": path, "purpose": _focus_file_purpose(path, item, matched_terms)})
    return result


def _focus_file_purpose(path: str, item: dict[str, object], matched_terms: list[str]) -> str:
    behavior = str(item.get("matched_behavior") or "").strip()
    scene = str(item.get("scene") or "").strip()
    if matched_terms:
        return "依据：调研命中具体改造语义：" + "、".join(matched_terms[:4]) + "。"
    if behavior:
        return f"作为 {behavior} 相关方案落点候选。"
    if scene:
        return f"作为 {scene} 下的方案落点候选。"
    name = path.rsplit("/", 1)[-1]
    return f"作为 {name} 对应职责的方案落点候选。"


def _matched_focus_terms(path: str, item: dict[str, object], prepared: DesignInputBundle) -> list[str]:
    candidate_terms = _path_and_symbol_terms(path, str(item.get("symbol") or ""))
    if not candidate_terms:
        return []
    prepared_terms = set(_prepared_focus_terms(prepared))
    return [term for term in candidate_terms if term.lower() in prepared_terms]


def _path_and_symbol_terms(path: str, symbol: str) -> list[str]:
    text = f"{path} {symbol}"
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text)
    terms.extend(re.findall(r"[\u4e00-\u9fff]{2,12}", text))
    return as_str_list(terms)


def _prepared_focus_terms(prepared: DesignInputBundle) -> list[str]:
    text = "\n".join(
        [
            prepared.title,
            *prepared.sections.change_scope,
            *prepared.sections.key_constraints,
            *prepared.sections.acceptance_criteria,
        ]
    )
    terms = re.findall(r"`([^`]{2,80})`", text)
    terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text))
    terms.extend(re.findall(r"[\u4e00-\u9fff]{2,12}", text))
    non_goal_text = "\n".join(prepared.sections.non_goals).lower()
    return [term.lower() for term in as_str_list(terms) if term.lower() not in non_goal_text]


def _is_field_definition_candidate(path: str, repo_payload: dict[str, object], prepared: DesignInputBundle) -> bool:
    if str(repo_payload.get("work_hypothesis") or "") != "conditional":
        return False
    if not _looks_experiment_driven(prepared):
        return False
    path_lower = path.lower()
    return any(marker in path_lower for marker in _FIELD_DEFINITION_PATH_MARKERS)


def _solution_design_points(prepared: DesignInputBundle) -> list[str]:
    change_scope = prepared.sections.change_scope or [prepared.title]
    points: list[str] = []
    visible_change = first_non_empty(change_scope, prepared.title)
    points.append(f"用户可见变化：{visible_change}")
    points.append("服务端策略：在最靠近用户可见表达的数据组装层完成改造，避免扩大到非目标链路。")
    if _looks_experiment_driven(prepared):
        points.append("实验控制：优先复用已有实验或配置能力；如需新增字段，默认值必须保持线上逻辑不变。")
    if len(change_scope) > 1:
        points.append("覆盖范围：" + "；".join(change_scope[1:4]) + "。")
    if prepared.sections.acceptance_criteria:
        points.append("实验与回退：命中实验时启用新表现；未命中、取值异常或依赖缺失时保持现有线上逻辑。")
    if prepared.sections.non_goals:
        points.append("隔离边界：不触碰明确不做的链路，相关模块即使被调研识别也不能作为主改造范围。")
    return points


def _repo_solution_points(repo_payload: dict[str, object], prepared: DesignInputBundle) -> list[str]:
    change_scope = prepared.sections.change_scope or [prepared.title]
    work_hypothesis = str(repo_payload.get("work_hypothesis") or "").strip()
    points: list[str] = []
    normalized = _normalize_work_hypothesis(work_hypothesis)
    if normalized == "required":
        points.append("本仓承担本次需求的核心服务端表达或数据组装改造。")
        points.append("改造层级应收敛在业务表达层或数据转换层，不扩大到无关公共链路。")
        if _looks_experiment_driven(prepared):
            points.append("按实验或配置命中结果启用新表现；字段缺失、默认值或异常值时保持现有表现。")
    elif normalized == "conditional":
        points.append("本仓属于条件改造：仅当缺少公共字段、配置或协议能力时才需要改动。")
        points.append("进入 Plan 前需要先确认是否已有可复用能力；如需新增字段，应明确字段名、默认值和兼容语义。")
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


def _fallback_open_questions(prepared: DesignInputBundle, research_summary_payload: dict[str, object]) -> list[str]:
    questions: list[str] = []
    text = _prepared_text(prepared)
    if _looks_experiment_driven(prepared) and _has_conditional_or_common_repo(research_summary_payload):
        questions.append("待确认：实验或配置字段是否已有可复用能力；如需新增，需确认字段名、key、默认值和枚举含义。")
    if any(marker in text for marker in ("空", "回退", "fallback")):
        questions.append("待确认：用户可见表达所需资源、默认值和异常为空时的回退策略是否已有统一实现。")
    return questions


def _looks_experiment_driven(prepared: DesignInputBundle) -> bool:
    text = _prepared_text(prepared)
    return any(marker in text for marker in ("实验", "ab", "a/b", "命中", "灰度", "配置"))


def _has_conditional_or_common_repo(research_summary_payload: dict[str, object]) -> bool:
    for repo in dict_list(research_summary_payload.get("repos")):
        repo_text = f"{repo.get('repo_id') or ''} {repo.get('repo_path') or ''}".lower()
        if str(repo.get("work_hypothesis") or "") == "conditional":
            return True
        if any(marker in repo_text for marker in ("common", "shared", "config", "schema", "idl")):
            return True
    return False


def _prepared_text(prepared: DesignInputBundle) -> str:
    return "\n".join(
        [
            prepared.title,
            prepared.refined_markdown,
            *prepared.sections.change_scope,
            *prepared.sections.key_constraints,
            *prepared.sections.acceptance_criteria,
            *prepared.sections.non_goals,
        ]
    ).lower()


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

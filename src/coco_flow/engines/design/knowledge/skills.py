"""Design Skills/SOP 选择与渐进式加载索引。

按 refined PRD、绑定仓库和业务术语筛选相关 Skill，将业务地图、仓库角色、
多仓联动和 SOP 规则整理成 native agent 可读取完整文件的索引。
fallback excerpt 只保留给 local fallback 使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from coco_flow.config import Settings
from coco_flow.services.queries.skills import SkillPackage, SkillStore

from coco_flow.engines.design.support import as_str_list, dedupe
from coco_flow.engines.design.types import DesignInputBundle

_MAX_SELECTED_SKILLS = 4
_MAX_TERMS = 18
_MAX_LINES_PER_BLOCK = 8
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "this",
    "that",
    "prd",
    "refined",
    "design",
}
_NEGATIVE_STOPWORDS = {
    "人工",
    "提炼",
    "范围",
    "系统",
    "改动",
    "面板",
    "卡片",
    "应回",
    "应回到",
    "之外",
    "状态",
    "链路",
    "默认",
    "调整",
    "阶段",
    "补充",
    "不扩",
    "扩大",
}


@dataclass(frozen=True)
class _SkillDocument:
    package: SkillPackage
    body: str
    references: list[tuple[str, Path, str]]


def build_design_skills_bundle(
    prepared: DesignInputBundle,
    settings: Settings,
) -> tuple[str, str, dict[str, object], list[str]]:
    documents = [_package_to_document(package) for package in SkillStore(settings).list_packages()]
    scored: list[tuple[int, dict[str, object], _SkillDocument]] = []
    unmatched: list[dict[str, object]] = []
    for document in documents:
        payload = score_design_skill_document(document, prepared)
        score = int(payload.get("score") or 0)
        if score > 0:
            scored.append((score, payload, document))
        else:
            unmatched.append(payload)
    scored.sort(key=lambda item: (-item[0], item[2].package.name))
    selected = scored[:_MAX_SELECTED_SKILLS]
    selected_documents = [item[2] for item in selected]
    selection_payload = {
        "selected_skill_ids": [item[2].package.id for item in selected],
        "selected_skill_titles": [item[2].package.name for item in selected],
        "selected_skill_sources": [_skill_source_payload(item[2], item[1]) for item in selected],
        "candidates": [item[1] for item in scored] + unmatched,
    }
    if not selected:
        return "", "", selection_payload, []
    index = render_design_skills_index(selected_documents, selection_payload["selected_skill_sources"])
    fallback = render_design_skills_fallback(selected_documents, prepared)
    return index, fallback, selection_payload, [item[2].package.id for item in selected]


def score_design_skill_document(document: _SkillDocument, prepared: DesignInputBundle) -> dict[str, object]:
    terms = _infer_design_skill_terms(prepared)
    negative_terms = _infer_design_negative_terms(prepared)
    searchable = "\n".join(
        [
            document.package.name,
            document.package.description,
            document.package.domain,
            document.body,
        ]
    )
    keyword_hits = [
        term
        for term in terms
        if term.lower() in searchable.lower()
    ]
    repo_hits = _repo_hits(document, prepared)
    workflow_hits = _line_hits(
        document.body,
        ("workflow", "工作流", "主责任", "联动", "数据编排", "状态口径", "实验开关", "公共配置"),
        max_lines=6,
    )
    negative_hits = [term for term in negative_terms if _is_negative_hit(term, searchable)]
    score = min(len(keyword_hits), 6) + len(repo_hits) * 4 + min(len(workflow_hits), 3) * 2
    if keyword_hits:
        score += 2
    score -= min(len(negative_hits), 4) * 4
    score = max(score, 0)
    return {
        "id": document.package.id,
        "title": document.package.name,
        "domain": document.package.domain,
        "score": score,
        "keyword_hits": keyword_hits[:10],
        "repo_hits": repo_hits,
        "workflow_hits": workflow_hits[:4],
        "negative_hits": negative_hits[:8],
        "selected_references": _selected_reference_names(document, terms),
    }


def render_design_skills_fallback(documents: list[_SkillDocument], prepared: DesignInputBundle) -> str:
    lines = [
        "# Design Skills Local Fallback",
        "",
        "- 用途：仅用于 Design 阶段判断业务 workflow、repo 角色、多仓联动、SOP 和风险边界。",
        "- 优先级：refined PRD 与 repo research 证据优先于 skills；skills 不得单独证明某仓必须改代码。",
        "",
    ]
    for document in documents:
        lines.extend(
            [
                f"## {document.package.name}",
                "",
                f"- id: {document.package.id}",
                f"- domain: {document.package.domain or 'unknown'}",
                f"- description: {document.package.description or '无'}",
                "",
                "### Workflow Signals",
                _render_block(_line_hits(document.body, ("workflow", "工作流", "场景", "主责任", "数据编排", "状态口径", "实验开关", "公共配置"))),
                "",
                "### Stable Repo Roles",
                _render_block(_line_hits(document.body, ("repo:", "role:", "stable repo roles", "role: ", "live_", "content_live"))),
                "",
                "### Multi-Repo Patterns",
                _render_block(_line_hits(document.body, ("联动", "multi-repo", "多仓", "业务仓", "producer", "consumer", "上游", "下游"))),
                "",
                "### Preferred Research Areas",
                _render_block(_research_area_lines(document.body)),
                "",
                "### Producer / Consumer Checks",
                _render_block(_producer_consumer_lines(document.body)),
                "",
                "### Dependency Rules",
                _render_dependency_rules(document.body),
                "",
                "### Gate Checks",
                _render_block(_gate_check_lines(document.body, prepared)),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_design_skills_index(documents: list[_SkillDocument], sources: list[dict[str, object]]) -> str:
    lines = [
        "# Design Skills Index",
        "",
        "- 用途：给 native agent 做渐进式加载导航；这里不是事实摘要。",
        "- 规则：选中 skill 后，agent 必须读取下列完整文件，再把 Skills/SOP 作为稳定背景使用。",
        "",
    ]
    by_id = {document.package.id: document for document in documents}
    for source in sources:
        skill_id = str(source.get("id") or "")
        document = by_id.get(skill_id)
        if document is None:
            continue
        lines.extend(
            [
                f"## {document.package.name}",
                "",
                f"- id: {document.package.id}",
                f"- domain: {document.package.domain or 'unknown'}",
                f"- description: {document.package.description or '无'}",
                f"- match_reason: {_render_match_reason(source)}",
                "- files:",
            ]
        )
        for file_path in _skill_file_paths(document):
            lines.append(f"  - `{file_path}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _package_to_document(package: SkillPackage) -> _SkillDocument:
    references: list[tuple[str, Path, str]] = []
    for path in package.reference_paths:
        try:
            references.append((str(path.relative_to(package.root_path)), path, path.read_text(encoding="utf-8").strip()))
        except OSError:
            continue
    body_parts = [package.body.strip(), *(content for _name, _path, content in references)]
    body = "\n\n".join(part for part in body_parts if part)
    return _SkillDocument(package=package, body=body, references=references)


def _infer_design_skill_terms(prepared: DesignInputBundle) -> list[str]:
    values = [
        prepared.title,
        prepared.refined_markdown[:5000],
        *prepared.sections.change_scope,
        *prepared.sections.key_constraints,
        *prepared.sections.acceptance_criteria,
    ]
    terms: list[str] = []
    for value in values:
        for token in _WORD_RE.findall(value):
            lowered = token.lower()
            if lowered not in _STOPWORDS:
                terms.append(token)
        terms.extend(re.findall(r"[\u4e00-\u9fff]{2,12}", value))
    return dedupe(terms)[:_MAX_TERMS]


def _infer_design_negative_terms(prepared: DesignInputBundle) -> list[str]:
    terms: list[str] = []
    for value in prepared.sections.non_goals:
        for token in _WORD_RE.findall(value):
            lowered = token.lower()
            if lowered not in _STOPWORDS:
                terms.append(token)
        for token in re.findall(r"[\u4e00-\u9fff]{2,12}", value):
            terms.append(token)
            terms.extend(_chinese_ngrams(token))
    return [term for term in dedupe(terms) if term not in _NEGATIVE_STOPWORDS]


def _is_negative_hit(term: str, searchable: str) -> bool:
    normalized = term.strip()
    if len(normalized) < 3 or normalized in _NEGATIVE_STOPWORDS:
        return False
    return normalized.lower() in searchable.lower()


def _chinese_ngrams(value: str) -> list[str]:
    grams: list[str] = []
    for size in (2, 3, 4):
        if len(value) < size:
            continue
        grams.extend(value[index : index + size] for index in range(0, len(value) - size + 1))
    return grams


def _repo_hits(document: _SkillDocument, prepared: DesignInputBundle) -> list[str]:
    searchable = document.body.lower()
    hits: list[str] = []
    for repo in prepared.repo_scopes:
        candidates = dedupe([repo.repo_id, *[part for part in re.split(r"[/\\]", repo.repo_path) if part]])
        if any(candidate and candidate.lower() in searchable for candidate in candidates):
            hits.append(repo.repo_id)
    return dedupe(hits)


def _selected_reference_names(document: _SkillDocument, terms: list[str]) -> list[str]:
    selected = ["SKILL.md"] if document.package.body.strip() else []
    for name, _path, content in document.references:
        if any(term.lower() in content.lower() for term in terms):
            selected.append(name)
    return dedupe(selected)[:6]


def _skill_source_payload(document: _SkillDocument, score_payload: dict[str, object]) -> dict[str, object]:
    return {
        "id": document.package.id,
        "title": document.package.name,
        "domain": document.package.domain,
        "description": document.package.description,
        "score": score_payload.get("score"),
        "keyword_hits": score_payload.get("keyword_hits") or [],
        "repo_hits": score_payload.get("repo_hits") or [],
        "workflow_hits": score_payload.get("workflow_hits") or [],
        "files": _skill_file_paths(document),
    }


def _skill_file_paths(document: _SkillDocument) -> list[str]:
    files = [str(document.package.skill_path)]
    files.extend(str(path) for _name, path, _content in document.references)
    return dedupe(files)


def _render_match_reason(source: dict[str, object]) -> str:
    parts: list[str] = []
    repo_hits = as_str_list(source.get("repo_hits"))
    keyword_hits = as_str_list(source.get("keyword_hits"))
    workflow_hits = as_str_list(source.get("workflow_hits"))
    if repo_hits:
        parts.append("repo=" + ", ".join(repo_hits[:4]))
    if keyword_hits:
        parts.append("keywords=" + ", ".join(keyword_hits[:6]))
    if workflow_hits:
        parts.append("workflow_signals=" + str(len(workflow_hits)))
    return "; ".join(parts) or "programmatic selection"


def _line_hits(body: str, keywords: tuple[str, ...], *, max_lines: int = _MAX_LINES_PER_BLOCK) -> list[str]:
    result: list[str] = []
    for line in _meaningful_lines(body):
        lowered = line.lower()
        if any(keyword.lower() in lowered for keyword in keywords):
            result.append(line)
    return dedupe(result)[:max_lines]


def _research_area_lines(body: str) -> list[str]:
    lines = _line_hits(body, ("常见模块", "module", "entities/", "abtest/", "handler/", "service/", "converter", "loader"))
    path_lines = [
        line
        for line in _meaningful_lines(body)
        if re.search(r"[\w./-]+/(?:[\w./*-]+)", line) or re.search(r"\b[A-Za-z0-9_]+(?:Converter|Loader|Provider|Handler)\b", line)
    ]
    return dedupe([*lines, *path_lines])[:_MAX_LINES_PER_BLOCK]


def _producer_consumer_lines(body: str) -> list[str]:
    lines = _line_hits(body, ("实验开关", "公共配置", "ab", "tcc", "共享配置", "公共字段", "依赖", "producer", "consumer"))
    defaults = [
        "如果 PRD 提到命中实验，Design 必须判断实验字段是否已存在，以及哪个 repo 产出该字段。",
        "若公共字段或实验开关不存在，应明确 producer repo、consumer repo 和发布顺序；证据不足时写待确认项。",
    ]
    return dedupe([*lines, *defaults])[:_MAX_LINES_PER_BLOCK]


def _render_dependency_rules(body: str) -> str:
    cards = _dependency_rule_cards(body)
    if not cards:
        return "- 无"
    return "\n\n".join(cards[:3])


def _dependency_rule_cards(body: str) -> list[str]:
    cards: list[str] = []
    lines = body.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not re.match(r"^#{2,4}\s*规则[:：]", line):
            index += 1
            continue
        card: list[str] = [line]
        index += 1
        while index < len(lines):
            current = lines[index].rstrip()
            stripped = current.strip()
            if stripped.startswith("#") and not re.match(r"^#{2,4}\s*规则[:：]", stripped):
                break
            if re.match(r"^#{2,4}\s*规则[:：]", stripped):
                break
            if stripped:
                card.append(stripped)
            index += 1
        cards.append("\n".join(card)[:2000])
    return cards


def _gate_check_lines(body: str, prepared: DesignInputBundle) -> list[str]:
    lines = _line_hits(body, ("必须", "如果", "若", "不能", "默认", "风险", "边界", "不直接替代"))
    if _mentions_experiment(prepared):
        lines.append("PRD 出现实验/命中实验语义，Design 必须说明实验字段来源、是否需要新增、以及业务仓如何消费。")
    return dedupe(lines)[:_MAX_LINES_PER_BLOCK]


def _mentions_experiment(prepared: DesignInputBundle) -> bool:
    text = "\n".join([prepared.title, prepared.refined_markdown, *prepared.sections.acceptance_criteria])
    return any(token in text.lower() for token in ("实验", "ab", "a/b", "命中"))


def _meaningful_lines(body: str) -> list[str]:
    lines = []
    for raw in body.splitlines():
        line = raw.strip().strip("-").strip()
        if len(line) < 4 or line in {"---", "# Overview"}:
            continue
        lines.append(line[:240])
    return lines


def _render_block(lines: list[str]) -> str:
    values = as_str_list(lines)
    if not values:
        return "- 无"
    return "\n".join(f"- {line}" for line in values[:_MAX_LINES_PER_BLOCK])

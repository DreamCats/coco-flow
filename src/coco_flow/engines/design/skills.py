from __future__ import annotations

from dataclasses import dataclass
import re

from coco_flow.config import Settings
from coco_flow.services.queries.skills import SkillPackage, SkillStore

from .models import DesignInputBundle
from .utils import as_str_list, dedupe

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
    references: list[tuple[str, str]]


def build_design_skills_bundle(
    prepared: DesignInputBundle,
    settings: Settings,
) -> tuple[str, dict[str, object], list[str]]:
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
    selection_payload = {
        "selected_skill_ids": [item[2].package.id for item in selected],
        "selected_skill_titles": [item[2].package.name for item in selected],
        "candidates": [item[1] for item in scored] + unmatched,
    }
    if not selected:
        return "", selection_payload, []
    brief = render_design_skills_brief([item[2] for item in selected], prepared)
    return brief, selection_payload, [item[2].package.id for item in selected]


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


def render_design_skills_brief(documents: list[_SkillDocument], prepared: DesignInputBundle) -> str:
    lines = [
        "# Design Skills Brief",
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
                _render_block(_line_hits(document.body, ("联动", "multi-repo", "多仓", "live_common +", "业务仓", "producer", "consumer"))),
                "",
                "### Preferred Research Areas",
                _render_block(_research_area_lines(document.body)),
                "",
                "### Producer / Consumer Checks",
                _render_block(_producer_consumer_lines(document.body)),
                "",
                "### Gate Checks",
                _render_block(_gate_check_lines(document.body, prepared)),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _package_to_document(package: SkillPackage) -> _SkillDocument:
    references: list[tuple[str, str]] = []
    for path in package.reference_paths:
        try:
            references.append((str(path.relative_to(package.root_path)), path.read_text(encoding="utf-8").strip()))
        except OSError:
            continue
    body_parts = [package.body.strip(), *(content for _name, content in references)]
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
    for name, content in document.references:
        if any(term.lower() in content.lower() for term in terms):
            selected.append(name)
    return dedupe(selected)[:6]


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
    lines = _line_hits(body, ("实验开关", "公共配置", "ab", "tcc", "live_common +", "共享配置", "公共字段", "依赖"))
    defaults = [
        "如果 PRD 提到命中实验，Design 必须判断实验字段是否已存在，以及哪个 repo 产出该字段。",
        "若公共字段或实验开关不存在，应明确 producer repo、consumer repo 和发布顺序；证据不足时写待确认项。",
    ]
    return dedupe([*lines, *defaults])[:_MAX_LINES_PER_BLOCK]


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

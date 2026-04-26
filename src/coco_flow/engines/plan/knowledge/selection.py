from __future__ import annotations

import re

from coco_flow.config import Settings
from coco_flow.engines.shared.models import RefinedSections, RepoScope, SkillSourceDocument
from coco_flow.services.queries.skills import SkillPackage, SkillStore

SKILL_KIND_PRIORITY = {"skill": 0}
_PLAN_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
_DEFAULT_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "prd",
    "refined",
    "md",
    "ok",
    "no",
    "yes",
    "na",
}


def build_plan_skills_context(
    settings: Settings,
    *,
    title: str,
    sections: RefinedSections,
    repo_scopes: list[RepoScope],
) -> tuple[str, str, dict[str, object], list[str]]:
    candidates = list_plan_skill_candidates(settings)
    scored: list[tuple[int, dict[str, object], SkillSourceDocument]] = []
    unmatched_payloads: list[dict[str, object]] = []
    for document in candidates:
        payload = score_plan_skill_document(document, title=title, sections=sections, repo_scopes=repo_scopes)
        score = int(payload["score"])
        if score > 0:
            scored.append((score, payload, document))
        else:
            unmatched_payloads.append(payload)
    scored.sort(key=lambda item: (-item[0], SKILL_KIND_PRIORITY.get(item[2].kind, 9), item[2].title))
    selected = [item[2] for item in scored[:4]]
    skills_selection_payload = {
        "selected_skill_ids": [item.id for item in selected],
        "selected_skill_titles": [item.title for item in selected],
        "selected_skill_sources": [_plan_skill_source_payload(item[2], item[1]) for item in scored[:4]],
        "candidates": [item[1] for item in scored] + unmatched_payloads,
    }
    if not selected:
        return "", "", skills_selection_payload, []

    terms = infer_plan_skill_terms(title, sections)
    index_markdown = render_plan_skills_index(selected, skills_selection_payload["selected_skill_sources"])
    lines = [
        "# Plan Skills Local Fallback",
        "",
        "- 用途：用于 plan 阶段判断改动边界、主责任 repo、稳定规则、风险与验证要点。",
        "- 优先级：当前 refined PRD 与本地代码调研优先于 skills 历史材料。",
        "",
    ]
    for document in selected:
        boundaries = extract_plan_skill_lines(document.body, ("边界", "范围", "非", "仅", "不展示", "兼容"))
        rules = extract_plan_skill_lines(document.body, ("规则", "默认", "必须", "保持", "状态", "主链路"))
        validations = extract_plan_skill_lines(document.body, ("验证", "校验", "检查", "兼容", "风险"))
        lines.extend(
            [
                f"## {document.title} [{document.kind}]",
                "",
                f"- id: {document.id}",
                f"- domain: {document.domain_name or document.domain_id or 'unknown'}",
                f"- repos: {', '.join(document.repos) if document.repos else '无'}",
                "- 关键摘录：",
                render_plan_skill_excerpt(document.body, terms),
                "- 决策边界：",
                _render_decision_block(boundaries),
                "- 稳定规则：",
                _render_decision_block(rules),
                "- 验证要点：",
                _render_decision_block(validations),
                "",
            ]
        )
    return index_markdown, "\n".join(lines).rstrip() + "\n", skills_selection_payload, [item.id for item in selected]


def list_plan_skill_candidates(settings: Settings) -> list[SkillSourceDocument]:
    skill_store = SkillStore(settings)
    return [_skill_package_to_document(skill) for skill in skill_store.list_packages()]


def score_plan_skill_document(
    document: SkillSourceDocument,
    *,
    title: str,
    sections: RefinedSections,
    repo_scopes: list[RepoScope],
) -> dict[str, object]:
    repo_ids = [scope.repo_id for scope in repo_scopes]
    terms = infer_plan_skill_terms(title, sections)
    score = 0
    repo_match = any(repo_id in document.repos for repo_id in repo_ids)
    keyword_hits = sorted(
        {
            term
            for term in terms
            if any(
                term.lower() in value.lower()
                for value in [document.title, document.desc, document.domain_name, document.body]
            )
        }
    )
    if repo_match:
        score += 5
    score += min(len(keyword_hits), 4)
    summary_text = " ".join([title, *sections.change_scope, *sections.key_constraints, *sections.acceptance_criteria])
    if document.domain_name and document.domain_name.lower() in summary_text.lower():
        score += 2
    if document.kind == "skill":
        score += 2
    return {
        "id": document.id,
        "title": document.title,
        "kind": document.kind,
        "status": document.status,
        "score": score,
        "repo_match": repo_match,
        "keyword_hits": keyword_hits,
    }


def infer_plan_skill_terms(title: str, sections: RefinedSections) -> list[str]:
    values = [title, *sections.change_scope, *sections.non_goals, *sections.key_constraints, *sections.acceptance_criteria]
    terms: list[str] = []
    for value in values:
        for token in _PLAN_ASCII_WORD_RE.findall(value):
            lowered = token.lower().strip()
            if len(lowered) < 3 or lowered in _DEFAULT_STOPWORDS:
                continue
            terms.append(token)
        for token in re.findall(r"[\u4e00-\u9fff]{2,12}", value):
            terms.append(token)
    return _dedupe_terms(terms)[:12]


def render_plan_skill_excerpt(body: str, terms: list[str]) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return "- 无正文。"
    if terms:
        matched = [line for line in lines if any(term.lower() in line.lower() for term in terms)]
        if matched:
            return "\n".join(f"- {line}" for line in matched[:6])
    return "\n".join(f"- {line}" for line in lines[:4])


def extract_plan_skill_lines(body: str, keywords: tuple[str, ...]) -> list[str]:
    lines = [line.strip("- ").strip() for line in body.splitlines() if line.strip()]
    matched = [line for line in lines if any(keyword in line for keyword in keywords)]
    return matched[:4]


def _skill_package_to_document(skill: SkillPackage) -> SkillSourceDocument:
    return SkillSourceDocument(
        id=skill.id,
        kind="skill",
        status="approved",
        title=skill.name,
        desc=skill.description,
        domain_id=skill.domain,
        domain_name=skill.domain.replace("_", " "),
        engines=["refine", "plan"],
        repos=[],
        body=_skill_combined_body(skill),
        source_files=[str(skill.skill_path), *(str(path) for path in skill.reference_paths)],
    )


def _skill_combined_body(skill: SkillPackage) -> str:
    parts: list[str] = []
    if skill.body.strip():
        parts.append(skill.body.strip())
    for path in skill.reference_paths:
        content = path.read_text(encoding="utf-8").strip()
        if content:
            parts.append(content)
    return "\n\n".join(parts)


def render_plan_skills_index(documents: list[SkillSourceDocument], sources: list[dict[str, object]]) -> str:
    lines = [
        "# Plan Skills Index",
        "",
        "- 用途：给 native agent 做渐进式加载导航；这里不是事实摘要。",
        "- 规则：选中 skill 后，agent 必须读取下列完整文件，再把 Skills/SOP 作为稳定执行规则使用。",
        "",
    ]
    source_by_id = {str(source.get("id") or ""): source for source in sources}
    for document in documents:
        source = source_by_id.get(document.id, {})
        lines.extend(
            [
                f"## {document.title} [{document.kind}]",
                "",
                f"- id: {document.id}",
                f"- domain: {document.domain_name or document.domain_id or 'unknown'}",
                f"- description: {document.desc or '无'}",
                f"- match_reason: {_render_plan_match_reason(source)}",
                "- files:",
            ]
        )
        for file_path in document.source_files:
            lines.append(f"  - `{file_path}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _plan_skill_source_payload(document: SkillSourceDocument, score_payload: dict[str, object]) -> dict[str, object]:
    return {
        "id": document.id,
        "title": document.title,
        "kind": document.kind,
        "domain": document.domain_name or document.domain_id,
        "description": document.desc,
        "score": score_payload.get("score"),
        "repo_match": score_payload.get("repo_match"),
        "keyword_hits": score_payload.get("keyword_hits") or [],
        "files": document.source_files,
    }


def _render_plan_match_reason(source: dict[str, object]) -> str:
    parts: list[str] = []
    if source.get("repo_match"):
        parts.append("repo_match=true")
    keyword_hits = [str(item) for item in source.get("keyword_hits") or [] if str(item).strip()]
    if keyword_hits:
        parts.append("keywords=" + ", ".join(keyword_hits[:6]))
    return "; ".join(parts) or "programmatic selection"


def _render_decision_block(lines: list[str]) -> str:
    if not lines:
        return "- 无"
    return "\n".join(f"- {line}" for line in lines)


def _dedupe_terms(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(item)
    return result

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

from coco_flow.config import Settings

from .shared.models import KnowledgeDocumentLike, RefinedSections, RepoScope

KNOWLEDGE_KIND_PRIORITY = {"flow": 0, "rule": 1, "domain": 2}
KNOWLEDGE_KIND_DIRS = {
    "domain": "domains",
    "flow": "flows",
    "rule": "rules",
}
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


def build_plan_knowledge_brief(
    settings: Settings,
    *,
    title: str,
    sections: RefinedSections,
    repo_scopes: list[RepoScope],
) -> tuple[str, dict[str, object], list[str]]:
    candidates = list_plan_knowledge_candidates(settings)
    scored: list[tuple[int, dict[str, object], KnowledgeDocumentLike]] = []
    unmatched_payloads: list[dict[str, object]] = []
    for document in candidates:
        payload = score_plan_knowledge_document(document, title=title, sections=sections, repo_scopes=repo_scopes)
        score = int(payload["score"])
        if score > 0:
            scored.append((score, payload, document))
        else:
            unmatched_payloads.append(payload)
    scored.sort(key=lambda item: (-item[0], KNOWLEDGE_KIND_PRIORITY.get(item[2].kind, 9), item[2].title))
    selected = [item[2] for item in scored[:4]]
    selection_payload = {
        "selected_ids": [item.id for item in selected],
        "selected_titles": [item.title for item in selected],
        "candidates": [item[1] for item in scored] + unmatched_payloads,
    }
    if not selected:
        return "", selection_payload, []

    terms = infer_plan_knowledge_terms(title, sections)
    lines = [
        "# Plan Knowledge Brief",
        "",
        "- 用途：用于 plan 阶段判断改动边界、主责任 repo、稳定规则、风险与验证要点。",
        "- 优先级：当前 refined PRD 与本地代码调研优先于历史 knowledge。",
        "",
    ]
    for document in selected:
        boundaries = extract_plan_decision_lines(document.body, ("边界", "范围", "非", "仅", "不展示", "兼容"))
        rules = extract_plan_decision_lines(document.body, ("规则", "默认", "必须", "保持", "状态", "主链路"))
        validations = extract_plan_decision_lines(document.body, ("验证", "校验", "检查", "兼容", "风险"))
        lines.extend(
            [
                f"## {document.title} [{document.kind}]",
                "",
                f"- id: {document.id}",
                f"- domain: {document.domain_name or document.domain_id or 'unknown'}",
                f"- repos: {', '.join(document.repos) if document.repos else '无'}",
                "- 关键摘录：",
                render_plan_knowledge_excerpt(document.body, terms),
                "- 决策边界：",
                _render_decision_block(boundaries),
                "- 稳定规则：",
                _render_decision_block(rules),
                "- 验证要点：",
                _render_decision_block(validations),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n", selection_payload, [item.id for item in selected]


def list_plan_knowledge_candidates(settings: Settings) -> list[KnowledgeDocumentLike]:
    documents: list[KnowledgeDocumentLike] = []
    for kind, directory in KNOWLEDGE_KIND_DIRS.items():
        kind_dir = settings.knowledge_root / directory
        if not kind_dir.is_dir():
            continue
        for path in sorted(kind_dir.glob("*.md")):
            document = read_knowledge_document_for_plan(path, kind)
            if document.status == "approved" and "plan" in document.engines:
                documents.append(document)
    return documents


def read_knowledge_document_for_plan(path: Path, fallback_kind: str) -> KnowledgeDocumentLike:
    content = path.read_text(encoding="utf-8")
    meta, body = parse_knowledge_frontmatter(content)
    return KnowledgeDocumentLike(
        id=str(meta.get("id") or path.stem),
        kind=str(meta.get("kind") or fallback_kind),
        status=str(meta.get("status") or "draft"),
        title=str(meta.get("title") or path.stem),
        desc=str(meta.get("desc") or ""),
        domain_id=str(meta.get("domain_id") or ""),
        domain_name=str(meta.get("domain_name") or ""),
        engines=knowledge_as_string_list(meta.get("engines")),
        repos=knowledge_as_string_list(meta.get("repos")),
        body=body,
    )


def parse_knowledge_frontmatter(content: str) -> tuple[dict[str, object], str]:
    normalized = content.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized.strip()
    end = normalized.find("\n---\n", 4)
    if end == -1:
        return {}, normalized.strip()
    block = normalized[4:end]
    body = normalized[end + 5 :].strip()
    meta: dict[str, object] = {}
    for line in block.splitlines():
        current = line.strip()
        if not current or ":" not in current:
            continue
        key, raw_value = current.split(":", 1)
        meta[key.strip()] = parse_knowledge_frontmatter_value(raw_value.strip())
    return meta, body


def parse_knowledge_frontmatter_value(raw: str) -> object:
    if not raw:
        return ""
    if raw.startswith(("[", "{", '"')) or raw in {"true", "false", "null"}:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    if raw.startswith(("['", '["', "{'")):
        try:
            return ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            pass
    return raw


def knowledge_as_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def score_plan_knowledge_document(
    document: KnowledgeDocumentLike,
    *,
    title: str,
    sections: RefinedSections,
    repo_scopes: list[RepoScope],
) -> dict[str, object]:
    repo_ids = [scope.repo_id for scope in repo_scopes]
    terms = infer_plan_knowledge_terms(title, sections)
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
    if document.kind == "flow":
        score += 2
    elif document.kind == "rule":
        score += 1
    return {
        "id": document.id,
        "title": document.title,
        "kind": document.kind,
        "status": document.status,
        "score": score,
        "repo_match": repo_match,
        "keyword_hits": keyword_hits,
    }


def infer_plan_knowledge_terms(title: str, sections: RefinedSections) -> list[str]:
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


def render_plan_knowledge_excerpt(body: str, terms: list[str]) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return "- 无正文。"
    if terms:
        matched = [line for line in lines if any(term.lower() in line.lower() for term in terms)]
        if matched:
            return "\n".join(f"- {line}" for line in matched[:6])
    return "\n".join(f"- {line}" for line in lines[:4])


def extract_plan_decision_lines(body: str, keywords: tuple[str, ...]) -> list[str]:
    lines = [line.strip("- ").strip() for line in body.splitlines() if line.strip()]
    matched = [line for line in lines if any(keyword in line for keyword in keywords)]
    return matched[:4]


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

from __future__ import annotations

import ast
import json
from pathlib import Path

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.engines.business_memory import BusinessMemoryContext
from coco_flow.models import KnowledgeDocument, KnowledgeEvidence

from .models import RefineIntent, RefineKnowledgeBrief, RefinePreparedInput

_PRIORITY_KINDS = {"glossary", "rules", "history", "faq"}
_KNOWLEDGE_KIND_PRIORITY = {"domain": 0, "rule": 1, "flow": 2}
_KIND_DIRS = {
    "domain": "domains",
    "flow": "flows",
    "rule": "rules",
}


def build_refine_knowledge_brief(
    memory: BusinessMemoryContext,
    intent: RefineIntent,
    prepared: RefinePreparedInput,
    settings: Settings,
) -> RefineKnowledgeBrief:
    candidates = _list_refine_knowledge_candidates(settings)
    scored_payloads = [_score_payload(item, prepared, intent) for item in candidates]
    approved_documents = _select_refine_knowledge_documents(candidates, prepared, intent)
    adjudication_payload = build_refine_knowledge_adjudication_payload(
        settings=settings,
        prepared=prepared,
        intent=intent,
        selected_documents=approved_documents,
    )
    approved_documents = _apply_adjudication_result(approved_documents, adjudication_payload)
    terms = intent.key_terms[:8]
    ordered_documents = sorted(
        memory.documents,
        key=lambda item: (item.kind not in _PRIORITY_KINDS, item.name),
    )
    selected_memory = ordered_documents[:4]
    if not selected_memory and not approved_documents:
        return RefineKnowledgeBrief(
            markdown="",
            matched_documents=[],
            matched_terms=terms,
            selected_knowledge_ids=[],
            selection_payload={
                "selected_ids": [],
                "selected_titles": [],
                "candidates": [],
            },
        )

    lines = [
        "# Refine Knowledge Brief",
        "",
        "- 用途：仅用于 refine 阶段的术语消歧、历史规则补充和冲突识别。",
        "- 优先级：当前 PRD 原文优先于历史知识与 approved knowledge。",
        f"- context_mode: {memory.mode}",
        "",
        "## 当前需求意图",
        "",
        f"- 需求目标：{intent.goal or intent.title}",
        f"- 关键术语：{', '.join(terms) if terms else '无'}",
        "",
    ]
    if intent.constraints:
        lines.extend(
            [
                "## 约束提醒",
                "",
                *[f"- {item}" for item in intent.constraints[:4]],
                "",
            ]
        )

    matched_documents: list[str] = []
    for document in selected_memory:
        matched_documents.append(document.name)
        lines.extend(
            [
                f"## {document.name} ({document.kind})",
                "",
                _extract_relevant_excerpt(document.excerpt, terms),
                "",
            ]
        )

    if approved_documents:
        lines.extend(
            [
                "## Approved Knowledge",
                "",
            ]
        )
        for document in approved_documents:
            matched_documents.append(f"knowledge:{document.id}")
            lines.extend(
                [
                    f"### {document.title} [{document.kind}]",
                    "",
                    f"- id: {document.id}",
                    f"- domain: {document.domainName or document.domainId or 'unknown'}",
                    f"- repos: {', '.join(document.repos) if document.repos else '无'}",
                    f"- keywords: {', '.join(document.keywords[:8]) if document.keywords else '无'}",
                    _render_knowledge_excerpt(document, terms),
                    "",
                ]
            )

    selection_payload = {
        "selected_ids": [item.id for item in approved_documents],
        "selected_titles": [item.title for item in approved_documents],
        "candidates": scored_payloads,
        "adjudication": adjudication_payload,
    }
    return RefineKnowledgeBrief(
        markdown="\n".join(lines).rstrip() + "\n",
        matched_documents=matched_documents,
        matched_terms=terms,
        selected_knowledge_ids=[item.id for item in approved_documents],
        selection_payload=selection_payload,
    )


def _extract_relevant_excerpt(content: str, terms: list[str]) -> str:
    normalized_lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not normalized_lines:
        return "- 无可用历史知识摘录。"

    if terms:
        matched = [line for line in normalized_lines if any(term.lower() in line.lower() for term in terms)]
        if matched:
            return "\n".join(f"- {line}" for line in matched[:6])

    return "\n".join(f"- {line}" for line in normalized_lines[:4])


def _render_knowledge_excerpt(document: KnowledgeDocument, terms: list[str]) -> str:
    body = document.body.strip()
    if not body:
        return "- 摘要：无正文。"
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if terms:
        matched = [line for line in lines if any(term.lower() in line.lower() for term in terms)]
        if matched:
            return "\n".join(f"- {line}" for line in matched[:5])
    return "\n".join(f"- {line}" for line in lines[:4])


def _select_refine_knowledge_documents(
    candidates: list[KnowledgeDocument],
    prepared: RefinePreparedInput,
    intent: RefineIntent,
) -> list[KnowledgeDocument]:
    scored: list[tuple[int, KnowledgeDocument]] = []
    for document in candidates:
        score = _score_document(document, prepared, intent)
        if score > 0:
            scored.append((score, document))
    scored.sort(
        key=lambda item: (
            -item[0],
            _KNOWLEDGE_KIND_PRIORITY.get(item[1].kind, 9),
            item[1].title,
        )
    )
    return [item[1] for item in scored[:4]]


def _list_refine_knowledge_candidates(settings: Settings) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    for kind, directory in _KIND_DIRS.items():
        kind_dir = settings.knowledge_root / directory
        if not kind_dir.is_dir():
            continue
        for path in sorted(kind_dir.glob("*.md")):
            document = _read_knowledge_document(path, kind)
            if document.status == "approved" and "refine" in document.engines:
                documents.append(document)
    return documents


def build_refine_knowledge_adjudication_payload(
    *,
    settings: Settings,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    selected_documents: list[KnowledgeDocument],
) -> dict[str, object]:
    if settings.refine_executor.strip().lower() != "native":
        return {"mode": "rule_only", "selected_ids": [item.id for item in selected_documents], "reason": "executor_is_not_native"}
    if len(selected_documents) <= 1:
        return {"mode": "rule_only", "selected_ids": [item.id for item in selected_documents], "reason": "candidate_count_leq_1"}

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    try:
        raw = client.run_prompt_only(
            build_refine_knowledge_adjudication_prompt(prepared, intent, selected_documents),
            settings.native_query_timeout,
            cwd=prepared.repo_root,
        )
        payload = parse_refine_knowledge_adjudication_output(raw, selected_documents)
        payload["mode"] = "llm_adjudicated"
        return payload
    except ValueError as error:
        return {
            "mode": "rule_only",
            "selected_ids": [item.id for item in selected_documents],
            "reason": f"llm_adjudication_failed: {error}",
        }


def build_refine_knowledge_adjudication_prompt(
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    documents: list[KnowledgeDocument],
) -> str:
    lines = [
        "你在做 coco-flow refine knowledge adjudication。",
        "目标：从已规则筛中的 approved knowledge 中，选出最适合当前 refine 的知识。",
        "要求：",
        "1. 只保留对术语消歧、历史规则补充、冲突识别真正有帮助的知识。",
        "2. 如果知识更偏实现链路细节、对 refine 帮助弱，可以降级或剔除。",
        "3. 当前 PRD 原文优先，历史知识不能覆盖当前需求。",
        "4. 输出必须是 JSON 对象，不要输出其它文字。",
        '5. JSON 格式：{"selected_ids":["..."],"rejected_ids":["..."],"reason":"..."}',
        "",
        f"当前任务标题：{prepared.title}",
        f"需求目标：{intent.goal or prepared.title}",
        f"关键术语：{', '.join(intent.key_terms[:8]) if intent.key_terms else '无'}",
        f"约束：{'; '.join(intent.constraints[:4]) if intent.constraints else '无'}",
        "",
        "候选知识：",
    ]
    for document in documents:
        lines.extend(
            [
                f"- id: {document.id}",
                f"  kind: {document.kind}",
                f"  title: {document.title}",
                f"  domain: {document.domainName or document.domainId or 'unknown'}",
                f"  repos: {', '.join(document.repos) if document.repos else '无'}",
                f"  keywords: {', '.join(document.keywords[:8]) if document.keywords else '无'}",
                f"  desc: {document.desc or '无'}",
                f"  excerpt: {_excerpt_for_adjudication(document.body)}",
            ]
        )
    return "\n".join(lines)


def parse_refine_knowledge_adjudication_output(raw: str, documents: list[KnowledgeDocument]) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid_adjudication_json: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("adjudication_output_is_not_object")
    known_ids = {item.id for item in documents}
    selected_ids = [str(item) for item in payload.get("selected_ids", []) if str(item) in known_ids]
    rejected_ids = [str(item) for item in payload.get("rejected_ids", []) if str(item) in known_ids]
    if not selected_ids:
        raise ValueError("adjudication_selected_ids_empty")
    return {
        "selected_ids": selected_ids,
        "rejected_ids": rejected_ids,
        "reason": str(payload.get("reason") or ""),
    }


def _apply_adjudication_result(
    selected_documents: list[KnowledgeDocument],
    adjudication_payload: dict[str, object],
) -> list[KnowledgeDocument]:
    ids = adjudication_payload.get("selected_ids")
    if not isinstance(ids, list) or not ids:
        return selected_documents
    selected_id_set = {str(item) for item in ids}
    filtered = [item for item in selected_documents if item.id in selected_id_set]
    return filtered or selected_documents


def _excerpt_for_adjudication(body: str, limit: int = 240) -> str:
    normalized = " ".join(line.strip() for line in body.splitlines() if line.strip())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


def _score_document(document: KnowledgeDocument, prepared: RefinePreparedInput, intent: RefineIntent) -> int:
    score = 0
    repo_ids = _repo_ids(prepared)
    repo_paths = _repo_paths(prepared)
    if any(repo_id in document.repos for repo_id in repo_ids):
        score += 5
    if any(_path_matches(path, repo_paths) for path in document.paths):
        score += 4
    score += min(_keyword_hits(document, intent), 4)
    if document.domainName and any(document.domainName.lower() in value.lower() for value in [intent.title, intent.goal]):
        score += 3
    if document.kind == "domain":
        score += 1
    return score


def _score_payload(document: KnowledgeDocument, prepared: RefinePreparedInput, intent: RefineIntent) -> dict[str, object]:
    repo_ids = _repo_ids(prepared)
    repo_paths = _repo_paths(prepared)
    return {
        "id": document.id,
        "title": document.title,
        "kind": document.kind,
        "status": document.status,
        "score": _score_document(document, prepared, intent),
        "repo_match": any(repo_id in document.repos for repo_id in repo_ids),
        "path_match": any(_path_matches(path, repo_paths) for path in document.paths),
        "keyword_hits": sorted(
            {
                term
                for term in intent.key_terms
                if any(term.lower() in value.lower() for value in [*document.keywords, document.title, document.desc, document.domainName, document.body])
            }
        ),
    }


def _repo_ids(prepared: RefinePreparedInput) -> list[str]:
    repos = prepared.repos_meta.get("repos")
    if not isinstance(repos, list):
        return []
    return [str(item.get("id") or "") for item in repos if isinstance(item, dict) and str(item.get("id") or "")]


def _repo_paths(prepared: RefinePreparedInput) -> list[str]:
    repos = prepared.repos_meta.get("repos")
    if not isinstance(repos, list):
        return []
    return [str(item.get("path") or "") for item in repos if isinstance(item, dict) and str(item.get("path") or "")]


def _path_matches(path_value: str, repo_paths: list[str]) -> bool:
    current = path_value.strip()
    if not current:
        return False
    try:
        candidate = Path(current).resolve()
    except OSError:
        return False
    for repo_path in repo_paths:
        try:
            root = Path(repo_path).resolve()
        except OSError:
            continue
        if candidate == root or str(candidate).startswith(str(root) + "/"):
            return True
    return False


def _keyword_hits(document: KnowledgeDocument, intent: RefineIntent) -> int:
    values = [*document.keywords, document.title, document.desc, document.domainName, document.body]
    return sum(1 for term in intent.key_terms if any(term.lower() in value.lower() for value in values))


def _read_knowledge_document(path: Path, fallback_kind: str) -> KnowledgeDocument:
    content = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(content)
    evidence_payload = meta.get("evidence")
    return KnowledgeDocument(
        id=str(meta.get("id") or path.stem),
        traceId=str(meta.get("trace_id") or ""),
        kind=str(meta.get("kind") or fallback_kind),
        status=str(meta.get("status") or "draft"),
        title=str(meta.get("title") or path.stem),
        desc=str(meta.get("desc") or ""),
        domainId=str(meta.get("domain_id") or ""),
        domainName=str(meta.get("domain_name") or ""),
        engines=_as_string_list(meta.get("engines")),
        repos=_as_string_list(meta.get("repos")),
        paths=_as_string_list(meta.get("paths")),
        keywords=_as_string_list(meta.get("keywords")),
        priority=str(meta.get("priority") or "medium"),
        confidence=str(meta.get("confidence") or "medium"),
        updatedAt=str(meta.get("updated_at") or ""),
        owner=str(meta.get("owner") or "unknown"),
        body=body,
        evidence=_build_evidence(evidence_payload),
    )


def _parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
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
        meta[key.strip()] = _parse_frontmatter_value(raw_value.strip())
    return meta, body


def _parse_frontmatter_value(raw: str) -> object:
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


def _as_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _build_evidence(payload: object) -> KnowledgeEvidence:
    if isinstance(payload, dict):
        return KnowledgeEvidence(
            inputTitle=str(payload.get("inputTitle") or ""),
            inputDescription=str(payload.get("inputDescription") or ""),
            repoMatches=_as_string_list(payload.get("repoMatches")),
            keywordMatches=_as_string_list(payload.get("keywordMatches")),
            pathMatches=_as_string_list(payload.get("pathMatches")),
            candidateFiles=_as_string_list(payload.get("candidateFiles")),
            contextHits=_as_string_list(payload.get("contextHits")),
            retrievalNotes=_as_string_list(payload.get("retrievalNotes")),
            openQuestions=_as_string_list(payload.get("openQuestions")),
        )
    return KnowledgeEvidence(
        inputTitle="",
        inputDescription="",
        repoMatches=[],
        keywordMatches=[],
        pathMatches=[],
        candidateFiles=[],
        contextHits=[],
        retrievalNotes=[],
        openQuestions=[],
    )

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import ast
import json

from coco_flow.config import Settings
from coco_flow.models import KnowledgeDocument, KnowledgeEvidence, KnowledgeTraceResponse
from coco_flow.services.knowledge.common import infer_domain_name, slugify_domain
from coco_flow.services.knowledge.generation import (
    KnowledgeDraftInput,
    KnowledgeGenerationResult,
    ProgressHandler,
    generate_knowledge_drafts,
)

KNOWLEDGE_KIND_ORDER = ("domain", "flow", "rule")
KIND_DIRS = {
    "domain": "domains",
    "flow": "flows",
    "rule": "rules",
}


class KnowledgeStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ensure_root(self) -> Path:
        self.settings.knowledge_root.mkdir(parents=True, exist_ok=True)
        for directory in (*KIND_DIRS.values(), "trace", "jobs"):
            (self.settings.knowledge_root / directory).mkdir(parents=True, exist_ok=True)
        return self.settings.knowledge_root

    def list_documents(self) -> list[KnowledgeDocument]:
        self.ensure_root()
        documents: list[KnowledgeDocument] = []
        for kind in KNOWLEDGE_KIND_ORDER:
            kind_dir = self.settings.knowledge_root / KIND_DIRS[kind]
            if not kind_dir.is_dir():
                continue
            for path in sorted(kind_dir.glob("*.md")):
                documents.append(read_knowledge_document(path))
        documents.sort(key=lambda item: (item.domainName, item.kind, item.updatedAt, item.title), reverse=False)
        return documents

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        self.ensure_root()
        resolved = self._resolve_document_path(document_id)
        if resolved is not None:
            _, candidate = resolved
            return read_knowledge_document(candidate)
        return None

    def create_document(self, title: str, content: str) -> KnowledgeDocument:
        self.ensure_root()
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("knowledge title 不能为空")
        document = build_document_from_content(
            content,
            fallback_title=normalized_title,
            fallback_id=self._next_document_id(normalized_title),
        )
        if self._resolve_document_path(document.id) is not None:
            raise ValueError(f"knowledge document already exists: {document.id}")
        target = self.settings.knowledge_root / KIND_DIRS[document.kind] / f"{document.id}.md"
        write_knowledge_document(target, document)
        return read_knowledge_document(target)

    def create_drafts(
        self,
        payload: KnowledgeDraftInput,
        on_progress: ProgressHandler | None = None,
    ) -> KnowledgeGenerationResult:
        self.ensure_root()
        result = generate_knowledge_drafts(payload, self.settings, on_progress=on_progress)
        if on_progress is not None:
            on_progress("persisting", 96, "正在保存知识草稿和中间产物。")
        self.persist_generation_result(result)
        return result

    def persist_generation_result(self, result: KnowledgeGenerationResult) -> None:
        self._write_trace(result)
        if result.validation_errors:
            issues = "; ".join(result.validation_errors)
            raise ValueError(f"knowledge draft validation failed: {issues}")
        for document in result.documents:
            target = self.settings.knowledge_root / KIND_DIRS[document.kind] / f"{document.id}.md"
            write_knowledge_document(target, document)

    def update_document(self, document_id: str, payload: dict[str, object]) -> KnowledgeDocument:
        resolved = self._resolve_document_path(document_id)
        if resolved is None:
            raise ValueError(f"knowledge document not found: {document_id}")
        _, current_path = resolved
        existing = read_knowledge_document(current_path)

        updated = existing.model_copy(
            update={
                "title": str(payload.get("title") or existing.title),
                "desc": str(payload.get("desc") or existing.desc),
                "status": str(payload.get("status") or existing.status),
                "engines": _as_string_list(payload.get("engines"), existing.engines),
                "repos": _as_string_list(payload.get("repos"), existing.repos),
                "paths": _as_string_list(payload.get("paths"), existing.paths),
                "keywords": _as_string_list(payload.get("keywords"), existing.keywords),
                "priority": str(payload.get("priority") or existing.priority),
                "confidence": str(payload.get("confidence") or existing.confidence),
                "body": str(payload.get("body") or existing.body),
                "updatedAt": format_now(),
            }
        )
        target = self.settings.knowledge_root / KIND_DIRS[updated.kind] / f"{updated.id}.md"
        write_knowledge_document(target, updated)
        return read_knowledge_document(target)

    def update_document_content(self, document_id: str, content: str) -> KnowledgeDocument:
        resolved = self._resolve_document_path(document_id)
        if resolved is None:
            raise ValueError(f"knowledge document not found: {document_id}")
        _, current_path = resolved
        existing = read_knowledge_document(current_path)
        updated = build_document_from_content(
            content,
            fallback_title=existing.title,
            fallback_id=existing.id,
            fallback_kind=existing.kind,
            existing=existing,
        )
        target = self.settings.knowledge_root / KIND_DIRS[updated.kind] / f"{updated.id}.md"
        write_knowledge_document(target, updated)
        if target != current_path and current_path.exists():
            current_path.unlink()
        return read_knowledge_document(target)

    def delete_document(self, document_id: str) -> None:
        self.ensure_root()
        resolved = self._resolve_document_path(document_id)
        if resolved is not None:
            _, candidate = resolved
            candidate.unlink()
            return
        raise ValueError(f"knowledge document not found: {document_id}")

    def get_trace(self, trace_id: str) -> KnowledgeTraceResponse:
        self.ensure_root()
        trace_root = self.settings.knowledge_root / "trace" / trace_id.strip()
        if not trace_root.is_dir():
            raise ValueError(f"knowledge trace not found: {trace_id}")

        files = sorted(
            str(path.relative_to(trace_root))
            for path in trace_root.rglob("*.json")
            if path.is_file()
        )
        repo_research_root = trace_root / "repo-research"
        repo_research: dict[str, dict[str, object]] = {}
        if repo_research_root.is_dir():
            for path in sorted(repo_research_root.glob("*.json")):
                repo_research[path.stem] = _read_trace_json(path)

        return KnowledgeTraceResponse(
            trace_id=trace_id,
            files=files,
            intent=_read_trace_json(trace_root / "intent.json"),
            term_mapping=_read_trace_json(trace_root / "term-mapping.json"),
            candidate_ranking=_read_trace_json(trace_root / "candidate-ranking.json"),
            term_family=_read_trace_json(trace_root / "term-family.json"),
            focus_boundary=_read_trace_json(trace_root / "focus-boundary.json"),
            topic_adjudication=_read_trace_json(trace_root / "topic-adjudication.json"),
            anchor_selection=_read_trace_json(trace_root / "anchor-selection.json"),
            repo_discovery=_read_trace_json(trace_root / "repo-discovery.json"),
            repo_role_signals=_read_trace_json(trace_root / "repo-role-signals.json"),
            flow_slots=_read_trace_json(trace_root / "flow-slots.json"),
            storyline_outline=_read_trace_json(trace_root / "storyline-outline.json"),
            flow_judge=_read_trace_json(trace_root / "flow-judge.json"),
            repo_research=repo_research,
            knowledge_draft=_read_trace_json(trace_root / "knowledge-draft.json"),
            validation=_read_trace_json(trace_root / "validation-result.json"),
        )

    def _write_trace(self, result: KnowledgeGenerationResult) -> None:
        trace_root = self.settings.knowledge_root / "trace" / result.trace_id
        trace_root.mkdir(parents=True, exist_ok=True)
        for relative_path, payload in result.trace_files.items():
            target = trace_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _resolve_document_path(self, document_id: str) -> tuple[str, Path] | None:
        for kind in KNOWLEDGE_KIND_ORDER:
            candidate = self.settings.knowledge_root / KIND_DIRS[kind] / f"{document_id}.md"
            if candidate.is_file():
                return kind, candidate
        return None

    def _next_document_id(self, title: str) -> str:
        base = f"manual-{slugify_domain(title)}"
        candidate = base
        suffix = 2
        while self._resolve_document_path(candidate) is not None:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate


def read_knowledge_document(path: Path) -> KnowledgeDocument:
    content = path.read_text(encoding="utf-8")
    meta, body, raw_frontmatter = parse_frontmatter(content)
    evidence_payload = meta.pop("evidence", None)
    return KnowledgeDocument(
        id=path.stem,
        traceId=str(meta.get("trace_id") or ""),
        kind=str(meta.get("kind") or infer_kind_from_path(path)),
        status=str(meta.get("status") or "draft"),
        title=str(meta.get("title") or path.stem),
        desc=str(meta.get("desc") or ""),
        domainId=str(meta.get("domain_id") or ""),
        domainName=str(meta.get("domain_name") or ""),
        engines=_as_string_list(meta.get("engines"), []),
        repos=_as_string_list(meta.get("repos"), []),
        paths=_as_string_list(meta.get("paths"), []),
        keywords=_as_string_list(meta.get("keywords"), []),
        priority=str(meta.get("priority") or "medium"),
        confidence=str(meta.get("confidence") or "medium"),
        updatedAt=str(meta.get("updated_at") or ""),
        owner=str(meta.get("owner") or "unknown"),
        body=body,
        evidence=build_evidence(evidence_payload),
        rawFrontmatter=raw_frontmatter,
        rawContent=content,
    )


def write_knowledge_document(path: Path, document: KnowledgeDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_knowledge_document(document), encoding="utf-8")


def render_knowledge_document(document: KnowledgeDocument) -> str:
    if document.rawFrontmatter.strip():
        body = document.body.rstrip()
        content = f"---\n{document.rawFrontmatter.rstrip()}\n---"
        return f"{content}\n\n{body}\n" if body else f"{content}\n"

    hidden_evidence_fields = {"keywordMatches", "pathMatches", "candidateFiles"}
    evidence_payload = {
        key: value
        for key, value in document.evidence.model_dump().items()
        if key not in hidden_evidence_fields and value not in ("", [], {}, None)
    }
    meta = {
        "kind": document.kind,
        "id": document.id,
        "trace_id": document.traceId,
        "title": document.title,
        "desc": document.desc,
        "status": document.status,
        "engines": document.engines,
        "domain_id": document.domainId,
        "domain_name": document.domainName,
        "repos": document.repos,
        "priority": document.priority,
        "confidence": document.confidence,
        "updated_at": document.updatedAt,
        "owner": document.owner,
        "evidence": evidence_payload,
    }
    if document.paths:
        meta["paths"] = document.paths
    if document.keywords:
        meta["keywords"] = document.keywords
    frontmatter = ["---"]
    for key, value in meta.items():
        serialized = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
        frontmatter.append(f"{key}: {serialized}")
    frontmatter.append("---")
    return "\n".join(frontmatter) + "\n\n" + document.body.rstrip() + "\n"


def build_document_from_content(
    content: str,
    *,
    fallback_title: str,
    fallback_id: str,
    fallback_kind: str = "flow",
    existing: KnowledgeDocument | None = None,
) -> KnowledgeDocument:
    meta, body, raw_frontmatter = parse_frontmatter(content)
    evidence_payload = meta.pop("evidence", None)
    document_id = fallback_id if existing is not None else str(meta.get("id") or fallback_id).strip() or fallback_id
    title = str(meta.get("title") or fallback_title).strip() or fallback_title
    domain_name = str(meta.get("domain_name") or (existing.domainName if existing else "") or infer_domain_name(title)).strip()
    domain_id = str(meta.get("domain_id") or (existing.domainId if existing else "") or slugify_domain(domain_name)).strip()
    kind = str(meta.get("kind") or (existing.kind if existing else fallback_kind)).strip() or fallback_kind
    if kind not in KIND_DIRS:
        raise ValueError(f"unsupported knowledge kind: {kind}")
    return KnowledgeDocument(
        id=document_id,
        traceId=str(meta.get("trace_id") or (existing.traceId if existing else "")),
        kind=kind,
        status=str(meta.get("status") or (existing.status if existing else "draft") or "draft"),
        title=title,
        desc=str(meta.get("desc") or (existing.desc if existing else "")),
        domainId=domain_id,
        domainName=domain_name,
        engines=_coerce_string_list(meta.get("engines"), existing.engines if existing else []),
        repos=_coerce_string_list(meta.get("repos"), existing.repos if existing else []),
        paths=_coerce_string_list(meta.get("paths"), existing.paths if existing else []),
        keywords=_coerce_string_list(meta.get("keywords"), existing.keywords if existing else []),
        priority=str(meta.get("priority") or (existing.priority if existing else "medium") or "medium"),
        confidence=str(meta.get("confidence") or (existing.confidence if existing else "medium") or "medium"),
        updatedAt=format_now(),
        owner=str(meta.get("owner") or (existing.owner if existing else "Maifeng") or "Maifeng"),
        body=body,
        evidence=build_evidence(evidence_payload if evidence_payload is not None else (existing.evidence.model_dump() if existing else None)),
        rawFrontmatter=raw_frontmatter,
        rawContent=content,
    )


def parse_frontmatter(content: str) -> tuple[dict[str, object], str, str]:
    normalized = content.replace("\r\n", "\n")
    blocks, body = split_frontmatter_blocks(normalized)
    if not blocks:
        return {}, body, ""
    merged_meta: dict[str, object] = {}
    for block in blocks:
        merged_meta = merge_frontmatter_meta(merged_meta, parse_frontmatter_block(block))
    raw_frontmatter = blocks[0] if len(blocks) == 1 else render_frontmatter_block(merged_meta)
    return merged_meta, body, raw_frontmatter


def split_frontmatter_blocks(content: str) -> tuple[list[str], str]:
    remaining = content
    blocks: list[str] = []
    while remaining.startswith("---\n"):
        end = remaining.find("\n---\n", 4)
        if end == -1:
            break
        blocks.append(remaining[4:end].strip())
        remaining = remaining[end + 5 :].lstrip("\n")
    return blocks, remaining.strip()


def parse_frontmatter_block(block: str) -> dict[str, object]:
    meta: dict[str, object] = {}
    for line in block.splitlines():
        current = line.strip()
        if not current or ":" not in current:
            continue
        key, raw_value = current.split(":", 1)
        meta[key.strip()] = parse_frontmatter_value(raw_value.strip())
    return meta


def render_frontmatter_block(meta: dict[str, object]) -> str:
    lines: list[str] = []
    for key, value in meta.items():
        serialized = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
        lines.append(f"{key}: {serialized}")
    return "\n".join(lines)


def merge_frontmatter_meta(base: dict[str, object], patch: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in patch.items():
        if key == "id" and str(merged.get("id") or "").strip():
            continue
        merged[key] = value
    return merged


def parse_frontmatter_value(raw: str) -> object:
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


def build_evidence(payload: object) -> KnowledgeEvidence:
    if isinstance(payload, dict):
        return KnowledgeEvidence(
            inputTitle=str(payload.get("inputTitle") or ""),
            inputDescription=str(payload.get("inputDescription") or ""),
            repoMatches=_as_string_list(payload.get("repoMatches"), []),
            keywordMatches=_as_string_list(payload.get("keywordMatches"), []),
            pathMatches=_as_string_list(payload.get("pathMatches"), []),
            candidateFiles=_as_string_list(payload.get("candidateFiles"), []),
            contextHits=_as_string_list(payload.get("contextHits"), []),
            retrievalNotes=_as_string_list(payload.get("retrievalNotes"), []),
            openQuestions=_as_string_list(payload.get("openQuestions"), []),
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


def infer_kind_from_path(path: Path) -> str:
    parent = path.parent.name
    if parent == "domains":
        return "domain"
    if parent == "flows":
        return "flow"
    if parent == "rules":
        return "rule"
    return "domain"


def _as_string_list(value: object, default: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return default


def _coerce_string_list(value: object, default: list[str]) -> list[str]:
    if value is None:
        return default
    return _as_string_list(value, default)


def format_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def _read_trace_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

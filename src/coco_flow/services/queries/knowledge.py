from __future__ import annotations

from datetime import datetime
from pathlib import Path
import ast
import json

from coco_flow.config import Settings
from coco_flow.models import KnowledgeDocument, KnowledgeEvidence, KnowledgeTraceResponse
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
        for kind in KNOWLEDGE_KIND_ORDER:
            candidate = self.settings.knowledge_root / KIND_DIRS[kind] / f"{document_id}.md"
            if candidate.is_file():
                return read_knowledge_document(candidate)
        return None

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
        existing = self.get_document(document_id)
        if existing is None:
            raise ValueError(f"knowledge document not found: {document_id}")

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
        write_knowledge_document(self.settings.knowledge_root / KIND_DIRS[updated.kind] / f"{updated.id}.md", updated)
        return updated

    def delete_document(self, document_id: str) -> None:
        self.ensure_root()
        for kind in KNOWLEDGE_KIND_ORDER:
            candidate = self.settings.knowledge_root / KIND_DIRS[kind] / f"{document_id}.md"
            if candidate.is_file():
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
            anchor_selection=_read_trace_json(trace_root / "anchor-selection.json"),
            repo_discovery=_read_trace_json(trace_root / "repo-discovery.json"),
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


def read_knowledge_document(path: Path) -> KnowledgeDocument:
    content = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)
    evidence_payload = meta.pop("evidence", None)
    return KnowledgeDocument(
        id=str(meta.get("id") or path.stem),
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
    )


def write_knowledge_document(path: Path, document: KnowledgeDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        "paths": document.paths,
        "keywords": document.keywords,
        "priority": document.priority,
        "confidence": document.confidence,
        "updated_at": document.updatedAt,
        "owner": document.owner,
        "evidence": document.evidence.model_dump(),
    }
    frontmatter = ["---"]
    for key, value in meta.items():
        serialized = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
        frontmatter.append(f"{key}: {serialized}")
    frontmatter.append("---")
    path.write_text("\n".join(frontmatter) + "\n\n" + document.body.rstrip() + "\n", encoding="utf-8")


def parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
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
        meta[key.strip()] = parse_frontmatter_value(raw_value.strip())
    return meta, body


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


def format_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def _read_trace_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

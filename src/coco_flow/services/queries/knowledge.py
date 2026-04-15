from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import ast
import json

from coco_flow.config import Settings
from coco_flow.models import KnowledgeDocument, KnowledgeEvidence

KNOWLEDGE_KIND_ORDER = ("domain", "flow", "rule")
KIND_DIRS = {
    "domain": "domains",
    "flow": "flows",
    "rule": "rules",
}


@dataclass(frozen=True)
class KnowledgeDraftInput:
    description: str
    repos: list[str]
    kinds: list[str]
    notes: str


class KnowledgeStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ensure_root(self) -> Path:
        self.settings.knowledge_root.mkdir(parents=True, exist_ok=True)
        for directory in KIND_DIRS.values():
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

    def create_drafts(self, payload: KnowledgeDraftInput) -> list[KnowledgeDocument]:
        self.ensure_root()
        timestamp = format_now()
        documents = build_draft_documents(payload, timestamp=timestamp)
        for document in documents:
            write_knowledge_document(self.settings.knowledge_root / KIND_DIRS[document.kind] / f"{document.id}.md", document)
        return documents

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


def read_knowledge_document(path: Path) -> KnowledgeDocument:
    content = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)
    evidence_payload = meta.pop("evidence", None)
    document = KnowledgeDocument(
        id=str(meta.get("id") or path.stem),
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
    return document


def write_knowledge_document(path: Path, document: KnowledgeDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "kind": document.kind,
        "id": document.id,
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
        if isinstance(value, (list, dict)):
            serialized = json.dumps(value, ensure_ascii=False)
        else:
            serialized = str(value)
        frontmatter.append(f"{key}: {serialized}")
    frontmatter.append("---")
    payload = "\n".join(frontmatter) + "\n\n" + document.body.rstrip() + "\n"
    path.write_text(payload, encoding="utf-8")


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
        normalized = {
            "inputDescription": str(payload.get("inputDescription") or ""),
            "repoMatches": _as_string_list(payload.get("repoMatches"), []),
            "keywordMatches": _as_string_list(payload.get("keywordMatches"), []),
            "pathMatches": _as_string_list(payload.get("pathMatches"), []),
            "candidateFiles": _as_string_list(payload.get("candidateFiles"), []),
            "contextHits": _as_string_list(payload.get("contextHits"), []),
            "retrievalNotes": _as_string_list(payload.get("retrievalNotes"), []),
            "openQuestions": _as_string_list(payload.get("openQuestions"), []),
        }
        return KnowledgeEvidence(**normalized)
    return KnowledgeEvidence(
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


def build_draft_documents(payload: KnowledgeDraftInput, timestamp: str) -> list[KnowledgeDocument]:
    description = payload.description.strip()
    repos = payload.repos or ["live_pack"]
    domain_name = infer_domain_name(description)
    domain_id = slugify_domain(domain_name)
    keywords = infer_keywords(description)
    paths = infer_paths(description)
    files = infer_candidate_files(paths)
    context_hits = (
        [".livecoding/context/glossary.md 命中 explain_card", ".livecoding/context/patterns.md 命中 render"]
        if "讲解卡" in description
        else ["当前未命中明确的 repo context，仅保留 repo 扫描证据。"]
    )

    documents: list[KnowledgeDocument] = []
    for index, kind in enumerate([kind for kind in payload.kinds if kind in KNOWLEDGE_KIND_ORDER]):
        document = KnowledgeDocument(
            id=f"{kind}-{domain_id}-{int(datetime.now().timestamp() * 1000)}-{index}",
            kind=kind,
            status="draft",
            title=build_draft_title(kind, description),
            desc=build_draft_description(kind, description),
            domainId=domain_id,
            domainName=domain_name,
            engines=infer_engines(kind),
            repos=repos,
            paths=paths,
            keywords=keywords,
            priority="high" if kind == "flow" else "medium",
            confidence="medium",
            updatedAt=timestamp,
            owner="Maifeng",
            body=build_draft_body(kind, description, repos, paths, keywords, payload.notes.strip()),
            evidence=KnowledgeEvidence(
                inputDescription=description,
                repoMatches=repos,
                keywordMatches=keywords,
                pathMatches=paths,
                candidateFiles=files,
                contextHits=context_hits,
                retrievalNotes=[
                    "本次为本地 knowledge draft 生成，优先保留 domain / flow / rule 的高信号字段。",
                    "建议先确认摘要里的 repo hints 和正文里的待确认项，再决定是否发布。",
                    *([f"补充材料：{payload.notes.strip()}"] if payload.notes.strip() else []),
                ],
                openQuestions=build_open_questions(kind, description),
            ),
        )
        documents.append(document)
    return documents


def infer_engines(kind: str) -> list[str]:
    if kind == "flow":
        return ["plan", "refine"]
    return ["refine", "plan"]


def infer_domain_name(description: str) -> str:
    normalized = (
        description.strip()
        .replace("表达层", "")
        .replace("默认业务规则", "")
        .replace("业务规则", "")
        .replace("链路", "")
        .strip()
    )
    return normalized or description.strip() or "未命名领域"


def slugify_domain(name: str) -> str:
    if "讲解卡" in name:
        return "auction-explain-card"
    if "购物袋" in name:
        return "auction-shopping-bag"
    return f"knowledge-{int(datetime.now().timestamp())}"


def infer_keywords(description: str) -> list[str]:
    keywords: list[str] = []
    if "讲解卡" in description:
        keywords.extend(["讲解卡", "explain_card"])
    if "购物袋" in description:
        keywords.extend(["购物袋", "shopping_bag"])
    if "表达层" in description:
        keywords.extend(["表达层", "render", "卡片"])
    if not keywords:
        keywords.extend(["feature", "flow"])
    return list(dict.fromkeys(keywords))


def infer_paths(description: str) -> list[str]:
    if "讲解卡" in description:
        return ["app/explain_card", "service/card_render", "sdk/render"] if "表达层" in description else ["app/explain_card", "service/explain_card"]
    if "购物袋" in description:
        return ["app/shopping_bag", "service/shopping_bag", "gateway/bag"]
    return ["app/feature", "service/feature"]


def infer_candidate_files(paths: list[str]) -> list[str]:
    return [f"{path}/{path.split('/')[-1]}_handler.go" for path in paths]


def build_draft_title(kind: str, description: str) -> str:
    if kind == "flow":
        return "系统链路"
    if kind == "rule":
        return "业务规则"
    return "业务方向概览"


def build_draft_description(kind: str, description: str) -> str:
    if kind == "flow":
        return f"归纳 {description} 的主链路、关键依赖和 repo hints，供 plan 与 refine 渐进加载。"
    if kind == "rule":
        return f"整理 {description} 的默认规则、例外和待确认问题，供 refine 补边界时参考。"
    return f"概览 {infer_domain_name(description)} 的关键场景、相关链路和默认约束。"


def build_draft_body(kind: str, description: str, repos: list[str], paths: list[str], keywords: list[str], notes: str) -> str:
    repo_lines = "\n".join(f"- {repo}" for repo in repos)
    path_lines = "\n".join(f"- {path}" for path in paths)
    keyword_lines = "\n".join(f"- {keyword}" for keyword in keywords)
    notes_block = f"\n## Notes\n\n- {notes}\n" if notes else ""
    if kind == "flow":
        return (
            "## Summary\n\n"
            f"{description} 当前作为知识草稿，重点帮助 plan 先理解链路，再决定每个 repo 需要做什么。\n\n"
            "## Main Flow\n\n"
            "1. 根据场景入口识别表达层或业务入口。\n"
            "2. 收敛关键服务与状态判断。\n"
            "3. 明确需要联动的 repo 和模块。\n\n"
            "## Dependencies\n\n"
            f"{repo_lines}\n\n"
            "## Risks\n\n"
            "- 关键状态来源可能仍需人工确认。\n"
            "- 相邻模块边界可能需要在 repo 调研后继续收敛。\n\n"
            "## Repo Hints\n\n"
            f"{path_lines}\n\n"
            "## Open Questions\n\n"
            f"- 当前链路是否还有上游网关或配置依赖。{notes_block}"
        )
    if kind == "rule":
        return (
            "## Statement\n\n"
            f"- {description} 存在默认规则，但当前仍是待确认草稿。\n\n"
            "## Exceptions\n\n"
            "- 特殊实验或灰度逻辑可能覆盖默认规则。\n\n"
            "## Scope\n\n"
            f"- 当前只覆盖与 {description} 直接相关的主链路。\n\n"
            "## Open Questions\n\n"
            f"- 哪些例外规则已经在线上固化。{notes_block}"
        )
    return (
        "## Summary\n\n"
        f"{infer_domain_name(description)} 当前作为领域级知识入口，用来把相关 flow / rule 聚合到同一个 domain。\n\n"
        "## Terms\n\n"
        f"{keyword_lines}\n\n"
        "## Rules\n\n"
        "- 领域级规则仍待补齐。\n\n"
        "## Related Flows\n\n"
        f"- {description}{notes_block}"
    )


def build_open_questions(kind: str, description: str) -> list[str]:
    if kind == "rule":
        return ["默认规则和实验覆盖规则之间的优先级是否已经明确。"]
    if kind == "domain":
        return ["是否需要补一个领域级 glossary 文件。"]
    return [f"{description} 是否还有额外的上下游依赖没有被纳入当前链路。"]


def format_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")

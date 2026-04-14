from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

CONTEXT_MODE_SOURCE_ONLY = "source_only"
CONTEXT_MODE_PARTIAL_GROUNDED = "partial_grounded"
CONTEXT_MODE_GROUNDED = "grounded"
MAX_CONTEXT_EXCERPT = 1200
KNOWN_CONTEXT_FILES = (
    ("glossary.md", "glossary"),
    ("business-rules.md", "rules"),
    ("faq.md", "faq"),
    ("history-prds.md", "history"),
    ("architecture.md", "architecture"),
    ("patterns.md", "patterns"),
    ("gotchas.md", "gotchas"),
)


@dataclass(frozen=True)
class BusinessMemoryDocument:
    kind: str
    name: str
    path: str
    excerpt: str


@dataclass(frozen=True)
class BusinessMemoryContext:
    mode: str
    provider: str
    used: bool
    documents: list[BusinessMemoryDocument]
    risk_flags: list[str]


class BusinessMemoryProvider(Protocol):
    def load(self, repo_root: str | None) -> BusinessMemoryContext: ...


class NoopBusinessMemoryProvider:
    def load(self, repo_root: str | None) -> BusinessMemoryContext:
        return BusinessMemoryContext(
            mode=CONTEXT_MODE_SOURCE_ONLY,
            provider="noop",
            used=False,
            documents=[],
            risk_flags=[
                "terminology_may_be_ambiguous",
                "historical_business_rules_unavailable",
                "historical_decision_context_unavailable",
            ],
        )


class ContextDirectoryBusinessMemoryProvider:
    def load(self, repo_root: str | None) -> BusinessMemoryContext:
        if not repo_root:
            return NoopBusinessMemoryProvider().load(repo_root)

        context_dir = Path(repo_root) / ".livecoding" / "context"
        documents: list[BusinessMemoryDocument] = []
        for name, kind in KNOWN_CONTEXT_FILES:
            path = context_dir / name
            if not path.exists() or not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            excerpt = _excerpt(content)
            if not excerpt:
                continue
            documents.append(
                BusinessMemoryDocument(
                    kind=kind,
                    name=name,
                    path=str(path),
                    excerpt=excerpt,
                )
            )

        if not documents:
            return NoopBusinessMemoryProvider().load(repo_root)

        mode = CONTEXT_MODE_GROUNDED if len(documents) >= 3 else CONTEXT_MODE_PARTIAL_GROUNDED
        risk_flags = [] if mode == CONTEXT_MODE_GROUNDED else ["business_memory_is_partial"]
        return BusinessMemoryContext(
            mode=mode,
            provider="context_dir",
            used=True,
            documents=documents,
            risk_flags=risk_flags,
        )


def load_business_memory(repo_root: str | None) -> BusinessMemoryContext:
    return ContextDirectoryBusinessMemoryProvider().load(repo_root)


def render_business_memory_context(context: BusinessMemoryContext) -> str:
    if not context.used or not context.documents:
        return ""

    parts = [
        "## 业务历史上下文",
        "",
        "以下信息仅用于语义校准和术语消歧，不能覆盖当前 PRD 原文。",
        "如果历史上下文与当前 PRD 冲突，请优先遵循当前 PRD，并在“待确认问题”中明确指出冲突点。",
        "",
    ]
    for document in context.documents:
        parts.extend(
            [
                f"### {document.name} ({document.kind})",
                "",
                document.excerpt,
                "",
            ]
        )
    return "\n".join(parts).rstrip()


def _excerpt(content: str) -> str:
    normalized = content.strip()
    if len(normalized) <= MAX_CONTEXT_EXCERPT:
        return normalized
    return normalized[:MAX_CONTEXT_EXCERPT].rstrip() + "..."

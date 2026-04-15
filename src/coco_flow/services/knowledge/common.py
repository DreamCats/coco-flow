from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from json import JSONDecodeError, JSONDecoder
from pathlib import Path
import re
import uuid

from coco_flow.models.knowledge import KnowledgeDocument

KNOWLEDGE_KIND_ORDER = ("domain", "flow", "rule")
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"
SKIP_DIR_NAMES = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
SEARCHABLE_SUFFIXES = {
    ".go",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
GENERIC_TERM_STOPWORDS = {
    "api",
    "app",
    "biz",
    "cmd",
    "common",
    "config",
    "context",
    "controller",
    "core",
    "default",
    "domain",
    "entry",
    "handler",
    "impl",
    "infra",
    "internal",
    "local",
    "main",
    "manager",
    "model",
    "module",
    "pkg",
    "repo",
    "request",
    "response",
    "route",
    "router",
    "rpc",
    "schema",
    "service",
    "task",
    "test",
    "types",
    "util",
    "utils",
}
LOW_SIGNAL_SEARCH_TERMS = {
    "flow",
    "knowledge",
    "pipeline",
    "talent",
}
SYMBOL_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_]{2,}\b")
ROUTE_PATTERN = re.compile(r'["\'](/[^"\']+)["\']')
ANCHOR_PATH_KEYWORDS = {
    "router": 8,
    "route": 8,
    "handler": 7,
    "service": 6,
    "rpc": 6,
    "promotion": 5,
    "flash_sale": 7,
    "creator_promotion": 7,
    "exclusive": 7,
    "proto": 4,
    "pb_gen": 4,
    "idl": 4,
    "flow": 1,
    "pack": 1,
    "mw": 0,
}


@dataclass(frozen=True)
class KnowledgeDraftInput:
    title: str
    description: str
    selected_paths: list[str]
    kinds: list[str]
    notes: str = ""


@dataclass(frozen=True)
class KnowledgeGenerationResult:
    documents: list[KnowledgeDocument]
    trace_id: str
    open_questions: list[str]
    trace_files: dict[str, object]
    validation_errors: list[str]


ProgressHandler = Callable[[str, int, str], None]


def emit_progress(on_progress: ProgressHandler | None, status: str, progress: int, message: str) -> None:
    if on_progress is None:
        return
    on_progress(status, progress, message)


def normalize_selected_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_path in paths:
        value = str(raw_path).strip()
        if not value:
            continue
        if value not in normalized:
            normalized.append(value)
    return normalized


def normalize_kinds(kinds: list[str]) -> list[str]:
    normalized = [kind for kind in kinds if kind in KNOWLEDGE_KIND_ORDER]
    if "flow" not in normalized:
        normalized.insert(0, "flow")
    ordered = [kind for kind in KNOWLEDGE_KIND_ORDER if kind in normalized]
    return ordered or ["flow"]


def normalize_executor(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {EXECUTOR_LOCAL, EXECUTOR_NATIVE}:
        return normalized
    raise ValueError(f"unknown knowledge executor: {value}")


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return unique_strings([str(item) for item in value if str(item).strip()])


def extract_json_object(raw: str, error_message: str) -> dict[str, object]:
    decoder = JSONDecoder()
    text = raw.strip()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError(error_message)


def unique_questions(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        current = str(value).strip()
        if not current:
            continue
        normalized = normalize_question_key(current)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(current)
    return result


def normalize_question_key(value: str) -> str:
    current = str(value).strip().lower()
    current = current.replace("`", "")
    current = current.replace("（", "(").replace("）", ")")
    current = re.sub(r"[\s\u3000]+", "", current)
    current = re.sub(r"[。！？!?,，、:：;；'\"()\[\]{}<>]+", "", current)
    return current


def soften_weak_claims(body: str) -> str:
    softened = body
    replacements = {
        "可能参与处理。": "当前线索显示其可能参与处理，仍需进一步确认。",
        "可能参与处理": "当前线索显示其可能参与处理，仍需进一步确认",
        "可能调用": "当前更像会调用，仍需进一步确认",
        "可能用于": "当前更像用于，仍需进一步确认",
        "可能与": "当前线索显示可能与",
        "可能由": "当前线索显示可能由",
    }
    for source, target in replacements.items():
        softened = softened.replace(source, target)
    softened = re.sub(
        r"涉及分布式事务场景时，`([^`]+)` 的 `([^`]+)` 模块可能参与处理。",
        r"涉及分布式事务场景时，当前线索显示 `\1` 的 `\2` 模块可能参与处理，仍需进一步确认。",
        softened,
    )
    return softened


def build_display_paths(
    selected_paths: list[str],
    repo_research_payloads: list[dict[str, object]],
) -> list[str]:
    display_paths: list[str] = []
    for raw_path in selected_paths:
        current = str(raw_path).strip()
        if not current:
            continue
        display_paths.append(format_display_path(current, repo_research_payloads))
    return unique_strings(display_paths)


def format_display_path(path: str, repo_research_payloads: list[dict[str, object]]) -> str:
    target = Path(path).expanduser()
    try:
        resolved = target.resolve()
    except OSError:
        resolved = target

    best_match: tuple[int, str] | None = None
    for item in repo_research_payloads:
        repo_path = str(item.get("repo_path") or "").strip()
        repo_id = str(item.get("repo_id") or "").strip() or "repo"
        if not repo_path:
            continue
        repo_root = Path(repo_path).expanduser()
        try:
            relative = resolved.relative_to(repo_root.resolve())
        except (OSError, ValueError):
            continue
        rendered = f"{repo_id}:/" if str(relative) == "." else f"{repo_id}/{relative.as_posix()}"
        score = len(repo_root.as_posix())
        if best_match is None or score > best_match[0]:
            best_match = (score, rendered)
    if best_match is not None:
        return best_match[1]
    return resolved.name or path


def normalize_selected_paths_section(body: str, display_paths: list[str]) -> str:
    marker = "## Selected Paths"
    next_marker = "\n## "
    if marker not in body:
        return body
    start = body.find(marker)
    content_start = body.find("\n\n", start)
    if content_start == -1:
        return body
    content_start += 2
    next_section = body.find(next_marker, content_start)
    if next_section == -1:
        next_section = len(body)
    rendered_paths = "\n".join(f"- `{path}`" for path in display_paths) if display_paths else "- 待补充"
    return body[:content_start] + rendered_paths + body[next_section:]


def infer_domain_name(title: str) -> str:
    normalized = title
    for term in ("系统链路", "表达层", "默认业务规则", "业务规则", "链路"):
        normalized = normalized.replace(term, "")
    return normalized.strip() or title.strip() or "未命名领域"


def slugify_domain(name: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    if tokens:
        return "-".join(tokens[:4])
    stable_hash = hashlib.sha1(name.strip().encode("utf-8")).hexdigest()[:8]
    return f"knowledge-{stable_hash}"


def infer_query_terms(title: str, description: str, notes: str) -> list[str]:
    terms: list[str] = []
    for source in (title, description, notes):
        current = source.strip()
        if not current:
            continue
        terms.extend(term for term in re.findall(r"[A-Za-z0-9_/-]+", current) if len(term) >= 2)
        terms.extend(re.findall(r"[\u4e00-\u9fff]{2,8}", current))
    return unique_strings(terms)


def infer_search_terms(query_terms: list[str], domain_candidate: str) -> list[str]:
    search_terms: list[str] = list(query_terms)
    search_terms.extend([part for part in domain_candidate.split("-") if part])
    return sanitize_search_terms([term for term in search_terms if len(str(term).strip()) >= 2])


def candidate_terms(candidate: dict[str, object]) -> list[str]:
    return unique_strings(
        [
            *[str(item) for item in candidate.get("top_level_dirs", [])],
            *[str(item) for item in candidate.get("file_terms", [])],
            *[str(item) for item in candidate.get("route_terms", [])],
            *[str(item) for item in candidate.get("symbol_terms", [])],
            *[str(item) for item in candidate.get("commit_terms", [])],
        ]
    )


def infer_repo_terms_for_user_term(user_term: str, repo_candidates: list[dict[str, object]]) -> list[str]:
    repo_terms: list[str] = []
    for candidate in repo_candidates:
        for alias in candidate.get("context_aliases", []):
            if not isinstance(alias, dict):
                continue
            source_terms = [str(item) for item in alias.get("source_terms", [])]
            if not any(score_term_match(user_term, source_term) > 0 for source_term in source_terms):
                continue
            repo_terms.extend(str(item) for item in alias.get("repo_terms", []))
        for repo_term in candidate_terms(candidate):
            if score_term_match(user_term, repo_term) <= 0:
                continue
            repo_terms.append(repo_term)
    return unique_strings([term for term in repo_terms if is_meaningful_term(term)])[:8]


def normalize_match_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def split_match_tokens(value: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", value)
    parts: list[str] = []
    for token in tokens:
        parts.extend(part for part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", token) if part)
    normalized = [part.lower() for part in parts if len(part) >= 2]
    if "_" in value or "-" in value or "/" in value:
        normalized.extend(part.lower() for part in re.split(r"[_/\-]+", value) if len(part) >= 2)
    return unique_strings(normalized)


def score_term_match(user_term: str, repo_term: str) -> int:
    normalized_user = normalize_match_text(user_term)
    normalized_repo = normalize_match_text(repo_term)
    if not normalized_user or not normalized_repo:
        return 0
    if normalized_user in normalized_repo or normalized_repo in normalized_user:
        return 3
    user_tokens = set(split_match_tokens(user_term))
    repo_tokens = set(split_match_tokens(repo_term))
    overlap = len(user_tokens & repo_tokens)
    if overlap:
        return overlap + 1
    return 0


def is_meaningful_term(value: str) -> bool:
    current = str(value).strip()
    if len(current) < 2:
        return False
    if current.lower() in GENERIC_TERM_STOPWORDS:
        return False
    return True


def sanitize_search_terms(values: list[str]) -> list[str]:
    sanitized: list[str] = []
    for value in values:
        current = str(value).strip()
        lowered = current.lower()
        if not current:
            continue
        if lowered in LOW_SIGNAL_SEARCH_TERMS:
            continue
        if lowered in {"knowledge", "talent", "pipeline"}:
            continue
        if lowered in GENERIC_TERM_STOPWORDS and "_" not in current and current == lowered:
            continue
        sanitized.append(current)
    return unique_strings(sanitized)


def clean_document_keywords(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen_normalized: set[str] = set()
    for value in values:
        current = str(value).strip()
        if not current:
            continue
        normalized = normalize_keyword_for_document(current)
        if not normalized:
            continue
        dedupe_key = normalized.lower()
        if dedupe_key in seen_normalized:
            continue
        seen_normalized.add(dedupe_key)
        cleaned.append(normalized)
    return cleaned


def normalize_keyword_for_document(value: str) -> str:
    current = str(value).strip()
    lowered = current.lower()
    if not current:
        return ""
    if re.fullmatch(r"[a-f0-9]{8,}", lowered):
        return ""
    if lowered.startswith("knowledge-"):
        return ""
    if lowered in LOW_SIGNAL_SEARCH_TERMS:
        return ""
    if lowered in {"flash", "sale", "create", "update", "launch", "deactivate", "operate", "save"}:
        return ""
    if lowered in {"live promotion", "live_promotion"}:
        return ""
    if " " in current and current.lower() == current:
        current = current.replace(" ", "_")
    if re.fullmatch(r"[A-Z][a-z]+", current):
        current = current.lower()
    return current


def slugify_repo_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "repo"


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        current = str(value).strip()
        if not current or current in result:
            continue
        result.append(current)
    return result

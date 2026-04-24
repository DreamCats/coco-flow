from __future__ import annotations

from pathlib import Path
import re

from coco_flow.config import Settings
from coco_flow.prompts.design import build_search_hints_prompt, build_search_hints_template_json

from .agent_io import run_agent_json
from .models import DesignInputBundle
from .utils import as_str_list, dedupe

_MAX_SEARCH_TERMS = 12
_MAX_SYMBOLS = 12
_MAX_FILE_PATTERNS = 10
_MAX_NEGATIVE_TERMS = 8
_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "this",
    "that",
    "true",
    "false",
    "refined",
    "prd",
    "should",
    "must",
}


def build_search_hints(
    prepared: DesignInputBundle,
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> dict[str, object]:
    if native_ok:
        try:
            payload = run_agent_json(
                prepared,
                settings,
                build_search_hints_template_json(),
                lambda template_path: build_search_hints_prompt(
                    title=prepared.title,
                    refined_markdown=prepared.refined_markdown,
                    design_skills_brief_markdown=prepared.design_skills_brief_markdown,
                    repo_context_payload=_repo_context(prepared),
                    template_path=template_path,
                ),
                ".design-search-hints-",
            )
            normalized = normalize_search_hints(payload, source="native")
            if _has_usable_hints(normalized):
                return normalized
        except Exception as error:
            on_log(f"design_v3_search_hints_degraded: {error}")
    return build_local_search_hints(prepared)


def build_local_search_hints(prepared: DesignInputBundle) -> dict[str, object]:
    source_text = "\n".join(
        [
            prepared.title,
            *prepared.sections.change_scope,
            *prepared.sections.key_constraints,
            *prepared.sections.acceptance_criteria,
            prepared.refined_markdown[:4000],
            prepared.design_skills_brief_markdown[:2500],
        ]
    )
    identifiers = _extract_identifier_terms(source_text)
    chinese_terms = _extract_chinese_terms(source_text)
    search_terms = dedupe([*identifiers, *chinese_terms])[:_MAX_SEARCH_TERMS]
    symbols = [term for term in identifiers if _looks_like_symbol(term)][:_MAX_SYMBOLS]
    file_patterns = _derive_file_patterns(identifiers)[:_MAX_FILE_PATTERNS]
    return {
        "source": "local",
        "search_terms": search_terms or [prepared.title],
        "likely_symbols": symbols,
        "likely_file_patterns": file_patterns,
        "negative_terms": [],
        "confidence": "medium" if search_terms else "low",
        "rationale": "本地从 refined PRD 的标题、范围、约束和验收标准中提取搜索线索。",
    }


def normalize_search_hints(payload: dict[str, object], *, source: str) -> dict[str, object]:
    search_terms = _clean_terms(payload.get("search_terms"), _MAX_SEARCH_TERMS)
    symbols = _clean_terms(payload.get("likely_symbols"), _MAX_SYMBOLS)
    file_patterns = _clean_file_patterns(payload.get("likely_file_patterns"), _MAX_FILE_PATTERNS)
    negative_terms = _clean_terms(payload.get("negative_terms"), _MAX_NEGATIVE_TERMS)
    confidence = str(payload.get("confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    return {
        "source": source,
        "search_terms": search_terms,
        "likely_symbols": symbols,
        "likely_file_patterns": file_patterns,
        "negative_terms": negative_terms,
        "confidence": confidence,
        "rationale": str(payload.get("rationale") or "").strip()[:500],
    }


def _repo_context(prepared: DesignInputBundle) -> list[dict[str, object]]:
    return [
        {
            "repo_id": repo.repo_id,
            "repo_name": Path(repo.repo_path).name,
        }
        for repo in prepared.repo_scopes
    ]


def _has_usable_hints(payload: dict[str, object]) -> bool:
    return bool(as_str_list(payload.get("search_terms")) or as_str_list(payload.get("likely_symbols")) or as_str_list(payload.get("likely_file_patterns")))


def _extract_identifier_terms(text: str) -> list[str]:
    terms: list[str] = []
    for value in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text):
        lower = value.lower()
        if lower not in _STOPWORDS:
            terms.append(value)
    return dedupe(terms)


def _extract_chinese_terms(text: str) -> list[str]:
    return dedupe(re.findall(r"[\u4e00-\u9fff]{2,8}", text))


def _looks_like_symbol(value: str) -> bool:
    return bool(re.search(r"[A-Z_]", value)) or "." in value or "-" in value


def _derive_file_patterns(identifiers: list[str]) -> list[str]:
    patterns: list[str] = []
    for value in identifiers:
        for part in _identifier_parts(value):
            if len(part) >= 3 and part.lower() not in _STOPWORDS:
                patterns.append(part.lower())
    return dedupe(patterns)


def _identifier_parts(value: str) -> list[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return [part for part in re.split(r"[^A-Za-z0-9]+|_", expanded) if part]


def _clean_terms(raw: object, max_items: int) -> list[str]:
    values: list[str] = []
    for item in as_str_list(raw):
        value = item.strip()
        if 2 <= len(value) <= 80 and value.lower() not in _STOPWORDS:
            values.append(value)
    return dedupe(values)[:max_items]


def _clean_file_patterns(raw: object, max_items: int) -> list[str]:
    values: list[str] = []
    for item in as_str_list(raw):
        value = item.strip().strip("*").strip("/")
        if not value or value.startswith(".") or value in {"go", "py", "ts", "tsx", "js", "jsx"}:
            continue
        if 2 <= len(value) <= 80:
            values.append(value)
    return dedupe(values)[:max_items]

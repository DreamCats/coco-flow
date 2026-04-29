"""Scope guard helpers for Design repository research."""

from __future__ import annotations

import re

from coco_flow.engines.design.support import as_str_list, dedupe

_NEGATION_PREFIXES = (
    "不改",
    "不涉及",
    "不影响",
    "不触碰",
    "不扩大到",
    "不纳入",
    "排除",
    "非",
)
_CN_SUFFIXES = ("价格展示", "展示", "价格", "链路", "逻辑", "规则", "模块", "能力", "范围")
_CN_STOP_TERMS = {"真实", "底层", "通用", "公共", "服务", "字段", "配置", "协议"}
_EN_STOP_TERMS = {
    "change",
    "display",
    "format",
    "global",
    "logic",
    "module",
    "price",
    "rule",
    "service",
    "shared",
    "value",
}


def build_scope_guard_terms(non_goals: list[str]) -> list[str]:
    """Derive exclusion terms from refined PRD non-goals."""
    terms: list[str] = []
    for item in as_str_list(non_goals):
        terms.extend(_terms_from_non_goal(item))
    return dedupe(terms)[:16]


def exclusion_reason(path: str, matches: list[dict[str, object]], negative_terms: list[str]) -> str:
    hits = _negative_hits(path, matches, negative_terms)
    if not hits:
        return ""
    return "命中 PRD 明确不做/排除信号：" + "、".join(hits[:4])


def _negative_hits(path: str, matches: list[dict[str, object]], negative_terms: list[str]) -> list[str]:
    haystack = " ".join([path, *(str(item.get("text") or "") for item in matches)]).lower()
    return dedupe(term for term in as_str_list(negative_terms) if term.strip() and term.lower() in haystack)


def _terms_from_non_goal(value: str) -> list[str]:
    text = _strip_negation_prefix(value.strip())
    return [*_cn_terms(text), *_en_terms(text)]


def _strip_negation_prefix(value: str) -> str:
    text = re.sub(r"^[\s\-*•\d.、]+", "", value)
    for prefix in _NEGATION_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :].strip(" ：:，,。.")
    return text


def _cn_terms(text: str) -> list[str]:
    terms: list[str] = []
    for match in re.findall(r"[\u4e00-\u9fff]{2,16}", text):
        terms.append(match)
        trimmed = _trim_cn_suffix(match)
        if trimmed != match:
            terms.append(trimmed)
    return [term for term in terms if term and term not in _CN_STOP_TERMS]


def _trim_cn_suffix(value: str) -> str:
    result = value
    for suffix in _CN_SUFFIXES:
        if result.endswith(suffix) and len(result) > len(suffix):
            result = result[: -len(suffix)]
    return result


def _en_terms(text: str) -> list[str]:
    words = [item.lower() for item in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)]
    terms = [word for word in words if word not in _EN_STOP_TERMS]
    if len(terms) >= 2:
        phrase = " ".join(terms[:3])
        terms.extend([phrase, phrase.replace(" ", "_")])
    return terms

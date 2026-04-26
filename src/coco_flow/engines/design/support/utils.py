"""Design 引擎通用小工具。

集中放置字符串列表归一化、dict 列表过滤、去重等无业务含义的纯函数。
"""

from __future__ import annotations

from typing import Iterable


def as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def first_non_empty(values: Iterable[str], fallback: str) -> str:
    for value in values:
        if str(value).strip():
            return str(value).strip()
    return fallback


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        result.append(text)
    return result

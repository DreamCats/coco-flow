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


def normalize_issue(item: dict[str, object]) -> dict[str, object]:
    severity = str(item.get("severity") or "warning").strip()
    if severity not in {"blocking", "warning", "info"}:
        severity = "warning"
    return {
        "severity": severity,
        "failure_type": str(item.get("failure_type") or "semantic_risk"),
        "target": str(item.get("target") or ""),
        "expected": str(item.get("expected") or ""),
        "actual": str(item.get("actual") or ""),
        "suggested_action": str(item.get("suggested_action") or ""),
    }


def issue(severity: str, failure_type: str, target: str, expected: str, actual: str, suggested_action: str) -> dict[str, object]:
    return {
        "severity": severity,
        "failure_type": failure_type,
        "target": target,
        "expected": expected,
        "actual": actual,
        "suggested_action": suggested_action,
    }


def issues(payload: dict[str, object]) -> list[dict[str, object]]:
    return [normalize_issue(item) for item in dict_list(payload.get("issues"))]


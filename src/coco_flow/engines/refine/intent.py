from __future__ import annotations

import re

from .models import RefineIntent, RefinePreparedInput

_ASCII_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_CJK_TERM_RE = re.compile(r"[\u4e00-\u9fff]{2,12}")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+\.))\s*")
_STOPWORDS = {
    "需求",
    "功能",
    "页面",
    "支持",
    "需要",
    "当前",
    "用户",
    "系统",
    "相关",
    "进行",
    "实现",
    "处理",
    "说明",
    "方案",
    "规则",
    "状态",
    "逻辑",
    "内容",
    "流程",
    "原文",
    "默认",
    "功能点",
    "边界条件",
    "交互与展示",
    "验收标准",
    "业务规则",
    "待确认问题",
}
_CONSTRAINT_HINTS = ("必须", "需要", "不能", "不可", "仅", "限制", "兼容", "支持", "不支持", "默认", "至少", "最多")
_QUESTION_HINTS = ("?", "？", "待确认", "TODO", "todo", "确认", "是否")


def extract_refine_intent(prepared: RefinePreparedInput) -> RefineIntent:
    lines = _normalized_lines(prepared.source_content)
    goal = _extract_goal(lines, prepared.title)
    features = _extract_features(lines)
    constraints = _extract_constraints(lines)
    open_questions = _extract_open_questions(lines)
    key_terms = _extract_key_terms("\n".join([prepared.title, prepared.source_content]))
    return RefineIntent(
        title=prepared.title,
        source_type=prepared.source_type,
        goal=goal,
        key_terms=key_terms,
        potential_features=features,
        constraints=constraints,
        open_questions=open_questions,
        source_length=len(prepared.source_content),
    )


def render_intent_summary(intent: RefineIntent) -> str:
    return "\n".join(
        [
            "- 需求目标：",
            _render_list([intent.goal], default="  - 无"),
            "- 关键术语：",
            _render_list(intent.key_terms, default="  - 无"),
            "- 候选功能点：",
            _render_list(intent.potential_features, default="  - 无"),
            "- 约束与边界：",
            _render_list(intent.constraints, default="  - 无"),
            "- 待确认项：",
            _render_list(intent.open_questions, default="  - 无"),
        ]
    )


def _normalized_lines(content: str) -> list[str]:
    items: list[str] = []
    for raw in content.splitlines():
        current = raw.strip()
        if not current:
            continue
        current = _LIST_PREFIX_RE.sub("", current)
        if not current or current.startswith("#"):
            continue
        items.append(current)
    return items


def _extract_goal(lines: list[str], title: str) -> str:
    for line in lines:
        if len(line) < 6:
            continue
        return line[:120]
    return title


def _extract_features(lines: list[str]) -> list[str]:
    features: list[str] = []
    for line in lines:
        if any(hint in line for hint in _QUESTION_HINTS):
            continue
        if len(line) > 2:
            features.append(line[:120])
        if len(features) >= 6:
            break
    return _unique(features)


def _extract_constraints(lines: list[str]) -> list[str]:
    return _unique([line[:120] for line in lines if any(hint in line for hint in _CONSTRAINT_HINTS)])[:6]


def _extract_open_questions(lines: list[str]) -> list[str]:
    return _unique([line[:120] for line in lines if any(hint in line for hint in _QUESTION_HINTS)])[:6]


def _extract_key_terms(content: str) -> list[str]:
    candidates = [*_ASCII_TERM_RE.findall(content), *_CJK_TERM_RE.findall(content)]
    terms: list[str] = []
    for item in candidates:
        current = item.strip("`'\"()[]{}<>.,:;，。！？、")
        if len(current) < 2 or current in _STOPWORDS:
            continue
        if current.isascii() and current.lower() in {"http", "https", "json", "markdown"}:
            continue
        terms.append(current)
    return _unique(terms)[:12]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _render_list(items: list[str], default: str) -> str:
    if not items:
        return default
    return "\n".join(f"  - {item}" for item in items)

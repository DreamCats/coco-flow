from __future__ import annotations

import json
import re

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings

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


def extract_native_refine_intent(prepared: RefinePreparedInput, settings: Settings) -> RefineIntent:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    raw = client.run_prompt_only(
        build_native_refine_intent_prompt(prepared),
        settings.native_query_timeout,
        cwd=prepared.repo_root,
        fresh_session=True,
    )
    return parse_native_refine_intent_output(raw, prepared)


def build_native_refine_intent_prompt(prepared: RefinePreparedInput) -> str:
    return f"""你在做 coco-flow refine intent extraction。

目标：只根据当前 PRD 原文，抽取一份供后续 refine 使用的结构化意图骨架。

要求：
1. 只能基于当前 PRD 原文，不要引入代码实现、历史知识或外部假设。
2. 如果信息不明确，放入 open_questions，不要编造。
3. 输出必须是 JSON 对象，不要输出其它文字。
4. JSON 格式：
{{
  "goal": "一句话需求目标",
  "key_terms": ["术语1", "术语2"],
  "potential_features": ["功能点1", "功能点2"],
  "constraints": ["约束1", "约束2"],
  "open_questions": ["待确认1", "待确认2"]
}}

当前任务标题：{prepared.title}

PRD 原文：
{prepared.source_content}
"""


def parse_native_refine_intent_output(raw: str, prepared: RefinePreparedInput) -> RefineIntent:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid_intent_json: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("intent_output_is_not_object")
    return RefineIntent(
        title=prepared.title,
        source_type=prepared.source_type,
        goal=str(payload.get("goal") or prepared.title).strip() or prepared.title,
        key_terms=_normalized_string_list(payload.get("key_terms"))[:12],
        potential_features=_normalized_string_list(payload.get("potential_features"))[:6],
        constraints=_normalized_string_list(payload.get("constraints"))[:6],
        open_questions=_normalized_string_list(payload.get("open_questions"))[:6],
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


def _normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        current = str(item).strip()
        if current:
            result.append(current[:160])
    return _unique(result)


def _render_list(items: list[str], default: str) -> str:
    if not items:
        return default
    return "\n".join(f"  - {item}" for item in items)

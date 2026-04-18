from __future__ import annotations

import json
import re
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.refine import build_refine_intent_agent_prompt, build_refine_intent_template_json

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
    "输入",
    "风险提示",
    "讨论点",
    "边界",
}
_RISK_HINTS = ("风险", "兼容", "依赖", "异常", "回退", "失败", "冲突", "影响")
_QUESTION_HINTS = ("?", "？", "待确认", "TODO", "todo", "确认", "是否", "补充")
_BOUNDARY_HINTS = ("仅", "不", "除外", "不做", "非目标", "不涉及", "限定", "范围")
_BACKGROUND_HINTS = ("背景", "当前", "现状", "目前", "已有", "存在", "有时", "会导致")


def extract_refine_intent(prepared: RefinePreparedInput) -> RefineIntent:
    lines = _normalized_lines("\n".join([prepared.source_content, prepared.supplement]).strip())
    goal = next((line[:120] for line in lines if len(line) >= 6), prepared.title)
    return RefineIntent(
        goal=goal,
        change_points=_extract_change_points(lines),
        terms=_extract_key_terms("\n".join([prepared.title, prepared.source_content, prepared.supplement])),
        risks_seed=_extract_by_hints(lines, _RISK_HINTS, limit=5),
        discussion_seed=_extract_discussion(lines),
        boundary_seed=_extract_by_hints(lines, _BOUNDARY_HINTS, limit=5),
    )


def extract_native_refine_intent(prepared: RefinePreparedInput, settings: Settings) -> RefineIntent:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_intent_template(prepared.task_dir)
    try:
        reply = client.run_agent(
            build_refine_intent_agent_prompt(
                title=prepared.title,
                source_markdown=prepared.source_markdown,
                supplement=prepared.supplement,
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        if _contains_fill_marker(raw):
            raise ValueError("intent_template_unfilled")
        _ = reply
    finally:
        if template_path.exists():
            template_path.unlink()
    return parse_native_refine_intent_output(raw, prepared)


def _write_intent_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".refine-intent-",
        suffix=".json",
        delete=False,
    ) as handle:
        handle.write(build_refine_intent_template_json())
        handle.flush()
        return Path(handle.name)


def _contains_fill_marker(raw: str) -> bool:
    return "__FILL__" in raw


def parse_native_refine_intent_output(raw: str, prepared: RefinePreparedInput) -> RefineIntent:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid_intent_json: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("intent_output_is_not_object")
    if _payload_has_fill_marker(payload):
        raise ValueError("intent_output_contains_fill_marker")
    return RefineIntent(
        goal=str(payload.get("goal") or prepared.title).strip() or prepared.title,
        change_points=_normalized_string_list(payload.get("change_points"))[:6],
        terms=_normalized_string_list(payload.get("terms"))[:12],
        risks_seed=_normalized_string_list(payload.get("risks_seed"))[:6],
        discussion_seed=_normalized_string_list(payload.get("discussion_seed"))[:8],
        boundary_seed=_normalized_string_list(payload.get("boundary_seed"))[:6],
    )


def _payload_has_fill_marker(value: object) -> bool:
    if isinstance(value, str):
        return "__FILL__" in value
    if isinstance(value, list):
        return any(_payload_has_fill_marker(item) for item in value)
    if isinstance(value, dict):
        return any(_payload_has_fill_marker(item) for item in value.values())
    return False


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


def _extract_change_points(lines: list[str]) -> list[str]:
    return _unique([line[:120] for line in lines if not any(hint in line for hint in _QUESTION_HINTS)][:6])


def _extract_discussion(lines: list[str]) -> list[str]:
    extracted = [line[:120] for line in lines if any(hint in line for hint in _QUESTION_HINTS)]
    if extracted:
        return _unique(extracted)[:8]
    return _extract_by_hints(lines, ("需确认", "建议", "可选", "口径", "是否"), limit=6)


def _extract_by_hints(lines: list[str], hints: tuple[str, ...], *, limit: int) -> list[str]:
    selected: list[str] = []
    for line in lines:
        if not any(hint in line for hint in hints):
            continue
        if hints == _RISK_HINTS and _looks_like_background(line):
            continue
        selected.append(line[:120])
    return _unique(selected)[:limit]


def _looks_like_background(line: str) -> bool:
    return any(hint in line for hint in _BACKGROUND_HINTS) and "可能" not in line and "误" not in line


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


def _normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        current = str(item).strip()
        if current:
            result.append(current[:160])
    return _unique(result)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(item)
    return ordered

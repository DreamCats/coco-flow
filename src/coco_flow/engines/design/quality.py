"""Lightweight Design quality inference."""

from __future__ import annotations

import re

from coco_flow.engines.design.support import dedupe
from coco_flow.engines.shared.models import RefinedSections


def infer_design_open_questions(sections: RefinedSections) -> list[str]:
    """Infer implementation-blocking questions from refined PRD text."""
    questions: list[str] = []
    text = _section_text(sections)
    preserved_decimal = _find_preserved_decimal_example(text)
    if preserved_decimal and _has_remove_trailing_zero_rule(text):
        trimmed_decimal = _trim_decimal_zeros(preserved_decimal)
        questions.append(
            f"待确认：格式规则存在冲突：`{preserved_decimal}` 被描述为保持不变，同时又要求去掉尾随 0；"
            f"请确认该示例是否保持原样，还是转换为 `{trimmed_decimal}`。"
        )
    return dedupe(questions)


def merge_open_questions(existing: list[str], inferred: list[str]) -> list[str]:
    return dedupe([*existing, *inferred])


def ensure_inferred_open_questions(markdown: str, sections: RefinedSections) -> tuple[str, int]:
    inferred = infer_design_open_questions(sections)
    missing = [item for item in inferred if item not in markdown]
    if not missing:
        return markdown, 0
    return _append_open_questions(markdown, missing), len(missing)


def _section_text(sections: RefinedSections) -> str:
    return "\n".join(
        [
            sections.raw,
            *sections.change_scope,
            *sections.key_constraints,
            *sections.acceptance_criteria,
            *sections.open_questions,
        ]
    )


def _append_open_questions(markdown: str, questions: list[str]) -> str:
    lines = markdown.rstrip().splitlines()
    heading_index = _find_heading(lines, "风险与待确认")
    question_lines = [f"- {item}" for item in questions]
    if heading_index < 0:
        lines.extend(["", "## 风险与待确认", *question_lines])
        return "\n".join(lines).rstrip() + "\n"

    next_heading_index = _find_next_same_or_higher_heading(lines, heading_index)
    insert_at = next_heading_index if next_heading_index >= 0 else len(lines)
    while insert_at > heading_index + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines[insert_at:insert_at] = question_lines
    return "\n".join(lines).rstrip() + "\n"


def _find_heading(lines: list[str], title: str) -> int:
    pattern = re.compile(rf"^##+\s+{re.escape(title)}\s*$")
    for index, line in enumerate(lines):
        if pattern.match(line.strip()):
            return index
    return -1


def _find_next_same_or_higher_heading(lines: list[str], heading_index: int) -> int:
    current_level = len(lines[heading_index]) - len(lines[heading_index].lstrip("#"))
    for index in range(heading_index + 1, len(lines)):
        line = lines[index].lstrip()
        if not line.startswith("#"):
            continue
        level = len(line) - len(line.lstrip("#"))
        if level <= current_level:
            return index
    return -1


def _find_preserved_decimal_example(text: str) -> str:
    keep_markers = ("保持", "不变", "保留", "remain", "unchanged", "keep")
    for sentence in _sentences(text):
        normalized = sentence.lower()
        if not any(marker in normalized for marker in keep_markers):
            continue
        match = re.search(r"\b\d+\.\d*[1-9]0+\b", sentence)
        if match:
            return match.group(0)
    return ""


def _has_remove_trailing_zero_rule(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.lower())
    return any(
        marker in normalized
        for marker in (
            "小数点后面的0都去掉",
            "小数点后的0都去掉",
            "尾随0都去掉",
            "去掉尾随0",
            "去除尾随0",
            "trimtrailingzero",
            "removetrailingzero",
            "remove trailing zero",
        )
    )


def _trim_decimal_zeros(value: str) -> str:
    if "." not in value:
        return value
    trimmed = value.rstrip("0").rstrip(".")
    return trimmed or value


def _sentences(text: str) -> list[str]:
    return [item for item in re.split(r"[\n。；;!?？]+", text) if item.strip()]

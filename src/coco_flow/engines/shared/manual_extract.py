from __future__ import annotations

import re

MANUAL_EXTRACT_HEADING = "## 人工提炼范围"
LEGACY_MANUAL_EXTRACT_HEADINGS = ("## 研发补充说明",)
MANUAL_EXTRACT_SECTION_TITLES = (
    "本次范围",
    "人工提炼改动点",
    "明确不做",
    "前置条件 / 待确认项",
)
REQUIRED_MANUAL_EXTRACT_SECTION_TITLES = (
    "本次范围",
    "人工提炼改动点",
)
MANUAL_EXTRACT_SECTION_BODIES = {
    "本次范围": "- [必填] 这次只做什么，先用一句话收敛范围。",
    "人工提炼改动点": "- [必填] 按“场景 / 状态 / 改动”逐条列出服务端改动点。",
    "明确不做": "- 如无可写：无",
    "前置条件 / 待确认项": "- 如有实验命中条件、接口依赖、跨端协同点，请写这里；如无可写：无",
}
MANUAL_EXTRACT_TEMPLATE = "\n\n".join(
    f"## {title}\n{MANUAL_EXTRACT_SECTION_BODIES[title]}" for title in MANUAL_EXTRACT_SECTION_TITLES
)

_section_heading = re.compile(r"^##\s+(.+?)\s*$")
_list_marker = re.compile(r"^(?:[-*+]\s+|\d+\.\s+|\[\s?[xX]?\s?\]\s*)")
_empty_markers = {"无", "暂无", "待补充", "todo", "tbd", "n/a", "na"}


def split_source_and_manual_extract(content: str) -> tuple[str, str]:
    positions = [
        (content.find(heading), heading)
        for heading in (MANUAL_EXTRACT_HEADING, *LEGACY_MANUAL_EXTRACT_HEADINGS)
        if heading in content
    ]
    if not positions:
        return content.strip(), ""
    index, heading = min(positions, key=lambda item: item[0])
    return content[:index].strip(), content[index + len(heading) :].strip()


def validate_manual_extract(content: str) -> str | None:
    trimmed = content.strip()
    if not trimmed:
        return "人工提炼范围不能为空，请先按模板补齐“本次范围”和“人工提炼改动点”。"
    sections = parse_manual_extract_sections(trimmed)
    missing = [title for title in REQUIRED_MANUAL_EXTRACT_SECTION_TITLES if not _has_meaningful_content(sections.get(title, ""), title)]
    if missing:
        return f"人工提炼范围未填写完整，请至少补齐：{'、'.join(missing)}。"
    return None


def require_manual_extract(content: str) -> str:
    error = validate_manual_extract(content)
    if error:
        raise ValueError(error)
    return content.strip()


def parse_manual_extract_sections(content: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_title: str | None = None
    for raw_line in content.strip().splitlines():
        line = raw_line.rstrip()
        matched = _section_heading.match(line.strip())
        if matched:
            current_title = matched.group(1).strip()
            sections.setdefault(current_title, [])
            continue
        if current_title is None:
            continue
        sections[current_title].append(line)
    return {title: "\n".join(lines).strip() for title, lines in sections.items()}


def _has_meaningful_content(body: str, title: str) -> bool:
    entries = _normalize_entries(body)
    if not entries:
        return False
    if all(entry.lower() in _empty_markers for entry in entries):
        return False
    return entries != _normalize_entries(MANUAL_EXTRACT_SECTION_BODIES[title])


def _normalize_entries(body: str) -> list[str]:
    entries: list[str] = []
    for raw_line in body.splitlines():
        line = _list_marker.sub("", raw_line.strip())
        line = line.replace("[必填]", "", 1).strip()
        if line:
            entries.append(line)
    return entries

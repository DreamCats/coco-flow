from __future__ import annotations

import re

_TABLE_PATTERN = re.compile(r"<lark-table\b([^>]*)>(.*?)</lark-table>", re.DOTALL)
_ROW_PATTERN = re.compile(r"<lark-tr\b[^>]*>(.*?)</lark-tr>", re.DOTALL)
_CELL_PATTERN = re.compile(r"<lark-td\b[^>]*>(.*?)</lark-td>", re.DOTALL)
_ATTR_PATTERN = re.compile(r'([A-Za-z0-9_-]+)="(.*?)"')
_ANNOTATION_PATTERN = re.compile(r"\s*\{[A-Za-z0-9_-]+=\"[^\"]*\"\}")
_HEADING_ONLY_PATTERN = re.compile(r"^\s*#{1,6}\s*$")
_ATX_HEADING_PATTERN = re.compile(r"^(?P<prefix>\s*#{1,6}\s+)(?P<body>.*?)(?:\s+#+\s*|\s*#+\s*)$")
_SELF_CLOSING_TAGS = ("mention-user", "image", "file")
_MENTION_DOC_PATTERN = re.compile(r"<mention-doc\b([^>]*)>(.*?)</mention-doc>", re.DOTALL)
_GENERIC_TAG_PATTERN = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s+[^>\n]*)?/?>")


def normalize_lark_markdown(content: str) -> str:
    text = content.replace("\r\n", "\n").strip()
    if not text:
        return ""

    previous = ""
    while previous != text:
        previous = text
        text = _TABLE_PATTERN.sub(lambda match: _render_table(match.group(1), match.group(2)), text)
        text = _MENTION_DOC_PATTERN.sub(lambda match: _render_mention_doc(match.group(1), match.group(2)), text)
        for tag in ("callout", "quote-container", "grid", "column", "view"):
            text = _replace_wrapped_tag(text, tag, block=True)
        text = _replace_wrapped_tag(text, "text", block=False)
        for tag in _SELF_CLOSING_TAGS:
            text = _replace_self_closing_tag(text, tag)

    text = _ANNOTATION_PATTERN.sub("", text)
    text = _GENERIC_TAG_PATTERN.sub("", text)
    text = _normalize_markdown_lines(text)
    text = _normalize_blank_lines(text)
    return text.strip()


def _render_table(attrs_text: str, body: str) -> str:
    rows: list[list[str]] = []
    for row_match in _ROW_PATTERN.finditer(body):
        cells = [
            _normalize_inline_fragment(cell_match.group(1))
            for cell_match in _CELL_PATTERN.finditer(row_match.group(1))
        ]
        if cells:
            rows.append(cells)

    if not rows:
        return normalize_lark_markdown(body)

    if len(rows) == 1:
        return "\n".join(f"- {cell}" for cell in rows[0] if cell.strip())

    attributes = _parse_attrs(attrs_text)
    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    if attributes.get("header-row") == "true":
        header = normalized_rows[0]
        data_rows = normalized_rows[1:]
    else:
        header = normalized_rows[0]
        data_rows = normalized_rows[1:]

    lines = [
        _render_table_row(header),
        _render_table_row(["---"] * column_count),
        *(_render_table_row(row) for row in data_rows),
    ]
    return "\n" + "\n".join(lines) + "\n"


def _render_table_row(cells: list[str]) -> str:
    escaped = [cell.replace("|", r"\|").strip() for cell in cells]
    return f"| {' | '.join(escaped)} |"


def _render_mention_doc(attrs_text: str, inner: str) -> str:
    attributes = _parse_attrs(attrs_text)
    label = normalize_lark_markdown(inner).strip() or "Lark Doc"
    token = attributes.get("token", "").strip()
    doc_type = attributes.get("type", "").strip()
    if token and doc_type in {"wiki", "doc", "docx"}:
        path = "wiki" if doc_type == "wiki" else "docx"
        return f"[{label}](https://bytedance.larkoffice.com/{path}/{token})"
    return label


def _replace_wrapped_tag(text: str, tag: str, *, block: bool) -> str:
    pattern = re.compile(rf"<{tag}\b[^>]*>(.*?)</{tag}>", re.DOTALL)
    return pattern.sub(lambda match: _render_wrapped_tag(match.group(1), block=block), text)


def _replace_self_closing_tag(text: str, tag: str) -> str:
    pattern = re.compile(rf"<{tag}\b([^>]*)/?>")
    return pattern.sub(lambda match: _render_self_closing_tag(tag, match.group(1)), text)


def _render_self_closing_tag(tag: str, attrs_text: str) -> str:
    attributes = _parse_attrs(attrs_text)
    if tag == "mention-user":
        user_id = attributes.get("id", "").strip()
        return f"@{user_id}" if user_id else "@unknown"
    if tag == "image":
        token = attributes.get("token", "").strip()
        label = f"[图片 token={token}]" if token else "[图片]"
        return f"\n{label}\n"
    if tag == "file":
        name = attributes.get("name", "").strip()
        token = attributes.get("token", "").strip()
        if name and token:
            return f"\n[附件: {name} ({token})]\n"
        if name:
            return f"\n[附件: {name}]\n"
        if token:
            return f"\n[附件 token={token}]\n"
        return "\n[附件]\n"
    return ""


def _render_wrapped_tag(inner: str, *, block: bool) -> str:
    normalized = normalize_lark_markdown(inner)
    return f"\n{normalized}\n" if block and normalized.strip() else normalized


def _normalize_inline_fragment(text: str) -> str:
    normalized = normalize_lark_markdown(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    return "<br>".join(lines).strip()


def _parse_attrs(attrs_text: str) -> dict[str, str]:
    return {key: value for key, value in _ATTR_PATTERN.findall(attrs_text)}


def _normalize_blank_lines(text: str) -> str:
    stripped_lines = [line.rstrip() for line in text.splitlines()]
    joined = "\n".join(stripped_lines)
    return re.sub(r"\n{3,}", "\n\n", joined)


def _normalize_markdown_lines(text: str) -> str:
    normalized_lines: list[str] = []
    for line in text.splitlines():
        if _HEADING_ONLY_PATTERN.fullmatch(line):
            continue
        heading_match = _ATX_HEADING_PATTERN.match(line)
        if heading_match and heading_match.group("body").strip():
            line = f"{heading_match.group('prefix')}{heading_match.group('body').rstrip()}"
        normalized_lines.append(line)
    return "\n".join(normalized_lines)

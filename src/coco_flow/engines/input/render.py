from __future__ import annotations

from datetime import datetime

from .models import ResolvedSource, SUPPLEMENT_HEADING


def build_source_markdown(source: ResolvedSource, supplement: str, now: datetime) -> str:
    lines = [
        "# PRD Source",
        "",
        f"- title: {source.title}",
        f"- source_type: {source.source_type}",
    ]
    if source.path:
        lines.append(f"- path: {source.path}")
    if source.url:
        lines.append(f"- url: {source.url}")
    if source.doc_token:
        lines.append(f"- doc_token: {source.doc_token}")
    if source.fetch_error:
        lines.append(f"- fetch_error: {source.fetch_error}")
    if source.fetch_error_code:
        lines.append(f"- fetch_error_code: {source.fetch_error_code}")
    lines.extend(
        [
            f"- captured_at: {now.isoformat()}",
            "",
            "---",
            "",
            source.content
            or (
                "当前版本尚未自动拉取该来源的正文内容。\n"
                "请稍候等待 Input 阶段完成，或手动补充正文后再执行 refine。"
            ),
            "",
        ]
    )
    trimmed_supplement = supplement.strip()
    if trimmed_supplement:
        lines.extend(["", SUPPLEMENT_HEADING, "", trimmed_supplement, ""])
    return "\n".join(lines)

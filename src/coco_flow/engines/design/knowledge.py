from __future__ import annotations

from .models import DesignPreparedInput


def build_design_knowledge_brief(prepared: DesignPreparedInput) -> str:
    markdown = prepared.refine_knowledge_read_markdown.strip()
    if not markdown:
        return ""
    lines = [
        "# Design Knowledge Brief",
        "",
        "- 来源：继承 Refine 已筛选并深读的知识结果。",
        "- 用途：帮助 Design 判断系统边界、稳定规则、协议/配置约束和验证重点。",
        "",
        markdown,
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"

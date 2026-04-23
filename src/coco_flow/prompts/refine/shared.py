from __future__ import annotations

from coco_flow.prompts.core import PromptSection


def build_refine_file_section(*, title: str, paths: list[str]) -> PromptSection:
    lines = [f"- {path}" for path in paths]
    return PromptSection(title=title, body="\n".join(lines))


def build_refine_constraints_section(items: list[str]) -> PromptSection:
    return PromptSection(
        title="硬约束",
        body="\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1)),
    )

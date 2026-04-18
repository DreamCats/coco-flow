from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PromptSection:
    title: str
    body: str


@dataclass(frozen=True)
class PromptDocument:
    intro: str = ""
    goal: str = ""
    requirements: list[str] = field(default_factory=list)
    output_contract: str = ""
    sections: list[PromptSection] = field(default_factory=list)
    closing: str = ""


def render_prompt(document: PromptDocument) -> str:
    parts: list[str] = []
    if document.intro.strip():
        parts.append(document.intro.strip())
    if document.goal.strip():
        parts.append("目标：\n" + document.goal.strip())
    if document.requirements:
        parts.append(
            "要求：\n" + "\n".join(f"{index}. {item}" for index, item in enumerate(document.requirements, start=1))
        )
    if document.output_contract.strip():
        parts.append("输出契约：\n" + document.output_contract.strip())
    for section in document.sections:
        body = section.body.strip()
        if not body:
            continue
        parts.append(f"{section.title}\n\n{body}")
    if document.closing.strip():
        parts.append(document.closing.strip())
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"

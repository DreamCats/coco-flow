from __future__ import annotations

import json


def render_bullets(items: list[str], *, default: str = "- 无") -> str:
    normalized = [item.strip() for item in items if item.strip()]
    if not normalized:
        return default
    return "\n".join(f"- {item}" for item in normalized)


def render_json_block(payload: dict[str, object]) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def render_yaml_cards(cards: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for card in cards:
        lines.append("-")
        for key, value in card.items():
            if value in ("", None, [], {}):
                continue
            lines.append(f"  {key}: {value}")
    return "\n".join(lines).strip() or "- {}"

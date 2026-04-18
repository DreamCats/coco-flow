from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re

_ascii_word = re.compile(r"[a-zA-Z0-9]+")
_slug_dash = re.compile(r"-+")


def build_task_id(title: str) -> str:
    now = datetime.now().astimezone()
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{build_task_slug(title)}"


def build_task_slug(title: str) -> str:
    tokens = [token.lower() for token in _ascii_word.findall(title) if len(token) >= 2]
    if tokens:
        return trim_slug("-".join(tokens[:4]))
    compact = re.sub(r"\s+", "", title)
    if compact:
        return "task"
    return "task"


def trim_slug(value: str) -> str:
    return _slug_dash.sub("-", value.strip("-"))[:48] or "task"


def derive_repo_id(path: str) -> str:
    name = Path(path).name.strip()
    return name or "repo"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

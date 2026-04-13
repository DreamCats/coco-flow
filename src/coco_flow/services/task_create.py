from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re

from coco_flow.config import Settings, load_settings

STATUS_INITIALIZED = "initialized"
SOURCE_TYPE_TEXT = "text"

_ascii_word = re.compile(r"[a-zA-Z0-9]+")
_spacing = re.compile(r"[ \t]+")
_slug_dash = re.compile(r"-+")


def create_task(
    raw_input: str,
    title: str | None,
    repos: list[str],
    settings: Settings | None = None,
) -> tuple[str, str]:
    cfg = settings or load_settings()
    normalized_input = raw_input.strip()
    normalized_repos = normalize_repo_paths(repos)
    if not normalized_input:
        raise ValueError("input 不能为空")
    if not normalized_repos:
        raise ValueError("repos 不能为空")

    resolved_title = normalize_title(title, normalized_input)
    task_id = build_task_id(resolved_title)
    task_dir = cfg.task_root / task_id
    task_dir.mkdir(parents=True, exist_ok=False)

    now = datetime.now().astimezone()
    source_value = normalized_input

    write_json(
        task_dir / "task.json",
        {
            "task_id": task_id,
            "title": resolved_title,
            "status": STATUS_INITIALIZED,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "source_type": SOURCE_TYPE_TEXT,
            "source_value": source_value,
            "repo_count": len(normalized_repos),
        },
    )
    write_json(
        task_dir / "source.json",
        {
            "type": SOURCE_TYPE_TEXT,
            "title": resolved_title,
            "captured_at": now.isoformat(),
        },
    )
    write_json(
        task_dir / "repos.json",
        {
            "repos": [
                {
                    "id": derive_repo_id(path),
                    "path": path,
                    "status": STATUS_INITIALIZED,
                }
                for path in normalized_repos
            ]
        },
    )
    (task_dir / "prd.source.md").write_text(build_source_markdown(resolved_title, normalized_input, now))
    return task_id, STATUS_INITIALIZED


def normalize_repo_paths(repos: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for repo in repos:
        path = str(Path(repo).expanduser()).strip()
        if not path or path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def normalize_title(title: str | None, raw_input: str) -> str:
    if title and title.strip():
        return collapse_spacing(title.strip())
    first_line = raw_input.strip().splitlines()[0].strip()
    if first_line:
        return collapse_spacing(first_line[:80])
    return "未命名任务"


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


def build_source_markdown(title: str, raw_input: str, now: datetime) -> str:
    return (
        "# PRD Source\n\n"
        f"- title: {title}\n"
        f"- source_type: {SOURCE_TYPE_TEXT}\n"
        f"- captured_at: {now.isoformat()}\n\n"
        "---\n\n"
        f"{raw_input.strip()}\n"
    )


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def collapse_spacing(value: str) -> str:
    return _spacing.sub(" ", value).strip()

from __future__ import annotations

from pathlib import Path
import os
import subprocess


def list_fs_roots() -> list[dict[str, str]]:
    home = str(Path.home())
    cwd = str(Path.cwd().resolve())
    roots = [
        {"label": "cwd", "path": cwd},
        {"label": "home", "path": home},
    ]
    return roots


def list_fs_entries(path: str) -> list[dict[str, object]]:
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"path not found: {root}")
    if not root.is_dir():
        raise ValueError(f"path is not a directory: {root}")

    entries: list[dict[str, object]] = []
    for child in sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name.startswith(".") and child.name not in {".config", ".livecoding"}:
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "isGitRepo": is_git_repo(child),
            }
        )
    return entries


def is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"

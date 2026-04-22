from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import subprocess
from typing import Any

_PACKAGE_NAME = "coco-flow"
_REPO_MARKERS = ("pyproject.toml", "src/coco_flow")


def current_build_meta(*, started_at: str = "") -> dict[str, Any]:
    version_value = _package_version()
    source_root = _source_root(Path(__file__).resolve())
    git_root = _git_root(source_root)
    git_commit = ""
    git_dirty = False
    fingerprint = f"version:{version_value}"
    source_kind = "package"
    if git_root is not None:
        git_commit = _git_output(git_root, ["rev-parse", "--short", "HEAD"])
        if git_commit:
            git_dirty = bool(_git_output(git_root, ["status", "--short"]))
            fingerprint = f"git:{git_commit}{'-dirty' if git_dirty else ''}"
            source_kind = "git"
    payload: dict[str, Any] = {
        "name": "coco-flow",
        "version": version_value,
        "fingerprint": fingerprint,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "source_kind": source_kind,
        "source_root": str(source_root),
    }
    if started_at:
        payload["started_at"] = started_at
    return payload


def _package_version() -> str:
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.1.0"


def _source_root(path: Path) -> Path:
    for candidate in path.parents:
        if all((candidate / marker).exists() for marker in _REPO_MARKERS):
            return candidate
    return path.parents[2]


def _git_root(source_root: Path) -> Path | None:
    candidate = source_root
    while True:
        if (candidate / ".git").exists():
            return candidate
        if candidate.parent == candidate:
            return None
        candidate = candidate.parent


def _git_output(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()

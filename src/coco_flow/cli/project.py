from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import subprocess

import typer

_PROJECT_MARKER_GROUPS = (
    ("pyproject.toml", "src/coco_flow/cli/__init__.py"),
    ("pyproject.toml", "src/coco_flow/cli.py"),
)
_PYTHON_VERSION = "3.13"
_DEFAULT_INSTALL_DIR = Path.home() / ".local" / "share" / "coco-flow"


def package_version() -> str:
    try:
        return version("coco-flow")
    except PackageNotFoundError:
        return "0.1.0"


def resolve_project_root(raw_path: str) -> Path:
    project_root = Path(raw_path).expanduser().resolve()
    if not any(all((project_root / marker).exists() for marker in group) for group in _PROJECT_MARKER_GROUPS):
        raise typer.BadParameter(f"not a coco-flow project root: {project_root}")
    return project_root


def installed_repo_root() -> Path:
    raw_path = os.getenv("COCO_FLOW_INSTALL_DIR", "").strip()
    if not raw_path:
        return _DEFAULT_INSTALL_DIR
    return Path(raw_path).expanduser()


def ensure_git_checkout(project_root: Path) -> None:
    if not (project_root / ".git").exists():
        raise typer.BadParameter(f"git checkout not found: {project_root}")


def install_tool_from_project(project_root: Path) -> None:
    run_project_command(
        ["uv", "tool", "install", "--force", "--python", _PYTHON_VERSION, "--editable", str(project_root)],
        cwd=project_root,
    )
    run_project_command(["uv", "tool", "update-shell"], cwd=project_root)


def tool_bin_dir(project_root: Path) -> str:
    result = subprocess.run(
        ["uv", "tool", "dir", "--bin"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
    return result.stdout.strip()


def run_project_command(args: list[str], cwd: Path) -> None:
    typer.echo(f"$ {' '.join(args)}")
    result = subprocess.run(args, cwd=cwd, check=False)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)

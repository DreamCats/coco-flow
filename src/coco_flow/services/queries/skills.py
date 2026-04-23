from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re

import yaml

from coco_flow.config import Settings
from coco_flow.models.skills import SkillTreeNode

_PACKAGE_NAME_RE = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True)
class SkillPackage:
    id: str
    root_path: Path
    skill_path: Path
    name: str
    description: str
    domain: str
    body: str
    reference_paths: list[Path]


class SkillStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ensure_root(self) -> Path:
        root = skills_root_path(self.settings)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def list_tree(self) -> tuple[Path, list[SkillTreeNode]]:
        root = self.ensure_root()
        nodes = [self._build_tree_node(path, root=root) for path in _iter_children(root)]
        return root, nodes

    def list_packages(self) -> list[SkillPackage]:
        root = self.ensure_root()
        packages: list[SkillPackage] = []
        for path in _iter_children(root):
            if not path.is_dir():
                continue
            skill_path = path / "SKILL.md"
            if not skill_path.is_file():
                continue
            packages.append(read_skill_package(path))
        return packages

    def get_package(self, package_id: str) -> SkillPackage | None:
        normalized = package_id.strip()
        if not normalized:
            return None
        package_root = self.ensure_root() / normalized
        skill_path = package_root / "SKILL.md"
        if not skill_path.is_file():
            return None
        return read_skill_package(package_root)

    def read_file(self, relative_path: str) -> tuple[str, str]:
        path = self._resolve_path(relative_path, expect_file=True)
        return self._relative_path(path), path.read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> tuple[str, str]:
        path = self._resolve_path(relative_path, expect_file=True)
        path.write_text(content, encoding="utf-8")
        return self._relative_path(path), content

    def create_package(self, name: str, description: str = "", domain: str = "") -> tuple[str, Path, str]:
        normalized_name = slugify_skill_package_name(name)
        if not normalized_name:
            raise ValueError("skill package name 不能为空")

        root = self.ensure_root()
        package_root = root / normalized_name
        if package_root.exists():
            raise ValueError(f"skill package already exists: {normalized_name}")

        references_dir = package_root / "references"
        references_dir.mkdir(parents=True, exist_ok=True)
        skill_path = package_root / "SKILL.md"
        skill_path.write_text(
            render_skill_markdown(
                name=normalized_name,
                description=description.strip(),
                domain=domain.strip(),
            ),
            encoding="utf-8",
        )
        (references_dir / "domain.md").write_text("# Domain\n\n", encoding="utf-8")
        (references_dir / "main-flow.md").write_text("# Main Flow\n\n", encoding="utf-8")
        (references_dir / "change-workflows.md").write_text("# Change Workflows\n\n", encoding="utf-8")
        return normalized_name, package_root, self._relative_path(skill_path)

    def _build_tree_node(self, path: Path, *, root: Path) -> SkillTreeNode:
        if path.is_dir():
            return SkillTreeNode(
                name=path.name,
                path=self._relative_path(path),
                nodeType="directory",
                children=[self._build_tree_node(child, root=root) for child in _iter_children(path)],
            )
        return SkillTreeNode(
            name=path.name,
            path=self._relative_path(path),
            nodeType="file",
            children=[],
        )

    def _resolve_path(self, relative_path: str, *, expect_file: bool) -> Path:
        root = self.ensure_root().resolve()
        raw = relative_path.strip()
        if not raw:
            raise ValueError("path 不能为空")
        candidate = (root / raw).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ValueError(f"invalid skill path: {relative_path}") from error
        if not candidate.exists():
            raise ValueError(f"skill path not found: {relative_path}")
        if expect_file and not candidate.is_file():
            raise ValueError(f"skill file not found: {relative_path}")
        return candidate

    def _relative_path(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.ensure_root().resolve()))


def skills_root_path(settings: Settings) -> Path:
    configured = os.getenv("COCO_FLOW_SKILLS_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()
    return settings.config_root / "skills"


def slugify_skill_package_name(name: str) -> str:
    lowered = name.strip().lower().replace(" ", "-")
    normalized = _PACKAGE_NAME_RE.sub("-", lowered)
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-_")


def render_skill_markdown(*, name: str, description: str, domain: str) -> str:
    frontmatter = yaml.safe_dump(
        {
            "name": name,
            "description": description,
            "domain": domain,
        },
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    return (
        f"---\n{frontmatter}\n---\n\n"
        "# Overview\n\n"
        "Describe when this skill should be used.\n"
    )


def read_skill_package(package_root: Path) -> SkillPackage:
    skill_path = package_root / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")
    meta, body = parse_skill_frontmatter(content)
    references_dir = package_root / "references"
    reference_paths = []
    if references_dir.is_dir():
        reference_paths = sorted(
            [
                path
                for path in references_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
            ],
            key=lambda path: str(path.relative_to(package_root)).lower(),
        )
    return SkillPackage(
        id=package_root.name,
        root_path=package_root,
        skill_path=skill_path,
        name=str(meta.get("name") or package_root.name),
        description=str(meta.get("description") or ""),
        domain=str(meta.get("domain") or ""),
        body=body,
        reference_paths=reference_paths,
    )


def parse_skill_frontmatter(content: str) -> tuple[dict[str, object], str]:
    normalized = content.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized.strip()
    end = normalized.find("\n---\n", 4)
    if end == -1:
        return {}, normalized.strip()
    raw_block = normalized[4:end]
    try:
        parsed = yaml.safe_load(raw_block) or {}
    except yaml.YAMLError:
        parsed = {}
    body = normalized[end + 5 :].strip()
    return parsed if isinstance(parsed, dict) else {}, body


def _iter_children(path: Path) -> list[Path]:
    children = [child for child in path.iterdir() if not child.name.startswith(".")]
    return sorted(children, key=_tree_sort_key)


def _tree_sort_key(path: Path) -> tuple[int, int, str]:
    if path.is_dir():
        return (0, 1, path.name.lower())
    if path.name == "SKILL.md":
        return (1, 0, path.name.lower())
    return (1, 1, path.name.lower())

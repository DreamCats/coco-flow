from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import subprocess

import yaml

from coco_flow.config import Settings
from coco_flow.models.skills import SkillTreeNode

_SOURCE_ID_RE = re.compile(r"[^a-z0-9_-]+")
_SOURCES_CONFIG_NAME = "skills-sources.json"
_SKILLS_SOURCES_DIR = "skills-sources"


@dataclass(frozen=True)
class SkillPackage:
    id: str
    package_id: str
    source_id: str
    source_type: str
    source_url: str
    root_path: Path
    skill_path: Path
    name: str
    description: str
    domain: str
    body: str
    reference_paths: list[Path]


@dataclass(frozen=True)
class SkillSourceConfig:
    id: str
    name: str
    source_type: str
    local_path: Path
    enabled: bool = True
    url: str = ""
    branch: str = ""
    managed: bool = False


class SkillStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_sources(self) -> list[dict[str, object]]:
        return [self._source_status(source) for source in self._source_configs()]

    def add_git_source(self, *, name: str, url: str, branch: str = "") -> dict[str, object]:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("Git URL 不能为空")
        source_id = slugify_skill_source_id(name or _repo_slug_from_url(clean_url))
        if not source_id:
            raise ValueError("source name 不能为空")
        sources = self._configured_sources()
        if any(item.id == source_id for item in sources):
            raise ValueError(f"skill source already exists: {source_id}")
        local_path = self.settings.config_root / _SKILLS_SOURCES_DIR / source_id
        sources.append(
            SkillSourceConfig(
                id=source_id,
                name=name.strip() or source_id,
                source_type="git",
                url=clean_url,
                branch=branch.strip(),
                local_path=local_path,
                enabled=True,
                managed=True,
            )
        )
        self._write_configured_sources(sources)
        return self._source_status(self._source_by_id(source_id))

    def clone_source(self, source_id: str) -> tuple[dict[str, object], str]:
        source = self._require_git_source(source_id)
        if source.local_path.exists() and any(source.local_path.iterdir()):
            raise ValueError(f"skill source already exists locally: {source.local_path}")
        source.local_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone"]
        if source.branch:
            cmd.extend(["--branch", source.branch])
        cmd.extend([source.url, str(source.local_path)])
        output = _run_git_command(cmd, cwd=None)
        return self._source_status(self._source_by_id(source.id)), output

    def pull_source(self, source_id: str) -> tuple[dict[str, object], str]:
        source = self._require_git_source(source_id)
        if not source.local_path.is_dir():
            raise ValueError(f"skill source not cloned: {source.id}")
        if not _is_git_repo(source.local_path):
            raise ValueError(f"skill source is not a git repo: {source.local_path}")
        dirty = _git_output(["git", "status", "--porcelain"], cwd=source.local_path).strip()
        if dirty:
            raise ValueError("skills 仓库存在本地改动，请先提交、stash 或清理后再更新")
        output = _run_git_command(["git", "pull", "--ff-only"], cwd=source.local_path)
        return self._source_status(self._source_by_id(source.id)), output

    def remove_source(self, source_id: str) -> dict[str, object]:
        normalized = slugify_skill_source_id(source_id)
        sources = self._configured_sources()
        if not any(source.id == normalized for source in sources):
            raise ValueError(f"skill source not found: {source_id}")
        self._write_configured_sources([source for source in sources if source.id != normalized])
        return self._source_status(
            SkillSourceConfig(
                id=normalized,
                name=normalized,
                source_type="git",
                local_path=self.settings.config_root / _SKILLS_SOURCES_DIR / normalized,
                enabled=False,
                managed=True,
            )
        )

    def list_tree_for_source(self, source_id: str) -> tuple[SkillSourceConfig, list[SkillTreeNode]]:
        source = self._source_by_id(source_id)
        root = source.local_path
        if not root.is_dir():
            return source, []
        nodes = [self._build_tree_node(path, root=root) for path in _iter_children(root)]
        return source, nodes

    def list_packages(self) -> list[SkillPackage]:
        packages: list[SkillPackage] = []
        for source in self._source_configs():
            if not source.enabled or not source.local_path.is_dir():
                continue
            for path in _iter_children(source.local_path):
                if not path.is_dir():
                    continue
                skill_path = path / "SKILL.md"
                if not skill_path.is_file():
                    continue
                packages.append(read_skill_package(path, source=source))
        return packages

    def get_package(self, package_id: str) -> SkillPackage | None:
        normalized = package_id.strip()
        if not normalized:
            return None
        source_id, local_package_id = self._split_skill_id(normalized)
        if not source_id or not local_package_id:
            return None
        try:
            source = self._source_by_id(source_id)
        except ValueError:
            return None
        package_root = source.local_path / local_package_id
        skill_path = package_root / "SKILL.md"
        if not skill_path.is_file():
            return None
        return read_skill_package(package_root, source=source)

    def read_file(self, relative_path: str, *, source_id: str) -> tuple[str, str, str]:
        source = self._source_by_id(source_id)
        path = self._resolve_path(relative_path, source=source, expect_file=True)
        return source.id, self._relative_path(path, root=source.local_path), path.read_text(encoding="utf-8")

    def _build_tree_node(self, path: Path, *, root: Path) -> SkillTreeNode:
        if path.is_dir():
            return SkillTreeNode(
                name=path.name,
                path=self._relative_path(path, root=root),
                nodeType="directory",
                children=[self._build_tree_node(child, root=root) for child in _iter_children(path)],
            )
        return SkillTreeNode(
            name=path.name,
            path=self._relative_path(path, root=root),
            nodeType="file",
            children=[],
        )

    def _resolve_path(self, relative_path: str, *, source: SkillSourceConfig, expect_file: bool) -> Path:
        root = source.local_path.resolve()
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

    def _relative_path(self, path: Path, *, root: Path | None = None) -> str:
        base = root or path.parent
        return str(path.resolve().relative_to(base.resolve()))

    def _source_configs(self) -> list[SkillSourceConfig]:
        return self._configured_sources()

    def _configured_sources(self) -> list[SkillSourceConfig]:
        path = self._sources_config_path()
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        raw_sources = payload.get("sources") if isinstance(payload, dict) else []
        if not isinstance(raw_sources, list):
            return []
        sources: list[SkillSourceConfig] = []
        for item in raw_sources:
            if not isinstance(item, dict):
                continue
            source_id = slugify_skill_source_id(str(item.get("id") or item.get("name") or ""))
            if not source_id:
                continue
            local_path = Path(str(item.get("local_path") or self.settings.config_root / _SKILLS_SOURCES_DIR / source_id)).expanduser()
            source_type = str(item.get("type") or item.get("source_type") or "git").strip().lower()
            if source_type != "git":
                continue
            sources.append(
                SkillSourceConfig(
                    id=source_id,
                    name=str(item.get("name") or source_id),
                    source_type=source_type,
                    url=str(item.get("url") or ""),
                    branch=str(item.get("branch") or ""),
                    local_path=local_path,
                    enabled=bool(item.get("enabled", True)),
                    managed=True,
                )
            )
        return sources

    def _write_configured_sources(self, sources: list[SkillSourceConfig]) -> None:
        path = self._sources_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sources": [
                {
                    "id": source.id,
                    "name": source.name,
                    "type": source.source_type,
                    "url": source.url,
                    "branch": source.branch,
                    "local_path": str(source.local_path),
                    "enabled": source.enabled,
                }
                for source in sources
                if source.managed
            ]
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _sources_config_path(self) -> Path:
        return self.settings.config_root / _SOURCES_CONFIG_NAME

    def _source_by_id(self, source_id: str) -> SkillSourceConfig:
        normalized = slugify_skill_source_id(source_id)
        for source in self._source_configs():
            if source.id == normalized:
                return source
        raise ValueError(f"skill source not found: {source_id}")

    def _require_git_source(self, source_id: str) -> SkillSourceConfig:
        source = self._source_by_id(source_id)
        if source.source_type != "git":
            raise ValueError(f"skill source is not git-backed: {source.id}")
        if not source.url:
            raise ValueError(f"skill source missing git url: {source.id}")
        return source

    def _source_status(self, source: SkillSourceConfig) -> dict[str, object]:
        local_path = source.local_path
        status = "ready"
        message = ""
        git_info = _read_git_info(local_path)
        if source.source_type == "git" and not local_path.exists():
            status = "not_cloned"
            message = "尚未初始化本地缓存"
        elif not local_path.is_dir():
            status = "missing"
            message = "本地目录不存在"
        elif source.source_type == "git" and not git_info["is_git_repo"]:
            status = "not_git"
            message = "本地目录不是 git 仓库"
        elif git_info["dirty"]:
            status = "dirty"
            message = "存在本地改动"
        elif int(git_info["behind"]) > 0:
            status = "behind"
            message = f"落后 {git_info['behind']} 个提交"
        elif git_info["is_git_repo"]:
            status = "clean"
        package_count = 0
        if local_path.is_dir():
            package_count = sum(1 for path in _iter_children(local_path) if path.is_dir() and (path / "SKILL.md").is_file())
        return {
            "id": source.id,
            "name": source.name,
            "sourceType": source.source_type,
            "enabled": source.enabled,
            "url": source.url,
            "branch": source.branch,
            "localPath": str(source.local_path),
            "status": status,
            "message": message,
            "isGitRepo": git_info["is_git_repo"],
            "currentBranch": git_info["branch"],
            "commit": git_info["commit"],
            "remoteUrl": git_info["remote_url"],
            "dirty": git_info["dirty"],
            "ahead": git_info["ahead"],
            "behind": git_info["behind"],
            "packageCount": package_count,
        }

    def _split_skill_id(self, skill_id: str) -> tuple[str, str]:
        if "/" not in skill_id:
            return "", skill_id
        source_id, package_id = skill_id.split("/", 1)
        return source_id.strip(), package_id.strip()


def skills_sources_root_path(settings: Settings) -> Path:
    return settings.config_root / _SKILLS_SOURCES_DIR


def slugify_skill_source_id(name: str) -> str:
    lowered = name.strip().lower().replace(" ", "-")
    normalized = _SOURCE_ID_RE.sub("-", lowered)
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-_")


def read_skill_package(package_root: Path, *, source: SkillSourceConfig) -> SkillPackage:
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
    package_id = package_root.name
    return SkillPackage(
        id=f"{source.id}/{package_id}",
        package_id=package_id,
        source_id=source.id,
        source_type=source.source_type,
        source_url=source.url,
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
    if not path.is_dir():
        return []
    children = [child for child in path.iterdir() if not child.name.startswith(".")]
    return sorted(children, key=_tree_sort_key)


def _tree_sort_key(path: Path) -> tuple[int, int, str]:
    if path.is_dir():
        return (0, 1, path.name.lower())
    if path.name == "SKILL.md":
        return (1, 0, path.name.lower())
    return (1, 1, path.name.lower())


def _repo_slug_from_url(url: str) -> str:
    tail = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    return tail or "skills"


def _is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _read_git_info(path: Path) -> dict[str, object]:
    info: dict[str, object] = {
        "is_git_repo": False,
        "branch": "",
        "commit": "",
        "remote_url": "",
        "dirty": False,
        "ahead": 0,
        "behind": 0,
    }
    if not _is_git_repo(path):
        return info
    info["is_git_repo"] = True
    info["branch"] = _git_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path).strip()
    info["commit"] = _git_output(["git", "rev-parse", "--short", "HEAD"], cwd=path).strip()
    info["remote_url"] = _git_output(["git", "config", "--get", "remote.origin.url"], cwd=path).strip()
    info["dirty"] = bool(_git_output(["git", "status", "--porcelain"], cwd=path).strip())
    ahead_behind = _git_output(["git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"], cwd=path).split()
    if len(ahead_behind) == 2 and all(item.isdigit() for item in ahead_behind):
        info["behind"] = int(ahead_behind[0])
        info["ahead"] = int(ahead_behind[1])
    return info


def _git_output(cmd: list[str], *, cwd: Path) -> str:
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _run_git_command(cmd: list[str], *, cwd: Path | None) -> str:
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"git command failed: {error}") from error
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    if result.returncode != 0:
        raise ValueError(output or f"git command failed: {' '.join(cmd)}")
    return output

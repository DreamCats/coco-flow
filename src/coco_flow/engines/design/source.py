from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

from coco_flow.config import Settings
from coco_flow.engines.input.persist import derive_repo_id
from coco_flow.engines.shared.models import RepoScope
from coco_flow.engines.shared.research import (
    build_design_research_signals,
    build_repo_researches,
    parse_refined_sections,
    parse_repo_scopes,
    read_text_if_exists,
    score_complexity,
)
from coco_flow.services import TaskStore
from coco_flow.services.queries.knowledge import KnowledgeStore
from coco_flow.services.queries.repos import list_recent_repos, validate_repo_path
from coco_flow.services.queries.skills import SkillPackage, SkillStore
from coco_flow.services.queries.task_detail import read_json_file

from .models import DesignPreparedInput


def locate_task_dir(task_id: str, settings: Settings) -> Path | None:
    primary = settings.task_root / task_id
    if primary.is_dir():
        return primary
    return None


def prepare_design_input(task_dir: Path, task_meta: dict[str, object], settings: Settings) -> DesignPreparedInput:
    """读取 Design 依赖的全部上游产物，并归一化成统一输入。

    这里是磁盘上的 task 文件和后续设计编排之间的桥梁。
    """
    task_id = task_dir.name
    input_meta = read_json_file(task_dir / "input.json")
    refine_intent_payload = read_json_file(task_dir / "refine-intent.json")
    refine_knowledge_selection_payload = read_json_file(task_dir / "refine-knowledge-selection.json")
    refine_knowledge_read_markdown = read_text_if_exists(task_dir / "refine-knowledge-read.md")
    refined_markdown = read_text_if_exists(task_dir / "prd-refined.md")
    repos_meta = read_json_file(task_dir / "repos.json")
    title = str(task_meta.get("title") or input_meta.get("title") or task_id)
    bound_repo_scopes = parse_repo_scopes(repos_meta)
    repo_scopes = bound_repo_scopes
    repo_discovery_payload = {
        "mode": "bound" if bound_repo_scopes else "none",
        "bound_repo_count": len(bound_repo_scopes),
        "inferred_repo_count": 0,
        "selected_knowledge_ids": [
            str(item) for item in refine_knowledge_selection_payload.get("selected_ids", []) if str(item).strip()
        ],
    }
    if not repo_scopes:
        repo_scopes, repo_discovery_payload = infer_repo_scopes_from_knowledge(settings, refine_knowledge_selection_payload)
    repo_lines = [f"- {scope.repo_id} ({scope.repo_path})" for scope in repo_scopes]
    sections = parse_refined_sections(refined_markdown)
    repo_researches = build_repo_researches(repo_scopes, title, sections)
    repo_root = repo_scopes[0].repo_path if repo_scopes else None
    research_signals = build_design_research_signals(repo_researches, sections)
    assessment = score_complexity(
        sections,
        type(
            "Finding",
            (),
            {
                "matched_terms": [item for repo in repo_researches for item in repo.finding.matched_terms],
                "unmatched_terms": [item for repo in repo_researches for item in repo.finding.unmatched_terms],
                "candidate_files": [item for repo in repo_researches for item in repo.finding.candidate_files],
                "candidate_dirs": [item for repo in repo_researches for item in repo.finding.candidate_dirs],
                "notes": [item for repo in repo_researches for item in repo.finding.notes],
            },
        )(),
    )
    return DesignPreparedInput(
        task_dir=task_dir,
        task_id=task_id,
        title=title,
        refined_markdown=refined_markdown,
        input_meta=input_meta,
        refine_intent_payload=refine_intent_payload,
        refine_knowledge_selection_payload=refine_knowledge_selection_payload,
        refine_knowledge_read_markdown=refine_knowledge_read_markdown,
        repo_lines=repo_lines,
        repo_scopes=repo_scopes,
        repo_researches=repo_researches,
        repo_ids={scope.repo_id for scope in repo_scopes},
        repo_root=repo_root,
        sections=sections,
        research_signals=research_signals,
        assessment=assessment,
        repo_discovery_payload=repo_discovery_payload,
        research_payload={},
    )


def infer_repo_scopes_from_knowledge(
    settings: Settings,
    refine_knowledge_selection_payload: dict[str, object],
) -> tuple[list[RepoScope], dict[str, object]]:
    """当 task 没有显式绑定 repo 时，尝试从 approved knowledge 里补 repo scopes。

    Design 默认更偏好显式 repo 绑定；这个函数是兜底路径，把知识文档里的
    repo 线索转成标准化的 RepoScope。
    """
    selected_ids = [
        str(item).strip()
        for item in refine_knowledge_selection_payload.get("selected_ids", [])
        if str(item).strip()
    ]
    payload = {
        "mode": "none",
        "bound_repo_count": 0,
        "inferred_repo_count": 0,
        "selected_knowledge_ids": selected_ids,
        "selected_knowledge_titles": [],
        "unresolved_repo_hints": [],
    }
    if not selected_ids:
        return [], payload

    store = KnowledgeStore(settings)
    documents = [document for document_id in selected_ids if (document := store.get_document(document_id)) is not None]
    payload["selected_knowledge_titles"] = [document.title for document in documents]
    if not documents:
        return _infer_repo_scopes_from_skills(settings, selected_ids, payload)

    recent_repo_entries = list_recent_repos(TaskStore(settings))
    recent_repo_map = _build_recent_repo_map(recent_repo_entries)
    candidates: dict[str, dict[str, object]] = {}
    unresolved_hints: list[str] = []

    for document in documents:
        repo_id_hints = [item for item in [*document.repos, *document.evidence.repoMatches] if item.strip()]
        path_match_repo_id_hint = repo_id_hints[0] if len(set(repo_id_hints)) == 1 else ""
        for path_hint in document.evidence.pathMatches:
            resolved_path = _resolve_repo_path_from_path_hint(path_hint)
            if resolved_path is None:
                unresolved_hints.append(path_hint)
                continue
            _record_repo_candidate(
                candidates,
                repo_path=resolved_path,
                repo_id_hint=path_match_repo_id_hint,
                source=f"{document.id}:path_match",
            )
        for candidate_file in document.evidence.candidateFiles:
            resolved_path = _resolve_repo_path_from_path_hint(candidate_file)
            if resolved_path is None:
                unresolved_hints.append(candidate_file)
                continue
            _record_repo_candidate(
                candidates,
                repo_path=resolved_path,
                repo_id_hint=path_match_repo_id_hint,
                source=f"{document.id}:candidate_file",
            )
        for repo_hint in repo_id_hints:
            resolved = _resolve_repo_path_from_repo_hint(repo_hint, recent_repo_map)
            if resolved is None:
                unresolved_hints.append(repo_hint)
                continue
            resolved_path, repo_id_hint = resolved
            _record_repo_candidate(
                candidates,
                repo_path=resolved_path,
                repo_id_hint=repo_id_hint or repo_hint,
                source=f"{document.id}:repo_hint",
            )

    repo_scopes = [
        RepoScope(
            repo_id=str(candidate.get("repo_id") or derive_repo_id(str(candidate.get("repo_path") or ""))),
            repo_path=str(candidate.get("repo_path") or ""),
        )
        for candidate in candidates.values()
        if str(candidate.get("repo_path") or "").strip()
    ]
    repo_scopes.sort(key=lambda item: item.repo_id)
    payload["mode"] = "knowledge_selection" if repo_scopes else "knowledge_selection_empty"
    payload["inferred_repo_count"] = len(repo_scopes)
    payload["unresolved_repo_hints"] = sorted({item for item in unresolved_hints if item.strip()})[:8]
    return repo_scopes, payload


def _infer_repo_scopes_from_skills(
    settings: Settings,
    selected_ids: list[str],
    payload: dict[str, object],
) -> tuple[list[RepoScope], dict[str, object]]:
    skill_store = SkillStore(settings)
    skills = [skill for skill_id in selected_ids if (skill := skill_store.get_package(skill_id)) is not None]
    payload["selected_knowledge_titles"] = [skill.name for skill in skills]
    if not skills:
        payload["mode"] = "knowledge_docs_missing"
        return [], payload

    recent_repo_entries = list_recent_repos(TaskStore(settings))
    recent_repo_map = _build_recent_repo_map(recent_repo_entries)
    candidates: dict[str, dict[str, object]] = {}
    unresolved_hints: list[str] = []

    for skill in skills:
        repo_hints, path_hints, candidate_files = _extract_skill_hints(skill)
        for path_hint in path_hints:
            resolved_path = _resolve_repo_path_from_path_hint(path_hint)
            if resolved_path is None:
                unresolved_hints.append(path_hint)
                continue
            _record_repo_candidate(
                candidates,
                repo_path=resolved_path,
                repo_id_hint="",
                source=f"{skill.id}:path_hint",
            )
        for candidate_file in candidate_files:
            resolved_path = _resolve_repo_path_from_path_hint(candidate_file)
            if resolved_path is None:
                unresolved_hints.append(candidate_file)
                continue
            _record_repo_candidate(
                candidates,
                repo_path=resolved_path,
                repo_id_hint="",
                source=f"{skill.id}:candidate_file",
            )
        for repo_hint in repo_hints:
            resolved = _resolve_repo_path_from_repo_hint(repo_hint, recent_repo_map)
            if resolved is None:
                unresolved_hints.append(repo_hint)
                continue
            resolved_path, repo_id_hint = resolved
            _record_repo_candidate(
                candidates,
                repo_path=resolved_path,
                repo_id_hint=repo_id_hint or repo_hint,
                source=f"{skill.id}:repo_hint",
            )

    repo_scopes = [
        RepoScope(
            repo_id=str(candidate.get("repo_id") or derive_repo_id(str(candidate.get("repo_path") or ""))),
            repo_path=str(candidate.get("repo_path") or ""),
        )
        for candidate in candidates.values()
        if str(candidate.get("repo_path") or "").strip()
    ]
    repo_scopes.sort(key=lambda item: item.repo_id)
    payload["mode"] = "skill_selection" if repo_scopes else "skill_selection_empty"
    payload["inferred_repo_count"] = len(repo_scopes)
    payload["unresolved_repo_hints"] = sorted({item for item in unresolved_hints if item.strip()})[:8]
    return repo_scopes, payload


def _build_recent_repo_map(recent_repo_entries: list[dict[str, object]]) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for item in recent_repo_entries:
        repo_id = str(item.get("id") or "").strip()
        repo_path = str(item.get("path") or "").strip()
        if not repo_path:
            continue
        aliases = {
            repo_id,
            str(item.get("displayName") or "").strip(),
            Path(repo_path).name,
            Path(repo_path).stem,
        }
        aliases.discard("")
        for alias in aliases:
            for normalized_alias in _hint_aliases(alias):
                mapping.setdefault(normalized_alias, (repo_path, repo_id))
    return mapping


def _resolve_repo_path_from_repo_hint(
    repo_hint: str,
    recent_repo_map: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    normalized_hint = repo_hint.strip()
    if not normalized_hint:
        return None
    direct_path = _resolve_repo_path_from_path_hint(normalized_hint)
    if direct_path is not None:
        return direct_path, derive_repo_id(direct_path)
    mirrored_path = _resolve_repo_mirror_path(normalized_hint)
    if mirrored_path is not None:
        return mirrored_path, _repo_id_from_hint(normalized_hint, mirrored_path)
    alias_candidates = _hint_aliases(normalized_hint)
    for alias in alias_candidates:
        matched = recent_repo_map.get(alias)
        if matched is not None:
            return matched
    fuzzy_matches = {
        value
        for alias, value in recent_repo_map.items()
        if any(alias == candidate or alias in candidate or candidate in alias for candidate in alias_candidates if candidate)
    }
    if len(fuzzy_matches) == 1:
        return next(iter(fuzzy_matches))
    return None


def _resolve_repo_mirror_path(repo_hint: str) -> str | None:
    normalized_hint = repo_hint.strip().strip("/")
    if not normalized_hint or "/" not in normalized_hint:
        return None
    for mirror_root in _local_repo_mirror_roots():
        candidate = mirror_root / normalized_hint
        resolved = _resolve_repo_path_from_path_hint(str(candidate))
        if resolved is not None:
            return resolved
    return None


def _resolve_repo_path_from_path_hint(path_hint: str) -> str | None:
    normalized = path_hint.strip()
    if not normalized:
        return None
    candidate = Path(normalized).expanduser()
    if not candidate.exists():
        return None
    git_target = candidate if candidate.is_dir() else candidate.parent
    try:
        repo_root = subprocess.run(
            ["git", "-C", str(git_target), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if repo_root.returncode == 0 and repo_root.stdout.strip():
            normalized = repo_root.stdout.strip()
    except OSError:
        return None
    try:
        validated = validate_repo_path(normalized)
    except ValueError:
        return None
    return str(validated.get("path") or "").strip() or None


def _record_repo_candidate(
    candidates: dict[str, dict[str, object]],
    *,
    repo_path: str,
    repo_id_hint: str,
    source: str,
) -> None:
    normalized_path = repo_path.strip()
    if not normalized_path:
        return
    current = candidates.get(normalized_path)
    if current is None:
        candidates[normalized_path] = {
            "repo_id": repo_id_hint.strip() or derive_repo_id(normalized_path),
            "repo_path": normalized_path,
            "sources": [source],
        }
        return
    if repo_id_hint.strip() and current["repo_id"] == derive_repo_id(normalized_path):
        current["repo_id"] = repo_id_hint.strip()
    if source not in current["sources"]:
        current["sources"].append(source)


def _hint_aliases(value: str) -> set[str]:
    raw = value.strip()
    if not raw:
        return set()
    normalized = raw.lower()
    collapsed = re.sub(r"[^a-z0-9]+", "", normalized)
    dashed = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    underscored = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return {item for item in {normalized, collapsed, dashed, underscored} if item}


def _local_repo_mirror_roots() -> list[Path]:
    roots: list[Path] = []
    gopath = os.getenv("GOPATH", "").strip()
    if gopath:
        for entry in gopath.split(os.pathsep):
            current = entry.strip()
            if not current:
                continue
            roots.append(Path(current).expanduser() / "src")
    if not roots:
        home = Path.home()
        roots.extend(
            [
                home / "go" / "src",
                home / "src",
            ]
        )
    unique: list[Path] = []
    seen: set[str] = set()
    for item in roots:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _repo_id_from_hint(repo_hint: str, repo_path: str) -> str:
    normalized_hint = repo_hint.strip().strip("/")
    if "/" in normalized_hint:
        return normalized_hint.rsplit("/", 1)[-1] or derive_repo_id(repo_path)
    return normalized_hint or derive_repo_id(repo_path)


def _extract_skill_hints(skill: SkillPackage) -> tuple[list[str], list[str], list[str]]:
    text_parts = [skill.name, skill.description, skill.domain, skill.body]
    for path in skill.reference_paths:
        text_parts.append(path.read_text(encoding="utf-8"))
    combined = "\n".join(part for part in text_parts if part.strip())

    repo_hints = sorted(set(re.findall(r"code\.byted\.org/[A-Za-z0-9._/-]+", combined)))
    path_hints = sorted(set(re.findall(r"/[A-Za-z0-9._/\-]+", combined)))
    candidate_files = [path for path in path_hints if Path(path).suffix]
    directory_paths = [path for path in path_hints if path not in set(candidate_files)]
    return repo_hints, directory_paths[:12], candidate_files[:12]

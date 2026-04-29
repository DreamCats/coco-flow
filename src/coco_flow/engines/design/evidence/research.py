"""Design 仓库调研。

根据 refined PRD、搜索线索和绑定仓库执行本地代码搜索、路径扫描与 git 证据提取，
输出候选文件、相关文件和证据摘要，供 design.md 使用。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
import subprocess

from coco_flow.engines.design.evidence.scope_guard import build_scope_guard_terms, exclusion_reason
from coco_flow.engines.design.support import as_str_list, dedupe, dict_list, first_non_empty
from coco_flow.engines.design.types import DesignInputBundle

_SEARCH_GLOBS = ("*.go", "*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.proto", "*.thrift", "*.sql")
_EXCLUDED_DIRS = {".git", ".livecoding", ".coco-flow", "node_modules", "dist", "build", "__pycache__"}
_GIT_TIMEOUT_SECONDS = 6
_MAX_GIT_WORKERS = 3
_MAX_GIT_TERMS = 6
_MAX_GIT_EVIDENCE = 16
_MAX_FILE_HISTORY_CANDIDATES = 8
_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "this",
    "that",
    "true",
    "false",
    "refined",
    "prd",
}


def build_research_plan(prepared: DesignInputBundle, search_hints_payload: dict[str, object] | None = None) -> dict[str, object]:
    search_hints_payload = search_hints_payload or {}
    hint_terms = [
        *as_str_list(search_hints_payload.get("search_terms")),
        *as_str_list(search_hints_payload.get("likely_symbols")),
    ]
    terms = dedupe([*hint_terms, *_extract_search_terms(prepared)])[:16]
    file_patterns = as_str_list(search_hints_payload.get("likely_file_patterns"))[:10]
    negative_terms = dedupe(
        [
            *as_str_list(search_hints_payload.get("negative_terms")),
            *build_scope_guard_terms(prepared.sections.non_goals),
        ]
    )[:16]
    questions = _default_questions(prepared)
    return {
        "repos": [
            {
                "repo_id": repo.repo_id,
                "repo_path": repo.repo_path,
                "questions": questions,
                "search_terms": terms,
                "likely_symbols": as_str_list(search_hints_payload.get("likely_symbols"))[:12],
                "likely_file_patterns": file_patterns,
                "negative_terms": negative_terms,
                "search_hints_source": str(search_hints_payload.get("source") or "local"),
                "search_hints_confidence": str(search_hints_payload.get("confidence") or "unknown"),
                "preferred_paths": _preferred_paths(repo.repo_path),
                "budget": {"max_files_read": 12, "max_search_commands": 12, "max_path_pattern_scans": 8},
            }
            for repo in prepared.repo_scopes
        ]
    }


def run_parallel_repo_research(prepared: DesignInputBundle, plan_payload: dict[str, object]) -> list[dict[str, object]]:
    plans = _repo_plan_items(plan_payload)
    by_repo = {str(item.get("repo_id") or ""): item for item in plans}
    max_workers = min(4, max(1, len(prepared.repo_scopes)))
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="design-v3-research") as executor:
        futures = {
            executor.submit(research_single_repo, repo.repo_id, repo.repo_path, by_repo.get(repo.repo_id, {})): repo.repo_id
            for repo in prepared.repo_scopes
        }
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda item: str(item.get("repo_id") or ""))


def research_single_repo(repo_id: str, repo_path: str, repo_plan: dict[str, object]) -> dict[str, object]:
    root = Path(repo_path)
    if not root.is_dir():
        return {
            "repo_id": repo_id,
            "repo_path": repo_path,
            "work_hypothesis": "unknown",
            "confidence": "low",
            "evidence": [],
            "candidate_files": [],
            "boundaries": [],
            "unknowns": [f"repo path not found: {repo_path}"],
            "budget_used": {"search_commands": 0, "path_pattern_scans": 0, "files_read": 0, "git_commands": 0},
        }

    terms = as_str_list(repo_plan.get("search_terms"))[: int(_budget(repo_plan, "max_search_commands", 8))]
    seen_files: dict[str, list[dict[str, object]]] = {}
    search_count = 0
    for term in terms:
        search_count += 1
        for match in _rg_matches(root, term):
            rel = match["path"]
            seen_files.setdefault(rel, []).append(match)

    path_patterns = as_str_list(repo_plan.get("likely_file_patterns"))[: int(_budget(repo_plan, "max_path_pattern_scans", 8))]
    path_scan_count = 1 if path_patterns else 0
    for match in _path_pattern_matches(root, path_patterns):
        rel = match["path"]
        seen_files.setdefault(rel, []).append(match)

    git_payload = build_git_evidence(root, terms, seen_files)
    max_files = int(_budget(repo_plan, "max_files_read", 12))
    ranked_files = _rank_candidate_files(seen_files, git_payload, as_str_list(repo_plan.get("negative_terms")))
    excluded_files = [item for item in ranked_files if bool(item.get("excluded"))][:max_files]
    candidate_files = [item for item in ranked_files if bool(item.get("core_evidence")) and not bool(item.get("excluded"))][:max_files]
    related_files = [item for item in ranked_files if not bool(item.get("core_evidence")) and not bool(item.get("excluded"))][:max_files]
    evidence: list[dict[str, object]] = []
    for item in candidate_files:
        first_match = seen_files.get(str(item["path"]), [{}])[0]
        evidence.append(
            {
                "path": item["path"],
                "line_hint": int(first_match.get("line") or 1),
                "why_relevant": item["reason"],
                "scene": item.get("scene", ""),
                "symbol": item.get("symbol", ""),
                "matched_behavior": item.get("matched_behavior", ""),
                "why_core": item.get("why_core", ""),
                "excerpt": _read_excerpt(root / str(item["path"]), int(first_match.get("line") or 1)),
            }
        )

    boundaries = []
    if not any(str(item["path"]).endswith((".proto", ".thrift")) for item in candidate_files):
        boundaries.append("未从搜索证据中发现协议文件改动信号。")
    if not candidate_files:
        boundaries.append("当前搜索预算内未定位到直接候选文件。")

    responsibility = _repo_responsibility(repo_id, repo_path, candidate_files, related_files)
    confidence = "high" if len(candidate_files) >= 3 else "medium" if candidate_files else "low"
    return {
        "repo_id": repo_id,
        "repo_path": repo_path,
        "work_hypothesis": responsibility,
        "confidence": confidence,
        "evidence": evidence,
        "candidate_files": candidate_files,
        "related_files": related_files,
        "excluded_files": excluded_files,
        "git_evidence": git_payload.get("git_evidence", []),
        "cochange_files": git_payload.get("cochange_files", []),
        "boundaries": boundaries,
        "unknowns": _repo_unknowns(responsibility, candidate_files),
        "budget_used": {
            "search_commands": search_count,
            "path_pattern_scans": path_scan_count,
            "files_read": len(candidate_files),
            "git_commands": int(git_payload.get("git_commands") or 0),
        },
    }


def _repo_responsibility(
    repo_id: str,
    repo_path: str,
    candidate_files: list[dict[str, object]],
    related_files: list[dict[str, object]],
) -> str:
    if candidate_files and _looks_conditional_shared_repo(repo_id, repo_path, candidate_files):
        return "conditional"
    if candidate_files:
        return "required"
    if related_files:
        return "reference_only"
    return "unknown"


def _looks_conditional_shared_repo(repo_id: str, repo_path: str, candidate_files: list[dict[str, object]]) -> bool:
    repo_text = f"{repo_id} {repo_path}".lower()
    if not any(token in repo_text for token in ("common", "shared", "schema", "idl", "config")):
        return False
    paths = [str(item.get("path") or "").lower() for item in candidate_files]
    if not paths:
        return False
    conditional_markers = (
        "abtest/",
        "tcc",
        "schema",
        "config",
        "confx",
        ".proto",
        ".thrift",
        "constant",
        "const",
    )
    return all(any(marker in path for marker in conditional_markers) for path in paths)


def _repo_unknowns(responsibility: str, candidate_files: list[dict[str, object]]) -> list[str]:
    if responsibility == "unknown":
        return ["需要人工确认该仓是否承担核心改造，或补充更明确的搜索术语。"]
    if responsibility == "conditional":
        return ["该仓仅在缺少公共字段、配置或协议能力时需要改造；进入 Plan 前需确认是否已有可复用能力。"]
    if responsibility == "reference_only" and not candidate_files:
        return ["该仓当前只有参考信号，未证明需要代码改造。"]
    return []


def build_research_summary(repo_research_payloads: list[dict[str, object]]) -> dict[str, object]:
    return {
        "repos": repo_research_payloads,
        "unknowns": [
            f"{repo.get('repo_id')}: {unknown}"
            for repo in repo_research_payloads
            for unknown in as_str_list(repo.get("unknowns"))
        ],
        "candidate_file_count": sum(len(dict_list(repo.get("candidate_files"))) for repo in repo_research_payloads),
        "excluded_file_count": sum(len(dict_list(repo.get("excluded_files"))) for repo in repo_research_payloads),
        "git_evidence_count": sum(len(dict_list(repo.get("git_evidence"))) for repo in repo_research_payloads),
        "git_command_count": sum(int(dict(repo.get("budget_used") or {}).get("git_commands") or 0) for repo in repo_research_payloads),
    }


def candidate_paths(repo: dict[str, object]) -> list[str]:
    return [
        str(item.get("path") or "")
        for item in dict_list(repo.get("candidate_files"))
        if str(item.get("path") or "").strip()
    ]


def safe_artifact_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()) or "repo"


def _rg_matches(root: Path, term: str) -> list[dict[str, object]]:
    if not term.strip():
        return []
    cmd = ["rg", "--line-number", "--no-heading", "-m", "5"]
    for glob in _SEARCH_GLOBS:
        cmd.extend(["--glob", glob])
    cmd.extend([term, str(root)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    matches: list[dict[str, object]] = []
    for line in result.stdout.splitlines()[:40]:
        path, line_no, text = _parse_rg_line(root, line)
        if path:
            matches.append({"path": path, "line": line_no, "term": term, "text": text})
    return matches


def _parse_rg_line(root: Path, line: str) -> tuple[str, int, str]:
    parts = line.split(":", 2)
    if len(parts) < 3:
        return "", 1, ""
    try:
        rel = str(Path(parts[0]).resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        rel = parts[0]
    if any(part in _EXCLUDED_DIRS for part in Path(rel).parts):
        return "", 1, ""
    try:
        line_no = int(parts[1])
    except ValueError:
        line_no = 1
    return rel, line_no, parts[2].strip()[:240]


def _path_pattern_matches(root: Path, patterns: list[str]) -> list[dict[str, object]]:
    clean_patterns = [_normalize_path_pattern(pattern) for pattern in patterns]
    clean_patterns = [pattern for pattern in dedupe(clean_patterns) if pattern]
    if not clean_patterns:
        return []
    try:
        result = subprocess.run(["rg", "--files", str(root)], capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    raw_matches: list[tuple[str, str]] = []
    root_resolved = root.resolve()
    for line in result.stdout.splitlines():
        rel = _relative_path(root_resolved, line)
        if not rel or any(part in _EXCLUDED_DIRS for part in Path(rel).parts) or not _is_searchable_history_path(rel):
            continue
        rel_lower = rel.lower()
        for pattern in clean_patterns:
            if pattern in rel_lower:
                raw_matches.append((rel, pattern))
                break
        if len(raw_matches) >= 80:
            break
    pattern_counts: dict[str, int] = {}
    for _rel, pattern in raw_matches:
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    matches: list[dict[str, object]] = []
    for rel, pattern in raw_matches[:40]:
        broad = pattern_counts.get(pattern, 0) > 12 or len(pattern) <= 4
        matches.append(
            {
                "path": rel,
                "line": 1,
                "term": pattern,
                "text": f"path name matches search hint: {pattern}",
                "source": "path_pattern_broad" if broad else "path_pattern",
            }
        )
    return matches


def _relative_path(root_resolved: Path, value: str) -> str:
    try:
        return str(Path(value).resolve().relative_to(root_resolved))
    except (OSError, ValueError):
        return value


def _normalize_path_pattern(value: str) -> str:
    pattern = value.strip().lower().strip("*").strip("/")
    pattern = re.sub(r"[^a-z0-9_.-]+", "", pattern)
    if pattern in {"go", "py", "ts", "tsx", "js", "jsx", "json", "yaml", "yml"}:
        return ""
    return pattern if len(pattern) >= 2 else ""


def build_git_evidence(root: Path, terms: list[str], seen_files: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    if not _is_git_repo(root):
        return {"git_evidence": [], "cochange_files": [], "git_commands": 0}
    git_terms = terms[:_MAX_GIT_TERMS]
    top_paths = [
        path
        for path, _matches in sorted(seen_files.items(), key=lambda item: (-len(item[1]), item[0]))[:_MAX_FILE_HISTORY_CANDIDATES]
    ]
    tasks: list[tuple[str, object]] = []
    if git_terms:
        tasks.append(("message", git_terms))
        tasks.append(("pickaxe", git_terms))
    for path in top_paths:
        tasks.append(("history", path))

    evidence: list[dict[str, object]] = []
    cochange_files: list[str] = []
    command_count = 0
    with ThreadPoolExecutor(max_workers=min(_MAX_GIT_WORKERS, max(1, len(tasks))), thread_name_prefix="design-git") as executor:
        futures = [executor.submit(_run_git_task, root, kind, payload) for kind, payload in tasks]
        for future in as_completed(futures):
            result = future.result()
            command_count += int(result.get("git_commands") or 0)
            evidence.extend(dict_list(result.get("git_evidence")))
            cochange_files.extend(as_str_list(result.get("cochange_files")))
    evidence = _dedupe_git_evidence(evidence)[:_MAX_GIT_EVIDENCE]
    return {
        "git_evidence": evidence,
        "cochange_files": dedupe(cochange_files)[:_MAX_GIT_EVIDENCE],
        "git_commands": command_count,
    }


def _run_git_task(root: Path, kind: str, payload: object) -> dict[str, object]:
    if kind == "message":
        return _git_message_evidence(root, as_str_list(payload))
    if kind == "pickaxe":
        return _git_pickaxe_evidence(root, as_str_list(payload))
    if kind == "history":
        return _git_file_history(root, str(payload or ""))
    return {"git_evidence": [], "cochange_files": [], "git_commands": 0}


def _git_message_evidence(root: Path, terms: list[str]) -> dict[str, object]:
    evidence: list[dict[str, object]] = []
    commands = 0
    for term in terms[:_MAX_GIT_TERMS]:
        commands += 1
        result = _run_git(root, ["log", "--since=12 months ago", "--max-count=5", "--name-only", "--format=%H%x09%s", "--grep", term])
        evidence.extend(_parse_git_log_name_output(result, "commit_message", f"commit message 命中搜索词：{term}"))
    return {"git_evidence": evidence, "cochange_files": _cochange_from_evidence(evidence), "git_commands": commands}


def _git_pickaxe_evidence(root: Path, terms: list[str]) -> dict[str, object]:
    evidence: list[dict[str, object]] = []
    commands = 0
    for term in terms[:_MAX_GIT_TERMS]:
        if len(term.strip()) < 3:
            continue
        commands += 1
        result = _run_git(
            root,
            ["log", "--since=12 months ago", "--max-count=5", "--name-only", "--format=%H%x09%s", "-G", re.escape(term)],
        )
        evidence.extend(_parse_git_log_name_output(result, "diff_pattern", f"历史 diff 命中搜索词：{term}"))
    return {"git_evidence": evidence, "cochange_files": _cochange_from_evidence(evidence), "git_commands": commands}


def _git_file_history(root: Path, path: str) -> dict[str, object]:
    if not path:
        return {"git_evidence": [], "cochange_files": [], "git_commands": 0}
    result = _run_git(root, ["log", "--since=12 months ago", "--max-count=5", "--name-only", "--format=%H%x09%s", "--", path])
    evidence = _parse_git_log_name_output(result, "file_history", f"候选文件近期有相关提交历史：{path}", preferred_path=path)
    return {"git_evidence": evidence, "cochange_files": _cochange_from_evidence(evidence), "git_commands": 1}


def _run_git(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _is_git_repo(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _parse_git_log_name_output(raw: str, evidence_type: str, why: str, preferred_path: str = "") -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    current_commit = ""
    current_subject = ""
    current_files: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if "\t" in text and re.match(r"^[0-9a-f]{7,40}\t", text):
            evidence.extend(_git_commit_entries(current_commit, current_subject, current_files, evidence_type, why, preferred_path))
            current_commit, current_subject = text.split("\t", 1)
            current_files = []
            continue
        if text:
            current_files.append(text)
    evidence.extend(_git_commit_entries(current_commit, current_subject, current_files, evidence_type, why, preferred_path))
    return evidence


def _git_commit_entries(
    commit: str,
    subject: str,
    files: list[str],
    evidence_type: str,
    why: str,
    preferred_path: str,
) -> list[dict[str, object]]:
    if not commit:
        return []
    filtered_files = [path for path in files if _is_searchable_history_path(path)]
    if preferred_path and preferred_path not in filtered_files:
        filtered_files.insert(0, preferred_path)
    return [
        {
            "path": path,
            "commit": commit[:12],
            "subject": subject,
            "type": evidence_type,
            "why_relevant": why,
            "cochanged_files": [item for item in filtered_files if item != path][:8],
        }
        for path in filtered_files[:8]
    ]


def _is_searchable_history_path(path: str) -> bool:
    if not path or any(part in _EXCLUDED_DIRS for part in Path(path).parts):
        return False
    return path.endswith((".go", ".py", ".ts", ".tsx", ".js", ".jsx", ".proto", ".thrift", ".sql", ".json", ".yaml", ".yml"))


def _cochange_from_evidence(evidence: list[dict[str, object]]) -> list[str]:
    values: list[str] = []
    for item in evidence:
        values.extend(as_str_list(item.get("cochanged_files")))
    return dedupe(values)


def _dedupe_git_evidence(evidence: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, object]] = []
    for item in evidence:
        key = (str(item.get("path") or ""), str(item.get("commit") or ""), str(item.get("type") or ""))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _rank_candidate_files(
    seen_files: dict[str, list[dict[str, object]]],
    git_payload: dict[str, object],
    negative_terms: list[str] | None = None,
) -> list[dict[str, object]]:
    git_by_path = _git_evidence_by_path(git_payload)
    negative_terms = [term.lower() for term in as_str_list(negative_terms) if term.strip()]
    all_paths = set(seen_files) | set(git_by_path)
    ranked = sorted(all_paths, key=lambda path: (-_evidence_score(path, seen_files.get(path, []), git_by_path, negative_terms), path))
    return [
        {
            "path": path,
            "kind": "core_change",
            "confidence": "high" if _evidence_score(path, seen_files.get(path, []), git_by_path, negative_terms) >= 8 else "medium",
            "reason": _candidate_reason(path, seen_files.get(path, []), git_by_path, negative_terms),
            "scene": _path_scene(path),
            "symbol": _match_symbol(seen_files.get(path, [])),
            "matched_behavior": _match_terms_text(seen_files.get(path, [])),
            "why_core": "当前代码命中和 git 历史信号共同支撑，适合作为核心候选。" if _is_core_candidate(path, seen_files.get(path, []), git_by_path, negative_terms) else "",
            "core_evidence": _is_core_candidate(path, seen_files.get(path, []), git_by_path, negative_terms),
            "excluded": bool(exclusion_reason(path, seen_files.get(path, []), negative_terms)),
            "exclude_reason": exclusion_reason(path, seen_files.get(path, []), negative_terms),
            "git_signal_count": len(git_by_path.get(path, [])),
        }
        for path in ranked
    ]


def _git_evidence_by_path(git_payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    by_path: dict[str, list[dict[str, object]]] = {}
    for item in dict_list(git_payload.get("git_evidence")):
        path = str(item.get("path") or "")
        if path:
            by_path.setdefault(path, []).append(item)
    return by_path


def _read_excerpt(path: Path, line_hint: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    start = max(0, line_hint - 3)
    end = min(len(lines), line_hint + 2)
    return "\n".join(lines[start:end])[:800]


def _extract_search_terms(prepared: DesignInputBundle) -> list[str]:
    source = "\n".join(
        [
            prepared.title,
            *prepared.sections.change_scope,
            *prepared.sections.key_constraints,
            *prepared.sections.acceptance_criteria,
            prepared.refined_markdown[:4000],
        ]
    )
    terms: list[str] = []
    for value in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", source):
        lower = value.lower()
        if lower not in _STOPWORDS:
            terms.append(value)
    for value in re.findall(r"[\u4e00-\u9fff]{2,8}", source):
        terms.append(value)
    return dedupe(terms)[:12] or [prepared.title]


def _preferred_paths(repo_path: str) -> list[str]:
    root = Path(repo_path)
    if not root.is_dir():
        return []
    names = ["src", "pkg", "biz", "internal", "api", "web", "service"]
    return [name for name in names if (root / name).is_dir()]


def _default_questions(prepared: DesignInputBundle) -> list[str]:
    scope = first_non_empty(prepared.sections.change_scope, prepared.title)
    return [
        f"仓库中是否存在与「{scope}」直接对应的模块、入口或数据转换逻辑？",
        "是否存在接口、协议、状态聚合或下游消费边界？",
        "如果该仓不需要代码改动，证据边界是什么？",
    ]


def _repo_plan_items(plan_payload: dict[str, object]) -> list[dict[str, object]]:
    return dict_list(plan_payload.get("repos"))


def _budget(repo_plan: dict[str, object], key: str, default: int) -> object:
    raw = repo_plan.get("budget")
    if isinstance(raw, dict):
        return raw.get(key) or default
    return default


def _evidence_score(
    path: str,
    matches: list[dict[str, object]],
    git_by_path: dict[str, list[dict[str, object]]] | None = None,
    negative_terms: list[str] | None = None,
) -> int:
    git_by_path = git_by_path or {}
    negative_terms = negative_terms or []
    distinct_terms = {str(item.get("term") or "").lower() for item in matches if str(item.get("term") or "").strip()}
    path_parts = {part.lower() for part in Path(path).parts}
    git_signal_count = len(git_by_path.get(path, []))
    path_hint_count = sum(1 for item in matches if str(item.get("source") or "") == "path_pattern")
    score = len(matches) + len(distinct_terms) * 2 + min(git_signal_count, 4) + path_hint_count * 3
    score -= _negative_hit_count(path, matches, negative_terms) * 4
    if any(part in {"test", "tests", "__tests__"} for part in path_parts) or path.endswith(("_test.go", ".test.ts", ".spec.ts")):
        score -= 4
    if any(part in {"src", "pkg", "internal", "entities", "converters", "dal", "service", "api"} for part in path_parts):
        score += 2
    return score


def _is_core_candidate(
    path: str,
    matches: list[dict[str, object]],
    git_by_path: dict[str, list[dict[str, object]]] | None = None,
    negative_terms: list[str] | None = None,
) -> bool:
    git_by_path = git_by_path or {}
    negative_terms = negative_terms or []
    distinct_terms = {str(item.get("term") or "").lower() for item in matches if str(item.get("term") or "").strip()}
    path_hint_count = sum(1 for item in matches if str(item.get("source") or "") == "path_pattern")
    if path.endswith(("_test.go", ".test.ts", ".spec.ts")):
        return False
    if _negative_hit_count(path, matches, negative_terms) and len(distinct_terms) <= 2 and len(git_by_path.get(path, [])) < 2:
        return False
    return _evidence_score(path, matches, git_by_path, negative_terms) >= 5 and (
        len(distinct_terms) >= 2 or len(git_by_path.get(path, [])) >= 2 or path_hint_count >= 1
    )


def _candidate_reason(
    path: str,
    matches: list[dict[str, object]],
    git_by_path: dict[str, list[dict[str, object]]] | None = None,
    negative_terms: list[str] | None = None,
) -> str:
    git_by_path = git_by_path or {}
    negative_terms = negative_terms or []
    distinct_terms = {str(item.get("term") or "") for item in matches if str(item.get("term") or "").strip()}
    git_signal_count = len(git_by_path.get(path, []))
    negative_hit_count = _negative_hit_count(path, matches, negative_terms)
    negative_note = f"，命中 {negative_hit_count} 条排除信号" if negative_hit_count else ""
    if _is_core_candidate(path, matches, git_by_path, negative_terms):
        return f"命中 {len(matches)} 条、{len(distinct_terms)} 组当前代码证据，另有 {git_signal_count} 条 git 历史信号。"
    return f"仅作为相关文件：命中 {len(matches)} 条、{len(distinct_terms)} 组当前代码证据，git 历史信号 {git_signal_count} 条{negative_note}，尚不足以证明需要修改。"


def _negative_hit_count(path: str, matches: list[dict[str, object]], negative_terms: list[str]) -> int:
    haystack = " ".join([path, *(str(item.get("text") or "") for item in matches)]).lower()
    return sum(1 for term in negative_terms if term and term in haystack)


def _path_scene(path: str) -> str:
    parts = [part for part in Path(path).parts if part not in {"", "."}]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return "/".join(parts[:-1])


def _match_symbol(matches: list[dict[str, object]]) -> str:
    for item in matches:
        text = str(item.get("text") or "")
        match = re.search(r"\b(?:func|type|class|interface|const|var)\s+([A-Za-z_][A-Za-z0-9_]*)", text)
        if match:
            return match.group(1)
    return ""


def _match_terms_text(matches: list[dict[str, object]]) -> str:
    terms = dedupe(str(item.get("term") or "") for item in matches if str(item.get("term") or "").strip())
    return "、".join(terms[:6])

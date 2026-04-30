"""Local repo index for Design Research Agent.

这个模块只做便宜、可复用的本地索引：
- 文件清单
- 轻量符号清单
- 近期 git 摘要

它不读取 `.livecoding/context`，也不依赖 embedding / LLM API。Research Agent
仍然负责最终判断；这里的职责只是把搜索空间先压小。
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import time

from coco_flow.config import Settings
from coco_flow.engines.design.support import dedupe, dict_list
from coco_flow.engines.design.types import DesignInputBundle
from coco_flow.engines.shared.models import RepoScope

INDEX_VERSION = 1
MAX_FILES = 50000
MAX_SYMBOLS = 30000
MAX_RECENT_COMMITS = 80
MAX_CONTEXT_FILES = 14
MAX_CONTEXT_SYMBOLS = 18
MAX_CONTEXT_COMMITS = 8
COMMAND_TIMEOUT_SECONDS = 18
GIT_TIMEOUT_SECONDS = 8

SEARCH_EXTENSIONS = {
    ".go",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".proto",
    ".thrift",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
}
EXCLUDED_DIRS = {".git", ".livecoding", ".coco-flow", "node_modules", "dist", "build", "__pycache__"}
STOPWORDS = {
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
    "design",
    "repo",
}


def build_repo_context_package(
    prepared: DesignInputBundle,
    settings: Settings,
    repo: RepoScope,
    *,
    on_log,
) -> dict[str, object]:
    """Build a small, agent-readable context package for one repo."""

    started = time.perf_counter()
    index_payload = load_or_build_repo_index(repo, settings)
    query_terms = _query_terms(prepared)
    package = {
        "source": "local_repo_index",
        "repo_id": repo.repo_id,
        "index": {
            "status": index_payload.get("index_status") or "unknown",
            "version": INDEX_VERSION,
            "head": index_payload.get("head") or "",
            "worktree_state": index_payload.get("worktree_state") or "",
            "file_count": len(dict_list(index_payload.get("files"))),
            "symbol_count": len(dict_list(index_payload.get("symbols"))),
            "recent_commit_count": len(dict_list(index_payload.get("recent_commits"))),
        },
        "query_terms": query_terms[:18],
        "top_files": _rank_files(index_payload, query_terms)[:MAX_CONTEXT_FILES],
        "top_symbols": _rank_symbols(index_payload, query_terms)[:MAX_CONTEXT_SYMBOLS],
        "top_git_commits": _rank_commits(index_payload, query_terms)[:MAX_CONTEXT_COMMITS],
        "notes": [
            "这些是本地索引给出的候选线索，不是最终结论。",
            "Research Agent 必须继续读取文件或 git 证据后再产出 claims/candidate_files。",
            "未读取 `.livecoding/context`；后续也不依赖该目录。",
        ],
    }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    on_log(
        "design_repo_index_ok: "
        f"repo={repo.repo_id} status={package['index']['status']} "
        f"files={package['index']['file_count']} symbols={package['index']['symbol_count']} "
        f"commits={package['index']['recent_commit_count']} ms={elapsed_ms}"
    )
    return package


def load_or_build_repo_index(repo: RepoScope, settings: Settings) -> dict[str, object]:
    root = Path(repo.repo_path).expanduser()
    cache_path = _cache_path(settings.config_root, root)
    repo_state = _repo_state(root)
    cached = _read_cache(cache_path)
    if _cache_valid(cached, root, repo_state):
        cached["index_status"] = "cache_hit"
        return cached

    payload = _build_index(repo, root, repo_state)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _write_cache(cache_path, payload)
    payload["index_status"] = "rebuilt"
    return payload


def _build_index(repo: RepoScope, root: Path, repo_state: dict[str, str]) -> dict[str, object]:
    now = datetime.now().astimezone().isoformat()
    if not root.is_dir():
        return {
            "version": INDEX_VERSION,
            "repo_id": repo.repo_id,
            "repo_path": str(root),
            "head": repo_state.get("head", ""),
            "worktree_state": repo_state.get("worktree_state", ""),
            "indexed_at": now,
            "files": [],
            "symbols": [],
            "recent_commits": [],
        }

    files = _list_files(root)
    return {
        "version": INDEX_VERSION,
        "repo_id": repo.repo_id,
        "repo_path": str(root),
        "head": repo_state.get("head", ""),
        "worktree_state": repo_state.get("worktree_state", ""),
        "indexed_at": now,
        "files": files,
        "symbols": _extract_symbols(root),
        "recent_commits": _recent_commits(root),
    }


def _list_files(root: Path) -> list[dict[str, object]]:
    try:
        result = subprocess.run(
            ["rg", "--files", str(root)],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    root_resolved = _safe_resolve(root)
    files: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        rel = _relative_path(root_resolved, line)
        if not _is_indexable_path(rel):
            continue
        files.append({"path": rel, "name": Path(rel).name, "ext": Path(rel).suffix})
        if len(files) >= MAX_FILES:
            break
    return files


def _extract_symbols(root: Path) -> list[dict[str, object]]:
    cmd = ["rg", "--line-number", "--no-heading"]
    for ext in sorted(SEARCH_EXTENSIONS):
        cmd.extend(["--glob", f"*{ext}"])
    cmd.extend([r"^\s*(func|type|const|var|class|interface|enum|export\s+|def)\b", str(root)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    root_resolved = _safe_resolve(root)
    symbols: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        parsed = _parse_symbol_line(root_resolved, line)
        if not parsed:
            continue
        symbols.append(parsed)
        if len(symbols) >= MAX_SYMBOLS:
            break
    return symbols


def _parse_symbol_line(root_resolved: Path, line: str) -> dict[str, object] | None:
    parts = line.split(":", 2)
    if len(parts) < 3:
        return None
    rel = _relative_path(root_resolved, parts[0])
    if not _is_indexable_path(rel):
        return None
    try:
        line_no = int(parts[1])
    except ValueError:
        line_no = 1
    signature = parts[2].strip()[:240]
    name = _symbol_name(signature)
    if not name:
        return None
    return {
        "path": rel,
        "line": line_no,
        "name": name,
        "kind": _symbol_kind(signature),
        "signature": signature,
    }


def _symbol_name(signature: str) -> str:
    patterns = [
        r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)",
        r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\b(?:const|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\b(?:class|interface|enum|def)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bexport\s+(?:function|class|interface|const|type)\s+([A-Za-z_][A-Za-z0-9_]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, signature)
        if match:
            return match.group(1)
    return ""


def _symbol_kind(signature: str) -> str:
    for kind in ("func", "type", "const", "var", "class", "interface", "enum", "def"):
        if re.search(rf"\b{kind}\b", signature):
            return kind
    if "export" in signature:
        return "export"
    return "symbol"


def _recent_commits(root: Path) -> list[dict[str, object]]:
    if not _is_git_repo(root):
        return []
    raw = _run_git(root, ["log", f"--max-count={MAX_RECENT_COMMITS}", "--name-only", "--format=%H%x09%s"])
    commits: list[dict[str, object]] = []
    current_hash = ""
    current_subject = ""
    current_files: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if "\t" in text and re.match(r"^[0-9a-f]{7,40}\t", text):
            _append_commit(commits, current_hash, current_subject, current_files)
            current_hash, current_subject = text.split("\t", 1)
            current_files = []
            continue
        if text and _is_indexable_path(text):
            current_files.append(text)
    _append_commit(commits, current_hash, current_subject, current_files)
    return commits[:MAX_RECENT_COMMITS]


def _append_commit(commits: list[dict[str, object]], commit_hash: str, subject: str, files: list[str]) -> None:
    if not commit_hash:
        return
    commits.append(
        {
            "commit": commit_hash[:12],
            "subject": subject,
            "files": dedupe(files)[:20],
        }
    )


def _rank_files(index_payload: dict[str, object], terms: list[str]) -> list[dict[str, object]]:
    ranked: list[tuple[int, dict[str, object]]] = []
    commit_hits = _commit_file_hits(index_payload, terms)
    for item in dict_list(index_payload.get("files")):
        path = str(item.get("path") or "")
        score = _score_text(path, terms) + min(commit_hits.get(path, 0), 4)
        if score <= 0:
            continue
        ranked.append(
            (
                score,
                {
                    "path": path,
                    "score": score,
                    "reason": _reason(path, terms, commit_hits.get(path, 0)),
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("path") or "")))
    return [item for _score, item in ranked]


def _rank_symbols(index_payload: dict[str, object], terms: list[str]) -> list[dict[str, object]]:
    ranked: list[tuple[int, dict[str, object]]] = []
    for item in dict_list(index_payload.get("symbols")):
        haystack = " ".join([str(item.get("name") or ""), str(item.get("signature") or ""), str(item.get("path") or "")])
        score = _score_text(haystack, terms)
        if score <= 0:
            continue
        ranked.append(
            (
                score,
                {
                    "path": str(item.get("path") or ""),
                    "line": int(item.get("line") or 1),
                    "name": str(item.get("name") or ""),
                    "kind": str(item.get("kind") or "symbol"),
                    "score": score,
                    "signature": str(item.get("signature") or ""),
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("path") or ""), str(item[1].get("name") or "")))
    return [item for _score, item in ranked]


def _rank_commits(index_payload: dict[str, object], terms: list[str]) -> list[dict[str, object]]:
    ranked: list[tuple[int, dict[str, object]]] = []
    for item in dict_list(index_payload.get("recent_commits")):
        files = [str(path) for path in item.get("files", []) if str(path).strip()] if isinstance(item.get("files"), list) else []
        haystack = " ".join([str(item.get("subject") or ""), *files])
        score = _score_text(haystack, terms)
        if score <= 0:
            continue
        ranked.append(
            (
                score,
                {
                    "commit": str(item.get("commit") or ""),
                    "subject": str(item.get("subject") or ""),
                    "files": files[:10],
                    "score": score,
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("commit") or "")))
    return [item for _score, item in ranked]


def _query_terms(prepared: DesignInputBundle) -> list[str]:
    source = "\n".join(
        [
            prepared.title,
            *prepared.sections.change_scope,
            *prepared.sections.key_constraints,
            *prepared.sections.acceptance_criteria,
            prepared.design_skills_index_markdown,
            prepared.refined_markdown[:5000],
        ]
    )
    terms: list[str] = []
    for value in re.findall(r"[A-Za-z][A-Za-z0-9_/-]{2,}", source):
        cleaned = value.strip("/").strip()
        if cleaned.lower() not in STOPWORDS:
            terms.append(cleaned)
            terms.extend(_split_identifier(cleaned))
    for value in re.findall(r"[\u4e00-\u9fff]{2,8}", source):
        terms.append(value)
    return dedupe(terms)[:32] or [prepared.title]


def _split_identifier(value: str) -> list[str]:
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ").replace("-", " ").split()
    return [part for part in parts if len(part) >= 3 and part.lower() not in STOPWORDS]


def _score_text(text: str, terms: list[str]) -> int:
    haystack = text.lower()
    score = 0
    for term in terms:
        needle = term.lower()
        if not needle:
            continue
        if needle in haystack:
            score += 4 if "/" in needle or "_" in needle else 2
        elif len(needle) >= 5 and needle.replace("_", "").replace("-", "") in haystack.replace("_", "").replace("-", ""):
            score += 1
    return score


def _commit_file_hits(index_payload: dict[str, object], terms: list[str]) -> dict[str, int]:
    hits: dict[str, int] = {}
    for commit in _rank_commits(index_payload, terms):
        for path in commit.get("files", []):
            text = str(path).strip()
            if text:
                hits[text] = hits.get(text, 0) + 1
    return hits


def _reason(path: str, terms: list[str], commit_hits: int) -> str:
    matched = [term for term in terms if term.lower() in path.lower()][:5]
    parts: list[str] = []
    if matched:
        parts.append("路径命中：" + "、".join(matched))
    if commit_hits:
        parts.append(f"近期 git 摘要中出现 {commit_hits} 次")
    return "；".join(parts) or "索引召回候选"


def _cache_path(config_root: Path, repo_root: Path) -> Path:
    key = sha256(str(_safe_resolve(repo_root)).encode("utf-8")).hexdigest()[:24]
    return config_root / "repo-index" / key / "index.json"


def _read_cache(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_cache(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _cache_valid(payload: dict[str, object], root: Path, repo_state: dict[str, str]) -> bool:
    return (
        bool(payload)
        and int(payload.get("version") or 0) == INDEX_VERSION
        and str(payload.get("repo_path") or "") == str(root)
        and str(payload.get("head") or "") == repo_state.get("head", "")
        and str(payload.get("worktree_state") or "") == repo_state.get("worktree_state", "")
    )


def _repo_state(root: Path) -> dict[str, str]:
    if not _is_git_repo(root):
        return {"head": "no-git", "worktree_state": _non_git_fingerprint(root)}
    head = _run_git(root, ["rev-parse", "HEAD"]).strip() or "unknown"
    status = _run_git(root, ["status", "--porcelain=v1", "--untracked-files=normal"])
    return {"head": head, "worktree_state": _worktree_fingerprint(root, status)}


def _worktree_fingerprint(root: Path, status: str) -> str:
    # status 只能说明文件脏了，不能区分同一个文件的不同未提交内容。
    # 这里额外带上 size/mtime，保证常见编辑后会刷新索引。
    parts = [status]
    for rel in _status_paths(status)[:200]:
        path = root / rel
        try:
            stat = path.stat()
        except OSError:
            parts.append(f"{rel}:missing")
            continue
        parts.append(f"{rel}:{stat.st_size}:{stat.st_mtime_ns}")
    return sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _status_paths(status: str) -> list[str]:
    paths: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        text = line[3:].strip()
        if " -> " in text:
            text = text.split(" -> ", 1)[1].strip()
        if text:
            paths.append(text)
    return dedupe(paths)


def _non_git_fingerprint(root: Path) -> str:
    files = _list_files(root)
    payload = "\n".join(str(item.get("path") or "") for item in files)
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def _is_git_repo(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _run_git(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _relative_path(root_resolved: Path, value: str) -> str:
    try:
        return str(Path(value).resolve().relative_to(root_resolved))
    except (OSError, ValueError):
        return value


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _is_indexable_path(path: str) -> bool:
    if not path or any(part in EXCLUDED_DIRS for part in Path(path).parts):
        return False
    return Path(path).suffix in SEARCH_EXTENSIONS

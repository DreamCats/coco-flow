from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
import subprocess

from .models import DesignInputBundle
from .utils import as_str_list, dedupe, dict_list, first_non_empty

_SEARCH_GLOBS = ("*.go", "*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.proto", "*.thrift", "*.sql")
_EXCLUDED_DIRS = {".git", ".livecoding", ".coco-flow", "node_modules", "dist", "build", "__pycache__"}
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


def build_research_plan(prepared: DesignInputBundle) -> dict[str, object]:
    terms = _extract_search_terms(prepared)
    questions = _default_questions(prepared)
    return {
        "repos": [
            {
                "repo_id": repo.repo_id,
                "repo_path": repo.repo_path,
                "questions": questions,
                "search_terms": terms,
                "preferred_paths": _preferred_paths(repo.repo_path),
                "budget": {"max_files_read": 12, "max_search_commands": 8},
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
            "budget_used": {"search_commands": 0, "files_read": 0},
        }

    terms = as_str_list(repo_plan.get("search_terms"))[: int(_budget(repo_plan, "max_search_commands", 8))]
    seen_files: dict[str, list[dict[str, object]]] = {}
    search_count = 0
    for term in terms:
        search_count += 1
        for match in _rg_matches(root, term):
            rel = match["path"]
            seen_files.setdefault(rel, []).append(match)

    max_files = int(_budget(repo_plan, "max_files_read", 12))
    ranked_files = _rank_candidate_files(seen_files)
    candidate_files = [item for item in ranked_files if bool(item.get("core_evidence"))][:max_files]
    related_files = [item for item in ranked_files if not bool(item.get("core_evidence"))][:max_files]
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

    confidence = "high" if len(candidate_files) >= 3 else "medium" if candidate_files else "low"
    return {
        "repo_id": repo_id,
        "repo_path": repo_path,
        "work_hypothesis": "requires_code_change" if candidate_files else "needs_human_confirmation",
        "confidence": confidence,
        "evidence": evidence,
        "candidate_files": candidate_files,
        "related_files": related_files,
        "boundaries": boundaries,
        "unknowns": [] if candidate_files else ["需要人工确认该仓是否承担核心改造，或补充更明确的搜索术语。"],
        "budget_used": {"search_commands": search_count, "files_read": len(candidate_files)},
    }


def build_research_summary(repo_research_payloads: list[dict[str, object]]) -> dict[str, object]:
    return {
        "repos": repo_research_payloads,
        "unknowns": [
            f"{repo.get('repo_id')}: {unknown}"
            for repo in repo_research_payloads
            for unknown in as_str_list(repo.get("unknowns"))
        ],
        "candidate_file_count": sum(len(dict_list(repo.get("candidate_files"))) for repo in repo_research_payloads),
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


def _rank_candidate_files(seen_files: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    ranked = sorted(seen_files.items(), key=lambda item: (-_evidence_score(item[0], item[1]), item[0]))
    return [
        {
            "path": path,
            "kind": "core_change",
            "confidence": "high" if _evidence_score(path, matches) >= 6 else "medium",
            "reason": _candidate_reason(path, matches),
            "scene": _path_scene(path),
            "symbol": _match_symbol(matches),
            "matched_behavior": _match_terms_text(matches),
            "why_core": "路径和多组需求术语共同命中，适合作为核心候选。" if _is_core_candidate(path, matches) else "",
            "core_evidence": _is_core_candidate(path, matches),
        }
        for path, matches in ranked
    ]


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


def _evidence_score(path: str, matches: list[dict[str, object]]) -> int:
    distinct_terms = {str(item.get("term") or "").lower() for item in matches if str(item.get("term") or "").strip()}
    path_parts = {part.lower() for part in Path(path).parts}
    score = len(matches) + len(distinct_terms) * 2
    if any(part in {"test", "tests", "__tests__"} for part in path_parts) or path.endswith(("_test.go", ".test.ts", ".spec.ts")):
        score -= 4
    if any(part in {"src", "pkg", "internal", "entities", "converters", "dal", "service", "api"} for part in path_parts):
        score += 2
    return score


def _is_core_candidate(path: str, matches: list[dict[str, object]]) -> bool:
    distinct_terms = {str(item.get("term") or "").lower() for item in matches if str(item.get("term") or "").strip()}
    if path.endswith(("_test.go", ".test.ts", ".spec.ts")):
        return False
    return _evidence_score(path, matches) >= 5 and len(distinct_terms) >= 2


def _candidate_reason(path: str, matches: list[dict[str, object]]) -> str:
    distinct_terms = {str(item.get("term") or "") for item in matches if str(item.get("term") or "").strip()}
    if _is_core_candidate(path, matches):
        return f"命中 {len(matches)} 条、{len(distinct_terms)} 组 refined scope 相关证据，且路径不像测试或生成产物。"
    return f"仅作为相关文件：命中 {len(matches)} 条、{len(distinct_terms)} 组证据，尚不足以证明需要修改。"


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


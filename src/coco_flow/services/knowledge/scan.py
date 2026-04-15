from __future__ import annotations

from pathlib import Path
import re
import subprocess

from .common import (
    ANCHOR_PATH_KEYWORDS,
    ROUTE_PATTERN,
    SEARCHABLE_SUFFIXES,
    SKIP_DIR_NAMES,
    SYMBOL_PATTERN,
    is_meaningful_term,
    normalize_match_text,
    split_match_tokens,
    unique_strings,
)


def find_repo_root(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def scan_candidate_files(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    matched_files: list[tuple[int, str]] = []
    matched_keywords: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 1600:
            break
        relative_path = str(path.relative_to(root))
        hits = matched_search_terms(relative_path, search_terms)
        if not hits:
            continue
        matched_files.append((score_path_signal(relative_path, hits), relative_path))
        matched_keywords.extend(hits)
    matched_files.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in matched_files[:24]], unique_strings(matched_keywords)


def scan_candidate_dirs(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    scored_dirs: dict[str, int] = {}
    matched_keywords: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 1200:
            break
        relative_path = Path(path.relative_to(root))
        for parent in relative_path.parents:
            current = str(parent)
            if current in {"", "."}:
                continue
            hits = matched_search_terms(current, search_terms)
            if not hits:
                continue
            scored_dirs[current] = max(scored_dirs.get(current, 0), score_path_signal(current, hits))
            matched_keywords.extend(hits)
    matched_dirs = [path for path, _ in sorted(scored_dirs.items(), key=lambda item: (-item[1], item[0]))]
    return matched_dirs[:16], unique_strings(matched_keywords)


def scan_route_hits(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    hits: list[tuple[int, str]] = []
    matched_keywords: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 240:
            break
        relative_path = str(path.relative_to(root))
        if not any(token in relative_path.lower() for token in ("router", "route", "handler", "api")):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for route in unique_strings(ROUTE_PATTERN.findall(content))[:24]:
            current_hits = matched_search_terms(route, search_terms)
            if not current_hits:
                continue
            rendered = f"{relative_path}#{route} 命中 {', '.join(current_hits[:3])}"
            hits.append((score_path_signal(relative_path, current_hits) + 6, rendered))
            matched_keywords.extend(current_hits)
    hits.sort(key=lambda item: (-item[0], item[1]))
    return [item for _, item in hits[:8]], unique_strings(matched_keywords)


def scan_symbol_hits(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    hits: list[tuple[int, str]] = []
    matched_keywords: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 180:
            break
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(content) > 120_000:
            content = content[:120_000]
        identifiers = unique_strings(SYMBOL_PATTERN.findall(content))[:120]
        for identifier in identifiers:
            current_hits = matched_search_terms(identifier, search_terms)
            if not current_hits:
                continue
            relative_path = str(path.relative_to(root))
            hits.append(
                (
                    score_symbol_signal(relative_path, identifier, current_hits),
                    f"{relative_path}#{identifier} 命中 {', '.join(current_hits[:3])}",
                )
            )
            matched_keywords.extend(current_hits)
    hits.sort(key=lambda item: (-item[0], item[1]))
    return [item for _, item in hits[:12]], unique_strings(matched_keywords)


def scan_recent_commit_hits(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    commit_titles = collect_recent_commit_terms(root, limit=20)
    hits: list[tuple[int, str]] = []
    matched_keywords: list[str] = []
    for title in commit_titles:
        current_hits = matched_search_terms(title, search_terms)
        if not current_hits:
            continue
        hits.append((score_commit_signal(title, current_hits), f"{title} 命中 {', '.join(current_hits[:3])}"))
        matched_keywords.extend(current_hits)
    hits.sort(key=lambda item: (-item[0], item[1]))
    return [item for _, item in hits[:6]], unique_strings(matched_keywords[:12])


def iter_repo_files(root: Path):
    for current_root, dirnames, filenames in root.walk():
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in SKIP_DIR_NAMES and not dirname.startswith(".")
        ]
        for filename in filenames:
            path = current_root / filename
            if path.suffix.lower() not in SEARCHABLE_SUFFIXES:
                continue
            yield path


def scan_context_hits(context_root: Path, search_terms: list[str]) -> list[str]:
    if not context_root.is_dir():
        return []
    hits: list[str] = []
    for path in sorted(context_root.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in SEARCHABLE_SUFFIXES:
            continue
        if len(hits) >= 6:
            break
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = content.lower()
        matched = [term for term in search_terms if term.lower() in lowered]
        if not matched:
            continue
        relative_path = str(path.relative_to(context_root))
        hits.append(f"{relative_path} 命中 {', '.join(unique_strings(matched)[:4])}")
    return hits


def collect_repo_file_terms(root: Path, limit: int = 24) -> list[str]:
    terms: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 180:
            break
        relative_path = str(path.relative_to(root))
        terms.extend(extract_path_terms(relative_path))
        if len(unique_strings(terms)) >= limit:
            break
    return [term for term in unique_strings(terms) if is_meaningful_term(term)][:limit]


def collect_repo_route_terms(root: Path, limit: int = 18) -> list[str]:
    terms: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 200:
            break
        relative_path = str(path.relative_to(root))
        if not any(token in relative_path.lower() for token in ("router", "route", "handler", "api")):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for route in unique_strings(ROUTE_PATTERN.findall(content))[:24]:
            for token in route.split("/"):
                if is_meaningful_term(token):
                    terms.append(token)
    return unique_strings(terms)[:limit]


def collect_context_aliases(root: Path, limit: int = 16) -> list[dict[str, list[str]]]:
    candidates = [
        root / ".livecoding" / "context",
        root / "AGENTS.md",
        root / "README.md",
        root / "README.zh-CN.md",
    ]
    aliases: list[dict[str, list[str]]] = []
    for candidate in candidates:
        if candidate.is_dir():
            paths = sorted(path for path in candidate.rglob("*") if path.is_file() and path.suffix.lower() in SEARCHABLE_SUFFIXES)
        elif candidate.is_file():
            paths = [candidate]
        else:
            continue
        for path in paths:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for line in lines[:120]:
                source_terms = unique_strings(re.findall(r"[\u4e00-\u9fff]{2,8}", line))
                repo_terms = unique_strings(
                    [
                        token
                        for token in re.findall(r"[A-Za-z0-9_/-]+", line)
                        if len(token) >= 2 and is_meaningful_term(token)
                    ]
                )
                if not source_terms or not repo_terms:
                    continue
                aliases.append({"source_terms": source_terms[:4], "repo_terms": repo_terms[:6]})
                if len(aliases) >= limit:
                    return aliases[:limit]
    return aliases[:limit]


def collect_repo_symbol_terms(root: Path, limit: int = 28) -> list[str]:
    terms: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 120:
            break
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(content) > 120_000:
            content = content[:120_000]
        for identifier in unique_strings(SYMBOL_PATTERN.findall(content)):
            if not is_meaningful_term(identifier):
                continue
            terms.append(identifier)
            if len(unique_strings(terms)) >= limit:
                return unique_strings(terms)[:limit]
    return unique_strings(terms)[:limit]


def collect_recent_commit_terms(root: Path, limit: int = 12) -> list[str]:
    git_dir = root / ".git"
    if not git_dir.exists():
        return []
    try:
        completed = subprocess.run(
            ["git", "log", "-n", str(max(limit, 20)), "--pretty=%s"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if completed.returncode != 0:
        return []
    titles = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return unique_strings(titles)[:limit]


def collect_recent_commit_keywords(root: Path, limit: int = 12) -> list[str]:
    keywords: list[str] = []
    for title in collect_recent_commit_terms(root, limit=max(limit, 20)):
        for token in extract_path_terms(title):
            if not is_meaningful_term(token):
                continue
            if token in {"merge", "branch", "master", "feat", "fix", "development", "task", "build", "pass"}:
                continue
            keywords.append(token)
            if len(unique_strings(keywords)) >= limit:
                return unique_strings(keywords)[:limit]
    return unique_strings(keywords)[:limit]


def extract_path_terms(relative_path: str) -> list[str]:
    parts = list(Path(relative_path).parts)
    stem = Path(relative_path).stem
    terms: list[str] = []
    for part in [*parts, stem]:
        terms.extend(split_match_tokens(part))
        if is_meaningful_term(part):
            terms.append(part)
    return unique_strings(terms)


def matched_search_terms(text: str, search_terms: list[str]) -> list[str]:
    matches: list[str] = []
    normalized_text = normalize_match_text(text)
    text_tokens = set(split_match_tokens(text))
    for term in search_terms:
        current = str(term).strip()
        normalized_term = normalize_match_text(current)
        if not normalized_term:
            continue
        if normalized_term in normalized_text or normalized_text in normalized_term:
            matches.append(current)
            continue
        term_tokens = set(split_match_tokens(current))
        if term_tokens and term_tokens & text_tokens:
            matches.append(current)
    return unique_strings(matches)


def score_path_signal(path: str, hits: list[str]) -> int:
    score = len(unique_strings(hits)) * 10
    lowered = path.lower()
    for keyword, bonus in ANCHOR_PATH_KEYWORDS.items():
        if keyword in lowered:
            score += bonus
    return score


def score_symbol_signal(path: str, identifier: str, hits: list[str]) -> int:
    from .common import split_match_tokens

    score = score_path_signal(path, hits) + len(split_match_tokens(identifier))
    lowered = identifier.lower()
    for keyword, bonus in ANCHOR_PATH_KEYWORDS.items():
        if keyword in lowered:
            score += bonus + 1
    if any(token in identifier for token in ("Request", "Response", "Service", "Handler", "Promotion", "FlashSale", "Exclusive")):
        score += 4
    return score


def score_commit_signal(title: str, hits: list[str]) -> int:
    score = len(unique_strings(hits)) * 4
    lowered = title.lower()
    if "rebuild" in lowered:
        score -= 3
    if "merge branch" in lowered:
        score -= 4
    if any(token in lowered for token in ("flash_sale", "creator", "promotion", "exclusive", "秒杀")):
        score += 2
    return score


def extract_repo_anchors(discovery: dict[str, object]) -> dict[str, list[str]]:
    candidate_files = [str(item) for item in discovery.get("candidate_files", [])]
    route_hits = [str(item) for item in discovery.get("route_hits", [])]
    symbol_hits = [str(item) for item in discovery.get("symbol_hits", [])]
    matched_keywords = [str(item) for item in discovery.get("matched_keywords", [])]
    entry_files = [
        path
        for path in candidate_files
        if any(token in path.lower() for token in ("router", "route", "handler", "service", "rpc"))
    ][:4]
    if not entry_files:
        entry_files = candidate_files[:4]
    business_symbols: list[str] = []
    for hit in symbol_hits:
        _, _, tail = hit.partition("#")
        identifier = tail.split(" 命中 ", 1)[0].strip()
        if not identifier:
            continue
        business_symbols.append(identifier)
    return {
        "entry_files": unique_strings(entry_files)[:4],
        "business_symbols": unique_strings([value for value in business_symbols if is_meaningful_term(value)])[:6],
        "route_signals": unique_strings(route_hits)[:4],
        "keywords": unique_strings([value for value in matched_keywords if is_meaningful_term(value)])[:6],
    }


def derive_modules_from_entry_files(entry_files: list[str]) -> list[str]:
    modules: list[str] = []
    for raw_path in entry_files:
        parent = str(Path(raw_path).parent)
        if parent in {"", "."}:
            continue
        modules.append(parent)
    return unique_strings(modules)


def select_core_route_signals(route_signals: list[str], intent_payload: dict[str, object]) -> list[str]:
    scored: list[tuple[int, str]] = []
    intent_text = " ".join([str(intent_payload.get("title") or ""), str(intent_payload.get("description") or "")]).lower()
    has_business_prefix = any(any(token in str(signal).lower() for token in ("/flash_sale", "/live_promotion")) for signal in route_signals)
    for signal in route_signals:
        current = str(signal).strip()
        lowered = current.lower()
        score = 0
        if "/flash_sale" in lowered or "/live_promotion" in lowered:
            score += 8
        if any(token in lowered for token in ("/create", "/update", "/launch", "/deactivate", "/delete", "/status")):
            score += 5
        if has_business_prefix and not any(token in lowered for token in ("/flash_sale", "/live_promotion")):
            score -= 8
        if "/operate" in lowered:
            score -= 6
        if "/save_template" in lowered or "/template" in lowered:
            score -= 12
        if "启动" in intent_text and any(token in lowered for token in ("/launch", "/status")):
            score += 2
        if "更新" in intent_text and "/update" in lowered:
            score += 2
        if "删除" in intent_text and any(token in lowered for token in ("/delete", "/deactivate")):
            score += 2
        scored.append((score, current))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [value for score, value in scored if score > 0][:3]
    if selected:
        return unique_strings(selected)
    return unique_strings(route_signals[:2])


def rank_likely_modules(candidate_dirs: list[str], anchors: dict[str, list[str]], discovery: dict[str, object]) -> list[str]:
    strongest_terms = [str(item).lower() for item in anchors.get("keywords", [])]
    entry_modules = derive_modules_from_entry_files(anchors.get("entry_files", []))
    scored: dict[str, int] = {}
    for module in candidate_dirs:
        lowered = module.lower()
        score = 0
        if module in entry_modules:
            score += 12
        if any(term and term.replace("_", "").lower() in lowered.replace("_", "") for term in strongest_terms):
            score += 6
        if any(token in lowered for token in ("router", "route", "handler", "service", "rpc", "flash_sale", "promotion")):
            score += 4
        if any(token in lowered for token in ("billboard", "flow_task", "packer", "archive", "openspec", "specs", "developing")):
            score -= 6
        scored[module] = score
    ranked = [value for value, _ in sorted(scored.items(), key=lambda item: (-item[1], item[0]))]
    return unique_strings([*entry_modules, *ranked])


def extract_discarded_noise(discovery: dict[str, object], strongest_terms: list[str]) -> list[str]:
    strongest = {str(item).lower() for item in strongest_terms}
    noise: list[str] = []
    for source in (discovery.get("commit_keywords", []), discovery.get("matched_keywords", [])):
        for item in source:
            current = str(item).strip()
            lowered = current.lower()
            if not current or lowered in strongest:
                continue
            if any(token in lowered for token in ("rebuild", "merge", "pack", "flow", "mw", "middleware", "pipeline")):
                noise.append(current)
    for path in discovery.get("candidate_files", []):
        current = str(path).strip()
        lowered = current.lower()
        if any(token in lowered for token in ("openspec/", "/spec.", "archive/", "readme", "build.sh")):
            noise.append(current)
    return unique_strings(noise)[:6]


def list_top_level_dirs(root: Path) -> list[str]:
    directories = [
        item.name
        for item in sorted(root.iterdir())
        if item.is_dir() and item.name not in SKIP_DIR_NAMES and not item.name.startswith(".")
    ]
    return directories[:6]

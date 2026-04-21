from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess

from .plan_models import (
    ComplexityAssessment,
    ComplexityDimension,
    ContextSnapshot,
    DesignResearchSignals,
    GlossaryEntry,
    RefinedSections,
    RepoResearch,
    RepoScope,
    ResearchFinding,
)

PLAN_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
DEFAULT_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "prd",
    "refined",
    "md",
    "ok",
    "no",
    "yes",
    "na",
}
SEARCH_FILE_GLOBS = (
    "*.go",
    "*.py",
    "*.ts",
    "*.tsx",
    "*.js",
    "*.jsx",
    "*.proto",
    "*.thrift",
    "*.sql",
)
SEARCH_EXCLUDED_PREFIXES = (
    ".git/",
    ".livecoding/",
    "node_modules/",
    "dist/",
    ".coco-flow/",
)
MAX_SEARCH_FILES = 8
MAX_UNMATCHED_TERMS = 10


def describe_repos(repos_meta: dict[str, object]) -> list[str]:
    repos = repos_meta.get("repos")
    if not isinstance(repos, list):
        return []
    lines: list[str] = []
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo_id = str(repo.get("id") or "repo")
        repo_path = str(repo.get("path") or "-")
        lines.append(f"- {repo_id} ({repo_path})")
    return lines


def parse_repo_scopes(repos_meta: dict[str, object]) -> list[RepoScope]:
    repos = repos_meta.get("repos")
    if not isinstance(repos, list):
        return []
    scopes: list[RepoScope] = []
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo_id = str(repo.get("id") or "repo").strip() or "repo"
        repo_path = str(repo.get("path") or "").strip()
        if not repo_path:
            continue
        scopes.append(RepoScope(repo_id=repo_id, repo_path=repo_path))
    return scopes


def build_repo_researches(repo_scopes: list[RepoScope], title: str, sections: RefinedSections) -> list[RepoResearch]:
    researches: list[RepoResearch] = []
    for scope in repo_scopes:
        context = load_optional_context_snapshot(scope.repo_path)
        finding = research_codebase(scope.repo_path, title, sections, context)
        researches.append(
            RepoResearch(
                repo_id=scope.repo_id,
                repo_path=scope.repo_path,
                context=context,
                finding=finding,
            )
        )
    return researches


def combine_context_snapshots(repo_researches: list[RepoResearch]) -> ContextSnapshot:
    if not repo_researches:
        return ContextSnapshot(
            available=False,
            glossary_entries=[],
            missing_files=["glossary.md", "architecture.md", "patterns.md"],
        )

    glossary_sections: list[str] = []
    architecture_sections: list[str] = []
    patterns_sections: list[str] = []
    gotchas_sections: list[str] = []
    glossary_entries: list[GlossaryEntry] = []
    missing_files: list[str] = []
    available = False

    for repo in repo_researches:
        context = repo.context
        available = available or context.available
        if context.glossary_excerpt:
            glossary_sections.extend([f"### repo: {repo.repo_id}", context.glossary_excerpt])
        if context.architecture_excerpt:
            architecture_sections.extend([f"### repo: {repo.repo_id}", context.architecture_excerpt])
        if context.patterns_excerpt:
            patterns_sections.extend([f"### repo: {repo.repo_id}", context.patterns_excerpt])
        if context.gotchas_excerpt:
            gotchas_sections.extend([f"### repo: {repo.repo_id}", context.gotchas_excerpt])
        glossary_entries.extend(context.glossary_entries or [])
        for name in context.missing_files or []:
            missing_files.append(f"{repo.repo_id}/{name}")

    return ContextSnapshot(
        available=available,
        glossary_excerpt="\n".join(glossary_sections).strip(),
        architecture_excerpt="\n".join(architecture_sections).strip(),
        patterns_excerpt="\n".join(patterns_sections).strip(),
        gotchas_excerpt="\n".join(gotchas_sections).strip(),
        glossary_entries=dedupe_glossary_entries(glossary_entries),
        missing_files=dedupe_and_sort(missing_files),
    )


def combine_research_findings(repo_researches: list[RepoResearch], repo_count: int) -> ResearchFinding:
    matched_terms: list[GlossaryEntry] = []
    unmatched_terms: list[str] = []
    candidate_files: list[str] = []
    candidate_dirs: list[str] = []
    notes: list[str] = []

    for repo in repo_researches:
        matched_terms.extend(repo.finding.matched_terms)
        unmatched_terms.extend(repo.finding.unmatched_terms)
        qualified_files = [qualify_repo_path(repo.repo_id, file_path, repo_count) for file_path in repo.finding.candidate_files]
        qualified_dirs = [qualify_repo_path(repo.repo_id, dir_path, repo_count) for dir_path in repo.finding.candidate_dirs]
        candidate_files.extend(qualified_files)
        candidate_dirs.extend(qualified_dirs)
        notes.extend(f"[{repo.repo_id}] {note}" for note in repo.finding.notes)

    return ResearchFinding(
        matched_terms=dedupe_glossary_entries(matched_terms),
        unmatched_terms=dedupe_terms(unmatched_terms)[:MAX_UNMATCHED_TERMS],
        candidate_files=dedupe_and_sort(candidate_files)[: max(MAX_SEARCH_FILES, repo_count * 4 or MAX_SEARCH_FILES)],
        candidate_dirs=dedupe_and_sort(candidate_dirs),
        notes=notes,
    )


def build_design_research_signals(repo_researches: list[RepoResearch], sections: RefinedSections) -> DesignResearchSignals:
    system_summaries: list[str] = []
    system_dependencies: list[str] = []
    critical_flows: list[str] = []
    protocol_changes: list[str] = []
    storage_config_changes: list[str] = []
    experiment_changes: list[str] = []
    qa_inputs: list[str] = []

    previous_repo = ""
    for repo in repo_researches:
        candidate_dirs = repo.finding.candidate_dirs[:3]
        candidate_files = repo.finding.candidate_files[:3]
        primary_scope = sections.change_scope[0] if sections.change_scope else "当前需求改动"
        dir_summary = "、".join(candidate_dirs) if candidate_dirs else "仓库根目录"
        if repo.finding.matched_terms:
            term_summary = "、".join(entry.business for entry in repo.finding.matched_terms[:2])
            system_summaries.append(
                f"仓库 {repo.repo_id} 主要承接「{primary_scope}」相关改动，重点范围在 {dir_summary}，术语命中 {term_summary}。"
            )
        else:
            system_summaries.append(f"仓库 {repo.repo_id} 主要承接「{primary_scope}」相关改动，重点范围在 {dir_summary}。")

        if previous_repo:
            system_dependencies.append(f"建议先完成 {previous_repo} 的主改动，再推进 {repo.repo_id} 的联动收口。")
        else:
            system_dependencies.append(f"{repo.repo_id} 可作为起始仓库先行推进。")
        previous_repo = repo.repo_id

        if candidate_files:
            first_file = candidate_files[0]
            critical_flows.append(f"在 {repo.repo_id} 中，主链路优先从 {first_file} 所在路径收敛，再确认上下游联动。")
        if repo.finding.notes:
            critical_flows.extend(f"[{repo.repo_id}] {note}" for note in repo.finding.notes[:2])

        protocol_candidates = [
            file_path
            for file_path in candidate_files
            if file_path.endswith((".proto", ".thrift")) or "/handler/" in file_path or "/api/" in file_path
        ]
        if protocol_candidates:
            protocol_changes.append(
                f"{repo.repo_id} 检测到接口或协议边界变更信号，重点确认 {', '.join(protocol_candidates[:3])} 的上下游兼容性。"
            )

        storage_candidates = [
            file_path
            for file_path in candidate_files
            if any(keyword in file_path.lower() for keyword in ("config", "dao", "repo", "model", "store", "cache"))
        ]
        if storage_candidates:
            storage_config_changes.append(
                f"{repo.repo_id} 检测到存储或配置变更信号，重点确认 {', '.join(storage_candidates[:3])} 的默认行为和回滚方式。"
            )

        experiment_candidates = [
            file_path
            for file_path in candidate_files
            if any(keyword in file_path.lower() for keyword in ("ab", "experiment", "grey", "gray", "feature", "switch"))
        ]
        if experiment_candidates:
            experiment_changes.append(
                f"{repo.repo_id} 检测到实验或开关变更信号，重点确认 {', '.join(experiment_candidates[:3])} 的生效范围。"
            )

    joined_sections = "\n".join([*sections.change_scope, *sections.key_constraints, *sections.open_questions])
    if contains_any(joined_sections, "协议", "接口", "rpc", "字段", "请求", "返回") and not protocol_changes:
        protocol_changes.append("需求描述中存在协议或字段变更信号，需要重点确认上下游兼容性。")
    if contains_any(joined_sections, "数据库", "配置", "缓存", "tcc", "持久化", "状态") and not storage_config_changes:
        storage_config_changes.append("需求描述中存在存储或配置层变更信号，需要确认上线和回滚策略。")
    if contains_any(joined_sections, "实验", "灰度", "开关", "ab", "bucket") and not experiment_changes:
        experiment_changes.append("需求描述中存在实验或灰度开关信号，需要确认流量范围和回滚策略。")

    if sections.acceptance_criteria:
        qa_inputs.extend(f"主链路验证：{item}" for item in sections.acceptance_criteria[:4])
    if sections.key_constraints:
        qa_inputs.extend(f"关键约束校验：{item}" for item in sections.key_constraints[:4])
    if sections.non_goals:
        qa_inputs.extend(f"非目标回归：重点确认 {item}" for item in sections.non_goals[:3])
    if sections.open_questions:
        qa_inputs.extend(f"待确认项：{item}" for item in sections.open_questions[:4])

    return DesignResearchSignals(
        system_summaries=dedupe_terms(system_summaries),
        system_dependencies=dedupe_terms(system_dependencies),
        critical_flows=dedupe_terms(critical_flows),
        protocol_changes=dedupe_terms(protocol_changes),
        storage_config_changes=dedupe_terms(storage_config_changes),
        experiment_changes=dedupe_terms(experiment_changes),
        qa_inputs=dedupe_terms(qa_inputs),
    )


def qualify_repo_path(repo_id: str, path: str, repo_count: int) -> str:
    normalized = path.strip().lstrip("./")
    if not normalized:
        return normalized
    if repo_count <= 1:
        return normalized
    return f"{repo_id}/{normalized}"


def dedupe_glossary_entries(entries: list[GlossaryEntry]) -> list[GlossaryEntry]:
    seen: set[tuple[str, str, str]] = set()
    result: list[GlossaryEntry] = []
    for entry in entries:
        key = (entry.business.lower(), entry.identifier.lower(), entry.module.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def load_optional_context_snapshot(repo_root: str | None) -> ContextSnapshot:
    if not repo_root:
        return ContextSnapshot(
            available=False,
            glossary_entries=[],
            missing_files=["glossary.md", "architecture.md", "patterns.md"],
        )

    context_dir = Path(repo_root) / ".livecoding" / "context"
    missing: list[str] = []
    contents: dict[str, str] = {}
    for name in ("glossary.md", "architecture.md", "patterns.md", "gotchas.md"):
        path = context_dir / name
        if not path.exists():
            missing.append(name)
            continue
        try:
            contents[name] = path.read_text()
        except OSError:
            missing.append(name)

    glossary_content = contents.get("glossary.md", "")
    return ContextSnapshot(
        available=bool(contents),
        glossary_excerpt=excerpt_context(glossary_content),
        architecture_excerpt=excerpt_context(contents.get("architecture.md", "")),
        patterns_excerpt=excerpt_context(contents.get("patterns.md", "")),
        gotchas_excerpt=excerpt_context(contents.get("gotchas.md", "")),
        glossary_entries=parse_glossary_entries(glossary_content),
        missing_files=missing,
    )


def parse_glossary_entries(content: str) -> list[GlossaryEntry]:
    entries: list[GlossaryEntry] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        if "---" in line or "业务术语" in line:
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 4:
            continue
        business, identifier, _, module = parts[:4]
        if not business or not identifier:
            continue
        entries.append(GlossaryEntry(business=business, identifier=identifier, module=module))
    return entries


def parse_refined_sections(content: str) -> RefinedSections:
    sections = split_markdown_sections(content)
    return RefinedSections(
        change_scope=_combine_section_items(
            sections.get("核心诉求", ""),
            sections.get("改动范围", ""),
            sections.get("变更范围", ""),
            sections.get("需求概述", ""),
            sections.get("具体变更点", ""),
            sections.get("功能点", ""),
        ),
        non_goals=_combine_section_items(
            sections.get("边界与非目标", ""),
            sections.get("非目标", ""),
            sections.get("边界条件", ""),
        ),
        key_constraints=_combine_section_items(
            sections.get("风险提示", ""),
            sections.get("关键约束", ""),
            sections.get("业务规则", ""),
        ),
        acceptance_criteria=_combine_section_items(sections.get("验收标准", "")),
        open_questions=_combine_section_items(
            sections.get("讨论点", ""),
            sections.get("待确认项", ""),
            sections.get("待确认问题", ""),
        ),
        raw=content.strip(),
    )


def split_markdown_sections(content: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = ""
    current_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(current_lines).strip()
            current = line.removeprefix("## ").strip()
            current_lines = []
            continue
        if current:
            current_lines.append(line)
    if current:
        sections[current] = "\n".join(current_lines).strip()
    return sections


def clean_section_lines(section: str) -> str:
    lines = extract_bullet_items(section)
    if not lines:
        return section.strip()
    return "；".join(lines)


def extract_bullet_items(section: str) -> list[str]:
    items: list[str] = []
    for line in section.splitlines():
        current = re.sub(r"^(\d+\.\s*|[-*]\s*)", "", line.strip())
        if current:
            items.append(current)
    return items


def _combine_section_items(*parts: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for part in parts:
        extracted = extract_bullet_items(part)
        if not extracted and part.strip():
            extracted = [part.strip()]
        for item in extracted:
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            items.append(item)
    return items


def research_codebase(
    repo_root: str | None,
    title: str,
    sections: RefinedSections,
    context: ContextSnapshot,
) -> ResearchFinding:
    if not repo_root:
        return ResearchFinding(
            matched_terms=[],
            unmatched_terms=[],
            candidate_files=[],
            candidate_dirs=[],
            notes=["当前未绑定可调研的 repo root。"],
        )

    search_text = "\n".join(
        [
            title,
            "\n".join(sections.change_scope),
            "\n".join(sections.key_constraints),
            "\n".join(sections.acceptance_criteria),
        ]
    )
    matched_terms = [
        entry
        for entry in context.glossary_entries or []
        if contains_any(search_text, entry.business, entry.identifier)
    ]
    unmatched_terms = infer_unmatched_terms(search_text, matched_terms)
    search_terms = infer_search_terms(title, sections, matched_terms)
    candidate_files = find_candidate_files(repo_root, matched_terms, search_terms)
    if not candidate_files:
        candidate_files = heuristic_candidate_files(repo_root, search_terms)
    candidate_dirs = summarize_dirs(candidate_files)

    notes: list[str] = []
    if not matched_terms:
        notes.append("未在 glossary 中命中明显术语，调研可信度较低。")
    if not candidate_files:
        notes.append("未通过现有术语映射找到候选代码文件。")
    if sections.open_questions:
        notes.append(f"存在 {len(sections.open_questions)} 个待确认问题，说明需求仍有不确定性。")
    if search_terms:
        notes.append(f"命中检索词: {', '.join(search_terms[:8])}")
    return ResearchFinding(
        matched_terms=matched_terms,
        unmatched_terms=unmatched_terms,
        candidate_files=candidate_files,
        candidate_dirs=candidate_dirs,
        notes=notes,
    )


def infer_unmatched_terms(search_text: str, matched: list[GlossaryEntry]) -> list[str]:
    terms: list[str] = []
    for token in PLAN_ASCII_WORD_RE.findall(search_text):
        lower = token.lower().strip()
        if len(lower) < 3 or lower in DEFAULT_STOPWORDS:
            continue
        if matched_contains_identifier(matched, token):
            continue
        terms.append(token)
    return dedupe_terms(terms)[:MAX_UNMATCHED_TERMS]


def infer_search_terms(title: str, sections: RefinedSections, matched: list[GlossaryEntry]) -> list[str]:
    source_text = "\n".join(
        [
            title,
            "\n".join(sections.change_scope),
            "\n".join(sections.non_goals),
            "\n".join(sections.key_constraints),
            "\n".join(sections.acceptance_criteria),
        ]
    )
    terms = [item for entry in matched for item in (entry.business, entry.identifier)]
    for token in PLAN_ASCII_WORD_RE.findall(source_text):
        lowered = token.lower().strip()
        if lowered in DEFAULT_STOPWORDS:
            continue
        terms.append(lowered)
    return dedupe_and_sort(terms)


def matched_contains_identifier(entries: list[GlossaryEntry], keyword: str) -> bool:
    lower = keyword.lower()
    return any(lower in {entry.identifier.lower(), entry.business.lower()} for entry in entries)


def contains_any(text: str, *keywords: str) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def find_candidate_files(repo_root: str, matched: list[GlossaryEntry], terms: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for entry in matched:
        for term in (entry.identifier, entry.business):
            for file_path in search_files(repo_root, term):
                if file_path in seen:
                    continue
                seen.add(file_path)
                result.append(file_path)
                if len(result) >= MAX_SEARCH_FILES:
                    return sorted(result)

    for term in terms:
        for file_path in search_files(repo_root, term):
            if file_path in seen:
                continue
            seen.add(file_path)
            result.append(file_path)
            if len(result) >= MAX_SEARCH_FILES:
                return sorted(result)
    return sorted(result)


def search_files(repo_root: str, term: str) -> list[str]:
    term = term.strip()
    if not term:
        return []

    files = run_rg_search(repo_root, term)
    if len(files) < 3:
        lower_term = term.lower()
        for file_path in list_repo_files(repo_root):
            if lower_term in file_path.lower():
                files.append(file_path)
    return dedupe_and_sort(files)


def heuristic_candidate_files(repo_root: str, search_terms: list[str]) -> list[str]:
    scored: list[tuple[int, str]] = []
    for file_path in list_repo_files(repo_root):
        lower_path = file_path.lower()
        score = sum(1 for term in search_terms if term and term.lower() in lower_path)
        if score > 0:
            scored.append((score, file_path))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored[:MAX_SEARCH_FILES]]


def run_rg_search(repo_root: str, term: str) -> list[str]:
    command = ["rg", "--files-with-matches"]
    for pattern in SEARCH_FILE_GLOBS:
        command.extend(["--glob", pattern])
    command.extend([term, "."])
    result = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        return []
    return normalize_repo_files(result.stdout.splitlines())


def list_repo_files(repo_root: str) -> list[str]:
    command = ["rg", "--files", "."]
    for pattern in SEARCH_FILE_GLOBS:
        command.extend(["--glob", pattern])
    result = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return normalize_repo_files(result.stdout.splitlines())


def normalize_repo_files(lines: list[str]) -> list[str]:
    files: list[str] = []
    for line in lines:
        current = line.strip()
        if not current:
            continue
        if current.startswith("./"):
            current = current[2:]
        if any(current.startswith(prefix) for prefix in SEARCH_EXCLUDED_PREFIXES):
            continue
        files.append(current)
    return dedupe_and_sort(files)


def dedupe_terms(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(item)
    return result


def dedupe_and_sort(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        current = item.strip()
        if not current:
            continue
        lowered = current.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(current)
    return sorted(result)


def summarize_dirs(files: list[str]) -> list[str]:
    seen: set[str] = set()
    dirs: list[str] = []
    for file_path in files:
        directory = str(Path(file_path).parent)
        if directory == "." or directory in seen:
            continue
        seen.add(directory)
        dirs.append(directory)
    return sorted(dirs)


def has_path_keyword(files: list[str], *keywords: str) -> bool:
    return any(keyword in file_path for file_path in files for keyword in keywords if keyword)


def score_complexity(sections: RefinedSections, findings: ResearchFinding) -> ComplexityAssessment:
    dimensions: list[ComplexityDimension] = []

    file_count = len(findings.candidate_files)
    scope_score = 0
    scope_reason = "候选改动文件较少，范围集中。"
    if file_count > 5:
        scope_score = 2
        scope_reason = "候选改动文件超过 5 个，范围偏大。"
    elif file_count > 2:
        scope_score = 1
        scope_reason = "候选改动文件在 3-5 个之间，范围中等。"
    dimensions.append(ComplexityDimension("改动范围", scope_score, scope_reason))

    interface_score = 0
    interface_reason = "未发现明显的接口或协议变更信号。"
    if contains_any(
        "\n".join([*sections.change_scope, *sections.key_constraints, *sections.acceptance_criteria]),
        "接口",
        "协议",
        "请求",
        "返回",
        "字段",
        "rpc",
    ):
        interface_score = 1
        interface_reason = "需求描述中包含接口/字段类变更信号。"
    if has_path_keyword(findings.candidate_files, "handler", ".proto", ".thrift"):
        interface_score = 2
        interface_reason = "候选文件涉及 handler/IDL，可能影响对外接口。"
    dimensions.append(ComplexityDimension("接口协议", interface_score, interface_reason))

    data_score = 0
    data_reason = "未发现复杂数据或持久化变更。"
    if contains_any(
        "\n".join([*sections.non_goals, *sections.key_constraints]),
        "状态",
        "缓存",
        "数据库",
        "表",
        "持久化",
        "配置",
        "tcc",
    ):
        data_score = 1
        data_reason = "边界条件中出现状态/数据类描述。"
    if contains_any("\n".join(sections.key_constraints), "状态流转", "一致性", "数据同步"):
        data_score = 2
        data_reason = "业务规则暗示存在复杂状态流转或一致性要求。"
    dimensions.append(ComplexityDimension("数据状态", data_score, data_reason))

    question_count = len(sections.open_questions)
    rule_score = 0
    rule_reason = "业务规则相对清晰。"
    if question_count > 5:
        rule_score = 2
        rule_reason = "待确认问题较多，业务规则仍不清晰。"
    elif question_count > 2:
        rule_score = 1
        rule_reason = "存在少量待确认问题，需要人工确认。"
    dimensions.append(ComplexityDimension("规则清晰度", rule_score, rule_reason))

    dependency_score = 0
    dependency_reason = "候选目录较集中，依赖面可控。"
    if len(findings.candidate_dirs) > 2:
        dependency_score = 2
        dependency_reason = "候选目录跨多个模块，可能需要跨模块协作。"
    elif len(findings.candidate_dirs) > 1:
        dependency_score = 1
        dependency_reason = "候选目录跨两个模块，存在一定依赖关系。"
    dimensions.append(ComplexityDimension("依赖联动", dependency_score, dependency_reason))

    verify_score = 0
    verify_reason = "需求较易验证。"
    if len(findings.unmatched_terms) > 2:
        verify_score = 1
        verify_reason = "存在 glossary 未命中的术语，调研结果需要额外验证。"
    if not findings.candidate_files:
        verify_score = 2
        verify_reason = "未找到候选文件，当前无法形成可靠实现方案。"
    dimensions.append(ComplexityDimension("验证风险", verify_score, verify_reason))

    total = sum(item.score for item in dimensions)
    level = "简单"
    conclusion = "复杂度较低，可以进入详细编码计划阶段。"
    if total > 6:
        level = "复杂"
        conclusion = "复杂度超过阈值，建议先人工拆解或补充上下文，不直接进入自动实现。"
    elif total > 4:
        level = "中等"
        conclusion = "复杂度中等，可以生成计划，但需重点关注风险与待确认项。"

    return ComplexityAssessment(dimensions=dimensions, total=total, level=level, conclusion=conclusion)


def excerpt_context(content: str, limit: int = 800) -> str:
    normalized = content.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text()

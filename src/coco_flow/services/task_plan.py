from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import os
import re
import subprocess
from typing import Callable

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings, load_settings
from coco_flow.services.task_detail import read_json_file
from coco_flow.services.task_refine import locate_task_dir

STATUS_INITIALIZED = "initialized"
STATUS_REFINED = "refined"
STATUS_PLANNING = "planning"
STATUS_PLANNED = "planned"
STATUS_FAILED = "failed"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"

PLAN_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
SECTION_MARKERS = {
    "summary": "=== IMPLEMENTATION SUMMARY ===",
    "candidate_files": "=== CANDIDATE FILES ===",
    "steps": "=== IMPLEMENTATION STEPS ===",
    "risks": "=== RISK NOTES ===",
    "validation_extra": "=== VALIDATION EXTRA ===",
}
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

LogHandler = Callable[[str], None]


@dataclass
class PlanAISections:
    summary: str = ""
    candidate_files: str = ""
    steps: str = ""
    risks: str = ""
    validation_extra: str = ""


@dataclass
class GlossaryEntry:
    business: str
    identifier: str
    module: str


@dataclass
class RefinedSections:
    summary: str
    features: list[str]
    boundaries: list[str]
    business_rules: list[str]
    open_questions: list[str]
    raw: str


@dataclass
class ContextSnapshot:
    available: bool
    glossary_excerpt: str = ""
    architecture_excerpt: str = ""
    patterns_excerpt: str = ""
    gotchas_excerpt: str = ""
    glossary_entries: list[GlossaryEntry] | None = None
    missing_files: list[str] | None = None


@dataclass
class ResearchFinding:
    matched_terms: list[GlossaryEntry]
    unmatched_terms: list[str]
    candidate_files: list[str]
    candidate_dirs: list[str]
    notes: list[str]


@dataclass
class ComplexityDimension:
    name: str
    score: int
    reason: str


@dataclass
class ComplexityAssessment:
    dimensions: list[ComplexityDimension]
    total: int
    level: str
    conclusion: str


@dataclass
class PlanTask:
    id: str
    title: str
    goal: str
    depends_on: list[str]
    files: list[str]
    input: list[str]
    output: list[str]
    actions: list[str]
    done: list[str]


@dataclass
class RepoScope:
    repo_id: str
    repo_path: str


@dataclass
class RepoResearch:
    repo_id: str
    repo_path: str
    context: ContextSnapshot
    finding: ResearchFinding


@dataclass
class PlanBuild:
    task_id: str
    title: str
    source_value: str
    source_markdown: str
    refined_markdown: str
    repo_lines: list[str]
    repo_scopes: list[RepoScope]
    repo_researches: list[RepoResearch]
    repo_ids: set[str]
    repo_root: str | None
    context: ContextSnapshot
    sections: RefinedSections
    finding: ResearchFinding
    assessment: ComplexityAssessment


def plan_task(task_id: str, settings: Settings | None = None, on_log: LogHandler | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {STATUS_REFINED, STATUS_PLANNED, STATUS_PLANNING, STATUS_FAILED}:
        raise ValueError(f"task status {status} does not allow plan")

    logger = on_log or (lambda line: append_plan_log(task_dir, line))
    owns_log_lifecycle = on_log is None
    started_at = datetime.now().astimezone()
    if owns_log_lifecycle:
        logger("=== PLAN START ===")
        logger(f"task_id: {task_id}")
        logger(f"task_dir: {task_dir}")
        logger(f"executor: {cfg.plan_executor}")

    try:
        return _plan_task_impl(task_dir, task_meta, cfg, logger)
    except Exception as error:
        if owns_log_lifecycle:
            logger(f"error: {error}")
            logger(f"status: {STATUS_FAILED}")
        raise
    finally:
        if owns_log_lifecycle:
            duration = datetime.now().astimezone() - started_at
            logger(f"duration: {round(duration.total_seconds(), 3)}s")
            logger("=== PLAN END ===")


def _plan_task_impl(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    on_log: LogHandler,
) -> str:
    executor = settings.plan_executor.strip().lower()
    if executor == EXECUTOR_NATIVE:
        return plan_task_native(task_dir, task_meta, settings, on_log=on_log)
    if executor == EXECUTOR_LOCAL:
        return plan_task_local(task_dir, task_meta, on_log=on_log)
    raise ValueError(f"unknown plan executor: {settings.plan_executor}")


def start_planning_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {STATUS_REFINED, STATUS_PLANNED, STATUS_FAILED}:
        raise ValueError(f"task status {status} does not allow plan")

    _update_task_status(task_dir, task_meta, STATUS_PLANNING)
    return STATUS_PLANNING


def mark_task_failed(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    _update_task_status(task_dir, task_meta, STATUS_FAILED)
    return STATUS_FAILED


def plan_task_local(task_dir: Path, task_meta: dict[str, object], on_log: LogHandler) -> str:
    build = prepare_plan_build(task_dir, task_meta)
    log_plan_research(build, on_log)
    on_log("fallback_local_plan: true")
    design = build_design(build, ai=None)
    plan = build_plan(build, ai=None)

    (task_dir / "design.md").write_text(design)
    (task_dir / "plan.md").write_text(plan)
    on_log(f"status: {STATUS_PLANNED}")

    _update_task_status(task_dir, task_meta, STATUS_PLANNED)
    sync_repo_statuses(task_dir, STATUS_PLANNED)
    return STATUS_PLANNED


def plan_task_native(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    on_log: LogHandler,
) -> str:
    build = prepare_plan_build(task_dir, task_meta)
    log_plan_research(build, on_log)
    on_log("generator_mode: explorer(readonly)")
    on_log(f"prompt_start: timeout={settings.native_query_timeout}")

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    try:
        raw = client.run_readonly_agent(
            build_plan_prompt(build),
            settings.native_query_timeout,
            build.repo_root or os.getcwd(),
        )
    except ValueError as error:
        on_log(f"generate_plan_with_native_error: {error}")
        return plan_task_local(task_dir, task_meta, on_log=on_log)

    on_log(f"prompt_ok: {len(raw)} bytes")
    ai_sections, ok = extract_plan_outputs(raw)
    if not ok:
        on_log("parse_plan_output_error: missing required marker sections")
        return plan_task_local(task_dir, task_meta, on_log=on_log)
    validate_plan_outputs(build, ai_sections)

    ai_files = parse_ai_candidate_files(ai_sections.candidate_files, build)
    if ai_files:
        build.finding.candidate_files = ai_files
        build.finding.candidate_dirs = summarize_dirs(ai_files)
        build.assessment = score_complexity(build.sections, build.finding)
        on_log(f"candidate_files_override: {len(ai_files)}")
        on_log(f"complexity_after_ai: {build.assessment.level} ({build.assessment.total})")

    design = build_design(build, ai=ai_sections)
    plan = build_plan(build, ai=ai_sections)

    (task_dir / "design.md").write_text(design)
    (task_dir / "plan.md").write_text(plan)
    on_log(f"status: {STATUS_PLANNED}")

    _update_task_status(task_dir, task_meta, STATUS_PLANNED)
    sync_repo_statuses(task_dir, STATUS_PLANNED)
    return STATUS_PLANNED


def prepare_plan_build(task_dir: Path, task_meta: dict[str, object]) -> PlanBuild:
    task_id = task_dir.name
    title = str(task_meta.get("title") or task_id)
    source_value = str(task_meta.get("source_value") or "")
    source_markdown = read_text_if_exists(task_dir / "prd.source.md")
    refined_markdown = read_text_if_exists(task_dir / "prd-refined.md")
    repos_meta = read_json_file(task_dir / "repos.json")
    repo_lines = describe_repos(repos_meta)
    sections = parse_refined_sections(refined_markdown)
    repo_scopes = parse_repo_scopes(repos_meta)
    repo_researches = build_repo_researches(repo_scopes, title, sections)
    repo_root = repo_scopes[0].repo_path if repo_scopes else None
    context = combine_context_snapshots(repo_researches)
    finding = combine_research_findings(repo_researches, len(repo_scopes))
    assessment = score_complexity(sections, finding)
    return PlanBuild(
        task_id=task_id,
        title=title,
        source_value=source_value,
        source_markdown=source_markdown,
        refined_markdown=refined_markdown,
        repo_lines=repo_lines,
        repo_scopes=repo_scopes,
        repo_researches=repo_researches,
        repo_ids={scope.repo_id for scope in repo_scopes},
        repo_root=repo_root,
        context=context,
        sections=sections,
        finding=finding,
        assessment=assessment,
    )


def log_plan_research(build: PlanBuild, on_log: LogHandler) -> None:
    on_log(f"repo_count: {len(build.repo_scopes)}")
    for repo in build.repo_researches:
        on_log(
            "repo_research: "
            f"{repo.repo_id} matched={len(repo.finding.matched_terms)} "
            f"files={len(repo.finding.candidate_files)} dirs={len(repo.finding.candidate_dirs)}"
        )
    if build.context.missing_files:
        on_log(f"context_missing: {', '.join(build.context.missing_files)}")
    on_log(f"context_available: {build.context.available}")
    on_log(f"glossary_matched_terms: {len(build.finding.matched_terms)}")
    if build.finding.matched_terms:
        matched = ", ".join(f"{item.business}->{item.identifier}" for item in build.finding.matched_terms[:6])
        on_log(f"glossary_hits: {matched}")
    on_log(f"unmatched_terms_count: {len(build.finding.unmatched_terms)}")
    if build.finding.unmatched_terms:
        on_log(f"unmatched_terms: {', '.join(build.finding.unmatched_terms[:6])}")
    on_log(f"candidate_files_count: {len(build.finding.candidate_files)}")
    if build.finding.candidate_files:
        on_log(f"candidate_files: {', '.join(build.finding.candidate_files[:6])}")
    on_log(f"candidate_dirs_count: {len(build.finding.candidate_dirs)}")
    if build.finding.notes:
        on_log(f"research_notes: {' | '.join(build.finding.notes)}")
    on_log(f"complexity: {build.assessment.level} ({build.assessment.total})")


def sync_repo_statuses(task_dir: Path, status: str) -> None:
    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    repos = repos_meta.get("repos")
    if not isinstance(repos, list):
        return

    changed = False
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        current = str(repo.get("status") or "")
        if current in {"", STATUS_INITIALIZED, STATUS_REFINED, STATUS_PLANNING, STATUS_PLANNED}:
            repo["status"] = status
            changed = True

    if changed:
        repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n")


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


def resolve_primary_repo_root(repos_meta: dict[str, object]) -> str | None:
    repos = repos_meta.get("repos")
    if not isinstance(repos, list) or not repos:
        return None
    first = repos[0]
    if not isinstance(first, dict):
        return None
    path = str(first.get("path") or "").strip()
    return path or None


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


def build_design(build: PlanBuild, ai: PlanAISections | None) -> str:
    repo_section = "\n".join(build.repo_lines) if build.repo_lines else "- current-repo"
    parts = [
        "# Design\n\n",
        "## 背景与目标\n\n",
        f"- task_id: {build.task_id}\n",
        f"- 任务标题：{build.title}\n",
        f"- 原始输入：{build.source_value or '未记录'}\n",
        "- 基于 refined PRD、context 和本地调研结果收敛实现边界。\n\n",
        "## 涉及仓库\n\n",
        f"{repo_section}\n\n",
        "## 需求理解\n\n",
        render_requirement_summary(build.sections, build.source_markdown),
        "\n\n",
        "## Context 摘要\n\n",
        render_context_snapshot(build.context),
        "\n\n",
        "## 本地调研结果\n\n",
        render_research_summary(build.finding),
        "\n\n",
        "## 复杂度评估\n\n",
        render_complexity_summary(build.assessment),
        "\n\n",
        "## 实施摘要\n\n",
        render_implementation_summary(ai, build.assessment),
        "\n\n",
        "## 候选文件\n\n",
        render_candidate_files(ai, build.finding.candidate_files),
        "\n\n",
        "## 风险与约束\n\n",
        render_risk_section(ai, build.finding.notes),
        "\n",
    ]
    return "".join(parts)


def build_plan(build: PlanBuild, ai: PlanAISections | None) -> str:
    repo_order = [scope.repo_id for scope in build.repo_scopes]
    tasks = build_plan_tasks(build.sections, build.finding, ai, build.repo_ids, repo_order)
    repo_groups = build_plan_repo_groups(build.finding.candidate_files, build.repo_ids, repo_order)
    parts = [
        "# Plan\n\n",
        f"- task_id: {build.task_id}\n",
        f"- title: {build.title}\n\n",
        "## 复杂度评估\n\n",
        f"- complexity: {build.assessment.level} ({build.assessment.total})\n",
        f"- 结论: {build.assessment.conclusion}\n\n",
        "## 实现概要\n\n",
        render_implementation_summary(ai, build.assessment),
        "\n\n",
    ]

    if build.assessment.total > 6:
        parts.extend(
            [
                "## 结论\n\n",
                "- 当前需求被判定为复杂，暂不建议直接进入自动 code 阶段。\n",
                "- 建议先人工拆分需求、补充上下文或补全 PRD 后再重新执行 plan。\n\n",
            ]
        )
    else:
        parts.extend(["## 实现目标\n\n", render_goal_list(build.sections), "\n\n"])

    if repo_groups:
        parts.extend(["## 涉及仓库\n\n"])
        for repo_id, files in repo_groups:
            parts.append(f"- {repo_id}：{len(files)} 个候选文件\n")
        parts.append("\n")

    parts.extend(["## 拟改文件\n\n", render_plan_candidate_groups(repo_groups, ai), "\n\n"])
    parts.extend(["## 任务列表\n\n", render_plan_tasks(tasks), "\n\n"])
    parts.extend(["## 实施步骤\n\n", render_implementation_steps(tasks, ai), "\n\n"])
    parts.extend(["## 风险补充\n\n", render_risk_section(ai, build.finding.notes), "\n\n"])
    parts.extend(["## 待确认项\n\n", render_open_questions(build.sections.open_questions), "\n\n"])
    parts.extend(["## 验证建议\n\n", render_validation_section(build.finding.notes, ai), "\n"])
    return "".join(parts)


def build_plan_prompt(build: PlanBuild) -> str:
    repo_section = "\n".join(build.repo_lines) if build.repo_lines else "- current-repo"
    matched_terms = render_glossary_hits(build.finding.matched_terms)
    unmatched_terms = render_list_block(build.finding.unmatched_terms, default="  - 无")
    candidate_files = render_list_block(build.finding.candidate_files, default="  - 无")
    candidate_dirs = render_list_block(build.finding.candidate_dirs, default="  - 无")
    local_notes = render_list_block(build.finding.notes, default="  - 无")
    dimension_lines = "\n".join(
        f"  - {dimension.name}: {dimension.score} | {dimension.reason}" for dimension in build.assessment.dimensions
    )
    return f"""你是一名资深技术方案与研发计划助手。基于提供的 PRD refined 内容、本地 context 事实和代码调研结果，输出结构化的方案内容。

要求:
1. 只能基于提供的信息工作，不要编造未出现的模块、文件或接口。
2. 不要输出 task_id、title、复杂度总分、待确认项这些固定字段。
3. 如果需求复杂，仍然要在总结或风险里明确写出“不建议自动实现”。
4. 输出必须严格使用下面的标记格式:
{SECTION_MARKERS["summary"]}
- ...
{SECTION_MARKERS["candidate_files"]}
(每行一个文件路径，只输出你认为真正需要改动的文件，不要盲目照搬本地调研结果。)
- path/to/file1.go
- path/to/file2.go
{SECTION_MARKERS["steps"]}
- ...
{SECTION_MARKERS["risks"]}
- ...
{SECTION_MARKERS["validation_extra"]}
- ...
5. 不要输出其它前言或解释。

## PRD Refined
{build.sections.raw or build.refined_markdown}

## 任务关联仓库
{repo_section}

## Context 摘要
{render_context_snapshot(build.context)}

## glossary 命中术语
{matched_terms}

## glossary 未命中术语
{unmatched_terms}

## 本地调研结果
- candidate_files_count: {len(build.finding.candidate_files)}
{candidate_files}
- candidate_dirs_count: {len(build.finding.candidate_dirs)}
{candidate_dirs}
- 本地风险备注：
{local_notes}

## 本地基线复杂度评分
- total: {build.assessment.total}
- level: {build.assessment.level}
{dimension_lines}
"""


def extract_plan_outputs(raw: str) -> tuple[PlanAISections, bool]:
    normalized = raw.replace("\r\n", "\n")
    sections = PlanAISections()
    markers = [
        (SECTION_MARKERS["summary"], "summary"),
        (SECTION_MARKERS["candidate_files"], "candidate_files"),
        (SECTION_MARKERS["steps"], "steps"),
        (SECTION_MARKERS["risks"], "risks"),
        (SECTION_MARKERS["validation_extra"], "validation_extra"),
    ]
    indexes = [normalized.find(marker) for marker, _ in markers]
    if indexes[0] == -1:
        return PlanAISections(), False

    for index, (marker, field_name) in enumerate(markers):
        start = indexes[index]
        if start == -1:
            continue
        content_start = start + len(marker)
        end = len(normalized)
        for next_index in indexes[index + 1 :]:
            if next_index != -1 and next_index > start:
                end = next_index
                break
        setattr(sections, field_name, normalize_ai_section(normalized[content_start:end]))
    return sections, True


def validate_plan_outputs(build: PlanBuild, ai: PlanAISections) -> None:
    combined = "\n".join([ai.summary, ai.steps, ai.risks, ai.validation_extra])
    for marker in ("(待生成)", "(待确认)", "未初始化"):
        if marker in combined:
            raise ValueError(f"AI 输出包含无效占位符: {marker}")
    if not ai.summary.strip():
        raise ValueError("AI plan 缺少实现概要")
    if build.assessment.total <= 6 and not ai.steps.strip():
        raise ValueError("AI plan 缺少实施步骤")
    for bad in ("/livecoding:prd-refine", "/livecoding:prd-plan"):
        if bad in combined:
            raise ValueError(f"AI plan 包含错误命令示例: {bad}")


def parse_ai_candidate_files(raw: str, build: PlanBuild) -> list[str]:
    files: list[str] = []
    for line in raw.splitlines():
        current = line.strip().removeprefix("- ").removeprefix("* ").strip()
        if not current:
            continue
        if current.startswith(("（", "(")):
            continue
        if "." not in current and "/" not in current:
            continue
        if " " in current:
            first = current.split(" ", 1)[0]
            if "." in first or "/" in first:
                current = first
        normalized = normalize_ai_candidate_file(current, build)
        if normalized:
            files.append(normalized)
    return dedupe_and_sort(files)[:MAX_SEARCH_FILES]


def normalize_ai_candidate_file(raw_path: str, build: PlanBuild) -> str:
    current = raw_path.strip()
    if not current:
        return ""
    candidate_absolute = ""
    if Path(current).is_absolute():
        candidate_absolute = str(Path(current).resolve(strict=False))
    for scope in build.repo_scopes:
        repo_prefix = str(Path(scope.repo_path).resolve(strict=False)) + os.sep
        if candidate_absolute.startswith(repo_prefix):
            relative = candidate_absolute[len(repo_prefix):].lstrip("/\\")
            return qualify_repo_path(scope.repo_id, relative, len(build.repo_scopes))
    normalized = current.lstrip("./")
    if normalized in build.finding.candidate_files:
        return normalized
    repo_id, relative = split_repo_prefixed_path(normalized, build.repo_ids)
    if repo_id and normalized in build.finding.candidate_files:
        return normalized

    matched = []
    for candidate in build.finding.candidate_files:
        _, candidate_relative = split_repo_prefixed_path(candidate, build.repo_ids)
        if candidate_relative == relative or candidate_relative.endswith("/" + relative):
            matched.append(candidate)
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1 and len(build.repo_ids) > 1:
        return ""
    return normalized


def normalize_ai_section(content: str) -> str:
    cleaned = content.strip()
    lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("("):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


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
        summary=clean_section_lines(sections.get("需求概述", "")),
        features=extract_bullet_items(sections.get("功能点", "")),
        boundaries=extract_bullet_items(sections.get("边界条件", "")),
        business_rules=extract_bullet_items(sections.get("业务规则", "")),
        open_questions=extract_bullet_items(sections.get("待确认问题", "")),
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
            sections.summary,
            "\n".join(sections.features),
            "\n".join(sections.business_rules),
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
            sections.summary,
            "\n".join(sections.features),
            "\n".join(sections.boundaries),
            "\n".join(sections.business_rules),
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
    if contains_any("\n".join(sections.features), "接口", "协议", "请求", "返回", "字段"):
        interface_score = 1
        interface_reason = "需求描述中包含接口/字段类变更信号。"
    if has_path_keyword(findings.candidate_files, "handler", ".proto", ".thrift"):
        interface_score = 2
        interface_reason = "候选文件涉及 handler/IDL，可能影响对外接口。"
    dimensions.append(ComplexityDimension("接口协议", interface_score, interface_reason))

    data_score = 0
    data_reason = "未发现复杂数据或持久化变更。"
    if contains_any("\n".join(sections.boundaries), "状态", "缓存", "数据库", "表", "持久化"):
        data_score = 1
        data_reason = "边界条件中出现状态/数据类描述。"
    if contains_any("\n".join(sections.business_rules), "状态流转", "一致性", "数据同步"):
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


def build_plan_tasks(
    sections: RefinedSections,
    findings: ResearchFinding,
    ai: PlanAISections | None,
    repo_ids: set[str] | None = None,
    repo_order: list[str] | None = None,
) -> list[PlanTask]:
    if not findings.candidate_files:
        return []

    ai_steps = ai.steps if ai else ""
    repo_dir_files: dict[str, dict[str, list[str]]] = {}
    for file_path in findings.candidate_files:
        repo_id = infer_repo_id_from_file(file_path, repo_ids or set())
        _, relative_path = split_repo_prefixed_path(file_path, repo_ids or set())
        directory = str(Path(relative_path).parent)
        repo_bucket = repo_dir_files.setdefault(repo_id, {})
        repo_bucket.setdefault(directory, []).append(file_path)

    tasks: list[PlanTask] = []
    task_index = 1
    last_repo_task_id: dict[str, str] = {}
    ordered_repos = [repo for repo in (repo_order or []) if repo in repo_dir_files]
    for repo_id in sorted(repo_dir_files):
        if repo_id not in ordered_repos:
            ordered_repos.append(repo_id)

    for repo_id in ordered_repos:
        repo_dirs = repo_dir_files.get(repo_id, {})
        for directory in sorted(repo_dirs):
            files = repo_dirs[directory]
            display_dir = directory if directory != "." else repo_id
            depends_on = [last_repo_task_id[repo_id]] if repo_id in last_repo_task_id else []
            goal_prefix = f"在仓库 {repo_id}" if repo_id not in {"", "current-repo"} else "在当前仓库"
            title_prefix = f"[{repo_id}] " if repo_id not in {"", "current-repo"} else ""
            task_id = f"T{task_index}"
            actions = build_task_actions(files, sections, ai_steps)
            if repo_id not in {"", "current-repo"}:
                actions.insert(0, f"先在仓库 {repo_id} 中确认目录 {display_dir} 的改动边界。")
            tasks.append(
                PlanTask(
                    id=task_id,
                    title=f"{title_prefix}修改 {display_dir} 下相关文件",
                    goal=f"{goal_prefix}的 {display_dir} 目录中完成需求涉及的改动。",
                    depends_on=depends_on,
                    files=files,
                    input=["refined PRD 中的功能点与边界条件", "context 调研结果"],
                    output=[f"{display_dir} 目录下的改动文件通过编译和自测"],
                    actions=actions,
                    done=["涉及文件编译通过，功能符合 PRD 要求。"],
                )
            )
            last_repo_task_id[repo_id] = task_id
            task_index += 1
    return tasks


def build_plan_repo_groups(files: list[str], repo_ids: set[str], repo_order: list[str]) -> list[tuple[str, list[str]]]:
    order: list[str] = [repo for repo in repo_order if repo]
    groups: dict[str, list[str]] = {repo: [] for repo in order}
    for file_path in files:
        repo_id = infer_repo_id_from_file(file_path, repo_ids)
        if repo_id not in groups:
            groups[repo_id] = []
            if repo_id not in order:
                order.append(repo_id)
        groups[repo_id].append(file_path)
    return [(repo_id, groups[repo_id]) for repo_id in order]


def split_repo_prefixed_path(file_path: str, repo_ids: set[str]) -> tuple[str, str]:
    normalized = file_path.strip().lstrip("./")
    first = Path(normalized).parts[0] if Path(normalized).parts else ""
    if first and first in repo_ids:
        rest_parts = Path(normalized).parts[1:]
        relative_path = str(Path(*rest_parts)) if rest_parts else ""
        return first, relative_path or normalized
    return "", normalized


def infer_repo_id_from_file(file_path: str, repo_ids: set[str]) -> str:
    prefixed_repo, normalized = split_repo_prefixed_path(file_path, repo_ids)
    if prefixed_repo:
        return prefixed_repo
    first = Path(normalized).parts[0] if Path(normalized).parts else "current-repo"
    if first in {"sdk", "client", "clients"}:
        return "shared-sdk"
    if first in {"web", "frontend", "ui"}:
        return "frontend"
    return "current-repo"


def build_task_actions(files: list[str], sections: RefinedSections, ai_steps: str) -> list[str]:
    actions: list[str] = []
    has_ai_match = False
    for file_path in files:
        step = match_ai_step_for_file(ai_steps, file_path)
        if step:
            actions.append(step)
            has_ai_match = True
        else:
            actions.append(f"检查并修改 {file_path}。")
    if not has_ai_match and sections.features:
        actions.append(f"确保满足功能点：{sections.features[0]}")
    return actions


def match_ai_step_for_file(ai_steps: str, file_path: str) -> str:
    if not ai_steps:
        return ""
    basename = Path(file_path).name
    for line in ai_steps.splitlines():
        current = line.strip().removeprefix("- ").strip()
        if not current:
            continue
        if file_path in current or basename in current:
            return current[:100] + "..." if len(current) > 100 else current
    return ""


def suggest_file_action(file_path: str) -> str:
    if "/handler/" in file_path:
        return "评估接口层入参、返回或展示逻辑是否需要调整。"
    if "/service/" in file_path:
        return "评估业务逻辑和下游调用是否需要补充。"
    if "/converter/" in file_path:
        return "优先检查字段映射和 response 拼装逻辑。"
    if "/model/" in file_path:
        return "检查结构体字段或状态定义是否需要扩展。"
    return "作为候选实现文件，需要人工确认是否纳入本次改动范围。"


def render_requirement_summary(sections: RefinedSections, source_markdown: str) -> str:
    items = []
    if sections.summary:
        items.append(f"- 需求概述：{sections.summary}")
    for feature in sections.features[:4]:
        items.append(f"- 功能点：{feature}")
    if not items:
        excerpt = extract_excerpt(source_markdown)
        return excerpt or "- 当前尚未提取到有效需求内容。"
    return "\n".join(items)


def render_context_snapshot(context: ContextSnapshot) -> str:
    lines: list[str] = []
    if context.glossary_excerpt:
        lines.extend(["### glossary", context.glossary_excerpt])
    if context.architecture_excerpt:
        lines.extend(["### architecture", context.architecture_excerpt])
    if context.patterns_excerpt:
        lines.extend(["### patterns", context.patterns_excerpt])
    if context.gotchas_excerpt:
        lines.extend(["### gotchas", context.gotchas_excerpt])
    if context.missing_files:
        lines.append(f"- 缺少 context 文件: {', '.join(context.missing_files)}")
    return "\n".join(lines) if lines else "- 无可用 context。"


def render_glossary_hits(entries: list[GlossaryEntry]) -> str:
    if not entries:
        return "  - 无"
    return "\n".join(f"  - {entry.business} -> {entry.identifier} ({entry.module or 'module-unknown'})" for entry in entries)


def render_research_summary(finding: ResearchFinding) -> str:
    parts = [
        "- glossary 命中术语：",
        render_glossary_hits(finding.matched_terms),
        "- glossary 未命中术语：",
        render_list_block(finding.unmatched_terms, default="  - 无"),
        "- candidate files：",
        render_list_block(finding.candidate_files, default="  - 无"),
        "- candidate dirs：",
        render_list_block(finding.candidate_dirs, default="  - 无"),
        "- 本地备注：",
        render_list_block(finding.notes, default="  - 无"),
    ]
    return "\n".join(parts)


def render_complexity_summary(assessment: ComplexityAssessment) -> str:
    lines = [f"- complexity: {assessment.level} ({assessment.total})", f"- 结论: {assessment.conclusion}"]
    lines.extend(f"- {item.name}: {item.score} | {item.reason}" for item in assessment.dimensions)
    return "\n".join(lines)


def render_implementation_summary(ai: PlanAISections | None, assessment: ComplexityAssessment) -> str:
    if ai and ai.summary.strip():
        return ensure_markdown_list(ai.summary)
    lines = [
        "- 基于 refined PRD、context 和本地调研结果收敛改动范围。",
        "- 优先在已有模块中收敛实现，保持最小改动范围。",
    ]
    if assessment.total > 6:
        lines.append("- 当前需求复杂度偏高，建议先人工拆解，不直接进入自动实现。")
    else:
        lines.append("- 先完成最小验证路径，再决定是否继续扩展。")
    return "\n".join(lines)


def render_candidate_files(ai: PlanAISections | None, fallback_files: list[str]) -> str:
    if ai and ai.candidate_files.strip():
        return ensure_markdown_list(ai.candidate_files)
    return ensure_markdown_list("\n".join(fallback_files))


def render_risk_section(ai: PlanAISections | None, notes: list[str]) -> str:
    if ai and ai.risks.strip():
        return ensure_markdown_list(ai.risks)
    if notes:
        return "\n".join(f"- {note}" for note in notes)
    return "- 当前未发现额外风险补充。"


def render_goal_list(sections: RefinedSections) -> str:
    if not sections.features:
        return "- 基于 refined PRD 补全实现目标。"
    return "\n".join(f"- {feature}" for feature in sections.features)


def render_plan_candidate_groups(repo_groups: list[tuple[str, list[str]]], ai: PlanAISections | None) -> str:
    if not repo_groups:
        return "- 暂未命中候选文件，需要补充 context 或人工指定模块。"
    ai_steps = ai.steps if ai else ""
    blocks: list[str] = []
    for repo_id, files in repo_groups:
        blocks.append(f"### repo: {repo_id}\n")
        for file_path in files:
            desc = match_ai_step_for_file(ai_steps, file_path) or suggest_file_action(file_path)
            blocks.append(f"- {file_path}：{desc}")
        blocks.append("")
    return "\n".join(blocks).strip()


def render_plan_tasks(tasks: list[PlanTask]) -> str:
    if not tasks:
        return "- 暂未生成任务列表，需要先收敛候选文件后再继续。"
    blocks: list[str] = []
    for task in tasks:
        blocks.extend(
            [
                f"### {task.id} {task.title}",
                "",
                f"- 目标：{task.goal}",
            ]
        )
        if task.depends_on:
            blocks.append(f"- 依赖任务：{', '.join(task.depends_on)}")
        blocks.append("- 涉及文件：")
        blocks.extend(f"  - {item}" for item in task.files)
        blocks.append("- 输入：")
        blocks.extend(f"  - {item}" for item in task.input)
        blocks.append("- 输出：")
        blocks.extend(f"  - {item}" for item in task.output)
        blocks.append("- 具体动作：")
        blocks.extend(f"  - {item}" for item in task.actions)
        blocks.append("- 完成标志：")
        blocks.extend(f"  - {item}" for item in task.done)
        blocks.append("")
    return "\n".join(blocks).rstrip()


def render_implementation_steps(tasks: list[PlanTask], ai: PlanAISections | None) -> str:
    if ai and ai.steps.strip():
        return ai.steps.strip()
    if not tasks:
        return "- 先补充 context 或人工确认目标模块，再继续细化实施步骤。"
    return "\n".join(f"- {task.id}：先完成「{task.title}」，再根据完成标志逐项自检。" for task in tasks)


def render_open_questions(open_questions: list[str]) -> str:
    if not open_questions:
        return "- 无额外待确认项。"
    return "\n".join(f"- {item}" for item in open_questions)


def render_validation_section(notes: list[str], ai: PlanAISections | None) -> str:
    lines = [
        "- 仅编译涉及的 package，不执行全仓 build/test。",
        "- 完成实现后建议进行最小范围 review。",
    ]
    if notes:
        lines.extend(f"- {note}" for note in notes)
    if ai and ai.validation_extra.strip():
        lines.append(ensure_markdown_list(ai.validation_extra))
    return "\n".join(lines)


def render_list_block(items: list[str], default: str = "  - 无") -> str:
    if not items:
        return default
    return "\n".join(f"  - {item}" for item in items)


def extract_excerpt(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.splitlines()]
    content_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(">"):
            continue
        if stripped.startswith("- "):
            content_lines.append(stripped)
        elif len(content_lines) < 4:
            content_lines.append(f"- {stripped}")
        if len(content_lines) >= 4:
            break
    return "\n".join(content_lines)


def ensure_markdown_list(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        return "- 无"
    lines: list[str] = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped if stripped.startswith("- ") else f"- {stripped}")
    return "\n".join(lines) if lines else "- 无"


def excerpt_context(content: str, limit: int = 800) -> str:
    normalized = content.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text()


def append_plan_log(task_dir: Path, message: str) -> None:
    log_path = task_dir / "plan.log"
    with log_path.open("a", encoding="utf-8") as file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file.write(f"{timestamp} {message}\n")


def _update_task_status(task_dir: Path, task_meta: dict[str, object], status: str) -> None:
    task_meta["status"] = status
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")

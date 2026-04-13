from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import os
import re
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

LogHandler = Callable[[str], None]


@dataclass
class PlanAISections:
    summary: str = ""
    candidate_files: str = ""
    steps: str = ""
    risks: str = ""
    validation_extra: str = ""


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

    executor = cfg.plan_executor.strip().lower()
    if executor == EXECUTOR_NATIVE:
        return plan_task_native(task_dir, task_meta, cfg, on_log=on_log)
    if executor == EXECUTOR_LOCAL:
        return plan_task_local(task_dir, task_meta, on_log=on_log)
    raise ValueError(f"unknown plan executor: {cfg.plan_executor}")


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


def plan_task_local(task_dir: Path, task_meta: dict[str, object], on_log: LogHandler | None = None) -> str:
    title = str(task_meta.get("title") or task_dir.name)
    source_value = str(task_meta.get("source_value") or "")
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    refined_markdown = (task_dir / "prd-refined.md").read_text() if (task_dir / "prd-refined.md").exists() else ""
    repos_meta = read_json_file(task_dir / "repos.json")
    repo_lines = describe_repos(repos_meta)

    if on_log is not None:
        on_log("fallback_local_plan: true")

    design = build_design(
        title,
        source_value,
        source_markdown,
        refined_markdown,
        repo_lines,
        ai=None,
    )
    plan = build_plan(title, source_value, repo_lines, ai=None)

    (task_dir / "design.md").write_text(design)
    (task_dir / "plan.md").write_text(plan)
    append_plan_log(task_dir, f"planned locally at {datetime.now().astimezone().isoformat()}")

    _update_task_status(task_dir, task_meta, STATUS_PLANNED)
    sync_repo_statuses(task_dir, STATUS_PLANNED)
    return STATUS_PLANNED


def plan_task_native(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    on_log: LogHandler | None = None,
) -> str:
    title = str(task_meta.get("title") or task_dir.name)
    source_value = str(task_meta.get("source_value") or "")
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    refined_markdown = (task_dir / "prd-refined.md").read_text() if (task_dir / "prd-refined.md").exists() else ""
    repos_meta = read_json_file(task_dir / "repos.json")
    repo_lines = describe_repos(repos_meta)

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    repo_root = resolve_primary_repo_root(repos_meta)

    if on_log is not None:
        on_log("generator_mode: explorer(readonly)")
        on_log(f"prompt_start: timeout={settings.native_query_timeout}")

    try:
        raw = client.run_readonly_agent(
            build_plan_prompt(title, source_markdown, refined_markdown, repo_lines),
            settings.native_query_timeout,
            repo_root or os.getcwd(),
        )
    except ValueError as error:
        if on_log is not None:
            on_log(f"generate_plan_with_native_error: {error}")
        return plan_task_local(task_dir, task_meta, on_log=on_log)

    if on_log is not None:
        on_log(f"prompt_ok: {len(raw)} bytes")

    ai_sections, ok = extract_plan_outputs(raw)
    if not ok:
        if on_log is not None:
            on_log("parse_plan_output_error: missing required marker sections")
        return plan_task_local(task_dir, task_meta, on_log=on_log)

    design = build_design(
        title,
        source_value,
        source_markdown,
        refined_markdown,
        repo_lines,
        ai=ai_sections,
    )
    plan = build_plan(title, source_value, repo_lines, ai=ai_sections)

    (task_dir / "design.md").write_text(design)
    (task_dir / "plan.md").write_text(plan)
    append_plan_log(task_dir, f"planned by native coco at {datetime.now().astimezone().isoformat()}")

    _update_task_status(task_dir, task_meta, STATUS_PLANNED)
    sync_repo_statuses(task_dir, STATUS_PLANNED)
    return STATUS_PLANNED


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


def build_design(
    title: str,
    source_value: str,
    source_markdown: str,
    refined_markdown: str,
    repo_lines: list[str],
    ai: PlanAISections | None,
) -> str:
    repo_section = "\n".join(repo_lines) if repo_lines else "- current-repo"
    source_excerpt = extract_excerpt(source_markdown)
    refined_excerpt = extract_excerpt(refined_markdown)

    parts = [
        "# Design\n\n",
        "## 背景与目标\n\n",
        f"- 任务标题：{title}\n",
        f"- 原始输入：{source_value or '未记录'}\n",
        "- 基于 refined PRD 和当前仓库上下文整理方案，目标是形成可执行设计草稿。\n\n",
        "## 涉及仓库\n\n",
        f"{repo_section}\n\n",
        "## 需求理解\n\n",
        f"{refined_excerpt or source_excerpt or '- 当前尚未提取到有效需求内容。'}\n\n",
    ]

    if ai and ai.summary:
        parts.extend(["## 实施摘要\n\n", ensure_markdown_list(ai.summary), "\n\n"])
    else:
        parts.extend(
            [
                "## 实施摘要\n\n",
                "- 先限定本次改动范围，避免在需求尚未明确前扩散实现面。\n",
                "- 优先保持现有行为不变，只补充本次需求直接相关的实现。\n",
                "- 先完成最小验证路径，再决定是否继续扩展。\n\n",
            ]
        )

    parts.extend(["## 候选文件\n\n", ensure_markdown_list(ai.candidate_files if ai else ""), "\n\n"])
    parts.extend(["## 风险与约束\n\n", ensure_markdown_list(ai.risks if ai else ""), "\n"])
    return "".join(parts)


def build_plan(
    title: str,
    source_value: str,
    repo_lines: list[str],
    ai: PlanAISections | None,
) -> str:
    repo_section = "\n".join(repo_lines) if repo_lines else "- current-repo"

    parts = [
        "# Plan\n\n",
        "## 复杂度评估\n\n",
        "- complexity: 中等 (2)\n",
        "- 当前按可拆解、可回滚、可验证的方式推进。\n\n",
        "## 实现目标\n\n",
        f"- 围绕任务“{title}”形成可执行的最小实现计划。\n",
        f"- 保持对原始输入“{source_value or '未记录'}”的直接响应。\n\n",
        "## 涉及仓库\n\n",
        f"{repo_section}\n\n",
        "## 任务列表\n\n",
        ensure_numbered_list(ai.steps if ai else ""),
        "\n\n",
        "## 待确认项\n\n",
        "- 无额外待确认项。\n\n",
        "## 验证建议\n\n",
        "- 仅编译涉及的 package，不执行全仓 build/test。\n",
        "- 完成实现后建议进行最小范围 review。\n",
    ]
    if ai and ai.validation_extra:
        parts.append(ensure_markdown_list(ai.validation_extra))
    return "".join(parts)


def build_plan_prompt(
    title: str,
    source_markdown: str,
    refined_markdown: str,
    repo_lines: list[str],
) -> str:
    repo_section = "\n".join(repo_lines) if repo_lines else "- current-repo"
    return f"""你是一名资深技术方案与研发计划助手。基于提供的 PRD refined 内容和任务关联仓库，输出结构化的方案内容。

要求:
1. 只能基于提供的信息工作，不要编造未出现的模块、文件或接口。
2. 不要输出 task_id、title、复杂度总分、待确认项这些固定字段。
3. 如果需求复杂，仍然要在总结或风险里明确写出“不建议自动实现”。
4. 输出必须严格使用下面的标记格式:
=== IMPLEMENTATION SUMMARY ===
- ...
=== CANDIDATE FILES ===
(每行一个文件路径，只输出你认为真正需要改动的文件。)
- path/to/file1.go
- path/to/file2.go
=== IMPLEMENTATION STEPS ===
- ...
=== RISK NOTES ===
- ...
=== VALIDATION EXTRA ===
- ...
5. 不要输出其它前言或解释。

## PRD Source
{source_markdown}

## PRD Refined
{refined_markdown}

## 任务关联仓库
{repo_section}

任务标题：{title}
"""


def extract_plan_outputs(raw: str) -> tuple[PlanAISections, bool]:
    normalized = raw.replace("\r\n", "\n")
    sections = PlanAISections()
    markers = [
        ("=== IMPLEMENTATION SUMMARY ===", "summary"),
        ("=== CANDIDATE FILES ===", "candidate_files"),
        ("=== IMPLEMENTATION STEPS ===", "steps"),
        ("=== RISK NOTES ===", "risks"),
        ("=== VALIDATION EXTRA ===", "validation_extra"),
    ]

    indexes = [normalized.find(marker) for marker, _ in markers]
    if indexes[0] == -1:
        return PlanAISections(), False

    for i, (marker, field_name) in enumerate(markers):
        start = indexes[i]
        if start == -1:
            continue
        content_start = start + len(marker)
        end = len(normalized)
        for next_index in indexes[i + 1 :]:
            if next_index != -1 and next_index > start:
                end = next_index
                break
        setattr(sections, field_name, normalize_ai_section(normalized[content_start:end]))
    return sections, True


def normalize_ai_section(content: str) -> str:
    cleaned = content.strip()
    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("("):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


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
    lines = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            lines.append(stripped)
        else:
            lines.append(f"- {stripped}")
    return "\n".join(lines) if lines else "- 无"


def ensure_numbered_list(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        return "\n".join(
            [
                "1. 读取现有上下文与任务产物，确认设计边界。",
                "2. 在受影响仓库内完成最小实现。",
                "3. 做最小验证，确认没有明显行为回退。",
                "4. 补充必要文档或产物，便于后续继续推进 code 阶段。",
            ]
        )
    items = []
    for line in normalized.splitlines():
        stripped = re.sub(r"^[-*]\s*", "", line.strip())
        stripped = re.sub(r"^\d+\.\s*", "", stripped)
        if stripped:
            items.append(stripped)
    if not items:
        return ensure_numbered_list("")
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def append_plan_log(task_dir: Path, message: str) -> None:
    log_path = task_dir / "plan.log"
    with log_path.open("a", encoding="utf-8") as file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file.write(f"{timestamp} {message}\n")


def _update_task_status(task_dir: Path, task_meta: dict[str, object], status: str) -> None:
    task_meta["status"] = status
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")

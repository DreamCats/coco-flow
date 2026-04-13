from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re

from coco_flow.clients import CocoCliClient
from coco_flow.config import Settings, load_settings
from coco_flow.services.task_detail import read_json_file
from coco_flow.services.task_refine import locate_task_dir

STATUS_REFINED = "refined"
STATUS_PLANNED = "planned"
STATUS_INITIALIZED = "initialized"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"
_design_heading = re.compile(r"(?m)^#\s+Design\s*$")
_plan_separator = "=== PLAN ==="


def plan_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {STATUS_REFINED, STATUS_PLANNED}:
        raise ValueError(f"task status {status} does not allow plan")

    executor = cfg.plan_executor.strip().lower()
    if executor == EXECUTOR_NATIVE:
        try:
            return plan_task_native(task_dir, task_meta, cfg)
        except ValueError:
            return plan_task_local(task_dir, task_meta)
    if executor == EXECUTOR_LOCAL:
        return plan_task_local(task_dir, task_meta)
    raise ValueError(f"unknown plan executor: {cfg.plan_executor}")


def plan_task_local(task_dir: Path, task_meta: dict[str, object]) -> str:
    title = str(task_meta.get("title") or task_dir.name)
    source_value = str(task_meta.get("source_value") or "")
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    refined_markdown = (task_dir / "prd-refined.md").read_text() if (task_dir / "prd-refined.md").exists() else ""
    repos_meta = read_json_file(task_dir / "repos.json")
    repo_lines = describe_repos(repos_meta)

    (task_dir / "design.md").write_text(build_design(title, source_value, source_markdown, refined_markdown, repo_lines))
    (task_dir / "plan.md").write_text(build_plan(title, source_value, repo_lines))
    append_plan_log(task_dir, f"planned locally at {datetime.now().astimezone().isoformat()}")

    now = datetime.now().astimezone().isoformat()
    task_meta["status"] = STATUS_PLANNED
    task_meta["updated_at"] = now
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
    sync_repo_statuses(task_dir, STATUS_PLANNED)
    return STATUS_PLANNED


def plan_task_native(task_dir: Path, task_meta: dict[str, object], settings: Settings) -> str:
    title = str(task_meta.get("title") or task_dir.name)
    source_value = str(task_meta.get("source_value") or "")
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    refined_markdown = (task_dir / "prd-refined.md").read_text() if (task_dir / "prd-refined.md").exists() else ""
    repos_meta = read_json_file(task_dir / "repos.json")
    repo_lines = describe_repos(repos_meta)

    client = CocoCliClient(settings.coco_bin)
    raw = client.run_prompt_only(
        build_plan_prompt(title, source_value, source_markdown, refined_markdown, repo_lines),
        settings.native_query_timeout,
    )
    design, plan = extract_plan_artifacts(raw)
    if not design or not plan:
        raise ValueError("native plan returned invalid content")

    (task_dir / "design.md").write_text(design.rstrip() + "\n")
    (task_dir / "plan.md").write_text(plan.rstrip() + "\n")
    append_plan_log(task_dir, f"planned by native coco at {datetime.now().astimezone().isoformat()}")

    task_meta["status"] = STATUS_PLANNED
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
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
        if current in {"", STATUS_INITIALIZED, STATUS_REFINED, STATUS_PLANNED}:
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
        lines.append(f"- `{repo_id}`: `{repo_path}`")
    return lines


def build_design(
    title: str,
    source_value: str,
    source_markdown: str,
    refined_markdown: str,
    repo_lines: list[str],
) -> str:
    repo_section = "\n".join(repo_lines) if repo_lines else "- 当前未绑定 repo。"
    source_excerpt = extract_excerpt(source_markdown)
    refined_excerpt = extract_excerpt(refined_markdown)
    return (
        "# Design\n\n"
        "## 背景与目标\n\n"
        f"- 任务标题：{title}\n"
        f"- 原始输入：{source_value or '未记录'}\n"
        "- 当前版本使用 coco-flow 本地模板生成 design，目标是尽快把 task 推进到可执行计划。\n\n"
        "## 涉及仓库\n\n"
        f"{repo_section}\n\n"
        "## 需求理解\n\n"
        f"{refined_excerpt or source_excerpt or '- 当前尚未提取到有效需求内容。'}\n\n"
        "## 方案草稿\n\n"
        "- 先限定本次改动范围，避免在任务尚未明确前扩散实现面。\n"
        "- 优先保持现有行为不变，只补充本次需求直接相关的实现。\n"
        "- 先完成最小验证路径，再决定是否继续扩展。\n\n"
        "## 风险与待确认\n\n"
        "- 当前 design 为本地模板稿，复杂依赖、跨仓影响和边界条件仍需在后续迭代补全。\n"
    )


def build_plan(title: str, source_value: str, repo_lines: list[str]) -> str:
    repo_section = "\n".join(repo_lines) if repo_lines else "- 当前未绑定 repo。"
    return (
        "# Plan\n\n"
        "## 复杂度评估\n\n"
        "- complexity: 中等 (2)\n"
        "- 当前为本地模板 plan，默认按可拆解、可回滚、可验证的方式推进。\n\n"
        "## 实现目标\n\n"
        f"- 围绕任务“{title}”形成可执行的最小实现计划。\n"
        f"- 保持对原始输入“{source_value or '未记录'}”的直接响应。\n\n"
        "## 涉及仓库\n\n"
        f"{repo_section}\n\n"
        "## 任务列表\n\n"
        "1. 读取现有上下文与任务产物，确认设计边界。\n"
        "2. 在受影响仓库内完成最小实现。\n"
        "3. 做最小验证，确认没有明显行为回退。\n"
        "4. 补充必要文档或产物，便于后续继续推进 code 阶段。\n\n"
        "## 验证建议\n\n"
        "- 只运行与本次改动直接相关的最小验证。\n"
        "- 如需跨仓推进，按 repo 逐个确认结果。\n"
    )


def build_plan_prompt(
    title: str,
    source_value: str,
    source_markdown: str,
    refined_markdown: str,
    repo_lines: list[str],
) -> str:
    repo_section = "\n".join(repo_lines) if repo_lines else "- 当前未绑定 repo。"
    return f"""你是一名严谨的技术方案助手。请基于任务信息输出两个 Markdown 文档：design 和 plan。

输出要求：
1. 先输出完整的 `# Design` 文档。
2. 然后单独一行输出 `{_plan_separator}`。
3. 再输出完整的 `# Plan` 文档。
4. 不要输出额外说明、前言或分析过程。
5. `# Plan` 中必须包含一行复杂度，格式严格为：`- complexity: 中等 (2)` 这类形式。

任务标题：{title}
原始输入：{source_value}

涉及仓库：
{repo_section}

PRD Source:
{source_markdown}

PRD Refined:
{refined_markdown}
"""


def extract_plan_artifacts(raw: str) -> tuple[str, str]:
    normalized = raw.replace("\r\n", "\n").strip()
    if not normalized:
        return "", ""
    if _plan_separator in normalized:
        design_raw, plan_raw = normalized.split(_plan_separator, 1)
        design = design_raw.strip()
        plan = plan_raw.strip()
        if design.startswith("# Design") and plan.startswith("# Plan"):
            return design, plan
    design_match = _design_heading.search(normalized)
    plan_index = normalized.find("# Plan")
    if design_match and plan_index > design_match.start():
        design = normalized[design_match.start() : plan_index].strip()
        plan = normalized[plan_index:].strip()
        if design.startswith("# Design") and plan.startswith("# Plan"):
            return design, plan
    return "", ""


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


def append_plan_log(task_dir: Path, message: str) -> None:
    log_path = task_dir / "plan.log"
    with log_path.open("a", encoding="utf-8") as file:
        file.write(message + "\n")

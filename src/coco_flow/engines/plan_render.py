from __future__ import annotations

from pathlib import Path
import re

from .plan_models import (
    ComplexityAssessment,
    ContextSnapshot,
    GlossaryEntry,
    PlanAISections,
    PlanBuild,
    PlanTask,
    RefinedSections,
    ResearchFinding,
)
from .plan_research import dedupe_and_sort

MAX_TASK_ACTIONS = 4


def build_design(build: PlanBuild, ai: PlanAISections | None) -> str:
    repo_section = "\n".join(build.repo_lines) if build.repo_lines else "- current-repo"
    candidate_summary = render_design_candidate_summary(build.finding.candidate_files)
    parts = [
        "# Design\n\n",
        "## 背景与目标\n\n",
        f"- task_id: {build.task_id}\n",
        f"- 任务标题：{build.title}\n",
        f"- 原始输入：{build.source_value or '未记录'}\n",
        "- 基于 refined PRD、context 和本地调研结果收敛实现边界。\n",
        "- 涉及仓库：\n",
        f"{indent_block(repo_section, prefix='  ')}\n\n",
        render_requirement_summary(build.sections, build.source_markdown),
        "\n\n",
        "## 现状与关键上下文\n\n",
        render_context_snapshot(build.context),
        "\n\n",
        render_plan_knowledge_section(build),
        "\n\n",
        render_research_summary(build.finding),
        "\n\n",
        "## 方案摘要\n\n",
        render_implementation_summary(ai, build.assessment),
        "\n\n",
        "- 候选文件摘要：\n",
        f"{candidate_summary}\n\n",
        "## 风险与待确认\n\n",
        render_complexity_summary(build.assessment),
        "\n\n",
        render_risk_section(ai, build.finding.notes),
        "\n\n",
        render_open_questions(build.sections.open_questions),
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
    parts.extend(["## Knowledge Brief\n\n", render_plan_knowledge_block(build), "\n\n"])
    parts.extend(["## 任务列表\n\n", render_plan_tasks(tasks), "\n\n"])
    parts.extend(["## 实施步骤\n\n", render_implementation_steps(tasks, ai), "\n\n"])
    parts.extend(["## 风险补充\n\n", render_risk_section(ai, build.finding.notes), "\n\n"])
    parts.extend(["## 待确认项\n\n", render_open_questions(build.sections.open_questions), "\n\n"])
    parts.extend(["## 验证建议\n\n", render_validation_section(build.finding.notes, ai), "\n"])
    return "".join(parts)


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
    previous_repo_last_task_id = ""
    ordered_repos = [repo for repo in (repo_order or []) if repo in repo_dir_files]
    for repo_id in sorted(repo_dir_files):
        if repo_id not in ordered_repos:
            ordered_repos.append(repo_id)

    for repo_id in ordered_repos:
        repo_dirs = repo_dir_files.get(repo_id, {})
        for directory, files in repo_dirs.items():
            files = dedupe_and_sort(files)
            display_dir = render_task_directory(repo_id, directory)
            depends_on = build_task_dependencies(repo_id, last_repo_task_id, previous_repo_last_task_id)
            task_id = f"T{task_index}"
            actions = build_task_actions_for_scope(files, sections, ai_steps, repo_id=repo_id, display_dir=display_dir)
            tasks.append(
                PlanTask(
                    id=task_id,
                    title=build_plan_task_title(repo_id, display_dir, files, sections, ai_steps),
                    goal=build_plan_task_goal(repo_id, display_dir, sections, files),
                    depends_on=depends_on,
                    files=files,
                    input=["refined PRD 中的功能点与边界条件", "context 调研结果"],
                    output=build_task_outputs(repo_id, display_dir, files),
                    actions=actions,
                    done=["涉及文件编译通过，功能符合 PRD 要求。"],
                )
            )
            last_repo_task_id[repo_id] = task_id
            task_index += 1
        if repo_id in last_repo_task_id:
            previous_repo_last_task_id = last_repo_task_id[repo_id]
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


def build_task_dependencies(
    repo_id: str,
    last_repo_task_id: dict[str, str],
    previous_repo_last_task_id: str,
) -> list[str]:
    if repo_id in last_repo_task_id:
        return [last_repo_task_id[repo_id]]
    if previous_repo_last_task_id:
        return [previous_repo_last_task_id]
    return []


def build_plan_task_title(
    repo_id: str,
    display_dir: str,
    files: list[str],
    sections: RefinedSections,
    ai_steps: str,
) -> str:
    repo_prefix = f"[{repo_id}] " if repo_id not in {"", "current-repo"} else ""
    feature = summarize_feature(sections)
    step = summarize_ai_focus(files, ai_steps)
    if step:
        return f"{repo_prefix}{step}"
    if feature:
        if display_dir == "仓库根目录":
            return f"{repo_prefix}为「{feature}」补齐核心改动"
        return f"{repo_prefix}为「{feature}」调整 {display_dir}"
    return f"{repo_prefix}修改 {display_dir} 下相关文件"


def build_plan_task_goal(repo_id: str, display_dir: str, sections: RefinedSections, files: list[str]) -> str:
    repo_scope = f"在仓库 {repo_id}" if repo_id not in {"", "current-repo"} else "在当前仓库"
    feature = summarize_feature(sections)
    if feature:
        return f"{repo_scope} 的 {display_dir} 中完成「{feature}」相关改动，并收敛到可验证的最小实现范围。"
    if len(files) == 1:
        return f"{repo_scope}围绕 {files[0]} 完成需求涉及的改动，并保证结果可验证。"
    return f"{repo_scope} 的 {display_dir} 中完成需求涉及的改动，并保证结果可验证。"


def build_task_outputs(repo_id: str, display_dir: str, files: list[str]) -> list[str]:
    outputs = [f"{display_dir} 下的改动文件通过编译和自测"]
    if repo_id not in {"", "current-repo"}:
        outputs.append(f"仓库 {repo_id} 的改动边界清晰，可继续推进后续仓库任务")
    if len(files) == 1:
        outputs.append(f"{files[0]} 的实现变更已落地")
    return outputs


def build_task_actions_for_scope(
    files: list[str],
    sections: RefinedSections,
    ai_steps: str,
    repo_id: str,
    display_dir: str,
) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    boundary = build_boundary_action(repo_id, display_dir)
    if boundary:
        actions.append(boundary)
        seen.add(boundary)

    for file_path in files:
        step = normalize_action_line(match_ai_step_for_file(ai_steps, file_path))
        if step and step not in seen:
            actions.append(step)
            seen.add(step)
        if len(actions) >= MAX_TASK_ACTIONS:
            break

    if len(actions) < MAX_TASK_ACTIONS:
        for file_path in files:
            fallback = normalize_action_line(f"处理 {file_path}：{suggest_file_action(file_path)}")
            if fallback not in seen:
                actions.append(fallback)
                seen.add(fallback)
            if len(actions) >= MAX_TASK_ACTIONS:
                break

    feature = summarize_feature(sections)
    if feature:
        feature_action = normalize_action_line(f"确保实现覆盖功能点「{feature}」及其边界条件。")
        if feature_action not in seen:
            actions.append(feature_action)

    return actions[:MAX_TASK_ACTIONS]


def build_boundary_action(repo_id: str, display_dir: str) -> str:
    if display_dir == "仓库根目录":
        if repo_id not in {"", "current-repo"}:
            return f"先确认仓库 {repo_id} 的改动边界，避免把无关文件带入本次实现。"
        return "先确认本次需求的改动边界，避免把无关文件带入实现。"
    if repo_id not in {"", "current-repo"}:
        return f"先确认仓库 {repo_id} 中 {display_dir} 的改动边界和上下游影响。"
    return f"先确认 {display_dir} 的改动边界和上下游影响。"


def render_task_directory(repo_id: str, directory: str) -> str:
    if directory in {"", "."}:
        return "仓库根目录"
    return directory


def summarize_feature(sections: RefinedSections, limit: int = 24) -> str:
    source = ""
    if sections.features:
        source = sections.features[0]
    elif sections.summary:
        source = sections.summary
    source = normalize_action_line(source).removesuffix("。")
    if len(source) > limit:
        return source[: limit - 1] + "…"
    return source


def summarize_ai_focus(files: list[str], ai_steps: str, limit: int = 32) -> str:
    for file_path in files:
        current = normalize_action_line(match_ai_step_for_file(ai_steps, file_path)).removesuffix("。")
        current = re.sub(r"^在\s+.+?\s+中", "", current).strip()
        if current:
            return current[: limit - 1] + "…" if len(current) > limit else current
    return ""


def normalize_action_line(content: str) -> str:
    current = content.strip().removeprefix("- ").strip()
    if not current:
        return ""
    return current if current.endswith(("。", "？", "！")) else current + "。"


def match_ai_step_for_file(ai_steps: str, file_path: str) -> str:
    if not ai_steps:
        return ""
    basename = Path(file_path).name
    exact_match = ""
    for line in ai_steps.splitlines():
        current = line.strip().removeprefix("- ").strip()
        if not current:
            continue
        if file_path in current:
            exact_match = current[:100] + "..." if len(current) > 100 else current
            break
    if exact_match:
        return exact_match
    for line in ai_steps.splitlines():
        current = line.strip().removeprefix("- ").strip()
        if not current:
            continue
        if basename in current:
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
        lines.extend(["- glossary：", indent_block(context.glossary_excerpt)])
    if context.architecture_excerpt:
        lines.extend(["- architecture：", indent_block(context.architecture_excerpt)])
    if context.patterns_excerpt:
        lines.extend(["- patterns：", indent_block(context.patterns_excerpt)])
    if context.gotchas_excerpt:
        lines.extend(["- gotchas：", indent_block(context.gotchas_excerpt)])
    if context.missing_files:
        lines.append(f"- 缺少 context 文件: {', '.join(context.missing_files)}")
    return "\n".join(lines) if lines else "- 无可用 context。"


def render_plan_knowledge_section(build: PlanBuild) -> str:
    return "## Approved Knowledge\n\n" + render_plan_knowledge_block(build)


def render_plan_knowledge_block(build: PlanBuild) -> str:
    if build.knowledge_brief_markdown.strip():
        return build.knowledge_brief_markdown.strip()
    return "- 当前未命中可用于 plan 的 approved knowledge。"


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


def render_design_candidate_summary(candidate_files: list[str]) -> str:
    if not candidate_files:
        return "  - 暂未命中候选文件，需要补充 context 或人工指定模块。"
    lines = [f"  - {file_path}" for file_path in candidate_files[:8]]
    remaining = len(candidate_files) - len(lines)
    if remaining > 0:
        lines.append(f"  - 其余 {remaining} 个候选文件见 plan.md")
    return "\n".join(lines)


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


def indent_block(content: str, prefix: str = "  ") -> str:
    stripped = content.strip()
    if not stripped:
        return f"{prefix}- 无"
    return "\n".join(f"{prefix}{line}" if line.strip() else line for line in stripped.splitlines())


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

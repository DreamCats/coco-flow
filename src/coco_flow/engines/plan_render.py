from __future__ import annotations

from pathlib import Path
import re

from .plan_models import (
    ComplexityAssessment,
    ContextSnapshot,
    GlossaryEntry,
    PlanAISections,
    PlanBuild,
    PlanExecutionSections,
    PlanTaskSpec,
    RefinedSections,
    ResearchFinding,
)
from .plan_research import dedupe_and_sort

MAX_TASK_ACTIONS = 4


def build_design(build: PlanBuild, ai: PlanAISections | None) -> str:
    repo_order = [scope.repo_id for scope in build.repo_scopes]
    tasks = build_plan_tasks(build.sections, build.finding, ai, build.repo_ids, repo_order)
    parts = [
        "# Design\n\n",
        f"- task_id: {build.task_id}\n",
        f"- title: {build.title}\n\n",
        "## 系统改造点\n\n",
        render_system_change_points(build.sections, ai),
        "\n\n",
        "## 方案设计\n\n",
        "### 总体方案\n\n",
        render_solution_overview(build, ai),
        "\n\n",
        "### 分系统改造\n\n",
        render_system_change_details(build, tasks, ai),
        "\n\n",
        "### 系统依赖关系\n\n",
        render_system_dependencies(build, tasks, ai),
        "\n\n",
        "### 关键链路说明\n\n",
        render_critical_flows(build, ai),
        "\n\n",
        "## 多端协议是否有变更\n\n",
        render_protocol_changes(build, ai),
        "\n\n",
        "## 存储&&配置是否有变更\n\n",
        render_storage_config_changes(build, ai),
        "\n\n",
        "## 是否有实验，实验怎么涉及\n\n",
        render_experiment_changes(build, ai),
        "\n\n",
        "## 给 QA 的输入\n\n",
        render_qa_inputs(build, ai),
        "\n\n",
        "## 人力评估\n\n",
        render_staffing_estimate(build, tasks, ai),
        "\n",
    ]
    return "".join(parts)


def build_plan(build: PlanBuild, ai: PlanAISections | None) -> str:
    execution = build_execution_sections(build, ai)
    parts = [
        "# Plan\n\n",
        f"- task_id: {build.task_id}\n",
        f"- title: {build.title}\n",
        f"- complexity: {build.assessment.level} ({build.assessment.total})\n\n",
        "## 实施策略\n\n",
        render_execution_strategy(build, execution.tasks, ai),
        "\n\n",
        "## 任务拆分\n\n",
        render_plan_tasks(execution.tasks),
        "\n\n",
        "## 执行顺序\n\n",
        render_execution_order(execution.tasks),
        "\n\n",
        "## 验证计划\n\n",
        render_validation_plan(execution.tasks, build.finding.notes, ai),
        "\n\n",
        "## 阻塞项与风险\n\n",
        render_blockers_and_risks(build, ai),
        "\n",
    ]
    return "".join(parts)


def build_execution_sections(build: PlanBuild, ai: PlanAISections | None) -> PlanExecutionSections:
    repo_order = [scope.repo_id for scope in build.repo_scopes]
    tasks = build_plan_tasks(build.sections, build.finding, ai, build.repo_ids, repo_order)
    strategy = parse_markdown_items(render_execution_strategy(build, tasks, ai))
    order = parse_markdown_items(render_execution_order(tasks))
    verification = parse_markdown_items(render_validation_plan(tasks, build.finding.notes, ai))
    blockers = parse_markdown_items(render_blockers_and_risks(build, ai))
    return PlanExecutionSections(
        execution_strategy=strategy,
        tasks=tasks,
        execution_order=order,
        verification_plan=verification,
        blockers_and_risks=blockers,
    )


def build_plan_tasks(
    sections: RefinedSections,
    findings: ResearchFinding,
    ai: PlanAISections | None,
    repo_ids: set[str] | None = None,
    repo_order: list[str] | None = None,
) -> list[PlanTaskSpec]:
    if not findings.candidate_files:
        return []

    ai_steps = ai.execution.steps if ai else ""
    repo_dir_files: dict[str, dict[str, list[str]]] = {}
    for file_path in findings.candidate_files:
        repo_id = infer_repo_id_from_file(file_path, repo_ids or set())
        _, relative_path = split_repo_prefixed_path(file_path, repo_ids or set())
        directory = str(Path(relative_path).parent)
        repo_bucket = repo_dir_files.setdefault(repo_id, {})
        repo_bucket.setdefault(directory, []).append(file_path)

    tasks: list[PlanTaskSpec] = []
    task_index = 1
    last_repo_task_id: dict[str, str] = {}
    previous_repo_last_task_id = ""
    ordered_repos = [repo for repo in (repo_order or []) if repo in repo_dir_files]
    for repo_id in sorted(repo_dir_files):
        if repo_id not in ordered_repos:
            ordered_repos.append(repo_id)

    change_point_ids = list(range(1, len(sections.change_scope) + 1))
    for repo_id in ordered_repos:
        repo_dirs = repo_dir_files.get(repo_id, {})
        for directory, files in repo_dirs.items():
            files = dedupe_and_sort(files)
            display_dir = render_task_directory(repo_id, directory)
            depends_on = build_task_dependencies(repo_id, last_repo_task_id, previous_repo_last_task_id)
            task_id = f"T{task_index}"
            actions = build_task_actions_for_scope(files, sections, ai_steps, repo_id=repo_id, display_dir=display_dir)
            tasks.append(
                PlanTaskSpec(
                    id=task_id,
                    title=build_plan_task_title(repo_id, display_dir, files, sections, ai_steps),
                    target_system_or_repo=repo_id,
                    serves_change_points=change_point_ids[:],
                    goal=build_plan_task_goal(repo_id, display_dir, sections, files),
                    depends_on=depends_on,
                    parallelizable_with=[],
                    change_scope=files,
                    actions=actions,
                    done_definition=build_done_definition(repo_id, display_dir, files),
                    verify_rule=["受影响 package 编译通过。"],
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
            return f"{repo_prefix}围绕「{feature}」收敛核心改造"
        return f"{repo_prefix}围绕「{feature}」调整 {display_dir}"
    return f"{repo_prefix}修改 {display_dir} 下相关文件"


def build_plan_task_goal(repo_id: str, display_dir: str, sections: RefinedSections, files: list[str]) -> str:
    repo_scope = f"在仓库 {repo_id}" if repo_id not in {"", "current-repo"} else "在当前仓库"
    feature = summarize_feature(sections)
    if feature:
        return f"{repo_scope}的 {display_dir} 中完成「{feature}」相关改动，并保持最小改动范围。"
    if len(files) == 1:
        return f"{repo_scope}围绕 {files[0]} 完成需求涉及的改动，并保证结果可验证。"
    return f"{repo_scope}的 {display_dir} 中完成需求涉及的改动，并保证结果可验证。"


def build_done_definition(repo_id: str, display_dir: str, files: list[str]) -> list[str]:
    outputs = [f"{display_dir} 范围内的改动已落地，并与依赖任务保持一致。"]
    if repo_id not in {"", "current-repo"}:
        outputs.append(f"仓库 {repo_id} 的改动边界已收敛，可继续推进后续任务。")
    if len(files) == 1:
        outputs.append(f"{files[0]} 的主要变更已完成。")
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
        feature_action = normalize_action_line(f"确保实现覆盖变更范围中的「{feature}」及其关键约束。")
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
    source = sections.change_scope[0] if sections.change_scope else ""
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


def render_system_change_points(sections: RefinedSections, ai: PlanAISections | None) -> str:
    items = parse_markdown_items(ai.design.system_change_points) if ai else []
    if not items:
        items = unique_items(sections.change_scope)
    if not items:
        return "- 当前未能从 refined PRD 中提取明确的系统改造点。"
    return "\n".join(f"- {item}" for item in items[:6])


def render_solution_overview(build: PlanBuild, ai: PlanAISections | None) -> str:
    lines: list[str] = []
    if ai and ai.design.solution_overview.strip():
        lines.extend(parse_markdown_items(ai.design.solution_overview))
    else:
        lines.append("优先在已有模块和明确候选文件范围内收敛最小改动。")
    if build.llm_scope.summary:
        lines.append(f"范围摘要：{build.llm_scope.summary}")
    if build.repo_lines:
        lines.append(f"涉及仓库：{', '.join(line.removeprefix('- ').strip() for line in build.repo_lines)}。")
    if build.context.available:
        lines.append("方案收敛时已参考本地 context 与代码调研结果。")
    if build.knowledge_brief_markdown.strip():
        lines.append("方案收敛时已参考 approved knowledge 中的稳定规则和验证要点。")
    return ensure_markdown_list("\n".join(lines))


def render_system_change_details(build: PlanBuild, tasks: list[PlanTaskSpec], ai: PlanAISections | None = None) -> str:
    research_lines: list[str] = []
    research_lines.extend(build.research_signals.system_summaries[:6])
    if ai and ai.design.solution_overview.strip():
        research_lines.extend(parse_markdown_items(ai.design.solution_overview))
    if not tasks and not research_lines:
        return "- 当前尚未形成稳定的分系统改造项，需要先收敛候选改动范围。"
    if not tasks:
        return "\n".join(f"- {item}" for item in research_lines[:6]) or "- 当前尚未形成稳定的分系统改造项，需要先收敛候选改动范围。"
    blocks: list[str] = []
    if research_lines:
        blocks.extend(f"- {item}" for item in research_lines[:6])
        blocks.append("")
    groups: dict[str, list[PlanTaskSpec]] = {}
    for task in tasks:
        groups.setdefault(task.target_system_or_repo, []).append(task)
    for system_id, system_tasks in groups.items():
        blocks.extend([f"### {system_id}", ""])
        blocks.append(f"- 主要职责：承接 {len(system_tasks)} 个执行任务，收敛当前需求在该系统/仓库内的改动。")
        blocks.append("- 涉及任务：")
        blocks.extend(f"  - {task.id} {task.title}" for task in system_tasks)
        blocks.append("- 计划改动：")
        for task in system_tasks:
            blocks.extend(f"  - {action}" for action in task.actions[:2])
        blocks.append("")
    return "\n".join(blocks).rstrip()


def render_system_dependencies(build: PlanBuild, tasks: list[PlanTaskSpec], ai: PlanAISections | None = None) -> str:
    lines: list[str] = []
    lines.extend(build.research_signals.system_dependencies[:6])
    if ai and ai.design.system_dependencies.strip():
        lines.extend(parse_markdown_items(ai.design.system_dependencies))
    for task in tasks:
        if task.depends_on:
            lines.append(f"- {task.id} 依赖 {', '.join(task.depends_on)}，应在上游任务完成后再推进。")
        else:
            lines.append(f"- {task.id} 可作为起始任务先行推进。")
    return "\n".join(f"- {item}" if not item.startswith("- ") else item for item in lines) if lines else "- 当前尚未形成可执行任务，暂无法给出系统依赖关系。"


def render_critical_flows(build: PlanBuild, ai: PlanAISections | None) -> str:
    lines: list[str] = []
    if ai and ai.design.critical_flows.strip():
        lines.extend(f"- {item}" for item in parse_markdown_items(ai.design.critical_flows))
    if build.research_signals.critical_flows:
        lines.extend(f"- {item}" for item in build.research_signals.critical_flows[:4])
    elif build.llm_scope.summary:
        lines.append(f"- 主链路概述：{build.llm_scope.summary}")
    if build.sections.change_scope:
        lines.append(f"- 入口目标：{build.sections.change_scope[0]}")
    if build.sections.key_constraints:
        lines.append(f"- 关键约束：{build.sections.key_constraints[0]}")
    if build.sections.non_goals:
        lines.append(f"- 非目标边界：{build.sections.non_goals[0]}")
    if build.sections.acceptance_criteria:
        lines.append(f"- 完成标志：{build.sections.acceptance_criteria[0]}")
    return "\n".join(lines) if lines else "- 当前未沉淀出额外的关键链路说明。"


def render_protocol_changes(build: PlanBuild, ai: PlanAISections | None = None) -> str:
    lines: list[str] = []
    if build.research_signals.protocol_changes:
        lines.extend(build.research_signals.protocol_changes)
    if ai and ai.design.protocol_changes.strip():
        lines.extend(parse_markdown_items(ai.design.protocol_changes))
    if lines:
        return "\n".join(f"- {item}" for item in unique_items(lines))
    matched_files = [
        file_path for file_path in build.finding.candidate_files if file_path.endswith((".proto", ".thrift")) or "/handler/" in file_path
    ]
    signal_text = "\n".join([*build.sections.change_scope, *build.sections.key_constraints, *build.sections.acceptance_criteria])
    if matched_files or contains_keywords(signal_text, "协议", "接口", "rpc", "字段", "请求", "返回"):
        lines = ["- 检测到可能存在多端协议或接口边界调整，需要重点确认上下游字段兼容性。"]
        if matched_files:
            lines.append("- 候选影响文件：")
            lines.extend(f"  - {file_path}" for file_path in matched_files[:6])
        return "\n".join(lines)
    return "- 当前未发现明确的多端协议变更信号。"


def render_storage_config_changes(build: PlanBuild, ai: PlanAISections | None = None) -> str:
    lines: list[str] = []
    if build.research_signals.storage_config_changes:
        lines.extend(build.research_signals.storage_config_changes)
    if ai and ai.design.storage_config_changes.strip():
        lines.extend(parse_markdown_items(ai.design.storage_config_changes))
    if lines:
        return "\n".join(f"- {item}" for item in unique_items(lines))
    matched_files = [
        file_path
        for file_path in build.finding.candidate_files
        if any(keyword in file_path.lower() for keyword in ("config", "dao", "repo", "model", "store"))
    ]
    signal_text = "\n".join([*build.sections.change_scope, *build.sections.key_constraints, *build.sections.non_goals])
    if matched_files or contains_keywords(signal_text, "数据库", "配置", "缓存", "tcc", "状态", "持久化"):
        lines = ["- 检测到可能存在存储或配置层变更，需要确认上线、回滚和默认行为。"]
        if matched_files:
            lines.append("- 候选影响文件：")
            lines.extend(f"  - {file_path}" for file_path in matched_files[:6])
        return "\n".join(lines)
    return "- 当前未发现明确的存储或配置变更信号。"


def render_experiment_changes(build: PlanBuild, ai: PlanAISections | None = None) -> str:
    lines: list[str] = []
    if build.research_signals.experiment_changes:
        lines.extend(build.research_signals.experiment_changes)
    if ai and ai.design.experiment_changes.strip():
        lines.extend(parse_markdown_items(ai.design.experiment_changes))
    if lines:
        return "\n".join(f"- {item}" for item in unique_items(lines))
    signal_text = "\n".join([*build.sections.change_scope, *build.sections.key_constraints, *build.sections.open_questions])
    if contains_keywords(signal_text, "实验", "灰度", "开关", "ab", "bucket"):
        return "\n".join(
            [
                "- 检测到可能存在实验或灰度开关影响，需要确认实验入口、流量范围和回滚策略。",
                "- 建议在进入 code 前补齐实验开关位置和生效链路。",
            ]
        )
    return "- 当前未发现明确的实验设计变更信号。"


def render_qa_inputs(build: PlanBuild, ai: PlanAISections | None) -> str:
    lines: list[str] = []
    if build.research_signals.qa_inputs:
        lines.extend(f"- {item}" for item in build.research_signals.qa_inputs[:8])
    if ai and ai.design.qa_inputs.strip():
        lines.extend(f"- {item}" for item in parse_markdown_items(ai.design.qa_inputs))
    if build.sections.acceptance_criteria:
        lines.append("- 主链路测试建议：")
        lines.extend(f"  - {item}" for item in build.sections.acceptance_criteria[:4])
    if build.sections.key_constraints:
        lines.append("- 关键约束校验：")
        lines.extend(f"  - {item}" for item in build.sections.key_constraints[:4])
    if build.sections.non_goals:
        lines.append("- 非目标回归：")
        lines.extend(f"  - 重点确认 {item}" for item in build.sections.non_goals[:3])
    if build.sections.open_questions:
        lines.append("- 待确认项：")
        lines.extend(f"  - {item}" for item in build.sections.open_questions[:4])
    return "\n".join(lines) if lines else "- 当前未生成额外 QA 输入。"


def render_staffing_estimate(build: PlanBuild, tasks: list[PlanTaskSpec], ai: PlanAISections | None = None) -> str:
    if ai and ai.design.staffing_estimate.strip():
        return ensure_markdown_list(ai.design.staffing_estimate)
    lines = [
        f"- 当前复杂度评估：{build.assessment.level} ({build.assessment.total})。",
        f"- 涉及仓库数：{len(build.repo_scopes)}。",
        f"- 当前任务拆分数：{len(tasks)}。",
        "- 当前未生成精确人天估算，建议在任务拆分评审后补齐具体人力安排。",
    ]
    return "\n".join(lines)


def render_execution_strategy(build: PlanBuild, tasks: list[PlanTaskSpec], ai: PlanAISections | None) -> str:
    lines = ["- 优先围绕受影响系统/仓库收敛最小改动范围，再按依赖顺序推进实现。"]
    if ai and ai.execution.execution_strategy.strip():
        lines.extend(parse_markdown_items(ai.execution.execution_strategy))
    if tasks:
        lines.append(f"- 建议从 {tasks[0].id} 开始执行，并按任务依赖逐步收口。")
    if build.llm_scope.summary:
        lines.append(f"- 范围摘要：{build.llm_scope.summary}")
    if build.llm_scope.priorities:
        lines.extend(f"- 优先事项：{item}" for item in build.llm_scope.priorities[:3])
    if build.assessment.total > 6:
        lines.append("- 当前复杂度偏高，建议先人工确认关键依赖，再决定是否进入自动 code。")
    return ensure_markdown_list("\n".join(lines))


def render_plan_tasks(tasks: list[PlanTaskSpec]) -> str:
    if not tasks:
        return "- 暂未生成任务拆分，需要先收敛候选改动范围。"
    blocks: list[str] = []
    for task in tasks:
        blocks.extend(
            [
                f"### {task.id} {task.title}",
                "",
                f"- 目标系统/仓库：{task.target_system_or_repo}",
                f"- 服务改造点：{', '.join(str(item) for item in task.serves_change_points) if task.serves_change_points else '无'}",
                f"- 目标：{task.goal}",
                f"- 依赖：{', '.join(task.depends_on) if task.depends_on else '无'}",
                f"- 可并行任务：{', '.join(task.parallelizable_with) if task.parallelizable_with else '无'}",
                "- 修改范围：",
            ]
        )
        blocks.extend(f"  - {item}" for item in task.change_scope)
        blocks.append("- 实施动作：")
        blocks.extend(f"  - {item}" for item in task.actions)
        blocks.append("- 完成定义：")
        blocks.extend(f"  - {item}" for item in task.done_definition)
        blocks.append("- 验证方式：")
        blocks.extend(f"  - {item}" for item in task.verify_rule)
        blocks.append("")
    return "\n".join(blocks).rstrip()


def render_execution_order(tasks: list[PlanTaskSpec]) -> str:
    if not tasks:
        return "- 当前尚未生成执行顺序，需要先完成任务拆分。"
    lines: list[str] = [f"- 推荐执行主顺序：{' -> '.join(task.id for task in tasks)}。"]
    for task in tasks:
        if task.depends_on:
            lines.append(f"- {task.id} 需在 {', '.join(task.depends_on)} 完成后执行。")
        else:
            lines.append(f"- {task.id} 可作为起始任务推进。")
    return "\n".join(lines)


def render_validation_plan(tasks: list[PlanTaskSpec], notes: list[str], ai: PlanAISections | None = None) -> str:
    lines = [
        "- 默认只做受影响 package 的编译验证，不展开全量测试矩阵。",
        "- 若涉及多仓库任务，则按各仓库受影响 package 分别完成编译验证。",
    ]
    if ai and ai.execution.validation_plan.strip():
        lines.extend(parse_markdown_items(ai.execution.validation_plan))
    for task in tasks:
        lines.append(f"- {task.id}：{' '.join(task.verify_rule)}")
    if notes:
        lines.extend(f"- 风险提醒：{note}" for note in notes[:3])
    return "\n".join(lines)


def render_blockers_and_risks(build: PlanBuild, ai: PlanAISections | None) -> str:
    lines: list[str] = []
    if build.assessment.total > 6:
        lines.append("- 当前需求复杂度超过自动推进阈值，建议先人工确认依赖和拆分策略。")
    if ai and ai.execution.blockers_and_risks.strip():
        lines.extend(f"- {item}" for item in parse_markdown_items(ai.execution.blockers_and_risks))
    elif build.finding.notes:
        lines.extend(f"- {note}" for note in build.finding.notes)
    if build.sections.open_questions:
        lines.append("- 当前待确认项：")
        lines.extend(f"  - {item}" for item in build.sections.open_questions[:5])
    return "\n".join(lines) if lines else "- 当前未发现额外阻塞项与风险。"


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


def render_plan_scope_block(build: PlanBuild) -> str:
    scope = build.llm_scope
    if not any([scope.summary, scope.boundaries, scope.priorities, scope.risk_focus, scope.validation_focus]):
        return "- 当前未生成额外的 plan scope 摘要。"
    lines: list[str] = []
    if scope.summary:
        lines.append(f"- summary: {scope.summary}")
    if scope.boundaries:
        lines.append("- boundaries:")
        lines.extend(f"  - {item}" for item in scope.boundaries)
    if scope.priorities:
        lines.append("- priorities:")
        lines.extend(f"  - {item}" for item in scope.priorities)
    if scope.risk_focus:
        lines.append("- risk_focus:")
        lines.extend(f"  - {item}" for item in scope.risk_focus)
    if scope.validation_focus:
        lines.append("- validation_focus:")
        lines.extend(f"  - {item}" for item in scope.validation_focus)
    return "\n".join(lines)


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
    if ai and ai.design.solution_overview.strip():
        return ensure_markdown_list(ai.design.solution_overview)
    lines = [
        "- 基于 refined PRD、context 和本地调研结果收敛改动范围。",
        "- 优先在已有模块中收敛实现，保持最小改动范围。",
    ]
    if assessment.total > 6:
        lines.append("- 当前需求复杂度偏高，建议先人工拆解，不直接进入自动实现。")
    else:
        lines.append("- 先完成最小验证路径，再决定是否继续扩展。")
    return "\n".join(lines)


def render_risk_section(ai: PlanAISections | None, notes: list[str]) -> str:
    if ai and ai.execution.blockers_and_risks.strip():
        return "\n".join(f"- {item}" for item in parse_markdown_items(ai.execution.blockers_and_risks))
    if notes:
        return "\n".join(f"- {note}" for note in notes)
    return "- 当前未发现额外风险补充。"


def render_requirement_summary(sections: RefinedSections, source_markdown: str) -> str:
    items = []
    for change in sections.change_scope[:4]:
        items.append(f"- 变更范围：{change}")
    for non_goal in sections.non_goals[:3]:
        items.append(f"- 非目标：{non_goal}")
    if not items:
        excerpt = extract_excerpt(source_markdown)
        return excerpt or "- 当前尚未提取到有效需求内容。"
    return "\n".join(items)


def render_goal_list(sections: RefinedSections) -> str:
    if not sections.change_scope:
        return "- 基于 refined PRD 补全实现目标。"
    return "\n".join(f"- {item}" for item in sections.change_scope)


def render_open_questions(open_questions: list[str]) -> str:
    if not open_questions:
        return "- 无额外待确认项。"
    return "\n".join(f"- {item}" for item in open_questions)


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


def parse_markdown_items(content: str) -> list[str]:
    items: list[str] = []
    for line in ensure_markdown_list(content).splitlines():
        stripped = line.strip().removeprefix("- ").strip()
        if stripped and stripped != "无":
            items.append(stripped)
    return items


def unique_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        lowered = item.lower().strip()
        if not lowered or lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(item)
    return ordered


def contains_keywords(content: str, *keywords: str) -> bool:
    lowered = content.lower()
    return any(keyword.lower() in lowered for keyword in keywords if keyword)

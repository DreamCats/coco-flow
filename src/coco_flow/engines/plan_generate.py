from __future__ import annotations

import os
from pathlib import Path

import json

from .plan_models import DesignAISections, ExecutionAISections, PlanBuild, PlanScope
from .plan_render import (
    render_context_snapshot,
    render_glossary_hits,
    render_list_block,
    render_plan_knowledge_block,
)
from .plan_research import dedupe_and_sort

MAX_SEARCH_FILES = 8

DESIGN_SECTION_MARKERS = {
    "system_change_points": "=== SYSTEM CHANGE POINTS ===",
    "solution_overview": "=== SOLUTION OVERVIEW ===",
    "system_dependencies": "=== SYSTEM DEPENDENCIES ===",
    "critical_flows": "=== CRITICAL FLOWS ===",
    "interface_changes": "=== INTERFACE CHANGES ===",
    "risk_boundaries": "=== RISK BOUNDARIES ===",
}

EXECUTION_SECTION_MARKERS = {
    "execution_strategy": "=== EXECUTION STRATEGY ===",
    "candidate_files": "=== CANDIDATE FILES ===",
    "steps": "=== TASK STEPS ===",
    "blockers_and_risks": "=== BLOCKERS AND RISKS ===",
    "validation_plan": "=== VALIDATION PLAN ===",
}


def build_design_prompt(build: PlanBuild) -> str:
    repo_section = "\n".join(build.repo_lines) if build.repo_lines else "- current-repo"
    matched_terms = render_glossary_hits(build.finding.matched_terms)
    unmatched_terms = render_list_block(build.finding.unmatched_terms, default="  - 无")
    candidate_files = render_list_block(build.finding.candidate_files, default="  - 无")
    candidate_dirs = render_list_block(build.finding.candidate_dirs, default="  - 无")
    local_notes = render_list_block(build.finding.notes, default="  - 无")
    return f"""你是一名资深技术设计助手。基于提供的 refined PRD、本地 context 和代码调研结果，输出面向研发的 design 内容。

要求：
1. 只能基于提供的信息工作，不要编造未出现的模块、文件、接口或风险结论。
2. 重点服务 design.md，不要写成执行任务列表。
3. 输出必须严格使用下面的标记格式：
{DESIGN_SECTION_MARKERS["system_change_points"]}
- ...
{DESIGN_SECTION_MARKERS["solution_overview"]}
- ...
{DESIGN_SECTION_MARKERS["system_dependencies"]}
- ...
{DESIGN_SECTION_MARKERS["critical_flows"]}
- ...
{DESIGN_SECTION_MARKERS["interface_changes"]}
- ...
{DESIGN_SECTION_MARKERS["risk_boundaries"]}
- ...
4. 不要输出其它前言或解释。

## PRD Refined
{build.sections.raw or build.refined_markdown}

## 任务关联仓库
{repo_section}

## Context 摘要
{render_context_snapshot(build.context)}

## Approved Knowledge Brief
{render_plan_knowledge_block(build)}

## Plan Scope
{render_plan_scope_summary(build.llm_scope)}

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
"""


def extract_design_outputs(raw: str) -> tuple[DesignAISections, bool]:
    payload, ok = extract_marked_sections(raw, DESIGN_SECTION_MARKERS)
    if not ok:
        return DesignAISections(), False
    return DesignAISections(**payload), True


def validate_design_outputs(build: PlanBuild, ai: DesignAISections) -> None:
    combined = "\n".join(
        [
            ai.system_change_points,
            ai.solution_overview,
            ai.system_dependencies,
            ai.critical_flows,
            ai.interface_changes,
            ai.risk_boundaries,
        ]
    )
    for marker in ("(待生成)", "(待确认)", "未初始化"):
        if marker in combined:
            raise ValueError(f"AI design 输出包含无效占位符: {marker}")
    if not ai.system_change_points.strip():
        raise ValueError("AI design 缺少系统改造点")
    if not ai.solution_overview.strip():
        raise ValueError("AI design 缺少总体方案")
    if not ai.system_dependencies.strip():
        raise ValueError("AI design 缺少系统依赖关系")


def build_design_verify_prompt(build: PlanBuild, ai: DesignAISections) -> str:
    return f"""你在做 coco-flow design verifier。

目标：检查 design generator 的输出是否满足设计文档需要的结构和边界。

要求：
1. 只输出 JSON 对象，不要输出其它文字。
2. 输出格式：
{{
  "ok": true,
  "issues": ["问题1"],
  "reason": "一句话结论"
}}
3. 重点检查：
   - 系统改造点是否清楚
   - 总体方案和系统依赖关系是否完整
   - 是否把接口变更与风险边界至少给出明确结论
   - 是否明显脱离当前候选文件和调研范围

## Scope
{render_plan_scope_summary(build.llm_scope)}

## Candidate Files Baseline
{render_list_block(build.finding.candidate_files, default="  - 无")}

## Design Output
system_change_points:
{ai.system_change_points}

solution_overview:
{ai.solution_overview}

system_dependencies:
{ai.system_dependencies}

critical_flows:
{ai.critical_flows}

interface_changes:
{ai.interface_changes}

risk_boundaries:
{ai.risk_boundaries}
"""


def build_execution_prompt(build: PlanBuild, design_ai: DesignAISections) -> str:
    repo_section = "\n".join(build.repo_lines) if build.repo_lines else "- current-repo"
    candidate_files = render_list_block(build.finding.candidate_files, default="  - 无")
    candidate_dirs = render_list_block(build.finding.candidate_dirs, default="  - 无")
    local_notes = render_list_block(build.finding.notes, default="  - 无")
    return f"""你是一名资深研发计划助手。基于 refined PRD、design 结论、本地调研结果和候选文件，输出面向执行的 plan 内容。

要求：
1. 只能基于提供的信息工作，不要编造新模块或新文件。
2. 重点服务 plan.md，不要重写设计背景。
3. 输出必须严格使用下面的标记格式：
{EXECUTION_SECTION_MARKERS["execution_strategy"]}
- ...
{EXECUTION_SECTION_MARKERS["candidate_files"]}
- path/to/file1.go
- path/to/file2.go
{EXECUTION_SECTION_MARKERS["steps"]}
- ...
{EXECUTION_SECTION_MARKERS["blockers_and_risks"]}
- ...
{EXECUTION_SECTION_MARKERS["validation_plan"]}
- ...
4. 不要输出其它前言或解释。

## PRD Refined
{build.sections.raw or build.refined_markdown}

## 任务关联仓库
{repo_section}

## Design 结论
system_change_points:
{ai_list_or_default(design_ai.system_change_points)}

solution_overview:
{ai_list_or_default(design_ai.solution_overview)}

system_dependencies:
{ai_list_or_default(design_ai.system_dependencies)}

critical_flows:
{ai_list_or_default(design_ai.critical_flows)}

interface_changes:
{ai_list_or_default(design_ai.interface_changes)}

risk_boundaries:
{ai_list_or_default(design_ai.risk_boundaries)}

## Plan Scope
{render_plan_scope_summary(build.llm_scope)}

## Candidate Files Baseline
{candidate_files}

## Candidate Dirs Baseline
{candidate_dirs}

## Local Notes
{local_notes}

## Complexity
- level: {build.assessment.level}
- total: {build.assessment.total}
"""


def build_execution_prompt_from_design_markdown(build: PlanBuild, design_markdown: str) -> str:
    repo_section = "\n".join(build.repo_lines) if build.repo_lines else "- current-repo"
    candidate_files = render_list_block(build.finding.candidate_files, default="  - 无")
    candidate_dirs = render_list_block(build.finding.candidate_dirs, default="  - 无")
    local_notes = render_list_block(build.finding.notes, default="  - 无")
    return f"""你是一名资深研发计划助手。基于 refined PRD、已有 design 文档、本地调研结果和候选文件，输出面向执行的 plan 内容。

要求：
1. 只能基于提供的信息工作，不要编造新模块或新文件。
2. 重点服务 plan.md，不要重写设计背景。
3. 输出必须严格使用下面的标记格式：
{EXECUTION_SECTION_MARKERS["execution_strategy"]}
- ...
{EXECUTION_SECTION_MARKERS["candidate_files"]}
- path/to/file1.go
- path/to/file2.go
{EXECUTION_SECTION_MARKERS["steps"]}
- ...
{EXECUTION_SECTION_MARKERS["blockers_and_risks"]}
- ...
{EXECUTION_SECTION_MARKERS["validation_plan"]}
- ...
4. 不要输出其它前言或解释。

## PRD Refined
{build.sections.raw or build.refined_markdown}

## 任务关联仓库
{repo_section}

## Existing Design
{design_markdown.strip() or "- 当前没有可用的 design.md。"}

## Candidate Files Baseline
{candidate_files}

## Candidate Dirs Baseline
{candidate_dirs}

## Local Notes
{local_notes}

## Complexity
- level: {build.assessment.level}
- total: {build.assessment.total}
"""


def extract_execution_outputs(raw: str) -> tuple[ExecutionAISections, bool]:
    payload, ok = extract_marked_sections(raw, EXECUTION_SECTION_MARKERS)
    if not ok:
        return ExecutionAISections(), False
    return ExecutionAISections(**payload), True


def validate_execution_outputs(build: PlanBuild, ai: ExecutionAISections) -> None:
    combined = "\n".join([ai.execution_strategy, ai.steps, ai.blockers_and_risks, ai.validation_plan])
    for marker in ("(待生成)", "(待确认)", "未初始化"):
        if marker in combined:
            raise ValueError(f"AI execution 输出包含无效占位符: {marker}")
    if not ai.execution_strategy.strip():
        raise ValueError("AI execution 缺少实施策略")
    if build.assessment.total <= 6 and not ai.steps.strip():
        raise ValueError("AI execution 缺少实施步骤")
    for bad in ("/livecoding:prd-refine", "/livecoding:prd-plan"):
        if bad in combined:
            raise ValueError(f"AI execution 包含错误命令示例: {bad}")


def build_execution_verify_prompt(build: PlanBuild, ai: ExecutionAISections) -> str:
    return f"""你在做 coco-flow execution verifier。

目标：检查执行计划输出是否与当前调研范围、复杂度和候选文件一致。

要求：
1. 只输出 JSON 对象，不要输出其它文字。
2. 输出格式：
{{
  "ok": true,
  "issues": ["问题1"],
  "reason": "一句话结论"
}}
3. 重点检查：
   - execution_strategy / steps / blockers_and_risks / validation_plan 是否完整
   - candidate_files 是否与本地候选范围明显冲突
   - 验证计划是否保持“受影响 package 编译通过”的最小原则

## Scope
{render_plan_scope_summary(build.llm_scope)}

## Candidate Files Baseline
{render_list_block(build.finding.candidate_files, default="  - 无")}

## Complexity
- level: {build.assessment.level}
- total: {build.assessment.total}

## Execution Output
execution_strategy:
{ai.execution_strategy}

candidate_files:
{ai.candidate_files}

steps:
{ai.steps}

blockers_and_risks:
{ai.blockers_and_risks}

validation_plan:
{ai.validation_plan}
"""


def build_plan_scope_prompt(build: PlanBuild) -> str:
    repo_section = "\n".join(build.repo_lines) if build.repo_lines else "- current-repo"
    candidate_files = render_list_block(build.finding.candidate_files, default="  - 无")
    candidate_dirs = render_list_block(build.finding.candidate_dirs, default="  - 无")
    notes = render_list_block(build.finding.notes, default="  - 无")
    return f"""你在做 coco-flow plan scope extraction。

目标：基于当前 refined PRD、knowledge brief、context 和本地调研结果，提炼后续 plan generator 的实施边界。

要求：
1. 只输出 JSON 对象，不要输出其它文字。
2. 不要编造新模块或新文件。
3. 输出格式：
{{
  "summary": "一句话范围总结",
  "boundaries": ["边界1", "边界2"],
  "priorities": ["优先事项1", "优先事项2"],
  "risk_focus": ["风险焦点1", "风险焦点2"],
  "validation_focus": ["验证重点1", "验证重点2"]
}}

## PRD Refined
{build.sections.raw or build.refined_markdown}

## 任务关联仓库
{repo_section}

## Approved Knowledge Brief
{render_plan_knowledge_block(build)}

## candidate files
{candidate_files}

## candidate dirs
{candidate_dirs}

## local notes
{notes}
"""


def extract_plan_scope_output(raw: str) -> PlanScope:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid_plan_scope_json: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("plan_scope_output_is_not_object")
    return PlanScope(
        summary=str(payload.get("summary") or "").strip(),
        boundaries=_normalized_list(payload.get("boundaries")),
        priorities=_normalized_list(payload.get("priorities")),
        risk_focus=_normalized_list(payload.get("risk_focus")),
        validation_focus=_normalized_list(payload.get("validation_focus")),
    )


def parse_plan_verify_output(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid_plan_verify_json: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("plan_verify_output_is_not_object")
    return {
        "ok": bool(payload.get("ok")),
        "issues": [str(item) for item in payload.get("issues", []) if str(item).strip()],
        "reason": str(payload.get("reason") or ""),
    }


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
            relative = candidate_absolute[len(repo_prefix) :].lstrip("/\\")
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


def extract_marked_sections(raw: str, markers: dict[str, str]) -> tuple[dict[str, str], bool]:
    normalized = raw.replace("\r\n", "\n")
    indexes = {field_name: normalized.find(marker) for field_name, marker in markers.items()}
    first_field = next(iter(markers))
    if indexes[first_field] == -1:
        return {field_name: "" for field_name in markers}, False

    payload: dict[str, str] = {}
    ordered = list(markers.items())
    for index, (field_name, marker) in enumerate(ordered):
        start = indexes[field_name]
        if start == -1:
            payload[field_name] = ""
            continue
        content_start = start + len(marker)
        end = len(normalized)
        for next_field_name, _ in ordered[index + 1 :]:
            next_index = indexes[next_field_name]
            if next_index != -1 and next_index > start:
                end = next_index
                break
        payload[field_name] = normalize_ai_section(normalized[content_start:end])
    return payload, True


def normalize_ai_section(content: str) -> str:
    cleaned = content.strip()
    lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("("):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def qualify_repo_path(repo_id: str, path: str, repo_count: int) -> str:
    normalized = path.strip().lstrip("./")
    if not normalized:
        return normalized
    if repo_count <= 1:
        return normalized
    return f"{repo_id}/{normalized}"


def split_repo_prefixed_path(file_path: str, repo_ids: set[str]) -> tuple[str, str]:
    normalized = file_path.strip().lstrip("./")
    first = Path(normalized).parts[0] if Path(normalized).parts else ""
    if first and first in repo_ids:
        rest_parts = Path(normalized).parts[1:]
        relative_path = str(Path(*rest_parts)) if rest_parts else ""
        return first, relative_path or normalized
    return "", normalized


def render_plan_scope_summary(scope: PlanScope) -> str:
    if not any([scope.summary, scope.boundaries, scope.priorities, scope.risk_focus, scope.validation_focus]):
        return "- 无额外 scope 摘要。"
    lines = []
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


def ai_list_or_default(content: str) -> str:
    return content.strip() or "- 无"


def _normalized_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        current = str(item).strip()
        if not current:
            continue
        lowered = current.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(current[:160])
    return result

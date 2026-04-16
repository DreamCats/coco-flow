from __future__ import annotations

import os
from pathlib import Path

import json

from .plan_models import PlanAISections, PlanBuild, PlanScope
from .plan_render import (
    render_context_snapshot,
    render_glossary_hits,
    render_list_block,
    render_plan_knowledge_block,
)
from .plan_research import dedupe_and_sort

MAX_SEARCH_FILES = 8

SECTION_MARKERS = {
    "summary": "=== IMPLEMENTATION SUMMARY ===",
    "candidate_files": "=== CANDIDATE FILES ===",
    "steps": "=== IMPLEMENTATION STEPS ===",
    "risks": "=== RISK NOTES ===",
    "validation_extra": "=== VALIDATION EXTRA ===",
}


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


def build_plan_verify_prompt(build: PlanBuild, ai: PlanAISections) -> str:
    return f"""你在做 coco-flow plan verifier。

目标：检查 plan generator 的输出是否与当前调研范围、复杂度和候选文件一致。

要求：
1. 只输出 JSON 对象，不要输出其它文字。
2. 输出格式：
{{
  "ok": true,
  "issues": ["问题1"],
  "reason": "一句话结论"
}}
3. 重点检查：
   - summary / steps / risks 是否完整
   - candidate_files 是否与本地候选范围明显冲突
   - 若复杂度偏高，是否在输出里保留足够风险提示

## Scope
{render_plan_scope_summary(build.llm_scope)}

## Candidate Files Baseline
{render_list_block(build.finding.candidate_files, default="  - 无")}

## Complexity
- level: {build.assessment.level}
- total: {build.assessment.total}

## Generator Output
summary:
{ai.summary}

candidate_files:
{ai.candidate_files}

steps:
{ai.steps}

risks:
{ai.risks}

validation_extra:
{ai.validation_extra}
"""


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

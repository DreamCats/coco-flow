"""Plan 结构化产物构建。

把 doc-only Design 编译成 Code 阶段可消费的任务、依赖图、验证契约和分仓 Markdown。
"""

from __future__ import annotations

from pathlib import Path
import re

from coco_flow.engines.plan.types import PlanPreparedInput
from coco_flow.engines.shared.contracts import (
    build_design_contracts_payload,
    extract_repo_sections,
    is_consumer_section,
    is_producer_section,
    looks_like_shared_repo,
    shared_dependency_signal,
)

_FILE_RE = re.compile(r"[\w./-]+\.(?:go|py|ts|tsx|js|jsx|proto|thrift|sql)")


def build_structured_plan_artifacts(prepared: PlanPreparedInput) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, str]]:
    repo_sections = extract_repo_sections(prepared.design_markdown, [scope.repo_id for scope in prepared.repo_scopes])
    work_items: list[dict[str, object]] = []

    for index, scope in enumerate(prepared.repo_scopes, start=1):
        section = repo_sections.get(scope.repo_id, "")
        files = _extract_files(section, scope.repo_id)
        steps = _extract_steps(section) or prepared.refined_sections.change_scope or [prepared.title]
        item = {
            "id": f"W{index}",
            "repo_id": scope.repo_id,
            "title": _infer_task_title(scope.repo_id, section, prepared.title),
            "goal": _infer_goal(scope.repo_id, section, prepared.title),
            "change_scope": files,
            "specific_steps": steps[:8],
            "done_definition": _done_definition(scope.repo_id, prepared.refined_sections.acceptance_criteria),
            "verification_steps": _verification_steps(scope.repo_id, prepared.refined_sections.acceptance_criteria),
            "depends_on": [],
            "blocks": [],
        }
        work_items.append(item)

    _apply_dependency_upgrade_tasks(work_items, prepared)
    edges, coordination_points = _infer_edges_and_coordination(work_items, repo_sections, prepared)
    depends_by_task = _depends_by_task(edges)
    blocks_by_task = _blocks_by_task(edges)
    for item in work_items:
        task_id = str(item.get("id") or "")
        item["depends_on"] = depends_by_task.get(task_id, [])
        item["blocks"] = blocks_by_task.get(task_id, [])

    execution_order = _topological_order([str(item["id"]) for item in work_items], edges)
    graph_payload = {
        "nodes": [
            {"task_id": item["id"], "repo_id": item["repo_id"], "title": item["title"]}
            for item in work_items
        ],
        "edges": edges,
        "execution_order": execution_order,
        "parallel_groups": _parallel_groups(execution_order, edges),
        "critical_path": _critical_path(execution_order, edges),
        "coordination_points": coordination_points,
    }
    work_items_payload = {"work_items": work_items}
    validation_payload = _build_validation_payload(work_items, prepared)
    blockers = _extract_blockers(prepared)
    plan_result_payload = {
        "status": "planned",
        "gate_status": "blocked_by_open_questions" if blockers else "passed",
        "code_allowed": not blockers,
        "blockers": blockers,
        "issues": [],
        "artifact_summary": {
            "work_item_count": len(work_items),
            "edge_count": len(edges),
            "repo_count": len(prepared.repo_scopes),
        },
    }
    repo_markdowns = {str(item["repo_id"]): render_repo_task_markdown(item, graph_payload, blockers) for item in work_items}
    return work_items_payload, graph_payload, validation_payload, plan_result_payload, repo_markdowns


def build_structured_plan_artifacts_from_repo_markdowns(
    prepared: PlanPreparedInput,
    repo_markdowns: dict[str, str],
    previous_work_items_payload: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    previous_items = {
        str(item.get("repo_id") or ""): item
        for item in _dict_list((previous_work_items_payload or {}).get("work_items"))
        if item.get("repo_id")
    }
    work_items: list[dict[str, object]] = []
    for index, scope in enumerate(prepared.repo_scopes, start=1):
        previous = previous_items.get(scope.repo_id, {})
        item = _parse_repo_task_markdown(repo_markdowns.get(scope.repo_id, ""), scope.repo_id, index, previous, prepared)
        work_items.append(item)

    edges = _edges_from_work_items(work_items, prepared)
    depends_by_task = _depends_by_task(edges)
    blocks_by_task = _blocks_by_task(edges)
    for item in work_items:
        task_id = str(item.get("id") or "")
        item["depends_on"] = depends_by_task.get(task_id, [])
        item["blocks"] = blocks_by_task.get(task_id, [])

    execution_order = _topological_order([str(item["id"]) for item in work_items], edges)
    graph_payload = {
        "nodes": [
            {"task_id": item["id"], "repo_id": item["repo_id"], "title": item["title"]}
            for item in work_items
        ],
        "edges": edges,
        "execution_order": execution_order,
        "parallel_groups": _parallel_groups(execution_order, edges),
        "critical_path": _critical_path(execution_order, edges),
        "coordination_points": [],
    }
    validation_payload = _build_validation_payload(work_items, prepared)
    blockers = _dedupe(_extract_blockers(prepared) + _extract_repo_markdown_blockers(repo_markdowns))
    plan_result_payload = {
        "status": "planned",
        "gate_status": "blocked_by_open_questions" if blockers else "passed",
        "code_allowed": not blockers,
        "blockers": blockers,
        "issues": [],
        "artifact_summary": {
            "work_item_count": len(work_items),
            "edge_count": len(edges),
            "repo_count": len(prepared.repo_scopes),
            "sync_source": "repo_markdown",
        },
    }
    return {"work_items": work_items}, graph_payload, validation_payload, plan_result_payload


def render_plan_markdown(
    prepared: PlanPreparedInput,
    work_items_payload: dict[str, object],
    graph_payload: dict[str, object],
    validation_payload: dict[str, object],
    result_payload: dict[str, object],
) -> str:
    work_items = _dict_list(work_items_payload.get("work_items"))
    blockers = [str(item).strip() for item in _object_list(result_payload.get("blockers")) if str(item).strip()]
    lines = [
        "# Plan",
        "",
        f"- task_id: {prepared.task_id}",
        f"- title: {prepared.title}",
        f"- repos: {', '.join(scope.repo_id for scope in prepared.repo_scopes)}",
        f"- code_allowed: {str(result_payload.get('code_allowed')).lower()}",
        "",
        "## 任务清单",
        "",
    ]
    for item in work_items:
        lines.extend(_render_work_item_block(item))
    lines.extend(["## 关系图", ""])
    lines.extend(_render_graph_summary(graph_payload))
    lines.extend(["", "## 跨仓契约", ""])
    lines.extend(_render_contracts_summary(graph_payload))
    lines.extend(["", "## 执行顺序", ""])
    lines.append("- execution_order: " + ", ".join(_string_list(graph_payload.get("execution_order"))) if graph_payload.get("execution_order") else "- execution_order: none")
    edges = _dict_list(graph_payload.get("edges"))
    if edges:
        lines.append("- hard_dependencies:")
        for edge in edges:
            lines.append(f"  - {edge.get('from')} -> {edge.get('to')}: {edge.get('reason')}")
    else:
        lines.append("- hard_dependencies: none")
    parallel_groups = _object_list(graph_payload.get("parallel_groups"))
    lines.append("- parallel_groups: " + (str(parallel_groups) if parallel_groups else "none"))
    coordination_points = _dict_list(graph_payload.get("coordination_points"))
    if coordination_points:
        lines.append("- coordination_points:")
        for point in coordination_points:
            lines.append(f"  - {point.get('id')}: {point.get('title')} ({point.get('reason')})")
    else:
        lines.append("- coordination_points: none")

    lines.extend(["", "## 验证策略", ""])
    lines.extend(_render_validation_summary(validation_payload))
    lines.extend(["", "## 风险与阻塞项", ""])
    if blockers:
        lines.append("- blockers:")
        lines.extend(f"  - {item}" for item in blockers)
    else:
        lines.append("- blockers: none")
    lines.append("- risks:")
    lines.append("  - 如果执行时发现 design.md 与真实代码职责不一致，先回到 Design 文档修正后再继续。")
    return "\n".join(lines).rstrip() + "\n"


def render_repo_task_markdown(
    work_item: dict[str, object],
    graph_payload: dict[str, object],
    blockers: list[str],
) -> str:
    repo_id = str(work_item.get("repo_id") or "")
    lines = [f"# {repo_id} Plan", "", *_render_repo_task_block(work_item)]
    related_edges = [
        edge for edge in _dict_list(graph_payload.get("edges"))
        if edge.get("from") == work_item.get("id") or edge.get("to") == work_item.get("id")
    ]
    lines.extend(["## 依赖关系", ""])
    if related_edges:
        for edge in related_edges:
            lines.append(f"- {edge.get('from')} -> {edge.get('to')}: {edge.get('reason')}")
    else:
        lines.append("- none")
    input_contracts = [edge for edge in related_edges if edge.get("to") == work_item.get("id") and isinstance(edge.get("contract"), dict)]
    output_contracts = [edge for edge in related_edges if edge.get("from") == work_item.get("id") and isinstance(edge.get("contract"), dict)]
    if output_contracts:
        lines.extend(["", "## 输出契约", ""])
        for edge in output_contracts:
            lines.extend(_render_repo_contract(edge, direction="output"))
    if input_contracts:
        lines.extend(["", "## 输入契约", ""])
        for edge in input_contracts:
            lines.extend(_render_repo_contract(edge, direction="input"))
    if blockers:
        lines.extend(["", "## 待确认项", ""])
        lines.extend(f"- {item}" for item in blockers)
    return "\n".join(lines).rstrip() + "\n"


def validate_plan_artifacts(
    prepared: PlanPreparedInput,
    work_items_payload: dict[str, object],
    graph_payload: dict[str, object],
    validation_payload: dict[str, object],
    repo_task_markdowns: dict[str, str],
) -> list[str]:
    issues: list[str] = []
    work_items = _dict_list(work_items_payload.get("work_items"))
    repo_ids = {scope.repo_id for scope in prepared.repo_scopes}
    item_ids = {str(item.get("id") or "") for item in work_items}
    if len(work_items) < len(repo_ids):
        issues.append("plan missing repo work items")
    for repo_id in sorted(repo_ids):
        if not any(item.get("repo_id") == repo_id for item in work_items):
            issues.append(f"repo {repo_id} missing work item")
        if not repo_task_markdowns.get(repo_id, "").strip():
            issues.append(f"repo {repo_id} missing plan-repos markdown")
    required_fields = ("id", "repo_id", "title", "goal", "specific_steps", "done_definition", "verification_steps", "depends_on")
    for item in work_items:
        for field in required_fields:
            value = item.get(field)
            if field == "depends_on":
                if value is None:
                    issues.append(f"work item {item.get('id') or '?'} missing {field}")
                continue
            if value in (None, "", []):
                issues.append(f"work item {item.get('id') or '?'} missing {field}")
        for dep in _string_list(item.get("depends_on")):
            if dep not in item_ids:
                issues.append(f"work item {item.get('id')} depends on unknown task {dep}")
    node_ids = {str(node.get("task_id") or "") for node in _dict_list(graph_payload.get("nodes"))}
    if item_ids != node_ids:
        issues.append("execution graph nodes do not match work items")
    for edge in _dict_list(graph_payload.get("edges")):
        if edge.get("from") not in item_ids or edge.get("to") not in item_ids:
            issues.append("execution graph edge references unknown task")
        if not edge.get("type") or not edge.get("reason"):
            issues.append("execution graph edge missing type or reason")
    validation_task_ids = {str(item.get("task_id") or "") for item in _dict_list(validation_payload.get("task_validations"))}
    for item_id in item_ids:
        if item_id not in validation_task_ids:
            issues.append(f"task {item_id} missing validation")
    return issues


def _extract_files(section: str, repo_id: str = "") -> list[str]:
    files = []
    for path in _FILE_RE.findall(section):
        normalized = path
        if repo_id and normalized.startswith(f"{repo_id}/"):
            normalized = normalized[len(repo_id) + 1 :]
        files.append(normalized)
    return _dedupe(files)[:12]


def _extract_steps(section: str) -> list[str]:
    steps: list[str] = []
    skip_nested_block = False
    for raw in section.splitlines():
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if _should_skip_step_line(line):
            continue
        if not line.startswith(("-", "*", "1.", "2.", "3.", "4.", "5.")):
            continue
        text = line.lstrip("-* ").strip()
        text = re.sub(r"^\d+\.\s*", "", text).strip()
        text = _clean_markdown_inline(text)
        if indent == 0:
            skip_nested_block = _is_non_task_label(text)
        elif skip_nested_block:
            continue
        if _should_skip_step_text(text):
            continue
        if text:
            steps.append(text)
    return _dedupe(steps)


def _should_skip_step_line(line: str) -> bool:
    return (
        not line
        or line.startswith("#")
        or line.startswith("|")
        or line.startswith("```")
    )


def _should_skip_step_text(text: str) -> bool:
    if not text or _is_empty_label(text):
        return True
    return text.startswith(
        (
            "仓库路径",
            "路径",
            "职责",
            "相关参考",
            "待修改文件",
            "涉及文件",
            "关键证据",
            "证据",
            "主要风险",
            "参考依据",
            "Skills 文件",
            "需求确认书",
            "代码证据",
        )
    )


def _is_non_task_label(text: str) -> bool:
    if not _is_empty_label(text):
        return False
    return text.rstrip("：:").strip() in {"关键证据", "主要风险", "参考依据", "风险", "证据"}


def _parse_repo_task_markdown(
    markdown: str,
    repo_id: str,
    index: int,
    previous: dict[str, object],
    prepared: PlanPreparedInput,
) -> dict[str, object]:
    task_id = str(previous.get("id") or f"W{index}")
    title = str(previous.get("title") or f"执行 {prepared.title}")
    header = re.search(r"^##\s+(W\d+)\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
    if header:
        task_id = header.group(1).strip()
        title = header.group(2).strip()
    goal = _extract_field_line(markdown, "goal") or str(previous.get("goal") or f"在 {repo_id} 中完成「{prepared.title}」相关改动。")
    change_scope = _extract_named_list(markdown, "change_scope") or _string_list(previous.get("change_scope"))
    specific_steps = _extract_named_list(markdown, "tasks") or _string_list(previous.get("specific_steps")) or prepared.refined_sections.change_scope or [prepared.title]
    depends_on = _parse_dependency_line(_extract_field_line(markdown, "depends_on")) or _string_list(previous.get("depends_on"))
    blocks = _parse_dependency_line(_extract_field_line(markdown, "blocks")) or _string_list(previous.get("blocks"))
    return {
        "id": task_id,
        "repo_id": repo_id,
        "title": title,
        "goal": goal,
        "change_scope": change_scope,
        "specific_steps": specific_steps,
        "done_definition": _done_definition(repo_id, prepared.refined_sections.acceptance_criteria),
        "verification_steps": _verification_steps(repo_id, prepared.refined_sections.acceptance_criteria),
        "depends_on": depends_on,
        "blocks": blocks,
    }


def _extract_field_line(markdown: str, field: str) -> str:
    match = re.search(rf"^-\s+{re.escape(field)}:\s*(.+?)\s*$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_named_list(markdown: str, field: str) -> list[str]:
    lines = markdown.splitlines()
    result: list[str] = []
    capture = False
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped == f"- {field}:":
            capture = True
            continue
        if capture and re.match(r"^-\s+\w[\w_-]*:", stripped):
            break
        if capture and stripped.startswith(("-", "*")):
            text = stripped.lstrip("-* ").strip()
            text = re.sub(r"^\[[ xX]\]\s*", "", text).strip()
            if text:
                result.append(text)
    return _dedupe(result)


def _parse_dependency_line(value: str) -> list[str]:
    if not value or value.lower() == "none":
        return []
    return _dedupe([item.strip() for item in re.split(r"[,，]\s*", value) if item.strip()])


def _apply_dependency_upgrade_tasks(work_items: list[dict[str, object]], prepared: PlanPreparedInput) -> None:
    scopes_by_repo = {scope.repo_id: scope for scope in prepared.repo_scopes}
    items_by_repo = {str(item.get("repo_id") or ""): item for item in work_items}
    for contract in _contracts_by_pair(prepared).values():
        if str(contract.get("type") or "") != "ab_experiment_field":
            continue
        producer_repo = str(contract.get("producer_repo") or "")
        consumer_repo = str(contract.get("consumer_repo") or "")
        consumer_item = items_by_repo.get(consumer_repo)
        consumer_scope = scopes_by_repo.get(consumer_repo)
        if not consumer_item or not consumer_scope:
            continue
        module_path = _find_consumer_module_dependency(str(consumer_scope.repo_path or ""), producer_repo, contract)
        if not module_path:
            continue
        _append_unique_string(consumer_item, "change_scope", "go.mod")
        _append_unique_string(consumer_item, "change_scope", "go.sum")
        field_name = str(contract.get("field_name") or "跨仓契约字段")
        _append_unique_string(consumer_item, "specific_steps", f"升级 {module_path} 依赖到包含 {field_name} 的版本")


def _find_consumer_module_dependency(consumer_repo_path: str, producer_repo: str, contract: dict[str, object]) -> str:
    go_mod_path = Path(consumer_repo_path) / "go.mod"
    if not go_mod_path.exists():
        return ""
    try:
        content = go_mod_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    candidates = _dependency_module_candidates(producer_repo, contract)
    for module_path in candidates:
        if re.search(rf"^\s*(?:require\s+)?{re.escape(module_path)}\s+", content, flags=re.MULTILINE):
            return module_path
    return ""


def _dependency_module_candidates(producer_repo: str, contract: dict[str, object]) -> list[str]:
    candidates: list[str] = []
    producer_files = _string_list(contract.get("producer_files"))
    if producer_repo == "live_common" and (
        str(contract.get("type") or "") == "ab_experiment_field"
        or any(path.startswith("abtest/") for path in producer_files)
    ):
        candidates.append("code.byted.org/oec/live_common/abtest")
    return _dedupe(candidates)


def _append_unique_string(item: dict[str, object], field: str, value: str) -> None:
    values = _string_list(item.get(field))
    if value not in values:
        values.append(value)
    item[field] = values


def _edges_from_work_items(work_items: list[dict[str, object]], prepared: PlanPreparedInput) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    item_ids = {str(item.get("id") or "") for item in work_items}
    item_repo_by_id = {str(item.get("id") or ""): str(item.get("repo_id") or "") for item in work_items}
    contracts_by_pair = _contracts_by_pair(prepared)
    for item in work_items:
        task_id = str(item.get("id") or "")
        repo_id = str(item.get("repo_id") or "")
        for dependency in _string_list(item.get("depends_on")):
            if dependency in item_ids:
                edges.append(
                    {
                        "from": dependency,
                        "to": task_id,
                        "type": "hard_dependency",
                        "reason": f"{repo_id} depends on {item_repo_by_id.get(dependency, dependency)}.",
                        **({"contract": contract} if (contract := contracts_by_pair.get((item_repo_by_id.get(dependency, ""), repo_id), {})) else {}),
                    }
                )
        for blocked in _string_list(item.get("blocks")):
            if blocked in item_ids:
                edges.append(
                    {
                        "from": task_id,
                        "to": blocked,
                        "type": "hard_dependency",
                        "reason": f"{item_repo_by_id.get(blocked, blocked)} depends on {repo_id}.",
                        **({"contract": contract} if (contract := contracts_by_pair.get((repo_id, item_repo_by_id.get(blocked, "")), {})) else {}),
                    }
                )
    return _dedupe_edges(edges)


def _extract_repo_markdown_blockers(repo_markdowns: dict[str, str]) -> list[str]:
    blockers: list[str] = []
    for markdown in repo_markdowns.values():
        capture = False
        for raw in markdown.splitlines():
            stripped = raw.strip()
            if stripped.startswith("## "):
                capture = any(token in stripped for token in ("待确认", "阻塞", "Open Questions"))
                continue
            if capture and stripped.startswith(("-", "*")):
                text = _clean_markdown_inline(stripped.lstrip("-* ").strip())
                if text and not _is_noop_question(text) and not _is_confirmed_question(text):
                    blockers.append(text)
    return _dedupe(blockers)


def _infer_task_title(repo_id: str, section: str, title: str) -> str:
    if "实验字段" in section or "AB" in section:
        if looks_like_shared_repo(repo_id):
            return "新增或更新实验字段契约"
        return "接入实验字段并更新业务逻辑"
    files = _extract_files(section, repo_id)
    if files:
        return f"修改 {files[0]} 相关逻辑"
    return f"执行 {title}"


def _infer_goal(repo_id: str, section: str, title: str) -> str:
    if section:
        summary = "；".join(_extract_steps(section)[:2])
        if summary:
            return summary
    return f"在 {repo_id} 中完成「{title}」相关改动。"


def _done_definition(repo_id: str, acceptance: list[str]) -> list[str]:
    base = [f"{repo_id} 的改动不超出 design.md 与 prd-refined.md 确认范围。"]
    return base + acceptance[:6]


def _verification_steps(repo_id: str, acceptance: list[str]) -> list[str]:
    checks = [f"执行 {repo_id} 受影响目录的最小编译或静态检查。"]
    checks.extend(f"验收映射：{item}" for item in acceptance[:6])
    return checks


def _infer_edges_and_coordination(
    work_items: list[dict[str, object]],
    repo_sections: dict[str, str],
    prepared: PlanPreparedInput,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    edges: list[dict[str, object]] = []
    design_text = prepared.design_markdown
    contracts_by_pair = _contracts_by_pair(prepared)
    for producer in work_items:
        producer_repo = str(producer.get("repo_id") or "")
        producer_text = repo_sections.get(producer_repo, "")
        if not is_producer_section(producer_repo, producer_text, design_text):
            continue
        for consumer in work_items:
            consumer_repo = str(consumer.get("repo_id") or "")
            if consumer_repo == producer_repo:
                continue
            consumer_text = repo_sections.get(consumer_repo, "")
            if is_consumer_section(consumer_text, design_text) or shared_dependency_signal(producer_text, consumer_text):
                contract = contracts_by_pair.get((producer_repo, consumer_repo), {})
                edges.append(
                    {
                        "from": producer.get("id"),
                        "to": consumer.get("id"),
                        "type": "hard_dependency",
                        "reason": f"{consumer_repo} 需要消费 {producer_repo} 产出的公共字段、接口或配置契约。",
                        **({"contract": contract} if contract else {}),
                    }
                )
    coordination_points: list[dict[str, object]] = []
    blockers = _extract_blockers(prepared)
    if blockers:
        coordination_points.append(
            {
                "id": "C1",
                "title": "进入 Code 前确认阻塞项",
                "tasks": [str(item.get("id") or "") for item in work_items],
                "reason": "；".join(blockers[:3]),
            }
        )
    return _dedupe_edges(edges), coordination_points


def _contracts_by_pair(prepared: PlanPreparedInput) -> dict[tuple[str, str], dict[str, object]]:
    payload = prepared.design_contracts_payload
    if not isinstance(payload.get("contracts"), list):
        payload = build_design_contracts_payload(prepared.design_markdown, prepared.repo_scopes)
    result: dict[tuple[str, str], dict[str, object]] = {}
    for item in payload.get("contracts", []):
        if not isinstance(item, dict):
            continue
        producer_repo = str(item.get("producer_repo") or "")
        consumer_repo = str(item.get("consumer_repo") or "")
        if producer_repo and consumer_repo:
            result[(producer_repo, consumer_repo)] = item
    return result


def _extract_blockers(prepared: PlanPreparedInput) -> list[str]:
    candidates: list[str] = []
    candidates.extend(
        _clean_markdown_inline(item)
        for item in prepared.refined_sections.open_questions
        if not _is_noop_question(item) and not _is_confirmed_question(item)
    )
    capture = False
    for line in prepared.design_markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            capture = any(key in stripped for key in ("风险", "待确认", "Open Questions"))
            continue
        if not capture or not stripped.startswith(("-", "*")):
            continue
        text = _clean_markdown_inline(stripped.lstrip("-* ").strip())
        if text and not _is_noop_question(text) and not _is_confirmed_question(text) and ("确认" in text or "待确认" in text or "是否" in text):
            candidates.append(text)
    return _dedupe(candidates)[:8]


def _is_empty_label(text: str) -> bool:
    return text.rstrip().endswith(("：", ":")) and len(text.rstrip("：:").strip()) <= 8


def _is_noop_question(text: str) -> bool:
    return any(token in text for token in ("当前无", "无额外", "暂无", "没有额外"))


def _is_confirmed_question(text: str) -> bool:
    normalized = _clean_markdown_inline(text).lstrip("：: ")
    return normalized.startswith(
        (
            "已确认",
            "确认结论",
            "结论已确认",
            "无需确认",
            "不阻塞",
            "非阻塞",
        )
    )


def _clean_markdown_inline(text: str) -> str:
    value = text.strip()
    value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
    value = value.replace("**", "")
    value = re.sub(r"`(.+?)`", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _depends_by_task(edges: list[dict[str, object]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for edge in edges:
        result.setdefault(str(edge.get("to") or ""), []).append(str(edge.get("from") or ""))
    return {key: _dedupe(values) for key, values in result.items()}


def _blocks_by_task(edges: list[dict[str, object]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for edge in edges:
        result.setdefault(str(edge.get("from") or ""), []).append(str(edge.get("to") or ""))
    return {key: _dedupe(values) for key, values in result.items()}


def _topological_order(task_ids: list[str], edges: list[dict[str, object]]) -> list[str]:
    remaining = set(task_ids)
    deps = {task_id: set() for task_id in task_ids}
    for edge in edges:
        deps.setdefault(str(edge.get("to") or ""), set()).add(str(edge.get("from") or ""))
    ordered: list[str] = []
    while remaining:
        ready = sorted(task_id for task_id in remaining if not deps.get(task_id, set()) & remaining)
        if not ready:
            ordered.extend(sorted(remaining))
            break
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def _parallel_groups(execution_order: list[str], edges: list[dict[str, object]]) -> list[list[str]]:
    if edges or len(execution_order) < 2:
        return []
    return [execution_order]


def _critical_path(execution_order: list[str], edges: list[dict[str, object]]) -> list[str]:
    if not edges:
        return execution_order[:1]
    return execution_order


def _build_validation_payload(work_items: list[dict[str, object]], prepared: PlanPreparedInput) -> dict[str, object]:
    acceptance = prepared.refined_sections.acceptance_criteria or ["完成与 Design 文档一致的最小验证。"]
    return {
        "global_validation_focus": acceptance,
        "task_validations": [
            {
                "task_id": item["id"],
                "repo_id": item["repo_id"],
                "checks": [
                    {
                        "kind": "acceptance",
                        "target": criterion,
                        "reason": f"{item['repo_id']} 需要覆盖该验收标准。",
                    }
                    for criterion in acceptance
                ],
            }
            for item in work_items
        ],
    }


def _render_work_item_block(item: dict[str, object]) -> list[str]:
    lines = [
        f"### {item.get('id')} [{item.get('repo_id')}] {item.get('title')}",
        f"- repo: `{item.get('repo_id')}`",
        f"- goal: {item.get('goal')}",
        "- change_scope:",
    ]
    lines.extend(f"  - {entry}" for entry in _string_list(item.get("change_scope")) or ["按 design.md 中该仓库范围收敛。"])
    lines.append("- specific_steps:")
    lines.extend(f"  - {entry}" for entry in _string_list(item.get("specific_steps")))
    lines.append("- done_definition:")
    lines.extend(f"  - {entry}" for entry in _string_list(item.get("done_definition")))
    lines.append("- depends_on: " + (", ".join(_string_list(item.get("depends_on"))) or "none"))
    lines.append("- blocks: " + (", ".join(_string_list(item.get("blocks"))) or "none"))
    lines.append("- verify:")
    lines.extend(f"  - {entry}" for entry in _string_list(item.get("verification_steps")))
    lines.append("")
    return lines


def _render_repo_task_block(item: dict[str, object]) -> list[str]:
    lines = [
        f"## {item.get('id')} {item.get('title')}",
        "",
        f"- repo: `{item.get('repo_id')}`",
        f"- goal: {item.get('goal')}",
        "- change_scope:",
    ]
    lines.extend(f"  - {entry}" for entry in _string_list(item.get("change_scope")) or ["按 design.md 中该仓库范围收敛。"])
    lines.append("- tasks:")
    lines.extend(f"  - [ ] {entry}" for entry in _string_list(item.get("specific_steps")))
    lines.append("- depends_on: " + (", ".join(_string_list(item.get("depends_on"))) or "none"))
    lines.append("- blocks: " + (", ".join(_string_list(item.get("blocks"))) or "none"))
    lines.append("")
    return lines


def _render_graph_summary(graph_payload: dict[str, object]) -> list[str]:
    edges = _dict_list(graph_payload.get("edges"))
    if not edges:
        return ["```mermaid", "graph LR", "  Start[Plan] --> Done[No hard dependency]", "```"]
    lines = ["```mermaid", "graph LR"]
    for edge in edges:
        lines.append(f"  {edge.get('from')} --> {edge.get('to')}")
    lines.append("```")
    return lines


def _render_contracts_summary(graph_payload: dict[str, object]) -> list[str]:
    edges = [edge for edge in _dict_list(graph_payload.get("edges")) if isinstance(edge.get("contract"), dict)]
    if not edges:
        return ["- none"]
    lines: list[str] = []
    for index, edge in enumerate(edges, start=1):
        contract = dict(edge.get("contract") or {})
        lines.extend(
            [
                f"### C{index} {edge.get('from')} -> {edge.get('to')}",
                f"- producer: `{contract.get('producer_repo') or edge.get('from')}`",
                f"- consumer: `{contract.get('consumer_repo') or edge.get('to')}`",
                f"- contract_type: {contract.get('type') or 'cross_repo_contract'}",
            ]
        )
        lines.extend(_render_contract_fields(contract))
        lines.append("")
    return lines


def _render_repo_contract(edge: dict[str, object], *, direction: str) -> list[str]:
    contract = dict(edge.get("contract") or {})
    if direction == "output":
        intro = f"向 `{contract.get('consumer_repo') or edge.get('to')}` 提供："
    else:
        intro = f"依赖 `{contract.get('producer_repo') or edge.get('from')}` 提供："
    lines = [f"- {intro}"]
    lines.extend(f"  {line}" for line in _render_contract_fields(contract))
    return lines


def _render_contract_fields(contract: dict[str, object]) -> list[str]:
    lines: list[str] = []
    fields = [
        ("field_name", "field"),
        ("json_tag", "json_tag"),
        ("default_value", "default"),
        ("consumer_access", "consumer_access"),
        ("compatibility", "compatibility"),
    ]
    for key, label in fields:
        value = str(contract.get(key) or "").strip()
        if value:
            lines.append(f"- {label}: {value}")
    value_semantics = _string_list(contract.get("value_semantics"))
    if value_semantics:
        lines.append("- value_semantics:")
        lines.extend(f"  - {item}" for item in value_semantics)
    return lines or ["- details: 以 design.md 中的跨仓约定为准。"]


def _render_validation_summary(validation_payload: dict[str, object]) -> list[str]:
    lines = ["- minimum_checks:"]
    for validation in _dict_list(validation_payload.get("task_validations")):
        task_id = validation.get("task_id")
        for check in _dict_list(validation.get("checks"))[:3]:
            lines.append(f"  - {task_id}: {check.get('target')}")
    lines.append("- acceptance_mapping:")
    for focus in _string_list(validation_payload.get("global_validation_focus")):
        lines.append(f"  - {focus}")
    lines.append("- regression_checks:")
    lines.append("  - 未命中实验或开关关闭时，旧链路行为不变。")
    return lines


def _dedupe_edges(edges: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[object, object, object]] = set()
    result: list[dict[str, object]] = []
    for edge in edges:
        key = (edge.get("from"), edge.get("to"), edge.get("type"))
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _object_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]

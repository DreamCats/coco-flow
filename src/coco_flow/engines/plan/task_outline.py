from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.prompts.plan import build_plan_planner_agent_prompt, build_plan_planner_template_json

from .agent_io import run_plan_agent_json_with_new_session
from .models import EXECUTOR_NATIVE, PlanPreparedInput, PlanWorkItem

_ALLOWED_TASK_TYPES = {"implementation", "coordination", "validation", "preparation"}


def build_plan_work_items(
    prepared: PlanPreparedInput,
    settings: Settings,
    skills_brief_markdown: str,
    on_log,
) -> tuple[list[PlanWorkItem], dict[str, object], dict[str, object]]:
    fallback_payload = build_local_plan_task_outline_payload(prepared)
    outline_payload = _with_planner_metadata(fallback_payload, source="local", degraded=False)
    if settings.plan_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            planner_payload = _build_plan_work_items_with_planner(prepared, settings, skills_brief_markdown, on_log)
            outline_payload = _with_planner_metadata(planner_payload, source="native", degraded=False)
            on_log(f"plan_planner_mode: native work_items={len(_payload_task_units(outline_payload))}")
        except Exception as error:
            on_log(f"plan_planner_fallback: {error}")
            outline_payload = _with_planner_metadata(
                fallback_payload,
                source="local_fallback",
                degraded=True,
                degraded_reason=str(error),
            )
    else:
        on_log("plan_planner_mode: local")
    return normalize_plan_work_items(outline_payload, prepared), outline_payload, outline_payload


def build_local_plan_task_outline_payload(prepared: PlanPreparedInput) -> dict[str, object]:
    binding_items = _in_scope_binding_items(prepared)
    task_units: list[dict[str, object]] = []
    task_index = 1
    must_change_ids: list[str] = []

    for item in binding_items:
        scope_tier = str(item.get("scope_tier") or "")
        if scope_tier not in {"must_change", "co_change", "validate_only"}:
            continue
        repo_id = str(item.get("repo_id") or "").strip()
        if not repo_id:
            continue
        task_type = "implementation" if scope_tier in {"must_change", "co_change"} else "validation"
        change_summary = _as_str_list(item.get("change_summary")) or [f"{repo_id} 完成本次职责范围内的执行收敛。"]
        candidate_files = _as_str_list(item.get("candidate_files"))[:8]
        candidate_dirs = _as_str_list(item.get("candidate_dirs"))[:4]
        boundaries = _as_str_list(item.get("boundaries"))[:4]
        depends_on = [f"W{must_change_ids.index(dep) + 1}" for dep in _as_str_list(item.get("depends_on")) if dep in must_change_ids]

        task_units.append(
            {
                "id": f"W{task_index}",
                "title": _build_task_title(repo_id, task_type, prepared),
                "repo_id": repo_id,
                "task_type": task_type,
                "serves_change_points": _as_int_list(item.get("serves_change_points")) or [1],
                "goal": _build_task_goal(repo_id, task_type, prepared),
                "specific_steps": _build_specific_steps(repo_id, task_type, change_summary, candidate_files, candidate_dirs),
                "scope_summary": change_summary[:4] + candidate_dirs[:2],
                "inputs": _build_task_inputs(prepared, repo_id, task_type),
                "outputs": _build_task_outputs(repo_id, task_type),
                "done_definition": change_summary[:3] + [f"{repo_id} 的执行边界与 Design 责任保持一致。"],
                "validation_focus": _build_validation_focus(prepared, task_type, boundaries),
                "risk_notes": boundaries[:3] or ["避免扩大到 Design 未纳入的仓库或系统。"],
                "change_scope": candidate_files,
                "handoff_notes": _build_handoff_notes(task_type, scope_tier),
                "depends_on": depends_on,
                "parallelizable_with": [],
            }
        )
        if scope_tier == "must_change":
            must_change_ids.append(repo_id)
        task_index += 1

    return {"task_units": task_units}


def normalize_plan_work_items(outline_payload: dict[str, object], prepared: PlanPreparedInput) -> list[PlanWorkItem]:
    normalized: list[PlanWorkItem] = []
    for index, item in enumerate(_payload_task_units(outline_payload), start=1):
        repo_id = str(item.get("repo_id") or "").strip()
        if not repo_id:
            continue
        normalized.append(
            PlanWorkItem(
                id=str(item.get("id") or f"W{index}"),
                title=str(item.get("title") or _build_task_title(repo_id, "implementation", prepared)).strip(),
                repo_id=repo_id,
                task_type=_normalize_task_type(item.get("task_type")),
                serves_change_points=_as_int_list(item.get("serves_change_points")) or [1],
                goal=str(item.get("goal") or _build_task_goal(repo_id, "implementation", prepared)).strip(),
                specific_steps=_as_str_list(item.get("specific_steps"))[:6],
                change_scope=_as_str_list(item.get("change_scope"))[:8],
                inputs=_as_str_list(item.get("inputs"))[:6],
                outputs=_as_str_list(item.get("outputs"))[:6],
                done_definition=_as_str_list(item.get("done_definition"))[:6],
                verification_steps=_as_str_list(item.get("validation_focus") or item.get("verification_steps"))[:6],
                risk_notes=_as_str_list(item.get("risk_notes"))[:6],
                handoff_notes=_as_str_list(item.get("handoff_notes"))[:4],
                depends_on=_as_str_list(item.get("depends_on"))[:6],
                parallelizable_with=_as_str_list(item.get("parallelizable_with"))[:6],
            )
        )
    return _dedupe_and_reindex_work_items(normalized, prepared)


def _build_plan_work_items_with_planner(
    prepared: PlanPreparedInput,
    settings: Settings,
    skills_brief_markdown: str,
    on_log,
) -> dict[str, object]:
    payload = run_plan_agent_json_with_new_session(
        prepared,
        settings,
        build_plan_planner_template_json(),
        lambda template_path: build_plan_planner_agent_prompt(
            title=prepared.title,
            design_markdown=prepared.design_markdown,
            refined_markdown=prepared.refined_markdown,
            skills_brief_markdown=skills_brief_markdown,
            repo_binding_payload=prepared.design_repo_binding_payload,
            design_sections_payload=prepared.design_sections_payload,
            template_path=template_path,
        ),
        ".plan-planner-",
        role="plan_planner",
        stage="draft_work_items",
        on_log=on_log,
    )
    if not _payload_task_units(payload):
        raise ValueError("plan_planner_output_invalid")
    return payload


def _with_planner_metadata(
    payload: dict[str, object],
    *,
    source: str,
    degraded: bool,
    degraded_reason: str = "",
) -> dict[str, object]:
    result = dict(payload)
    planner = result.get("planner")
    planner_payload = dict(planner) if isinstance(planner, dict) else {}
    planner_payload.update(
        {
            "role": "planner",
            "source": source,
            "degraded": degraded,
        }
    )
    if degraded_reason:
        planner_payload["degraded_reason"] = degraded_reason
        planner_payload["fallback_stage"] = "planner"
    result["planner"] = planner_payload
    return result


def _payload_task_units(payload: dict[str, object]) -> list[dict[str, object]]:
    raw = payload.get("task_units")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _dedupe_and_reindex_work_items(items: list[PlanWorkItem], prepared: PlanPreparedInput) -> list[PlanWorkItem]:
    seen: set[tuple[str, ...]] = set()
    result: list[PlanWorkItem] = []
    for item in items:
        key = _work_item_fingerprint(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    must_change_repo_ids = {
        str(entry.get("repo_id") or "")
        for entry in _in_scope_binding_items(prepared)
        if str(entry.get("scope_tier") or "") == "must_change"
    }
    covered = {item.repo_id for item in result}
    for repo_id in sorted(must_change_repo_ids - covered):
        result.append(
            PlanWorkItem(
                id="",
                title=_build_task_title(repo_id, "implementation", prepared),
                repo_id=repo_id,
                task_type="implementation",
                serves_change_points=[1],
                goal=_build_task_goal(repo_id, "implementation", prepared),
                specific_steps=_build_specific_steps(repo_id, "implementation", [], [], []),
                change_scope=[],
                inputs=_build_task_inputs(prepared, repo_id, "implementation"),
                outputs=_build_task_outputs(repo_id, "implementation"),
                done_definition=[f"{repo_id} 的主改执行项已经落地。"],
                verification_steps=_build_validation_focus(prepared, "implementation", []),
                risk_notes=["避免偏离 Design 确认的主改边界。"],
                handoff_notes=["后续 Code 需以该任务为主入口。"],
            )
        )
    id_map: dict[str, str] = {}
    for index, item in enumerate(result, start=1):
        old_id = item.id
        item.id = f"W{index}"
        if old_id:
            id_map[old_id] = item.id
    for item in result:
        item.depends_on = [id_map.get(task_id, task_id) for task_id in item.depends_on]
        item.parallelizable_with = [id_map.get(task_id, task_id) for task_id in item.parallelizable_with]
    return result


def _work_item_fingerprint(item: PlanWorkItem) -> tuple[str, ...]:
    return (
        item.repo_id,
        item.task_type,
        item.title.strip().lower(),
        item.goal.strip().lower(),
        "|".join(entry.strip().lower() for entry in item.change_scope),
        "|".join(entry.strip().lower() for entry in item.specific_steps),
    )


def _in_scope_binding_items(prepared: PlanPreparedInput) -> list[dict[str, object]]:
    raw = prepared.design_repo_binding_payload.get("repo_bindings")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and str(item.get("decision") or "") == "in_scope"]


def _normalize_task_type(value: object) -> str:
    task_type = str(value or "implementation").strip()
    if task_type in _ALLOWED_TASK_TYPES:
        return task_type
    return "implementation"


def _build_task_title(repo_id: str, task_type: str, prepared: PlanPreparedInput) -> str:
    if task_type == "validation":
        return f"[{repo_id}] 联动验证与收口"
    if task_type == "coordination":
        return f"[{repo_id}] 协同收口"
    feature = prepared.refined_sections.change_scope[0] if prepared.refined_sections.change_scope else prepared.title
    return f"[{repo_id}] 推进「{feature}」执行"


def _build_task_goal(repo_id: str, task_type: str, prepared: PlanPreparedInput) -> str:
    feature = prepared.refined_sections.change_scope[0] if prepared.refined_sections.change_scope else prepared.title
    if task_type == "validation":
        return f"在 {repo_id} 确认「{feature}」相关联动验证与兼容性收口。"
    return f"在 {repo_id} 完成「{feature}」相关执行任务，并保持与 Design 责任一致。"


def _build_task_inputs(prepared: PlanPreparedInput, repo_id: str, task_type: str) -> list[str]:
    items = [
        "design-repo-binding.json",
        "design-sections.json",
        "design.md",
    ]
    if task_type == "validation":
        items.append(f"{repo_id} 的上下游实现状态")
    return items


def _build_task_outputs(repo_id: str, task_type: str) -> list[str]:
    if task_type == "validation":
        return [f"{repo_id} 联动验证结论", f"{repo_id} 风险确认结果"]
    return [f"{repo_id} 执行改动完成", f"{repo_id} 最小验证通过"]


def _build_validation_focus(prepared: PlanPreparedInput, task_type: str, boundaries: list[str]) -> list[str]:
    checks = ["最小范围验证通过", "优先覆盖关键链路和核心约束"]
    if task_type == "validation":
        checks.insert(0, "重点做联动验证与兼容性检查")
    for item in boundaries[:2]:
        checks.append(f"边界检查：{item}")
    for item in prepared.refined_sections.acceptance_criteria[:2]:
        checks.append(f"验收：{item}")
    return checks[:6]


def _build_specific_steps(
    repo_id: str,
    task_type: str,
    change_summary: list[str],
    candidate_files: list[str],
    candidate_dirs: list[str],
) -> list[str]:
    steps: list[str] = []
    if task_type == "validation":
        for file_path in candidate_files[:2]:
            steps.append(f"在 {file_path} 所在链路中核对联动行为与兼容性。")
        if not steps:
            for directory in candidate_dirs[:2]:
                steps.append(f"在 {repo_id}/{directory} 范围内补齐联动验证与回归确认。")
    else:
        for file_path in candidate_files[:3]:
            steps.append(f"在 {file_path} 中收敛与本次需求直接相关的核心逻辑。")
        if not steps:
            for summary in change_summary[:3]:
                steps.append(f"在 {repo_id} 的对应模块中落地：{summary}")
    return _as_str_list(steps)[:5] or [f"在 {repo_id} 的核心模块中按 Design 结论完成最小范围改动。"]


def _build_handoff_notes(task_type: str, scope_tier: str) -> list[str]:
    notes = [f"scope_tier: {scope_tier or 'unknown'}"]
    if task_type == "validation":
        notes.append("后续 code 阶段应把它当作验证/联调项，而不是默认主改仓。")
    else:
        notes.append("后续 code 阶段应按该执行项推进，不要重新做 repo adjudication。")
    return notes


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        text = str(item).strip()
        if text.isdigit():
            result.append(int(text))
    return result

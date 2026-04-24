from __future__ import annotations

import json
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.engines.shared.diagnostics import enrich_verify_payload
from coco_flow.prompts.plan import build_plan_verify_agent_prompt, build_plan_verify_template_json

from .models import EXECUTOR_NATIVE, PlanExecutionGraph, PlanPreparedInput, PlanWorkItem


def build_plan_verify_payload(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    plan_markdown: str,
    settings: Settings,
    on_log,
) -> dict[str, object]:
    fallback = build_local_plan_verify_payload(prepared, work_items, graph, validation_payload, plan_markdown)
    if settings.plan_executor.strip().lower() != EXECUTOR_NATIVE:
        return enrich_verify_payload(stage="plan", verify_payload=fallback, artifact="plan.md")
    try:
        payload = build_native_plan_verify_payload(prepared, work_items, graph, validation_payload, plan_markdown, settings)
        on_log("plan_verify_mode: native")
        return enrich_verify_payload(stage="plan", verify_payload=payload, artifact="plan.md")
    except Exception as error:
        on_log(f"plan_verify_fallback: {error}")
        return enrich_verify_payload(stage="plan", verify_payload=fallback, artifact="plan.md")


def build_local_plan_verify_payload(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    plan_markdown: str,
) -> dict[str, object]:
    issues: list[str] = []
    must_change_repos = {
        str(item.get("repo_id") or "")
        for item in _in_scope_binding_items(prepared)
        if str(item.get("scope_tier") or "") == "must_change"
    }
    covered_repos = {item.repo_id for item in work_items}
    missing_repos = sorted(repo for repo in must_change_repos if repo and repo not in covered_repos)
    if missing_repos:
        issues.append("must_change repo 未被执行任务覆盖: " + ", ".join(missing_repos))
    if len(graph.execution_order) != len(work_items):
        issues.append("execution graph 未覆盖全部 work items")
    task_validations = validation_payload.get("task_validations")
    if not isinstance(task_validations, list) or len(task_validations) < len(work_items):
        issues.append("validation contract 未覆盖全部 work items")
    if not plan_markdown.strip().startswith("# Plan"):
        issues.append("plan.md 缺少稳定标题")
    for section in ("## 任务清单", "## 执行顺序", "## 验证策略", "## 风险与阻塞项"):
        if section not in plan_markdown:
            issues.append(f"plan.md 缺少必要章节: {section.removeprefix('## ')}")
    if any(not item.specific_steps for item in work_items):
        issues.append("存在 work item 缺少 specific_steps")
    return {
        "ok": not issues,
        "issues": issues,
        "reason": "local plan verify passed" if not issues else "local plan verify failed",
    }


def build_native_plan_verify_payload(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    plan_markdown: str,
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_template(prepared.task_dir)
    try:
        client.run_agent(
            build_plan_verify_agent_prompt(
                title=prepared.title,
                plan_markdown=plan_markdown,
                design_markdown=prepared.design_markdown,
                repo_binding_payload=prepared.design_repo_binding_payload,
                work_items_payload={"work_items": [item.to_payload() for item in work_items]},
                execution_graph_payload=graph.to_payload(),
                validation_payload=validation_payload,
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
    finally:
        if template_path.exists():
            template_path.unlink()
    if "__FILL__" in raw or not raw.strip():
        raise ValueError("plan_verify_template_unfilled")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("plan_verify_output_invalid")
    return {
        "ok": bool(payload.get("ok")),
        "issues": [str(item) for item in payload.get("issues", []) if str(item).strip()],
        "reason": str(payload.get("reason") or ""),
    }


def _write_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".plan-verify-",
        suffix=".json",
        delete=False,
    ) as handle:
        handle.write(build_plan_verify_template_json())
        handle.flush()
        return Path(handle.name)


def _in_scope_binding_items(prepared: PlanPreparedInput) -> list[dict[str, object]]:
    raw = prepared.design_repo_binding_payload.get("repo_bindings")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and str(item.get("decision") or "") == "in_scope"]

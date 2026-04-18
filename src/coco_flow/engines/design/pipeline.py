from __future__ import annotations

import json

from coco_flow.config import Settings

from .assignment import build_design_change_points_payload, build_design_repo_assignment_payload
from .binding import build_repo_binding
from .generate import build_design_sections_payload, generate_design_markdown
from .knowledge import build_design_knowledge_brief
from .models import DesignEngineResult
from .research import build_design_research_payload
from .source import prepare_design_input


def run_design_engine(task_dir, task_meta: dict[str, object], settings: Settings, on_log) -> DesignEngineResult:
    on_log("design_prepare_start: true")
    prepared = prepare_design_input(task_dir, task_meta)
    on_log(f"design_prepare_ok: repos={len(prepared.repo_scopes)}, refined_chars={len(prepared.refined_markdown.strip())}")
    if not prepared.refined_markdown.strip():
        raise ValueError("prd-refined.md 为空，无法执行 design")

    on_log("design_knowledge_start: true")
    knowledge_brief_markdown = build_design_knowledge_brief(prepared)
    on_log(f"design_knowledge_ok: used={'true' if bool(knowledge_brief_markdown.strip()) else 'false'}")

    on_log("design_change_points_start: true")
    change_points_payload = build_design_change_points_payload(prepared, settings, knowledge_brief_markdown, on_log)
    on_log(f"design_change_points_ok: count={len(change_points_payload.get('change_points', []))}")

    on_log("design_repo_assignment_start: true")
    repo_assignment_payload = build_design_repo_assignment_payload(prepared, change_points_payload)
    on_log(f"design_repo_assignment_ok: repo_briefs={len(repo_assignment_payload.get('repo_briefs', []))}")
    prepared.change_points_payload = change_points_payload
    prepared.repo_assignment_payload = repo_assignment_payload

    on_log("design_research_start: true")
    research_payload = build_design_research_payload(prepared, settings, knowledge_brief_markdown, on_log)
    on_log(f"design_research_ok: mode={research_payload.get('mode') or 'local'}")
    prepared.research_payload = research_payload
    artifacts: dict[str, str | dict[str, object]] = {
        "design-change-points.json": change_points_payload,
        "design-repo-assignment.json": repo_assignment_payload,
        "design-research.json": research_payload,
    }
    if knowledge_brief_markdown.strip():
        artifacts["design-knowledge-brief.md"] = knowledge_brief_markdown

    on_log("design_repo_binding_start: true")
    repo_binding = build_repo_binding(prepared, settings, knowledge_brief_markdown, on_log)
    repo_binding_payload = repo_binding.to_payload()
    artifacts["design-repo-binding.json"] = repo_binding_payload
    on_log(f"design_repo_binding_ok: mode={repo_binding.mode}, in_scope={sum(1 for item in repo_binding_payload.get('repo_bindings', []) if isinstance(item, dict) and str(item.get('decision') or '') == 'in_scope')}")

    on_log("design_sections_start: true")
    sections_payload = build_design_sections_payload(prepared, repo_binding_payload, knowledge_brief_markdown)
    artifacts["design-sections.json"] = sections_payload
    on_log(f"design_sections_ok: system_changes={len(sections_payload.get('system_changes', []))}, dependencies={len(sections_payload.get('system_dependencies', []))}")

    on_log("design_generate_start: true")
    design_markdown = generate_design_markdown(
        prepared,
        repo_binding_payload,
        sections_payload,
        knowledge_brief_markdown,
        settings,
        artifacts,
        on_log,
    )
    on_log("design_generate_ok: true")
    if "design-verify.json" not in artifacts:
        artifacts["design-verify.json"] = {"ok": True, "issues": [], "reason": "local design path"}
    verify_payload = artifacts.get("design-verify.json")
    if isinstance(verify_payload, dict):
        on_log(f"design_verify_ok: ok={'true' if bool(verify_payload.get('ok')) else 'false'}")
    artifacts["design-result.json"] = {
        "task_id": prepared.task_id,
        "status": "designed",
        "research_mode": str(research_payload.get("mode") or "local"),
        "repo_binding_mode": repo_binding.mode,
        "selected_knowledge_ids": [str(item) for item in prepared.refine_knowledge_selection_payload.get("selected_ids", []) if str(item).strip()],
        "artifacts": sorted(artifacts.keys()),
    }
    on_log("status: designed")
    return DesignEngineResult(
        status="designed",
        design_markdown=design_markdown,
        repo_binding_payload=repo_binding_payload,
        sections_payload=sections_payload,
        intermediate_artifacts=artifacts,
    )

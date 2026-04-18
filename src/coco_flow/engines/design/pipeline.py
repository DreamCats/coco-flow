from __future__ import annotations

import json

from coco_flow.config import Settings

from .binding import build_repo_binding
from .generate import build_design_sections_payload, generate_design_markdown
from .knowledge import build_design_knowledge_brief
from .models import DesignEngineResult
from .research import build_design_research_payload
from .source import prepare_design_input


def run_design_engine(task_dir, task_meta: dict[str, object], settings: Settings, on_log) -> DesignEngineResult:
    prepared = prepare_design_input(task_dir, task_meta)
    if not prepared.refined_markdown.strip():
        raise ValueError("prd-refined.md 为空，无法执行 design")

    knowledge_brief_markdown = build_design_knowledge_brief(prepared)
    research_payload = build_design_research_payload(prepared, settings, knowledge_brief_markdown, on_log)
    prepared.research_payload = research_payload
    artifacts: dict[str, str | dict[str, object]] = {"design-research.json": research_payload}
    if knowledge_brief_markdown.strip():
        artifacts["design-knowledge-brief.md"] = knowledge_brief_markdown

    repo_binding = build_repo_binding(prepared, settings, knowledge_brief_markdown, on_log)
    repo_binding_payload = repo_binding.to_payload()
    artifacts["design-repo-binding.json"] = repo_binding_payload

    sections_payload = build_design_sections_payload(prepared, repo_binding_payload, knowledge_brief_markdown)
    artifacts["design-sections.json"] = sections_payload

    design_markdown = generate_design_markdown(
        prepared,
        repo_binding_payload,
        sections_payload,
        knowledge_brief_markdown,
        settings,
        artifacts,
        on_log,
    )
    if "design-verify.json" not in artifacts:
        artifacts["design-verify.json"] = {"ok": True, "issues": [], "reason": "local design path"}
    artifacts["design-result.json"] = {
        "task_id": prepared.task_id,
        "status": "designed",
        "research_mode": str(research_payload.get("mode") or "local"),
        "repo_binding_mode": repo_binding.mode,
        "selected_knowledge_ids": [str(item) for item in prepared.refine_knowledge_selection_payload.get("selected_ids", []) if str(item).strip()],
        "artifacts": sorted(artifacts.keys()),
    }
    on_log("design_repo_binding: true")
    on_log("design_sections: true")
    on_log("status: designed")
    return DesignEngineResult(
        status="designed",
        design_markdown=design_markdown,
        repo_binding_payload=repo_binding_payload,
        sections_payload=sections_payload,
        intermediate_artifacts=artifacts,
    )

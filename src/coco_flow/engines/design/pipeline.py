from __future__ import annotations

import json

from coco_flow.config import Settings

from .assignment import build_design_change_points_payload, build_design_repo_assignment_payload
from .binding import build_repo_binding
from .generate import build_design_sections_payload, generate_design_markdown
from .skills import build_design_skills_brief
from .matrix import build_design_responsibility_matrix_payload
from .models import DesignEngineResult
from .research import build_design_research_payload
from .source import prepare_design_input


def run_design_engine(task_dir, task_meta: dict[str, object], settings: Settings, on_log) -> DesignEngineResult:
    """串起完整的 Design 阶段，从输入准备一直走到最终产物落盘。

    主流程：
    1. 准备 task / refine / repo 上下文。
    2. 生成 skills brief 与 change points。
    3. 为 change points 分配 repo，并补充 repo 调研。
    4. 生成职责矩阵，并收敛最终 repo binding。
    5. 组装 design sections，生成 design.md，并执行 verify。
    """
    on_log("design_prepare_start: true")
    prepared = prepare_design_input(task_dir, task_meta, settings)
    on_log(f"design_prepare_ok: repos={len(prepared.repo_scopes)}, refined_chars={len(prepared.refined_markdown.strip())}")
    repo_discovery = prepared.repo_discovery_payload
    if repo_discovery:
        on_log(
            "design_repo_discovery_ok: "
            f"mode={repo_discovery.get('mode') or 'none'}, "
            f"bound={int(repo_discovery.get('bound_repo_count') or 0)}, "
            f"inferred={int(repo_discovery.get('inferred_repo_count') or 0)}"
        )
    if not prepared.refined_markdown.strip():
        raise ValueError("prd-refined.md 为空，无法执行 design")

    # 先把 Refine 阶段的结果压缩成一个更短的 brief，供后续步骤复用。
    on_log("design_skills_start: true")
    skills_brief_markdown = build_design_skills_brief(prepared)
    on_log(f"design_skills_ok: used={'true' if bool(skills_brief_markdown.strip()) else 'false'}")

    # 再把 refined scope 收敛成少量明确的设计改造点。
    on_log("design_change_points_start: true")
    change_points_payload = build_design_change_points_payload(prepared, settings, skills_brief_markdown, on_log)
    on_log(f"design_change_points_ok: count={len(change_points_payload.get('change_points', []))}")

    # 基于改造点，先给出每个 repo 是主负责还是辅助负责的初步判断。
    on_log("design_repo_assignment_start: true")
    repo_assignment_payload = build_design_repo_assignment_payload(prepared, change_points_payload)
    on_log(f"design_repo_assignment_ok: repo_briefs={len(repo_assignment_payload.get('repo_briefs', []))}")
    prepared.change_points_payload = change_points_payload
    prepared.repo_assignment_payload = repo_assignment_payload

    # 在做最终 binding 之前，先补深 repo 级别的证据。
    on_log("design_research_start: true")
    research_payload = build_design_research_payload(prepared, settings, skills_brief_markdown, on_log)
    on_log(f"design_research_ok: mode={research_payload.get('mode') or 'local'}")
    prepared.research_payload = research_payload
    artifacts: dict[str, str | dict[str, object]] = {
        "design-change-points.json": change_points_payload,
        "design-repo-assignment.json": repo_assignment_payload,
        "design-research.json": research_payload,
    }
    if skills_brief_markdown.strip():
        artifacts["design-skills-brief.md"] = skills_brief_markdown

    # 把 repo research 转成更稳定的 repo 职责画像，方便后面做 binding。
    on_log("design_repo_matrix_start: true")
    responsibility_matrix_payload = build_design_responsibility_matrix_payload(prepared, settings, skills_brief_markdown, on_log)
    prepared.responsibility_matrix_payload = responsibility_matrix_payload
    artifacts["design-repo-responsibility-matrix.json"] = responsibility_matrix_payload
    on_log(
        "design_repo_matrix_ok: "
        f"repos={len(responsibility_matrix_payload.get('repos', []))}, "
        f"warnings={len(responsibility_matrix_payload.get('warnings', []))}"
    )

    # 最终 binding 负责确定哪些 repo 在范围内，以及各自的 scope tier。
    on_log("design_repo_binding_start: true")
    repo_binding = build_repo_binding(prepared, settings, skills_brief_markdown, on_log)
    repo_binding_payload = repo_binding.to_payload()
    artifacts["design-repo-binding.json"] = repo_binding_payload
    in_scope_count = sum(
        1
        for item in repo_binding_payload.get("repo_bindings", [])
        if isinstance(item, dict) and str(item.get("decision") or "") == "in_scope"
    )
    must_change_count = sum(
        1
        for item in repo_binding_payload.get("repo_bindings", [])
        if isinstance(item, dict)
        and str(item.get("decision") or "") == "in_scope"
        and str(item.get("scope_tier") or "") == "must_change"
    )
    on_log(
        "design_repo_binding_ok: "
        f"mode={repo_binding.mode}, "
        f"in_scope={in_scope_count}, "
        f"must_change={must_change_count}, "
        f"closure_mode={repo_binding.closure_mode}, "
        f"selection_basis={repo_binding.selection_basis}"
    )

    # sections 是渲染 design.md 前的最后一层结构化输入。
    on_log("design_sections_start: true")
    sections_payload = build_design_sections_payload(prepared, repo_binding_payload, skills_brief_markdown)
    artifacts["design-sections.json"] = sections_payload
    on_log(f"design_sections_ok: system_changes={len(sections_payload.get('system_changes', []))}, dependencies={len(sections_payload.get('system_dependencies', []))}")

    # 最终渲染会根据 executor 走本地生成或 native agent 生成。
    on_log("design_generate_start: true")
    design_markdown = generate_design_markdown(
        prepared,
        repo_binding_payload,
        sections_payload,
        skills_brief_markdown,
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
        "selected_skill_ids": _selected_skill_ids(prepared.refine_skills_selection_payload),
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


def _selected_skill_ids(selection_payload: dict[str, object]) -> list[str]:
    values = selection_payload.get("selected_skill_ids")
    if not isinstance(values, list):
        return []
    return [str(item) for item in values if str(item).strip()]

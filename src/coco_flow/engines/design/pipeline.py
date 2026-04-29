"""Design 阶段主编排。

当前 Design 第一版只生成 design.md：读取 refined PRD 和绑定仓库，
补充 Skills/SOP 与代码调研证据，然后交给 writer 形成可人工评审的 Markdown 技术方案。
"""

from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.engines.shared.contracts import build_design_contracts_payload

from .discovery import build_search_hints
from .evidence import build_research_plan, build_research_summary, run_parallel_repo_research
from .input import prepare_design_input
from .knowledge import build_design_skills_bundle
from .quality import build_design_quality_payload, evaluate_design_actionability
from .runtime import DesignAgentSession
from .supervisor import supervisor_review_design
from .types import EXECUTOR_NATIVE, STATUS_DESIGNED, DesignEngineResult
from .writer import repair_doc_only_design_markdown, write_doc_only_design_draft


def run_design_engine(
    task_dir,
    task_meta: dict[str, object],
    settings: Settings,
    on_log,
) -> DesignEngineResult:
    # 1. 读取上游输入。Design 的事实源是 prd-refined.md、input 元数据和已绑定仓库。
    on_log("design_prepare_start: true")
    prepared = prepare_design_input(task_dir, task_meta, settings)
    if not prepared.refined_markdown.strip():
        raise ValueError("prd-refined.md 为空，无法执行 design")
    if not prepared.repo_scopes:
        raise ValueError("design requires bound repos; please bind repos first")
    on_log(f"design_prepare_ok: repos={len(prepared.repo_scopes)} refined_chars={len(prepared.refined_markdown.strip())}")

    native_ok = settings.plan_executor.strip().lower() == EXECUTOR_NATIVE

    # 2. 选择业务 Skills/SOP。程序只召回候选；native 可用时由受控 selector 做语义选择。
    on_log("design_skills_start: true")
    index_markdown, fallback_markdown, selection_payload, selected_skill_ids = build_design_skills_bundle(
        prepared,
        settings,
        native_ok=native_ok,
        on_log=on_log,
    )
    prepared.design_skills_selection_payload = selection_payload
    prepared.design_skills_index_markdown = index_markdown
    prepared.design_skills_fallback_markdown = fallback_markdown
    prepared.design_selected_skill_ids = selected_skill_ids
    on_log(f"design_skills_ok: selected={len(selected_skill_ids)}")

    # 3. 做轻量代码调研。native 只负责给搜索线索，真正证据仍来自本地 repo research。
    on_log("design_research_start: true")
    search_hints_payload = build_search_hints(prepared, settings, native_ok=native_ok, on_log=on_log)
    research_plan_payload = build_research_plan(prepared, search_hints_payload)
    repo_research_payloads = run_parallel_repo_research(prepared, research_plan_payload)
    research_summary_payload = build_research_summary(repo_research_payloads)
    on_log(
        "design_research_ok: "
        f"repos={len(repo_research_payloads)} "
        f"candidate_files={int(research_summary_payload.get('candidate_file_count') or 0)}"
    )

    # 4. 写 Markdown 草稿，然后由 quality + supervisor 做有限审阅。
    on_log("design_writer_start: true")
    writer_draft = write_doc_only_design_draft(
        prepared,
        research_summary_payload,
        settings,
        native_ok=native_ok,
        on_log=on_log,
    )
    design_markdown = writer_draft.markdown
    on_log(f"design_writer_ok: source={writer_draft.source}")

    quality_payload = build_design_quality_payload(design_markdown, source=writer_draft.source)
    actionability = evaluate_design_actionability(design_markdown)
    if not actionability.passed:
        on_log(
            "design_quality_failed: "
            + ",".join(str(issue.issue_type) for issue in actionability.issues)
        )

    supervisor_review = supervisor_review_design(
        prepared,
        research_summary_payload,
        design_markdown,
        quality_payload,
        settings,
        native_ok=native_ok,
        on_log=on_log,
    )
    supervisor_payload = supervisor_review.to_payload()
    rejected_design_markdown = ""

    if supervisor_review.decision == "repair_writer":
        rejected_design_markdown = design_markdown if writer_draft.source == "native" else ""
        if supervisor_review.source == "native":
            repaired_markdown = repair_doc_only_design_markdown(
                prepared,
                research_summary_payload,
                design_markdown,
                supervisor_review.repair_instructions,
                settings,
                native_ok=native_ok,
                on_log=on_log,
            )
            repaired_source = f"{writer_draft.source}_repair"
        else:
            repaired_markdown = writer_draft.local_draft_markdown
            repaired_source = "local_fallback"
            on_log("design_writer_fallback: local_supervisor_repair")
        repaired_quality = build_design_quality_payload(
            repaired_markdown,
            source=repaired_source,
            supervisor_decision=supervisor_review.decision,
        )
        if bool(repaired_quality.get("actionability", {}).get("passed")):
            design_markdown = repaired_markdown
            quality_payload = repaired_quality
        else:
            design_markdown = _build_degraded_design_markdown(prepared, research_summary_payload, supervisor_payload)
            quality_payload = build_design_quality_payload(
                design_markdown,
                source="degraded",
                quality_status="degraded",
                supervisor_decision=supervisor_review.decision,
            )
            on_log("design_degraded: repair_failed")
    elif supervisor_review.decision in {"degrade_design", "needs_human", "fail", "redo_research"}:
        rejected_design_markdown = design_markdown if writer_draft.source == "native" else ""
        design_markdown = _build_degraded_design_markdown(prepared, research_summary_payload, supervisor_payload)
        quality_payload = build_design_quality_payload(
            design_markdown,
            source="degraded",
            quality_status="degraded",
            supervisor_decision=supervisor_review.decision,
        )
        on_log(f"design_degraded: supervisor_decision={supervisor_review.decision}")
    else:
        quality_payload = build_design_quality_payload(
            design_markdown,
            source=writer_draft.source,
            supervisor_decision=supervisor_review.decision,
        )

    contracts_payload = build_design_contracts_payload(design_markdown, prepared.repo_scopes)
    on_log(f"design_contracts_ok: count={int(contracts_payload.get('contract_count') or 0)}")
    on_log(f"status: {STATUS_DESIGNED}")
    return DesignEngineResult(
        status=STATUS_DESIGNED,
        design_markdown=design_markdown,
        design_skills_payload=selection_payload,
        design_contracts_payload=contracts_payload,
        design_research_summary_payload=research_summary_payload,
        design_quality_payload=quality_payload,
        design_supervisor_review_payload=supervisor_payload,
        rejected_design_markdown=rejected_design_markdown,
    )


def _build_degraded_design_markdown(
    prepared,
    research_summary_payload: dict[str, object],
    supervisor_payload: dict[str, object],
) -> str:
    issues = supervisor_payload.get("blocking_issues")
    issue_lines: list[str] = []
    if isinstance(issues, list):
        for item in issues:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or "").strip()
            if summary:
                issue_lines.append(summary)
    lines = [
        f"# {prepared.title} Design",
        "",
        "## 结论",
        "当前代码证据不足以生成可直接进入 Plan 的完整技术设计，本文按降级设计记录已确认事实和待补充信息。",
        "",
        "## 核心改造点",
    ]
    for index, item in enumerate(prepared.sections.change_scope or [prepared.title], start=1):
        lines.append(f"{index}. {item}")
    lines.extend(["", "## 方案设计"])
    lines.append("- 当前仅确认 refined PRD 中的目标和验收约束；具体实现落点需要补充 repo research 或人工确认。")
    lines.append("- 不把弱相关候选文件写成确定改造点。")
    lines.extend(["", "## 分仓库职责"])
    repos = research_summary_payload.get("repos")
    repo_by_id = {str(item.get("repo_id") or ""): item for item in repos if isinstance(item, dict)} if isinstance(repos, list) else {}
    for scope in prepared.repo_scopes:
        repo_payload = repo_by_id.get(scope.repo_id, {})
        work_hypothesis = str(repo_payload.get("work_hypothesis") or "unknown").strip()
        lines.extend(["", f"### {scope.repo_id}", f"- 仓库路径：{scope.repo_path}"])
        lines.append(f"- 职责判断：{work_hypothesis or 'unknown'}")
        lines.append("- 改造方案：当前证据不足以确定精准文件落点，进入 Plan 前需要补充定位或人工确认。")
    lines.extend(["", "## 验收与验证"])
    if prepared.sections.acceptance_criteria:
        lines.extend(f"- {item}" for item in prepared.sections.acceptance_criteria[:10])
    else:
        lines.append("- 按 prd-refined.md 的验收标准做最小验证。")
    lines.extend(["", "## 风险与待确认"])
    if issue_lines:
        lines.extend(f"- {item}" for item in issue_lines)
    else:
        lines.append("- 待确认：补充代码证据后再确定具体文件落点和仓库职责。")
    if prepared.sections.non_goals:
        lines.extend(["", "## 明确不做"])
        lines.extend(f"- {item}" for item in prepared.sections.non_goals)
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DesignAgentSession",
    "run_design_engine",
]

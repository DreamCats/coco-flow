"""Design 阶段主编排。

当前 Design 第一版只生成 design.md：读取 refined PRD 和绑定仓库，
补充 Skills/SOP 与代码调研证据，然后交给 writer 形成可人工评审的 Markdown 技术方案。
"""

from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.engines.shared.contracts import build_design_contracts_payload

from .discovery import build_search_hints
from .evidence import build_research_plan, build_research_summary, run_agent_repo_research, run_parallel_repo_research
from .input import prepare_design_input
from .knowledge import build_design_skills_bundle
from .quality import build_design_quality_payload, evaluate_design_actionability
from .runtime import DesignAgentSession
from .support import as_str_list, dict_list
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

    # 3. 代码调研。
    # native 主链路不再让程序做 candidate/excluded 裁决：
    # Research Agent 自己搜索、读文件、查 git，并由 Research Supervisor 审证据是否足够。
    # native agent 失败会显式进入 research_gate；旧程序 research 只保留给 local executor。
    on_log("design_research_start: true")
    if native_ok:
        try:
            research_summary_payload = run_agent_repo_research(prepared, settings, on_log=on_log)
        except Exception as error:
            on_log(f"design_research_agent_failed: {error}")
            research_summary_payload = _build_failed_research_payload(prepared, str(error))
    else:
        research_summary_payload = _run_local_repo_research(prepared, settings, on_log)
    on_log(
        "design_research_ok: "
        f"source={research_summary_payload.get('source') or 'local'} "
        f"repos={len(research_summary_payload.get('repos') or [])} "
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

    research_gate_payload = _research_gate_payload(research_summary_payload)
    quality_payload = build_design_quality_payload(design_markdown, source=writer_draft.source)
    if research_gate_payload:
        quality_payload["research_gate"] = research_gate_payload
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
        if research_gate_payload:
            repaired_quality["research_gate"] = research_gate_payload
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
            if research_gate_payload:
                quality_payload["research_gate"] = research_gate_payload
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
        if research_gate_payload:
            quality_payload["research_gate"] = research_gate_payload
        on_log(f"design_degraded: supervisor_decision={supervisor_review.decision}")
    else:
        quality_payload = build_design_quality_payload(
            design_markdown,
            source=writer_draft.source,
            supervisor_decision=supervisor_review.decision,
        )
        if research_gate_payload:
            quality_payload["research_gate"] = research_gate_payload

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


def _run_local_repo_research(prepared, settings: Settings, on_log) -> dict[str, object]:
    """Local fallback research.

    这个分支保留旧的轻量程序搜索能力，只用于 local executor。
    它不再代表 Design 的目标主架构；主架构应优先走 Research Agent + Supervisor。
    """

    search_hints_payload = build_search_hints(prepared, settings, native_ok=False, on_log=on_log)
    research_plan_payload = build_research_plan(prepared, search_hints_payload)
    repo_research_payloads = run_parallel_repo_research(prepared, research_plan_payload)
    payload = build_research_summary(repo_research_payloads)
    payload["source"] = "local"
    return payload


def _build_failed_research_payload(prepared, error: str) -> dict[str, object]:
    repos = [
        {
            "repo_id": scope.repo_id,
            "repo_path": scope.repo_path,
            "work_hypothesis": "unknown",
            "confidence": "low",
            "research_status": "failed",
            "research_error": error,
            "claims": [],
            "candidate_files": [],
            "related_files": [],
            "excluded_files": [],
            "rejected_candidates": [],
            "boundaries": [],
            "unknowns": [f"Research Agent failed: {error}"],
            "next_search_suggestions": [],
        }
        for scope in prepared.repo_scopes
    ]
    return {
        "source": "agent",
        "research_status": "failed",
        "repos": repos,
        "summary": f"Research Agent failed: {error}",
        "unknowns": [f"{scope.repo_id}: Research Agent failed: {error}" for scope in prepared.repo_scopes],
        "candidate_file_count": 0,
        "excluded_file_count": 0,
        "git_evidence_count": 0,
        "git_command_count": 0,
        "research_review": {
            "passed": False,
            "decision": "needs_human",
            "confidence": "low",
            "blocking_issues": [
                {
                    "type": "research_agent_failed",
                    "summary": f"Research Agent failed before producing usable evidence: {error}",
                    "evidence": [],
                }
            ],
            "research_instructions": [],
            "reason": "Research Agent failed; Design cannot be considered evidence-backed.",
        },
    }


def _research_gate_payload(research_summary_payload: dict[str, object]) -> dict[str, object]:
    review = research_summary_payload.get("research_review")
    status = str(research_summary_payload.get("research_status") or "ok")
    review_passed = bool(review.get("passed")) if isinstance(review, dict) else status == "ok"
    if status == "ok" and review_passed:
        return {}
    return {
        "passed": False,
        "research_status": status,
        "review_decision": str(review.get("decision") or "") if isinstance(review, dict) else "",
        "reason": str(review.get("reason") or "") if isinstance(review, dict) else "Research did not pass.",
    }


def _build_degraded_design_markdown(
    prepared,
    research_summary_payload: dict[str, object],
    supervisor_payload: dict[str, object],
) -> str:
    review = research_summary_payload.get("research_review")
    review_payload = review if isinstance(review, dict) else {}
    issue_lines = _issue_summaries(supervisor_payload.get("blocking_issues"))
    research_issue_lines = _issue_summaries(review_payload.get("blocking_issues"))
    research_instructions = as_str_list(review_payload.get("research_instructions"))
    confirmed_lines = _confirmed_research_lines(research_summary_payload)
    blockers = _dedupe(research_issue_lines or issue_lines)
    lines = [
        f"# {prepared.title} Design",
        "",
        "## 设计状态",
        "本设计已完成需求目标和部分代码证据的归档，但仍缺少少量关键实现决策。"
        "这些待确认项补齐前，本文先作为人工确认版设计草稿；补齐后可同步 Design 并进入 Plan。",
        "",
        "## 需求与改造范围",
    ]
    for index, item in enumerate(prepared.sections.change_scope or [prepared.title], start=1):
        lines.append(f"{index}. {item}")
    lines.extend(["", "## 方案概要"])
    lines.append("- 先以 refined PRD 中的目标、范围和验收标准作为设计边界。")
    lines.append("- 已有代码证据只用于支撑明确事实；缺少证据的实现细节保留为待确认设计决策。")
    lines.append("- 弱相关候选文件不会被写成确定改造点，避免后续 Plan 消费错误落点。")
    if confirmed_lines:
        lines.extend(["", "## 已确认设计基础"])
        lines.append("以下内容已经有代码证据支撑，可作为后续设计和 Plan 的基础：")
        lines.extend(f"- {item}" for item in confirmed_lines[:10])
    lines.extend(["", "## 待确认设计决策"])
    if blockers:
        lines.append("进入 Plan 前需要把下面问题补成明确结论，建议直接在本节改写为“已确认：...”形式：")
        lines.extend(f"- 待确认：{_strip_pending_prefix(item)}" for item in blockers[:10])
    else:
        lines.append("- 待确认：补充代码证据后再确定具体文件落点和仓库职责。")
    if research_instructions:
        lines.extend(["", "## 补齐建议"])
        lines.append("可以按下面线索补齐上一节的待确认决策；补齐后无需重跑 Design。")
        lines.extend(f"- {item}" for item in research_instructions[:10])
    lines.extend(["", "## 仓库影响分析"])
    repos = research_summary_payload.get("repos")
    repo_by_id = {str(item.get("repo_id") or ""): item for item in repos if isinstance(item, dict)} if isinstance(repos, list) else {}
    for scope in prepared.repo_scopes:
        repo_payload = repo_by_id.get(scope.repo_id, {})
        work_hypothesis = str(repo_payload.get("work_hypothesis") or "unknown").strip()
        lines.extend(["", f"### {scope.repo_id}", f"- 仓库：{scope.repo_id}"])
        lines.append(f"- 影响判断：{work_hypothesis or 'unknown'}")
        lines.append("- 设计说明：当前只记录已确认的职责和候选落点；具体改造步骤需要在待确认决策补齐后展开。")
    lines.extend(["", "## 验收与验证"])
    if prepared.sections.acceptance_criteria:
        lines.extend(f"- {item}" for item in prepared.sections.acceptance_criteria[:10])
    else:
        lines.append("- 按 prd-refined.md 的验收标准做最小验证。")
    lines.extend(["", "## 风险与待确认"])
    risk_lines = _dedupe(issue_lines or blockers)
    if risk_lines:
        lines.extend(f"- 待确认：{_strip_pending_prefix(item)}" for item in risk_lines)
    else:
        lines.append("- 待确认：补充代码证据后再确定具体文件落点和仓库职责。")
    if prepared.sections.non_goals:
        lines.extend(["", "## 明确不做"])
        lines.extend(f"- {item}" for item in prepared.sections.non_goals)
    return "\n".join(lines).rstrip() + "\n"


def _issue_summaries(value: object) -> list[str]:
    result: list[str] = []
    for item in dict_list(value):
        summary = str(item.get("summary") or "").strip()
        if summary:
            result.append(summary)
    return result


def _strip_pending_prefix(text: str) -> str:
    value = text.strip()
    for prefix in ("待确认：", "待确认:", "未确认：", "未确认:", "缺少：", "缺少:"):
        if value.startswith(prefix):
            return value[len(prefix) :].strip()
    return value


def _confirmed_research_lines(research_summary_payload: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for repo in dict_list(research_summary_payload.get("repos")):
        repo_id = str(repo.get("repo_id") or "repo").strip()
        work_hypothesis = str(repo.get("work_hypothesis") or "unknown").strip()
        if work_hypothesis:
            lines.append(f"{repo_id}: 职责判断为 {work_hypothesis}。")
        for claim in dict_list(repo.get("claims")):
            if str(claim.get("status") or "").strip() != "supported":
                continue
            text = str(claim.get("claim") or "").strip()
            if text:
                lines.append(f"{repo_id}: {text}")
        for candidate in dict_list(repo.get("candidate_files")):
            path = _short_path(str(candidate.get("path") or ""))
            symbol = str(candidate.get("symbol") or "").strip()
            if path:
                suffix = f" / {symbol}" if symbol else ""
                lines.append(f"{repo_id}: 候选落点 {path}{suffix}")
    return _dedupe(lines)


def _short_path(path: str) -> str:
    value = path.strip()
    if not value:
        return ""
    marker = "/src/code.byted.org/"
    if marker in value:
        return value.split(marker, 1)[1]
    parts = [part for part in value.split("/") if part]
    return "/".join(parts[-4:])


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


__all__ = [
    "DesignAgentSession",
    "run_design_engine",
]

from __future__ import annotations

from pathlib import Path

from coco_flow.config import Settings
from coco_flow.prompts.design import (
    build_architect_prompt,
    build_architect_template_json,
    build_revision_prompt,
    build_revision_template_json,
    build_skeptic_prompt,
    build_skeptic_template_json,
)

from .agent_io import run_agent_json
from .models import EXECUTOR_NATIVE, DesignInputBundle
from .research import candidate_paths
from .utils import as_str_list, dedupe, dict_list, first_non_empty, issue, issues, normalize_issue


def build_architect_adjudication(
    prepared: DesignInputBundle,
    research_plan_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> dict[str, object]:
    if native_ok:
        try:
            payload = run_agent_json(
                prepared,
                settings,
                build_architect_template_json(),
                lambda template_path: build_architect_prompt(
                    title=prepared.title,
                    refined_markdown=prepared.refined_markdown,
                    skills_brief_markdown=prepared.refine_skills_read_markdown,
                    research_plan_payload=research_plan_payload,
                    research_summary_payload=research_summary_payload,
                    template_path=template_path,
                ),
                ".design-architect-",
            )
            normalized = normalize_adjudication(prepared, payload, research_summary_payload)
            normalized["native"] = True
            return normalized
        except Exception as error:
            on_log(f"design_v3_architect_degraded: {error}")
    payload = build_local_adjudication(prepared, research_summary_payload)
    payload["native"] = False
    return payload


def build_local_adjudication(prepared: DesignInputBundle, research_summary_payload: dict[str, object]) -> dict[str, object]:
    decisions: list[dict[str, object]] = []
    for repo in dict_list(research_summary_payload.get("repos")):
        candidates = candidate_paths(repo)
        work_type = "must_change" if candidates else "validate_only"
        decisions.append(
            {
                "repo_id": str(repo.get("repo_id") or ""),
                "work_type": work_type,
                "responsibility": _repo_responsibility(prepared, str(repo.get("repo_id") or ""), candidates),
                "candidate_files": candidates,
                "candidate_dirs": sorted({str(Path(path).parent) for path in candidates if str(Path(path).parent) != "."})[:6],
                "boundaries": as_str_list(repo.get("boundaries")),
                "risks": as_str_list(repo.get("unknowns"))[:4],
                "unresolved_questions": as_str_list(repo.get("unknowns"))[:4],
                "confidence": str(repo.get("confidence") or "low"),
                "evidence_refs": [str(item.get("path") or "") for item in dict_list(repo.get("evidence")) if str(item.get("path") or "")],
            }
        )
    return {
        "decision_summary": first_non_empty(prepared.sections.change_scope, prepared.title),
        "core_change_points": prepared.sections.change_scope or [prepared.title],
        "repo_decisions": decisions,
        "system_boundaries": prepared.sections.non_goals,
        "risks": prepared.sections.open_questions,
        "unresolved_questions": [
            item for repo in decisions for item in as_str_list(repo.get("unresolved_questions"))
        ][:8],
    }


def normalize_adjudication(
    prepared: DesignInputBundle,
    payload: dict[str, object],
    research_summary_payload: dict[str, object],
) -> dict[str, object]:
    research_by_repo = {
        str(repo.get("repo_id") or ""): repo
        for repo in dict_list(research_summary_payload.get("repos"))
    }
    decisions: list[dict[str, object]] = []
    for repo in prepared.repo_scopes:
        raw = _find_repo_decision(payload, repo.repo_id)
        research = research_by_repo.get(repo.repo_id, {})
        allowed_files = set(candidate_paths(research))
        candidates = [path for path in as_str_list(raw.get("candidate_files")) if path in allowed_files]
        if not candidates:
            candidates = candidate_paths(research)
        work_type = _normalize_work_type(raw.get("work_type"), candidates)
        decisions.append(
            {
                "repo_id": repo.repo_id,
                "work_type": work_type,
                "responsibility": str(raw.get("responsibility") or _repo_responsibility(prepared, repo.repo_id, candidates)).strip(),
                "candidate_files": candidates[:12],
                "candidate_dirs": as_str_list(raw.get("candidate_dirs"))[:8],
                "boundaries": as_str_list(raw.get("boundaries"))[:8],
                "risks": as_str_list(raw.get("risks"))[:8],
                "unresolved_questions": as_str_list(raw.get("unresolved_questions"))[:8],
                "confidence": _normalize_confidence(raw.get("confidence"), "medium" if candidates else "low"),
                "evidence_refs": as_str_list(raw.get("evidence_refs"))[:12],
            }
        )
    return {
        "decision_summary": str(payload.get("decision_summary") or first_non_empty(prepared.sections.change_scope, prepared.title)).strip(),
        "core_change_points": as_str_list(payload.get("core_change_points")) or prepared.sections.change_scope or [prepared.title],
        "repo_decisions": decisions,
        "system_boundaries": as_str_list(payload.get("system_boundaries")) or prepared.sections.non_goals,
        "risks": as_str_list(payload.get("risks")) or prepared.sections.open_questions,
        "unresolved_questions": as_str_list(payload.get("unresolved_questions")),
    }


def build_skeptic_review(
    prepared: DesignInputBundle,
    adjudication_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> dict[str, object]:
    if native_ok:
        try:
            payload = run_agent_json(
                prepared,
                settings,
                build_skeptic_template_json(),
                lambda template_path: build_skeptic_prompt(
                    title=prepared.title,
                    refined_markdown=prepared.refined_markdown,
                    adjudication_payload=adjudication_payload,
                    research_summary_payload=research_summary_payload,
                    template_path=template_path,
                ),
                ".design-skeptic-",
            )
            return normalize_review(payload)
        except Exception as error:
            on_log(f"design_v3_skeptic_degraded: {error}")
    return local_skeptic_review(prepared, adjudication_payload)


def local_skeptic_review(prepared: DesignInputBundle, adjudication_payload: dict[str, object]) -> dict[str, object]:
    review_issues: list[dict[str, object]] = []
    decisions = dict_list(adjudication_payload.get("repo_decisions"))
    if not decisions:
        review_issues.append(issue("blocking", "repo_role_missing", "repo_decisions", "至少需要一个仓库职责裁决。", "没有 repo decision。", "补充 repo research 后重跑 design。"))
    if not prepared.sections.change_scope and not prepared.refined_markdown.strip():
        review_issues.append(issue("blocking", "prd_scope_missing", "prd-refined.md", "Design 必须有 refined PRD 基线。", "refined PRD 缺失。", "先完成 refine。"))
    for item in decisions:
        if str(item.get("work_type") or "") in {"must_change", "co_change"} and not as_str_list(item.get("candidate_files")):
            review_issues.append(
                issue(
                    "blocking",
                    "candidate_file_not_proven",
                    f"repo_decisions.{item.get('repo_id')}.candidate_files",
                    "代码改造仓库必须有候选文件证据。",
                    "该仓库被判定为代码改造，但 candidate_files 为空。",
                    "降级为 validate_only，或补充 repo research evidence。",
                )
            )
    if any(str(item.get("work_type") or "") == "must_change" for item in decisions):
        return {"ok": not any(str(item.get("severity")) == "blocking" for item in review_issues), "issues": review_issues}
    review_issues.append(
        issue(
            "blocking",
            "no_code_change_repo",
            "repo_decisions",
            "至少一个仓库需要有足够证据承接核心改造，或人工确认无需代码改造。",
            "没有 must_change 仓库。",
            "人工确认仓库职责或补充更明确的需求术语。",
        )
    )
    return {"ok": False, "issues": review_issues}


def normalize_review(payload: dict[str, object]) -> dict[str, object]:
    review_issues = [normalize_issue(item) for item in dict_list(payload.get("issues"))]
    return {"ok": bool(payload.get("ok")) and not any(item["severity"] == "blocking" for item in review_issues), "issues": review_issues}


def build_final_decision(
    prepared: DesignInputBundle,
    adjudication_payload: dict[str, object],
    review_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> tuple[dict[str, object], dict[str, object]]:
    blocking = [item for item in issues(review_payload) if str(item.get("severity")) == "blocking"]
    decision = normalize_decision_for_gate(dict(adjudication_payload), review_payload)
    revision_summary = "skeptic 未发现 blocking issue，无需修订。"
    issue_resolutions: list[dict[str, object]] = []
    if blocking:
        if native_ok:
            try:
                revision_payload = run_agent_json(
                    prepared,
                    settings,
                    build_revision_template_json(),
                    lambda template_path: build_revision_prompt(
                        title=prepared.title,
                        refined_markdown=prepared.refined_markdown,
                        adjudication_payload=adjudication_payload,
                        review_payload=review_payload,
                        research_summary_payload=research_summary_payload,
                        template_path=template_path,
                    ),
                    ".design-revision-",
                )
                issue_resolutions = dict_list(revision_payload.get("issue_resolutions"))
                raw_decision = revision_payload.get("decision")
                if isinstance(raw_decision, dict):
                    decision = normalize_adjudication(prepared, raw_decision, research_summary_payload)
                    revision_summary = "blocking issue 已触发 architect revision，并生成修订后的 design-decision。"
            except Exception as error:
                on_log(f"design_v3_revision_degraded: {error}")
        if not issue_resolutions:
            decision, issue_resolutions = apply_review_issues_to_decision(decision, review_payload)
            revision_summary = "blocking issue 已通过本地通用规则应用到 design-decision。"
        decision = normalize_decision_for_gate(decision, review_payload)
    decision["review_blocking_count"] = len(blocking)
    decision["finalized"] = not any(str(item.get("resolution") or "") != "accepted" for item in issue_resolutions) if blocking else True
    debate = {
        "rounds": [
            {"role": "architect", "artifact": "design-adjudication.json"},
            {"role": "skeptic", "artifact": "design-review.json", "blocking_count": len(blocking)},
        ],
        "revision": {
            "applied": bool(blocking),
            "summary": revision_summary,
            "issue_resolutions": issue_resolutions,
        },
        "task_id": prepared.task_id,
    }
    return decision, debate


def review_payload_after_revision(review_payload: dict[str, object], debate_payload: dict[str, object]) -> dict[str, object]:
    revision = debate_payload.get("revision")
    if not isinstance(revision, dict):
        return review_payload
    accepted_targets = {
        str(item.get("target") or "")
        for item in dict_list(revision.get("issue_resolutions"))
        if str(item.get("resolution") or "") == "accepted"
    }
    if not accepted_targets:
        return review_payload
    review_issues: list[dict[str, object]] = []
    for item in issues(review_payload):
        if str(item.get("target") or "") in accepted_targets and str(item.get("severity") or "") == "blocking":
            fixed = dict(item)
            fixed["severity"] = "info"
            fixed["suggested_action"] = "该 blocking issue 已由 bounded revision 接受并修订。"
            review_issues.append(fixed)
        else:
            review_issues.append(item)
    return {"ok": not any(str(item.get("severity") or "") == "blocking" for item in review_issues), "issues": review_issues}


def apply_review_issues_to_decision(
    decision_payload: dict[str, object],
    review_payload: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    decision = dict(decision_payload)
    repo_decisions = [dict(item) for item in dict_list(decision.get("repo_decisions"))]
    resolutions: list[dict[str, object]] = []
    for item in issues(review_payload):
        if str(item.get("severity") or "") != "blocking":
            continue
        target = str(item.get("target") or "")
        changed = False
        for repo in repo_decisions:
            candidates = as_str_list(repo.get("candidate_files"))
            filtered = [path for path in candidates if path not in target and target not in path]
            if len(filtered) != len(candidates):
                repo["candidate_files"] = filtered
                repo["candidate_dirs"] = sorted({str(Path(path).parent) for path in filtered if str(Path(path).parent) != "."})[:8]
                if not filtered and str(repo.get("work_type") or "") in {"must_change", "co_change"}:
                    repo["work_type"] = "validate_only"
                    repo["confidence"] = "low"
                changed = True
        if not changed:
            questions = as_str_list(decision.get("unresolved_questions"))
            action = str(item.get("suggested_action") or item.get("actual") or "").strip()
            if action:
                questions.append(action)
            decision["unresolved_questions"] = dedupe(questions)
        resolutions.append(
            {
                "failure_type": item.get("failure_type"),
                "target": target,
                "resolution": "accepted",
                "reason": "本地 revision 接受 blocking issue；删除命中的候选文件或转入待确认项。",
                "decision_change": "candidate_removed_or_question_added",
            }
        )
    decision["repo_decisions"] = repo_decisions
    return decision, resolutions


def normalize_decision_for_gate(decision_payload: dict[str, object], review_payload: dict[str, object]) -> dict[str, object]:
    decision = dict(decision_payload)
    repo_decisions: list[dict[str, object]] = []
    for raw in dict_list(decision.get("repo_decisions")):
        item = dict(raw)
        work_type = str(item.get("work_type") or "")
        if work_type in {"validate_only", "reference_only"}:
            item["candidate_files"] = []
            item["candidate_dirs"] = []
        repo_decisions.append(item)
    decision["repo_decisions"] = repo_decisions
    blocking_actions = [
        str(item.get("suggested_action") or item.get("actual") or "").strip()
        for item in issues(review_payload)
        if str(item.get("severity") or "") == "blocking"
    ]
    if blocking_actions:
        decision["unresolved_questions"] = dedupe([*as_str_list(decision.get("unresolved_questions")), *blocking_actions])
    return decision


def derive_repo_binding(prepared: DesignInputBundle, decision_payload: dict[str, object]) -> dict[str, object]:
    bindings: list[dict[str, object]] = []
    decisions = {str(item.get("repo_id") or ""): item for item in dict_list(decision_payload.get("repo_decisions"))}
    for repo in prepared.repo_scopes:
        item = decisions.get(repo.repo_id, {})
        work_type = str(item.get("work_type") or "validate_only")
        scope_tier = {
            "must_change": "must_change",
            "co_change": "co_change",
            "validate_only": "validate_only",
            "reference_only": "reference_only",
        }.get(work_type, "validate_only")
        decision = "in_scope" if scope_tier != "reference_only" else "out_of_scope"
        candidates = as_str_list(item.get("candidate_files"))
        bindings.append(
            {
                "repo_id": repo.repo_id,
                "repo_path": repo.repo_path,
                "decision": decision,
                "scope_tier": scope_tier,
                "serves_change_points": list(range(1, max(2, len(as_str_list(decision_payload.get("core_change_points"))) + 1))),
                "system_name": repo.repo_id,
                "responsibility": str(item.get("responsibility") or "").strip(),
                "change_summary": [str(item.get("responsibility") or "").strip()] if item.get("responsibility") else [],
                "boundaries": as_str_list(item.get("boundaries")),
                "candidate_dirs": as_str_list(item.get("candidate_dirs")),
                "candidate_files": candidates,
                "depends_on": [],
                "parallelizable_with": [other.repo_id for other in prepared.repo_scopes if other.repo_id != repo.repo_id],
                "confidence": _normalize_confidence(item.get("confidence"), "low"),
                "reason": "由 design-decision.json 派生，供 Plan/Code 兼容消费。",
            }
        )
    return {
        "repo_bindings": bindings,
        "missing_repos": [],
        "decision_summary": str(decision_payload.get("decision_summary") or ""),
        "closure_mode": "agentic_review",
        "selection_basis": "design-decision",
        "selection_note": "Design V3 由 repo research、architect、skeptic 和 semantic gate 共同裁决。",
        "mode": "agentic_v3",
    }


def derive_sections(prepared: DesignInputBundle, decision_payload: dict[str, object]) -> dict[str, object]:
    repo_decisions = dict_list(decision_payload.get("repo_decisions"))
    return {
        "system_change_points": as_str_list(decision_payload.get("core_change_points")) or prepared.sections.change_scope,
        "solution_overview": str(decision_payload.get("decision_summary") or prepared.title),
        "system_changes": [
            {
                "system_id": str(item.get("repo_id") or ""),
                "system_name": str(item.get("repo_id") or ""),
                "serves_change_points": [1],
                "responsibility": str(item.get("responsibility") or ""),
                "planned_changes": as_str_list(item.get("candidate_files")) or [str(item.get("responsibility") or "")],
                "upstream_inputs": [],
                "downstream_outputs": [],
                "touched_repos": [str(item.get("repo_id") or "")],
            }
            for item in repo_decisions
            if str(item.get("work_type") or "") in {"must_change", "co_change"}
        ],
        "system_dependencies": [],
        "critical_flows": [],
        "interface_changes": [],
        "risk_boundaries": [
            {"title": risk, "level": "medium", "mitigation": "进入 Plan 前确认。", "blocking": False}
            for risk in as_str_list(decision_payload.get("risks"))
        ],
    }


def _repo_responsibility(prepared: DesignInputBundle, repo_id: str, candidates: list[str]) -> str:
    scope = first_non_empty(prepared.sections.change_scope, prepared.title)
    if candidates:
        return f"围绕「{scope}」收敛 {repo_id} 中候选文件对应的实现边界。"
    return f"检查 {repo_id} 是否参与「{scope}」的上下游联动，不在证据不足时扩大改造范围。"


def _find_repo_decision(payload: dict[str, object], repo_id: str) -> dict[str, object]:
    for item in dict_list(payload.get("repo_decisions")):
        if str(item.get("repo_id") or "") == repo_id:
            return item
    return {}


def _normalize_work_type(value: object, candidates: list[str]) -> str:
    text = str(value or "").strip()
    if text in {"must_change", "co_change", "validate_only", "reference_only"}:
        return text
    return "must_change" if candidates else "validate_only"


def _normalize_confidence(value: object, default: str) -> str:
    text = str(value or default).strip().lower()
    if text in {"high", "medium", "low"}:
        return text
    return default


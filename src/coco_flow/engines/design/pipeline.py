from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Iterable

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.engines.shared.diagnostics import diagnosis_payload_from_verify, enrich_verify_payload
from coco_flow.prompts.design import (
    build_architect_prompt,
    build_architect_template_json,
    build_revision_prompt,
    build_revision_template_json,
    build_semantic_gate_prompt,
    build_semantic_gate_template_json,
    build_skeptic_prompt,
    build_skeptic_template_json,
    build_writer_prompt,
)

from .models import (
    EXECUTOR_NATIVE,
    GATE_DEGRADED,
    GATE_FAILED,
    GATE_NEEDS_HUMAN,
    GATE_PASSED,
    GATE_PASSED_WITH_WARNINGS,
    PLAN_ALLOWED_GATE_STATUSES,
    STATUS_DESIGNED,
    STATUS_FAILED,
    DesignEngineResult,
    DesignInputBundle,
)
from .source import prepare_design_input

_SEARCH_GLOBS = ("*.go", "*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.proto", "*.thrift", "*.sql")
_EXCLUDED_DIRS = {".git", ".livecoding", ".coco-flow", "node_modules", "dist", "build", "__pycache__"}
_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "this",
    "that",
    "true",
    "false",
    "refined",
    "prd",
}


def run_design_engine(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    on_log,
) -> DesignEngineResult:
    on_log("design_v3_prepare_start: true")
    prepared = prepare_design_input(task_dir, task_meta, settings)
    if not prepared.refined_markdown.strip():
        raise ValueError("prd-refined.md 为空，无法执行 design")
    if not prepared.repo_scopes:
        raise ValueError("design requires bound repos; please bind repos first")

    input_payload = build_design_input_payload(prepared)
    input_markdown = build_design_input_markdown(prepared)
    artifacts: dict[str, str | dict[str, object]] = {
        "design-input.json": input_payload,
        "design-input.md": input_markdown,
    }
    on_log(f"design_v3_prepare_ok: repos={len(prepared.repo_scopes)} refined_chars={len(prepared.refined_markdown.strip())}")

    on_log("design_v3_research_plan_start: true")
    research_plan_payload = build_research_plan(prepared)
    artifacts["design-research-plan.json"] = research_plan_payload
    on_log(f"design_v3_research_plan_ok: repos={len(research_plan_payload.get('repos', []))}")

    on_log("design_v3_repo_research_start: true")
    repo_research_payloads = run_parallel_repo_research(prepared, research_plan_payload)
    for repo_payload in repo_research_payloads:
        repo_id = str(repo_payload.get("repo_id") or "repo")
        artifacts[f"design-research/{_safe_artifact_name(repo_id)}.json"] = repo_payload
    research_summary_payload = build_research_summary(repo_research_payloads)
    artifacts["design-research-summary.json"] = research_summary_payload
    on_log(f"design_v3_repo_research_ok: repos={len(repo_research_payloads)}")

    native_ok = settings.plan_executor.strip().lower() == EXECUTOR_NATIVE
    on_log("design_v3_architect_start: true")
    adjudication_payload = build_architect_adjudication(
        prepared,
        research_plan_payload,
        research_summary_payload,
        settings,
        native_ok=native_ok,
        on_log=on_log,
    )
    artifacts["design-adjudication.json"] = adjudication_payload
    on_log(f"design_v3_architect_ok: native={'true' if bool(adjudication_payload.get('native')) else 'false'}")

    on_log("design_v3_skeptic_start: true")
    review_payload = build_skeptic_review(
        prepared,
        adjudication_payload,
        research_summary_payload,
        settings,
        native_ok=native_ok and bool(adjudication_payload.get("native")),
        on_log=on_log,
    )
    artifacts["design-review.json"] = review_payload
    on_log(f"design_v3_skeptic_ok: ok={'true' if bool(review_payload.get('ok')) else 'false'} issues={len(_issues(review_payload))}")

    decision_payload, debate_payload = build_final_decision(
        prepared,
        adjudication_payload,
        review_payload,
        research_summary_payload,
        settings,
        native_ok=native_ok and bool(adjudication_payload.get("native")),
        on_log=on_log,
    )
    artifacts["design-debate.json"] = debate_payload
    artifacts["design-decision.json"] = decision_payload
    repo_binding_payload = derive_repo_binding(prepared, decision_payload)
    sections_payload = derive_sections(prepared, decision_payload)
    artifacts["design-repo-binding.json"] = repo_binding_payload
    artifacts["design-sections.json"] = sections_payload
    gate_review_payload = review_payload_after_revision(review_payload, debate_payload)

    on_log("design_v3_writer_start: true")
    design_markdown = write_design_markdown(
        prepared,
        decision_payload,
        settings,
        native_ok=native_ok and bool(adjudication_payload.get("native")),
        on_log=on_log,
    )
    on_log("design_v3_writer_ok: true")

    on_log("design_v3_gate_start: true")
    verify_payload = run_semantic_gate(
        prepared,
        decision_payload,
        design_markdown,
        settings,
        native_ok=native_ok and bool(adjudication_payload.get("native")),
        review_payload=gate_review_payload,
        on_log=on_log,
    )
    gate_status = str(verify_payload.get("gate_status") or GATE_FAILED)
    verify_payload = enrich_verify_payload(stage="design", verify_payload=verify_payload, artifact="design.md")
    artifacts["design-verify.json"] = verify_payload
    diagnosis_payload = build_design_diagnosis(verify_payload)
    artifacts["design-diagnosis.json"] = diagnosis_payload
    on_log(f"design_v3_gate_ok: gate_status={gate_status} ok={'true' if bool(verify_payload.get('ok')) else 'false'}")

    task_status = STATUS_DESIGNED if gate_status in PLAN_ALLOWED_GATE_STATUSES else STATUS_FAILED
    artifacts["design-result.json"] = {
        "task_id": prepared.task_id,
        "status": task_status,
        "gate_status": gate_status,
        "agentic_version": "v3",
        "native": bool(adjudication_payload.get("native")) and gate_status != GATE_DEGRADED,
        "plan_allowed": gate_status in PLAN_ALLOWED_GATE_STATUSES,
        "artifacts": sorted(artifacts.keys()),
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    on_log(f"status: {task_status}")
    return DesignEngineResult(
        status=task_status,
        gate_status=gate_status,
        design_markdown=design_markdown,
        repo_binding_payload=repo_binding_payload,
        sections_payload=sections_payload,
        intermediate_artifacts=artifacts,
    )


def build_design_input_payload(prepared: DesignInputBundle) -> dict[str, object]:
    return {
        "task_id": prepared.task_id,
        "title": prepared.title,
        "repos": [{"repo_id": item.repo_id, "repo_path": item.repo_path} for item in prepared.repo_scopes],
        "selected_skill_ids": prepared.selected_skill_ids,
        "refined_scope": prepared.sections.change_scope,
        "manual_change_points": _manual_change_points(prepared),
        "constraints": prepared.sections.key_constraints,
        "non_goals": prepared.sections.non_goals,
        "open_questions": prepared.sections.open_questions,
    }


def build_design_input_markdown(prepared: DesignInputBundle) -> str:
    parts = [
        f"# Design Input: {prepared.title}",
        "",
        "## Bound Repos",
        *[f"- {repo.repo_id}: {repo.repo_path}" for repo in prepared.repo_scopes],
        "",
        "## Refined PRD",
        prepared.refined_markdown.strip(),
    ]
    if prepared.refine_skills_read_markdown.strip():
        parts.extend(["", "## Skills Brief", prepared.refine_skills_read_markdown.strip()])
    return "\n".join(parts).rstrip() + "\n"


def build_research_plan(prepared: DesignInputBundle) -> dict[str, object]:
    terms = _extract_search_terms(prepared)
    questions = _default_questions(prepared)
    return {
        "repos": [
            {
                "repo_id": repo.repo_id,
                "repo_path": repo.repo_path,
                "questions": questions,
                "search_terms": terms,
                "preferred_paths": _preferred_paths(repo.repo_path),
                "budget": {"max_files_read": 12, "max_search_commands": 8},
            }
            for repo in prepared.repo_scopes
        ]
    }


def run_parallel_repo_research(prepared: DesignInputBundle, plan_payload: dict[str, object]) -> list[dict[str, object]]:
    plans = _repo_plan_items(plan_payload)
    by_repo = {str(item.get("repo_id") or ""): item for item in plans}
    max_workers = min(4, max(1, len(prepared.repo_scopes)))
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="design-v3-research") as executor:
        futures = {
            executor.submit(research_single_repo, repo.repo_id, repo.repo_path, by_repo.get(repo.repo_id, {})): repo.repo_id
            for repo in prepared.repo_scopes
        }
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda item: str(item.get("repo_id") or ""))


def research_single_repo(repo_id: str, repo_path: str, repo_plan: dict[str, object]) -> dict[str, object]:
    root = Path(repo_path)
    if not root.is_dir():
        return {
            "repo_id": repo_id,
            "repo_path": repo_path,
            "work_hypothesis": "unknown",
            "confidence": "low",
            "evidence": [],
            "candidate_files": [],
            "boundaries": [],
            "unknowns": [f"repo path not found: {repo_path}"],
            "budget_used": {"search_commands": 0, "files_read": 0},
        }

    terms = _as_str_list(repo_plan.get("search_terms"))[: int(_budget(repo_plan, "max_search_commands", 8))]
    seen_files: dict[str, list[dict[str, object]]] = {}
    search_count = 0
    for term in terms:
        search_count += 1
        for match in _rg_matches(root, term):
            rel = match["path"]
            seen_files.setdefault(rel, []).append(match)

    max_files = int(_budget(repo_plan, "max_files_read", 12))
    ranked_files = _rank_candidate_files(seen_files)
    candidate_files = [item for item in ranked_files if bool(item.get("core_evidence"))][:max_files]
    related_files = [item for item in ranked_files if not bool(item.get("core_evidence"))][:max_files]
    evidence: list[dict[str, object]] = []
    for item in candidate_files:
        first_match = seen_files.get(item["path"], [{}])[0]
        evidence.append(
            {
                "path": item["path"],
                "line_hint": int(first_match.get("line") or 1),
                "why_relevant": item["reason"],
                "scene": item.get("scene", ""),
                "symbol": item.get("symbol", ""),
                "matched_behavior": item.get("matched_behavior", ""),
                "why_core": item.get("why_core", ""),
                "excerpt": _read_excerpt(root / item["path"], int(first_match.get("line") or 1)),
            }
        )

    boundaries = []
    if not any(str(item["path"]).endswith((".proto", ".thrift")) for item in candidate_files):
        boundaries.append("未从搜索证据中发现协议文件改动信号。")
    if not candidate_files:
        boundaries.append("当前搜索预算内未定位到直接候选文件。")

    confidence = "high" if len(candidate_files) >= 3 else "medium" if candidate_files else "low"
    return {
        "repo_id": repo_id,
        "repo_path": repo_path,
        "work_hypothesis": "requires_code_change" if candidate_files else "needs_human_confirmation",
        "confidence": confidence,
        "evidence": evidence,
        "candidate_files": candidate_files,
        "related_files": related_files,
        "boundaries": boundaries,
        "unknowns": [] if candidate_files else ["需要人工确认该仓是否承担核心改造，或补充更明确的搜索术语。"],
        "budget_used": {"search_commands": search_count, "files_read": len(candidate_files)},
    }


def build_research_summary(repo_research_payloads: list[dict[str, object]]) -> dict[str, object]:
    return {
        "repos": repo_research_payloads,
        "unknowns": [
            f"{repo.get('repo_id')}: {unknown}"
            for repo in repo_research_payloads
            for unknown in _as_str_list(repo.get("unknowns"))
        ],
        "candidate_file_count": sum(len(_dict_list(repo.get("candidate_files"))) for repo in repo_research_payloads),
    }


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
            payload = _run_agent_json(
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
    for repo in _dict_list(research_summary_payload.get("repos")):
        candidate_files = _candidate_paths(repo)
        work_type = "must_change" if candidate_files else "validate_only"
        decisions.append(
            {
                "repo_id": str(repo.get("repo_id") or ""),
                "work_type": work_type,
                "responsibility": _repo_responsibility(prepared, str(repo.get("repo_id") or ""), candidate_files),
                "candidate_files": candidate_files,
                "candidate_dirs": sorted({str(Path(path).parent) for path in candidate_files if str(Path(path).parent) != "."})[:6],
                "boundaries": _as_str_list(repo.get("boundaries")),
                "risks": _as_str_list(repo.get("unknowns"))[:4],
                "unresolved_questions": _as_str_list(repo.get("unknowns"))[:4],
                "confidence": str(repo.get("confidence") or "low"),
                "evidence_refs": [str(item.get("path") or "") for item in _dict_list(repo.get("evidence")) if str(item.get("path") or "")],
            }
        )
    return {
        "decision_summary": _first_non_empty(prepared.sections.change_scope, prepared.title),
        "core_change_points": prepared.sections.change_scope or [prepared.title],
        "repo_decisions": decisions,
        "system_boundaries": prepared.sections.non_goals,
        "risks": prepared.sections.open_questions,
        "unresolved_questions": [
            item for repo in decisions for item in _as_str_list(repo.get("unresolved_questions"))
        ][:8],
    }


def normalize_adjudication(
    prepared: DesignInputBundle,
    payload: dict[str, object],
    research_summary_payload: dict[str, object],
) -> dict[str, object]:
    research_by_repo = {
        str(repo.get("repo_id") or ""): repo
        for repo in _dict_list(research_summary_payload.get("repos"))
    }
    decisions: list[dict[str, object]] = []
    for repo in prepared.repo_scopes:
        raw = _find_repo_decision(payload, repo.repo_id)
        research = research_by_repo.get(repo.repo_id, {})
        allowed_files = set(_candidate_paths(research))
        candidate_files = [path for path in _as_str_list(raw.get("candidate_files")) if path in allowed_files]
        if not candidate_files:
            candidate_files = _candidate_paths(research)
        work_type = _normalize_work_type(raw.get("work_type"), candidate_files)
        decisions.append(
            {
                "repo_id": repo.repo_id,
                "work_type": work_type,
                "responsibility": str(raw.get("responsibility") or _repo_responsibility(prepared, repo.repo_id, candidate_files)).strip(),
                "candidate_files": candidate_files[:12],
                "candidate_dirs": _as_str_list(raw.get("candidate_dirs"))[:8],
                "boundaries": _as_str_list(raw.get("boundaries"))[:8],
                "risks": _as_str_list(raw.get("risks"))[:8],
                "unresolved_questions": _as_str_list(raw.get("unresolved_questions"))[:8],
                "confidence": _normalize_confidence(raw.get("confidence"), "medium" if candidate_files else "low"),
                "evidence_refs": _as_str_list(raw.get("evidence_refs"))[:12],
            }
        )
    return {
        "decision_summary": str(payload.get("decision_summary") or _first_non_empty(prepared.sections.change_scope, prepared.title)).strip(),
        "core_change_points": _as_str_list(payload.get("core_change_points")) or prepared.sections.change_scope or [prepared.title],
        "repo_decisions": decisions,
        "system_boundaries": _as_str_list(payload.get("system_boundaries")) or prepared.sections.non_goals,
        "risks": _as_str_list(payload.get("risks")) or prepared.sections.open_questions,
        "unresolved_questions": _as_str_list(payload.get("unresolved_questions")),
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
            payload = _run_agent_json(
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
    issues: list[dict[str, object]] = []
    decisions = _dict_list(adjudication_payload.get("repo_decisions"))
    if not decisions:
        issues.append(_issue("blocking", "repo_role_missing", "repo_decisions", "至少需要一个仓库职责裁决。", "没有 repo decision。", "补充 repo research 后重跑 design。"))
    if not prepared.sections.change_scope and not prepared.refined_markdown.strip():
        issues.append(_issue("blocking", "prd_scope_missing", "prd-refined.md", "Design 必须有 refined PRD 基线。", "refined PRD 缺失。", "先完成 refine。"))
    for item in decisions:
        if str(item.get("work_type") or "") in {"must_change", "co_change"} and not _as_str_list(item.get("candidate_files")):
            issues.append(
                _issue(
                    "blocking",
                    "candidate_file_not_proven",
                    f"repo_decisions.{item.get('repo_id')}.candidate_files",
                    "代码改造仓库必须有候选文件证据。",
                    "该仓库被判定为代码改造，但 candidate_files 为空。",
                    "降级为 validate_only，或补充 repo research evidence。",
                )
            )
    if any(str(item.get("work_type") or "") == "must_change" for item in decisions):
        return {"ok": not any(str(issue.get("severity")) == "blocking" for issue in issues), "issues": issues}
    issues.append(
        _issue(
            "blocking",
            "no_code_change_repo",
            "repo_decisions",
            "至少一个仓库需要有足够证据承接核心改造，或人工确认无需代码改造。",
            "没有 must_change 仓库。",
            "人工确认仓库职责或补充更明确的需求术语。",
        )
    )
    return {"ok": False, "issues": issues}


def normalize_review(payload: dict[str, object]) -> dict[str, object]:
    issues = [normalize_issue(item) for item in _dict_list(payload.get("issues"))]
    return {"ok": bool(payload.get("ok")) and not any(item["severity"] == "blocking" for item in issues), "issues": issues}


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
    blocking = [item for item in _issues(review_payload) if str(item.get("severity")) == "blocking"]
    decision = normalize_decision_for_gate(dict(adjudication_payload), review_payload)
    revision_summary = "skeptic 未发现 blocking issue，无需修订。"
    issue_resolutions: list[dict[str, object]] = []
    if blocking:
        if native_ok:
            try:
                revision_payload = _run_agent_json(
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
                issue_resolutions = _dict_list(revision_payload.get("issue_resolutions"))
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
        for item in _dict_list(revision.get("issue_resolutions"))
        if str(item.get("resolution") or "") == "accepted"
    }
    if not accepted_targets:
        return review_payload
    issues: list[dict[str, object]] = []
    for issue in _issues(review_payload):
        if str(issue.get("target") or "") in accepted_targets and str(issue.get("severity") or "") == "blocking":
            fixed = dict(issue)
            fixed["severity"] = "info"
            fixed["suggested_action"] = "该 blocking issue 已由 bounded revision 接受并修订。"
            issues.append(fixed)
        else:
            issues.append(issue)
    return {"ok": not any(str(item.get("severity") or "") == "blocking" for item in issues), "issues": issues}


def apply_review_issues_to_decision(
    decision_payload: dict[str, object],
    review_payload: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    decision = dict(decision_payload)
    repo_decisions = [dict(item) for item in _dict_list(decision.get("repo_decisions"))]
    resolutions: list[dict[str, object]] = []
    for issue in _issues(review_payload):
        severity = str(issue.get("severity") or "")
        if severity != "blocking":
            continue
        target = str(issue.get("target") or "")
        changed = False
        for repo in repo_decisions:
            candidate_files = _as_str_list(repo.get("candidate_files"))
            filtered = [path for path in candidate_files if path not in target and target not in path]
            if len(filtered) != len(candidate_files):
                repo["candidate_files"] = filtered
                repo["candidate_dirs"] = sorted({str(Path(path).parent) for path in filtered if str(Path(path).parent) != "."})[:8]
                if not filtered and str(repo.get("work_type") or "") in {"must_change", "co_change"}:
                    repo["work_type"] = "validate_only"
                    repo["confidence"] = "low"
                changed = True
        if not changed:
            questions = _as_str_list(decision.get("unresolved_questions"))
            action = str(issue.get("suggested_action") or issue.get("actual") or "").strip()
            if action:
                questions.append(action)
            decision["unresolved_questions"] = _dedupe(questions)
        resolutions.append(
            {
                "failure_type": issue.get("failure_type"),
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
    for raw in _dict_list(decision.get("repo_decisions")):
        item = dict(raw)
        work_type = str(item.get("work_type") or "")
        if work_type in {"validate_only", "reference_only"}:
            item["candidate_files"] = []
            item["candidate_dirs"] = []
        repo_decisions.append(item)
    decision["repo_decisions"] = repo_decisions
    blocking_actions = [
        str(issue.get("suggested_action") or issue.get("actual") or "").strip()
        for issue in _issues(review_payload)
        if str(issue.get("severity") or "") == "blocking"
    ]
    if blocking_actions:
        decision["unresolved_questions"] = _dedupe([*_as_str_list(decision.get("unresolved_questions")), *blocking_actions])
    return decision


def derive_repo_binding(prepared: DesignInputBundle, decision_payload: dict[str, object]) -> dict[str, object]:
    bindings: list[dict[str, object]] = []
    decisions = {str(item.get("repo_id") or ""): item for item in _dict_list(decision_payload.get("repo_decisions"))}
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
        candidate_files = _as_str_list(item.get("candidate_files"))
        bindings.append(
            {
                "repo_id": repo.repo_id,
                "repo_path": repo.repo_path,
                "decision": decision,
                "scope_tier": scope_tier,
                "serves_change_points": list(range(1, max(2, len(_as_str_list(decision_payload.get("core_change_points"))) + 1))),
                "system_name": repo.repo_id,
                "responsibility": str(item.get("responsibility") or "").strip(),
                "change_summary": [str(item.get("responsibility") or "").strip()] if item.get("responsibility") else [],
                "boundaries": _as_str_list(item.get("boundaries")),
                "candidate_dirs": _as_str_list(item.get("candidate_dirs")),
                "candidate_files": candidate_files,
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
    repo_decisions = _dict_list(decision_payload.get("repo_decisions"))
    return {
        "system_change_points": _as_str_list(decision_payload.get("core_change_points")) or prepared.sections.change_scope,
        "solution_overview": str(decision_payload.get("decision_summary") or prepared.title),
        "system_changes": [
            {
                "system_id": str(item.get("repo_id") or ""),
                "system_name": str(item.get("repo_id") or ""),
                "serves_change_points": [1],
                "responsibility": str(item.get("responsibility") or ""),
                "planned_changes": _as_str_list(item.get("candidate_files")) or [str(item.get("responsibility") or "")],
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
            for risk in _as_str_list(decision_payload.get("risks"))
        ],
    }


def write_design_markdown(
    prepared: DesignInputBundle,
    decision_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> str:
    if native_ok:
        try:
            return _run_agent_markdown(
                prepared,
                settings,
                build_local_design_markdown(prepared, decision_payload),
                lambda template_path: build_writer_prompt(
                    title=prepared.title,
                    decision_payload=decision_payload,
                    template_path=template_path,
                ),
                ".design-writer-",
            )
        except Exception as error:
            on_log(f"design_v3_writer_degraded: {error}")
    return build_local_design_markdown(prepared, decision_payload)


def build_local_design_markdown(prepared: DesignInputBundle, decision_payload: dict[str, object]) -> str:
    blocking_count = int(decision_payload.get("review_blocking_count") or 0)
    finalized = bool(decision_payload.get("finalized"))
    parts = [
        f"# {prepared.title} Design",
        "",
        "## 结论",
        _local_design_conclusion(decision_payload, blocking_count, finalized),
        "",
        "## 核心改造点",
    ]
    for index, item in enumerate(_as_str_list(decision_payload.get("core_change_points")) or prepared.sections.change_scope or [prepared.title], start=1):
        parts.append(f"{index}. {item}")
    parts.extend(["", "## 分仓库方案"])
    for item in _dict_list(decision_payload.get("repo_decisions")):
        repo_id = str(item.get("repo_id") or "")
        work_type = str(item.get("work_type") or "")
        action = "主要代码改造" if work_type in {"must_change", "co_change"} else "联动检查" if work_type == "validate_only" else "参考"
        parts.extend(["", f"### {repo_id}", f"- 主要事项：{action}。{str(item.get('responsibility') or '').strip()}"])
        files = _as_str_list(item.get("candidate_files"))
        if files:
            parts.append("- 候选文件：" + "、".join(files[:8]))
        boundaries = _as_str_list(item.get("boundaries"))
        if boundaries:
            parts.append("- 边界：" + "；".join(boundaries[:4]))
    risks = _as_str_list(decision_payload.get("risks"))
    unresolved = _as_str_list(decision_payload.get("unresolved_questions"))
    parts.extend(["", "## 风险与待确认"])
    if risks or unresolved:
        for item in [*risks, *unresolved]:
            parts.append(f"- {item}")
    else:
        parts.append("- 暂无阻塞性待确认项。")
    if blocking_count > 0 and not finalized:
        parts.extend(["", "## 当前阻断", "- Skeptic review 仍存在阻塞问题，当前 Design 不能进入 Plan。"])
    if prepared.sections.non_goals:
        parts.extend(["", "## 明确不做"])
        parts.extend(f"- {item}" for item in prepared.sections.non_goals)
    return "\n".join(parts).rstrip() + "\n"


def _local_design_conclusion(decision_payload: dict[str, object], blocking_count: int, finalized: bool) -> str:
    summary = str(decision_payload.get("decision_summary") or "本阶段已形成初版设计裁决。").strip()
    if blocking_count > 0 and not finalized:
        return f"当前不能进入 Plan。{summary}"
    return summary


def run_semantic_gate(
    prepared: DesignInputBundle,
    decision_payload: dict[str, object],
    design_markdown: str,
    settings: Settings,
    *,
    native_ok: bool,
    review_payload: dict[str, object],
    on_log,
) -> dict[str, object]:
    if native_ok:
        try:
            payload = _run_agent_json(
                prepared,
                settings,
                build_semantic_gate_template_json(),
                lambda template_path: build_semantic_gate_prompt(
                    title=prepared.title,
                    refined_markdown=prepared.refined_markdown,
                    decision_payload=decision_payload,
                    design_markdown=design_markdown,
                    template_path=template_path,
                ),
                ".design-gate-",
            )
            return normalize_gate_payload(payload, review_payload)
        except Exception as error:
            on_log(f"design_v3_gate_degraded: {error}")
    return local_gate_payload(prepared, decision_payload, design_markdown, review_payload, degraded=True)


def local_gate_payload(
    prepared: DesignInputBundle,
    decision_payload: dict[str, object],
    design_markdown: str,
    review_payload: dict[str, object],
    *,
    degraded: bool,
) -> dict[str, object]:
    issues = list(_issues(review_payload))
    if "# " not in design_markdown:
        issues.append(_issue("blocking", "design_markdown_invalid", "design.md", "design.md 必须是 Markdown 文档。", "缺少标题。", "重新生成 design.md。"))
    if not _dict_list(decision_payload.get("repo_decisions")):
        issues.append(_issue("blocking", "repo_decision_missing", "design-decision.json", "必须存在 repo_decisions。", "repo_decisions 为空。", "重跑 architect adjudication。"))
    blocking = [item for item in issues if str(item.get("severity")) == "blocking"]
    if blocking:
        gate_status = GATE_NEEDS_HUMAN
    elif degraded:
        gate_status = GATE_DEGRADED
    elif issues:
        gate_status = GATE_PASSED_WITH_WARNINGS
    else:
        gate_status = GATE_PASSED
    return {
        "ok": gate_status in {GATE_PASSED, GATE_PASSED_WITH_WARNINGS},
        "gate_status": gate_status,
        "issues": issues,
        "reason": _normalized_gate_reason(gate_status, issues, _gate_reason(gate_status, prepared)),
    }


def normalize_gate_payload(payload: dict[str, object], review_payload: dict[str, object]) -> dict[str, object]:
    issues = [normalize_issue(item) for item in _dict_list(payload.get("issues"))] + _issues(review_payload)
    blocking = [item for item in issues if str(item.get("severity")) == "blocking"]
    gate_status = str(payload.get("gate_status") or "").strip()
    if blocking:
        gate_status = GATE_NEEDS_HUMAN
    if gate_status not in {GATE_PASSED, GATE_PASSED_WITH_WARNINGS, GATE_NEEDS_HUMAN, GATE_DEGRADED, GATE_FAILED}:
        gate_status = GATE_PASSED if bool(payload.get("ok")) and not blocking else GATE_NEEDS_HUMAN
    return {
        "ok": gate_status in {GATE_PASSED, GATE_PASSED_WITH_WARNINGS},
        "gate_status": gate_status,
        "issues": issues,
        "reason": _normalized_gate_reason(gate_status, issues, str(payload.get("reason") or "")),
    }


def build_design_diagnosis(verify_payload: dict[str, object]) -> dict[str, object]:
    gate_status = str(verify_payload.get("gate_status") or GATE_FAILED)
    if gate_status == GATE_PASSED:
        return diagnosis_payload_from_verify(stage="design", verify_payload=verify_payload, artifact="design.md")
    severity = "warning" if gate_status == GATE_PASSED_WITH_WARNINGS else gate_status
    return {
        "ok": bool(verify_payload.get("ok")),
        "stage": "design",
        "severity": severity,
        "failure_type": gate_status,
        "next_action": "needs_human" if gate_status in {GATE_NEEDS_HUMAN, GATE_DEGRADED} else "retry",
        "retryable": gate_status == GATE_FAILED,
        "attempt": 0,
        "max_attempts": 0,
        "issues": _issues(verify_payload),
        "reason": str(verify_payload.get("reason") or _gate_reason(gate_status, None)),
    }


def _run_agent_json(
    prepared: DesignInputBundle,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
) -> dict[str, object]:
    raw = _run_agent_template(prepared, settings, template, prompt_builder, prefix, ".json")
    if "__FILL__" in raw or not raw.strip():
        raise ValueError("design_agent_template_unfilled")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("design_agent_payload_not_object")
    return payload


def _run_agent_markdown(
    prepared: DesignInputBundle,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
) -> str:
    raw = _run_agent_template(prepared, settings, template, prompt_builder, prefix, ".md")
    if not raw.strip():
        raise ValueError("design_agent_markdown_empty")
    return raw.rstrip() + "\n"


def _run_agent_template(
    prepared: DesignInputBundle,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
    suffix: str,
) -> str:
    path = _write_template(prepared.task_dir, prefix, suffix, template)
    client = CocoACPClient(settings.coco_bin, idle_timeout_seconds=settings.acp_idle_timeout_seconds, settings=settings)
    try:
        client.run_agent(
            prompt_builder(str(path)),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        return path.read_text(encoding="utf-8") if path.exists() else ""
    finally:
        if path.exists():
            path.unlink()


def _write_template(task_dir: Path, prefix: str, suffix: str, content: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=task_dir, prefix=prefix, suffix=suffix, delete=False) as handle:
        handle.write(content)
        handle.flush()
        return Path(handle.name)


def _rg_matches(root: Path, term: str) -> list[dict[str, object]]:
    if not term.strip():
        return []
    cmd = ["rg", "--line-number", "--no-heading", "-m", "5"]
    for glob in _SEARCH_GLOBS:
        cmd.extend(["--glob", glob])
    cmd.extend([term, str(root)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    matches: list[dict[str, object]] = []
    for line in result.stdout.splitlines()[:40]:
        path, line_no, text = _parse_rg_line(root, line)
        if path:
            matches.append({"path": path, "line": line_no, "term": term, "text": text})
    return matches


def _parse_rg_line(root: Path, line: str) -> tuple[str, int, str]:
    parts = line.split(":", 2)
    if len(parts) < 3:
        return "", 1, ""
    try:
        rel = str(Path(parts[0]).resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        rel = parts[0]
    if any(part in _EXCLUDED_DIRS for part in Path(rel).parts):
        return "", 1, ""
    try:
        line_no = int(parts[1])
    except ValueError:
        line_no = 1
    return rel, line_no, parts[2].strip()[:240]


def _rank_candidate_files(seen_files: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    ranked = sorted(seen_files.items(), key=lambda item: (-_evidence_score(item[0], item[1]), item[0]))
    return [
        {
            "path": path,
            "kind": "core_change",
            "confidence": "high" if _evidence_score(path, matches) >= 6 else "medium",
            "reason": _candidate_reason(path, matches),
            "scene": _path_scene(path),
            "symbol": _match_symbol(matches),
            "matched_behavior": _match_terms_text(matches),
            "why_core": "路径和多组需求术语共同命中，适合作为核心候选。" if _is_core_candidate(path, matches) else "",
            "core_evidence": _is_core_candidate(path, matches),
        }
        for path, matches in ranked
    ]


def _read_excerpt(path: Path, line_hint: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    start = max(0, line_hint - 3)
    end = min(len(lines), line_hint + 2)
    return "\n".join(lines[start:end])[:800]


def _extract_search_terms(prepared: DesignInputBundle) -> list[str]:
    source = "\n".join(
        [
            prepared.title,
            *prepared.sections.change_scope,
            *prepared.sections.key_constraints,
            *prepared.sections.acceptance_criteria,
            prepared.refined_markdown[:4000],
        ]
    )
    terms: list[str] = []
    for value in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", source):
        lower = value.lower()
        if lower not in _STOPWORDS:
            terms.append(value)
    for value in re.findall(r"[\u4e00-\u9fff]{2,8}", source):
        terms.append(value)
    return _dedupe(terms)[:12] or [prepared.title]


def _preferred_paths(repo_path: str) -> list[str]:
    root = Path(repo_path)
    if not root.is_dir():
        return []
    names = ["src", "pkg", "biz", "internal", "api", "web", "service"]
    return [name for name in names if (root / name).is_dir()]


def _default_questions(prepared: DesignInputBundle) -> list[str]:
    scope = _first_non_empty(prepared.sections.change_scope, prepared.title)
    return [
        f"仓库中是否存在与「{scope}」直接对应的模块、入口或数据转换逻辑？",
        "是否存在接口、协议、状态聚合或下游消费边界？",
        "如果该仓不需要代码改动，证据边界是什么？",
    ]


def _manual_change_points(prepared: DesignInputBundle) -> list[str]:
    raw = prepared.refine_brief_payload.get("change_points") or prepared.refine_intent_payload.get("change_points")
    return _as_str_list(raw)


def _repo_plan_items(plan_payload: dict[str, object]) -> list[dict[str, object]]:
    return _dict_list(plan_payload.get("repos"))


def _budget(repo_plan: dict[str, object], key: str, default: int) -> object:
    raw = repo_plan.get("budget")
    if isinstance(raw, dict):
        return raw.get(key) or default
    return default


def _candidate_paths(repo: dict[str, object]) -> list[str]:
    return [
        str(item.get("path") or "")
        for item in _dict_list(repo.get("candidate_files"))
        if str(item.get("path") or "").strip()
    ]


def _repo_responsibility(prepared: DesignInputBundle, repo_id: str, candidate_files: list[str]) -> str:
    scope = _first_non_empty(prepared.sections.change_scope, prepared.title)
    if candidate_files:
        return f"围绕「{scope}」收敛 {repo_id} 中候选文件对应的实现边界。"
    return f"检查 {repo_id} 是否参与「{scope}」的上下游联动，不在证据不足时扩大改造范围。"


def _find_repo_decision(payload: dict[str, object], repo_id: str) -> dict[str, object]:
    for item in _dict_list(payload.get("repo_decisions")):
        if str(item.get("repo_id") or "") == repo_id:
            return item
    return {}


def _normalize_work_type(value: object, candidate_files: list[str]) -> str:
    text = str(value or "").strip()
    if text in {"must_change", "co_change", "validate_only", "reference_only"}:
        return text
    return "must_change" if candidate_files else "validate_only"


def _normalize_confidence(value: object, default: str) -> str:
    text = str(value or default).strip().lower()
    if text in {"high", "medium", "low"}:
        return text
    return default


def normalize_issue(item: dict[str, object]) -> dict[str, object]:
    severity = str(item.get("severity") or "warning").strip()
    if severity not in {"blocking", "warning", "info"}:
        severity = "warning"
    return {
        "severity": severity,
        "failure_type": str(item.get("failure_type") or "semantic_risk"),
        "target": str(item.get("target") or ""),
        "expected": str(item.get("expected") or ""),
        "actual": str(item.get("actual") or ""),
        "suggested_action": str(item.get("suggested_action") or ""),
    }


def _issue(severity: str, failure_type: str, target: str, expected: str, actual: str, suggested_action: str) -> dict[str, object]:
    return {
        "severity": severity,
        "failure_type": failure_type,
        "target": target,
        "expected": expected,
        "actual": actual,
        "suggested_action": suggested_action,
    }


def _issues(payload: dict[str, object]) -> list[dict[str, object]]:
    return [normalize_issue(item) for item in _dict_list(payload.get("issues"))]


def _gate_reason(gate_status: str, prepared: DesignInputBundle | None) -> str:
    if gate_status == GATE_PASSED:
        return "Design V3 semantic gate passed."
    if gate_status == GATE_PASSED_WITH_WARNINGS:
        return "Design V3 semantic gate passed with warnings."
    if gate_status == GATE_DEGRADED:
        return "Design V3 only produced a local or partial draft; human confirmation is required before Plan."
    if gate_status == GATE_NEEDS_HUMAN:
        title = prepared.title if prepared is not None else "当前任务"
        return f"{title} 的设计裁决存在证据不足或 blocking issue，需要人工确认。"
    return "Design V3 failed."


def _normalized_gate_reason(gate_status: str, issues: list[dict[str, object]], fallback: str) -> str:
    blocking = [item for item in issues if str(item.get("severity") or "") == "blocking"]
    if gate_status in {GATE_NEEDS_HUMAN, GATE_FAILED, GATE_DEGRADED} and blocking:
        first = blocking[0]
        target = str(first.get("target") or "design decision")
        action = str(first.get("suggested_action") or first.get("actual") or "").strip()
        if action:
            return f"存在阻塞问题：{target}。{action}"
        return f"存在阻塞问题：{target}。"
    if gate_status == GATE_DEGRADED:
        return _gate_reason(gate_status, None)
    if gate_status == GATE_NEEDS_HUMAN and "能够支撑" in fallback:
        return _gate_reason(gate_status, None)
    return fallback or _gate_reason(gate_status, None)


def _evidence_score(path: str, matches: list[dict[str, object]]) -> int:
    distinct_terms = {str(item.get("term") or "").lower() for item in matches if str(item.get("term") or "").strip()}
    path_parts = {part.lower() for part in Path(path).parts}
    score = len(matches) + len(distinct_terms) * 2
    if any(part in {"test", "tests", "__tests__"} for part in path_parts) or path.endswith(("_test.go", ".test.ts", ".spec.ts")):
        score -= 4
    if any(part in {"src", "pkg", "internal", "entities", "converters", "dal", "service", "api"} for part in path_parts):
        score += 2
    return score


def _is_core_candidate(path: str, matches: list[dict[str, object]]) -> bool:
    distinct_terms = {str(item.get("term") or "").lower() for item in matches if str(item.get("term") or "").strip()}
    if path.endswith(("_test.go", ".test.ts", ".spec.ts")):
        return False
    return _evidence_score(path, matches) >= 5 and len(distinct_terms) >= 2


def _candidate_reason(path: str, matches: list[dict[str, object]]) -> str:
    distinct_terms = {str(item.get("term") or "") for item in matches if str(item.get("term") or "").strip()}
    if _is_core_candidate(path, matches):
        return f"命中 {len(matches)} 条、{len(distinct_terms)} 组 refined scope 相关证据，且路径不像测试或生成产物。"
    return f"仅作为相关文件：命中 {len(matches)} 条、{len(distinct_terms)} 组证据，尚不足以证明需要修改。"


def _path_scene(path: str) -> str:
    parts = [part for part in Path(path).parts if part not in {"", "."}]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return "/".join(parts[:-1])


def _match_symbol(matches: list[dict[str, object]]) -> str:
    for item in matches:
        text = str(item.get("text") or "")
        match = re.search(r"\b(?:func|type|class|interface|const|var)\s+([A-Za-z_][A-Za-z0-9_]*)", text)
        if match:
            return match.group(1)
    return ""


def _match_terms_text(matches: list[dict[str, object]]) -> str:
    terms = _dedupe(str(item.get("term") or "") for item in matches if str(item.get("term") or "").strip())
    return "、".join(terms[:6])


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_non_empty(values: Iterable[str], fallback: str) -> str:
    for value in values:
        if str(value).strip():
            return str(value).strip()
    return fallback


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        result.append(text)
    return result


def _safe_artifact_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()) or "repo"

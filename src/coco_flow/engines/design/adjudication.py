from __future__ import annotations

import json
from pathlib import Path
import re

from coco_flow.config import Settings
from coco_flow.prompts.design import (
    build_architect_prompt,
    build_architect_template_json,
    build_revision_prompt,
    build_revision_template_json,
    build_skeptic_prompt,
    build_skeptic_template_json,
)

from .agent_io import DesignAgentSession, run_agent_json, run_agent_json_in_session, run_agent_json_with_new_session
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
    agent_session: DesignAgentSession | None = None,
    on_log,
) -> dict[str, object]:
    if native_ok:
        try:
            prompt_builder = lambda template_path: build_architect_prompt(
                title=prepared.title,
                refined_markdown=prepared.refined_markdown,
                skills_brief_markdown=prepared.design_skills_brief_markdown or prepared.refine_skills_read_markdown,
                research_plan_payload=research_plan_payload,
                research_summary_payload=research_summary_payload,
                template_path=template_path,
            )
            if agent_session is not None:
                payload = run_agent_json_in_session(
                    prepared,
                    build_architect_template_json(),
                    prompt_builder,
                    ".design-architect-",
                    agent_session,
                    stage="architect",
                    inline_bootstrap=False,
                    on_log=on_log,
                )
            else:
                payload = run_agent_json(
                    prepared,
                    settings,
                    build_architect_template_json(),
                    prompt_builder,
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
        "repo_dependencies": infer_repo_dependencies(prepared, {"repo_decisions": decisions}),
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
        allowed_files = set(_eligible_candidate_paths(research))
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
        "repo_dependencies": normalize_repo_dependencies(prepared, payload, decisions),
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
            payload = run_agent_json_with_new_session(
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
                role="design_skeptic",
                stage="skeptic",
                on_log=on_log,
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
    agent_session: DesignAgentSession | None = None,
    on_log,
) -> tuple[dict[str, object], dict[str, object]]:
    blocking = [item for item in issues(review_payload) if str(item.get("severity")) == "blocking"]
    decision = normalize_decision_for_gate(dict(adjudication_payload), review_payload)
    revision_summary = "skeptic 未发现 blocking issue，无需修订。"
    issue_resolutions: list[dict[str, object]] = []
    if blocking:
        if native_ok:
            try:
                prompt_builder = lambda template_path: build_revision_prompt(
                    title=prepared.title,
                    refined_markdown=prepared.refined_markdown,
                    adjudication_payload=adjudication_payload,
                    review_payload=review_payload,
                    research_summary_payload=research_summary_payload,
                    template_path=template_path,
                )
                if agent_session is not None:
                    revision_payload = run_agent_json_in_session(
                        prepared,
                        build_revision_template_json(),
                        prompt_builder,
                        ".design-revision-",
                        agent_session,
                        stage="revision",
                        inline_bootstrap=False,
                        on_log=on_log,
                    )
                else:
                    revision_payload = run_agent_json(
                        prepared,
                        settings,
                        build_revision_template_json(),
                        prompt_builder,
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
        if not _all_accepted_resolutions_applied(review_payload, issue_resolutions, decision):
            decision, issue_resolutions = apply_review_issues_to_decision(decision, review_payload, research_summary_payload)
            revision_summary = "blocking issue 已通过本地校验后应用到 design-decision。"
        post_review = review_payload_after_revision(review_payload, {"revision": {"issue_resolutions": issue_resolutions}}, decision)
        decision = normalize_decision_for_gate(decision, post_review)
    else:
        post_review = review_payload
    remaining_blocking = [item for item in issues(post_review) if str(item.get("severity")) == "blocking"]
    decision["review_blocking_count"] = len(remaining_blocking)
    decision["finalized"] = not remaining_blocking
    decision["repo_dependencies"] = normalize_repo_dependencies(prepared, decision, dict_list(decision.get("repo_decisions")))
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


def review_payload_after_revision(
    review_payload: dict[str, object],
    debate_payload: dict[str, object],
    decision_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    revision = debate_payload.get("revision")
    if not isinstance(revision, dict):
        return review_payload
    accepted_resolutions = [
        item
        for item in dict_list(revision.get("issue_resolutions"))
        if str(item.get("resolution") or "") == "accepted"
    ]
    if not accepted_resolutions:
        return review_payload
    review_issues: list[dict[str, object]] = []
    for item in issues(review_payload):
        resolution = _matching_resolution(item, accepted_resolutions)
        if (
            resolution
            and str(item.get("severity") or "") == "blocking"
            and _resolution_applied_to_decision(item, resolution, decision_payload)
        ):
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
    research_summary_payload: dict[str, object] | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    decision = dict(decision_payload)
    repo_decisions = [dict(item) for item in dict_list(decision.get("repo_decisions"))]
    eligible_by_repo = _eligible_paths_by_repo(research_summary_payload or {})
    resolutions: list[dict[str, object]] = []
    for item in issues(review_payload):
        if str(item.get("severity") or "") != "blocking":
            continue
        target = str(item.get("target") or "")
        paths_to_add = _extract_file_paths(
            target,
            str(item.get("expected") or ""),
            str(item.get("actual") or ""),
            str(item.get("suggested_action") or ""),
        )
        changed = False
        if paths_to_add:
            changed = _add_candidate_paths(repo_decisions, target, paths_to_add, eligible_by_repo)
        if not changed:
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
                "reason": "本地 revision 接受 blocking issue；补齐候选文件、删除噪音候选，或转入待确认项。",
                "decision_change": "candidate_added_removed_or_question_added",
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
    dependency_edges = normalize_repo_dependencies(prepared, decision_payload, list(decisions.values()))
    dependency_map = _dependency_map(dependency_edges)
    connected_map = _connected_dependency_map(dependency_edges)
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
        depends_on = dependency_map.get(repo.repo_id, [])
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
                "depends_on": depends_on,
                "dependency_details": [
                    edge
                    for edge in dependency_edges
                    if str(edge.get("downstream_repo_id") or "") == repo.repo_id
                ],
                "parallelizable_with": [
                    other.repo_id
                    for other in prepared.repo_scopes
                    if other.repo_id != repo.repo_id and other.repo_id not in connected_map.get(repo.repo_id, [])
                ],
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
    dependency_edges = normalize_repo_dependencies(prepared, decision_payload, repo_decisions)
    dependency_map = _dependency_map(dependency_edges)
    reverse_dependency_map = _reverse_dependency_map(dependency_edges)
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
                "upstream_inputs": dependency_map.get(str(item.get("repo_id") or ""), []),
                "downstream_outputs": reverse_dependency_map.get(str(item.get("repo_id") or ""), []),
                "touched_repos": [str(item.get("repo_id") or "")],
            }
            for item in repo_decisions
            if str(item.get("work_type") or "") in {"must_change", "co_change"}
        ],
        "system_dependencies": [
            {
                "upstream_system_id": str(edge.get("upstream_repo_id") or ""),
                "downstream_system_id": str(edge.get("downstream_repo_id") or ""),
                "dependency_kind": str(edge.get("dependency_kind") or "producer_consumer"),
                "reason": str(edge.get("reason") or ""),
            }
            for edge in dependency_edges
        ],
        "critical_flows": [],
        "interface_changes": [],
        "risk_boundaries": [
            {"title": risk, "level": "medium", "mitigation": "进入 Plan 前确认。", "blocking": False}
            for risk in as_str_list(decision_payload.get("risks"))
        ],
    }


def normalize_repo_dependencies(
    prepared: DesignInputBundle,
    payload: dict[str, object],
    repo_decisions: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    known_repo_ids = {repo.repo_id for repo in prepared.repo_scopes}
    dependencies: list[dict[str, object]] = []
    for raw in dict_list(payload.get("repo_dependencies")):
        upstream = str(raw.get("upstream_repo_id") or raw.get("upstream") or raw.get("producer_repo_id") or "").strip()
        downstream = str(raw.get("downstream_repo_id") or raw.get("downstream") or raw.get("consumer_repo_id") or "").strip()
        if not upstream or not downstream or upstream == downstream:
            continue
        if upstream not in known_repo_ids or downstream not in known_repo_ids:
            continue
        dependencies.append(
            {
                "upstream_repo_id": upstream,
                "downstream_repo_id": downstream,
                "dependency_kind": _normalize_dependency_kind(raw.get("dependency_kind")),
                "reason": str(raw.get("reason") or "").strip(),
                "required_for": str(raw.get("required_for") or "").strip(),
            }
        )
    dependencies.extend(infer_repo_dependencies_from_skills(prepared, {"repo_decisions": repo_decisions or dict_list(payload.get("repo_decisions")), **payload}))
    return _dedupe_dependencies(dependencies)


def infer_repo_dependencies(prepared: DesignInputBundle, payload: dict[str, object]) -> list[dict[str, object]]:
    return infer_repo_dependencies_from_skills(prepared, payload)


def infer_repo_dependencies_from_skills(prepared: DesignInputBundle, payload: dict[str, object]) -> list[dict[str, object]]:
    repo_ids = {repo.repo_id for repo in prepared.repo_scopes}
    decisions = {str(item.get("repo_id") or ""): item for item in dict_list(payload.get("repo_decisions"))}
    task_text = _dependency_match_text(prepared, payload)
    dependencies: list[dict[str, object]] = []
    for rule in _skill_dependency_rules(prepared):
        upstream = str(rule.get("upstream_repo_id") or "").strip()
        downstream = str(rule.get("downstream_repo_id") or "").strip()
        required_repo_ids = as_str_list(rule.get("required_repo_ids")) or [upstream, downstream]
        if not upstream or not downstream or upstream == downstream:
            continue
        if upstream not in repo_ids or downstream not in repo_ids:
            continue
        if any(repo_id not in repo_ids for repo_id in required_repo_ids):
            continue
        if not _dependency_rule_terms_match(rule, task_text):
            continue
        if _repo_is_reference_only(decisions, upstream) or _repo_is_reference_only(decisions, downstream):
            continue
        dependencies.append(
            {
                "upstream_repo_id": upstream,
                "downstream_repo_id": downstream,
                "dependency_kind": _normalize_dependency_kind(rule.get("dependency_kind")),
                "reason": str(rule.get("reason") or "").strip(),
                "required_for": str(rule.get("required_for") or "").strip(),
            }
        )
    return dependencies


def _skill_dependency_rules(prepared: DesignInputBundle) -> list[dict[str, object]]:
    rules: list[dict[str, object]] = []
    for block in _json_code_blocks(prepared.design_skills_brief_markdown):
        parsed = _parse_json_object(block)
        if not parsed:
            continue
        raw_rules = parsed.get("design_dependency_rules") or parsed.get("dependency_rules")
        if isinstance(raw_rules, list):
            rules.extend(item for item in raw_rules if isinstance(item, dict))
    for card in _dependency_rule_cards(prepared.design_skills_brief_markdown):
        rule = _parse_dependency_rule_card(card)
        if rule:
            rules.append(rule)
    return rules


def _json_code_blocks(text: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"```(?:json)?\s*\n(.*?)\n```", text, flags=re.DOTALL | re.IGNORECASE)
    ]


def _parse_json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dependency_rule_cards(text: str) -> list[str]:
    cards: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not re.match(r"^#{2,4}\s*规则[:：]", line):
            index += 1
            continue
        card = [line]
        index += 1
        while index < len(lines):
            current = lines[index].strip()
            if current.startswith("#"):
                break
            if current:
                card.append(current)
            index += 1
        cards.append("\n".join(card))
    return cards


def _parse_dependency_rule_card(card: str) -> dict[str, object]:
    values = _card_key_values(card)
    upstream = _clean_rule_value(values.get("上游 producer") or values.get("上游") or values.get("producer"))
    downstream = _clean_rule_value(values.get("下游 consumer") or values.get("下游") or values.get("consumer"))
    if not upstream or not downstream:
        return {}
    required_repos = _repo_ids_from_rule_value(values.get("生效前提") or values.get("required repos") or "")
    if not required_repos:
        required_repos = [upstream, downstream]
    return {
        "trigger_terms_any": _terms_from_rule_value(values.get("触发信号") or values.get("trigger terms") or ""),
        "required_repo_ids": required_repos,
        "upstream_repo_id": upstream,
        "downstream_repo_id": downstream,
        "dependency_kind": _clean_rule_value(values.get("依赖类型") or values.get("dependency kind") or "producer_consumer"),
        "reason": _clean_rule_value(values.get("依赖原因") or values.get("reason") or ""),
        "required_for": _clean_rule_value(values.get("前置关系") or values.get("required for") or ""),
    }


def _card_key_values(card: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in card.splitlines():
        line = raw.strip().lstrip("-").strip()
        if "：" in line:
            key, value = line.split("：", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        key = re.sub(r"^#+\s*", "", key).strip().lower()
        values[key] = value.strip()
    return values


def _repo_ids_from_rule_value(value: str) -> list[str]:
    backticked = re.findall(r"`([^`]+)`", value)
    if backticked:
        return [item.strip() for item in backticked if item.strip()]
    return _terms_from_rule_value(value)


def _terms_from_rule_value(value: str) -> list[str]:
    clean = value.replace("`", "")
    return [
        item.strip()
        for item in re.split(r"[、,，/]+|\s+和\s+|\s+and\s+", clean)
        if item.strip()
    ]


def _clean_rule_value(value: object) -> str:
    return str(value or "").strip().strip("`").strip()


def _dependency_match_text(prepared: DesignInputBundle, payload: dict[str, object]) -> str:
    values = [
        prepared.title,
        prepared.refined_markdown,
        prepared.design_skills_brief_markdown,
        *prepared.sections.change_scope,
        *prepared.sections.key_constraints,
        *prepared.sections.acceptance_criteria,
        str(payload.get("decision_summary") or ""),
        *as_str_list(payload.get("core_change_points")),
    ]
    for repo in dict_list(payload.get("repo_decisions")):
        values.extend(
            [
                str(repo.get("responsibility") or ""),
                *as_str_list(repo.get("boundaries")),
                *as_str_list(repo.get("unresolved_questions")),
            ]
        )
    return "\n".join(values).lower()


def _dependency_rule_terms_match(rule: dict[str, object], text: str) -> bool:
    any_terms = as_str_list(rule.get("trigger_terms_any"))
    all_terms = as_str_list(rule.get("trigger_terms_all"))
    if any_terms and not any(term.lower() in text for term in any_terms):
        return False
    if all_terms and not all(term.lower() in text for term in all_terms):
        return False
    return bool(any_terms or all_terms)


def _repo_is_reference_only(decisions: dict[str, dict[str, object]], repo_id: str) -> bool:
    return str(dict(decisions.get(repo_id) or {}).get("work_type") or "") == "reference_only"


def _normalize_dependency_kind(value: object) -> str:
    text = str(value or "").strip()
    if text in {"producer_consumer", "version_dependency", "runtime_dependency", "validation_dependency"}:
        return text
    return "producer_consumer"


def _dedupe_dependencies(items: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        upstream = str(item.get("upstream_repo_id") or "")
        downstream = str(item.get("downstream_repo_id") or "")
        kind = str(item.get("dependency_kind") or "producer_consumer")
        key = (upstream, downstream, kind)
        if not upstream or not downstream or upstream == downstream or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dependency_map(edges: list[dict[str, object]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for edge in edges:
        upstream = str(edge.get("upstream_repo_id") or "")
        downstream = str(edge.get("downstream_repo_id") or "")
        if not upstream or not downstream:
            continue
        result.setdefault(downstream, [])
        if upstream not in result[downstream]:
            result[downstream].append(upstream)
    return result


def _reverse_dependency_map(edges: list[dict[str, object]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for edge in edges:
        upstream = str(edge.get("upstream_repo_id") or "")
        downstream = str(edge.get("downstream_repo_id") or "")
        if not upstream or not downstream:
            continue
        result.setdefault(upstream, [])
        if downstream not in result[upstream]:
            result[upstream].append(downstream)
    return result


def _connected_dependency_map(edges: list[dict[str, object]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for edge in edges:
        upstream = str(edge.get("upstream_repo_id") or "")
        downstream = str(edge.get("downstream_repo_id") or "")
        if not upstream or not downstream:
            continue
        result.setdefault(upstream, [])
        result.setdefault(downstream, [])
        if downstream not in result[upstream]:
            result[upstream].append(downstream)
        if upstream not in result[downstream]:
            result[downstream].append(upstream)
    return result


def _repo_responsibility(prepared: DesignInputBundle, repo_id: str, candidates: list[str]) -> str:
    scope = first_non_empty(prepared.sections.change_scope, prepared.title)
    if candidates:
        return f"围绕「{scope}」收敛 {repo_id} 中候选文件对应的实现边界。"
    return f"检查 {repo_id} 是否参与「{scope}」的上下游联动，不在证据不足时扩大改造范围。"


def _eligible_candidate_paths(research: dict[str, object]) -> list[str]:
    paths = candidate_paths(research)
    paths.extend(
        str(item.get("path") or "")
        for item in dict_list(research.get("related_files"))
        if str(item.get("path") or "").strip()
    )
    return dedupe(paths)


def _eligible_paths_by_repo(research_summary_payload: dict[str, object]) -> dict[str, set[str]]:
    return {
        str(repo.get("repo_id") or ""): set(_eligible_candidate_paths(repo))
        for repo in dict_list(research_summary_payload.get("repos"))
    }


def _add_candidate_paths(
    repo_decisions: list[dict[str, object]],
    target: str,
    paths_to_add: list[str],
    eligible_by_repo: dict[str, set[str]],
) -> bool:
    changed = False
    for path in paths_to_add:
        target_repos = _repos_for_path(repo_decisions, target, path, eligible_by_repo)
        for repo in repo_decisions:
            repo_id = str(repo.get("repo_id") or "")
            if repo_id not in target_repos:
                continue
            candidates = as_str_list(repo.get("candidate_files"))
            if path in candidates:
                continue
            candidates.append(path)
            repo["candidate_files"] = dedupe(candidates)
            repo["candidate_dirs"] = sorted({str(Path(item).parent) for item in candidates if str(Path(item).parent) != "."})[:8]
            if str(repo.get("work_type") or "") in {"validate_only", "reference_only", ""}:
                repo["work_type"] = "must_change"
            if str(repo.get("confidence") or "") == "low":
                repo["confidence"] = "medium"
            changed = True
    return changed


def _repos_for_path(
    repo_decisions: list[dict[str, object]],
    target: str,
    path: str,
    eligible_by_repo: dict[str, set[str]],
) -> set[str]:
    explicit = {
        str(repo.get("repo_id") or "")
        for repo in repo_decisions
        if str(repo.get("repo_id") or "") and str(repo.get("repo_id") or "") in target
    }
    eligible = {repo_id for repo_id, paths in eligible_by_repo.items() if path in paths}
    if explicit and eligible:
        return explicit & eligible
    if eligible:
        return eligible
    return explicit


def _all_accepted_resolutions_applied(
    review_payload: dict[str, object],
    issue_resolutions: list[dict[str, object]],
    decision_payload: dict[str, object],
) -> bool:
    accepted = [item for item in issue_resolutions if str(item.get("resolution") or "") == "accepted"]
    if not accepted:
        return False
    for review_issue in issues(review_payload):
        if str(review_issue.get("severity") or "") != "blocking":
            continue
        resolution = _matching_resolution(review_issue, accepted)
        if not resolution or not _resolution_applied_to_decision(review_issue, resolution, decision_payload):
            return False
    return True


def _matching_resolution(review_issue: dict[str, object], resolutions: list[dict[str, object]]) -> dict[str, object]:
    target = str(review_issue.get("target") or "")
    failure_type = str(review_issue.get("failure_type") or "")
    for item in resolutions:
        if target and str(item.get("target") or "") == target:
            return item
        if failure_type and str(item.get("failure_type") or "") == failure_type:
            return item
    return {}


def _resolution_applied_to_decision(
    review_issue: dict[str, object],
    resolution: dict[str, object],
    decision_payload: dict[str, object] | None,
) -> bool:
    if decision_payload is None:
        return True
    expected_paths = _extract_file_paths(
        str(review_issue.get("target") or ""),
        str(review_issue.get("expected") or ""),
        str(review_issue.get("actual") or ""),
        str(review_issue.get("suggested_action") or ""),
        str(resolution.get("reason") or ""),
        str(resolution.get("decision_change") or ""),
    )
    if not expected_paths:
        return True
    candidate_paths_in_decision = {
        path
        for repo in dict_list(decision_payload.get("repo_decisions"))
        for path in as_str_list(repo.get("candidate_files"))
    }
    return all(path in candidate_paths_in_decision for path in expected_paths)


def _extract_file_paths(*values: str) -> list[str]:
    paths: list[str] = []
    for value in values:
        for match in re.findall(r"[\w./-]+\.(?:go|py|ts|tsx|js|jsx|proto|thrift|sql|json|ya?ml)", value):
            paths.append(match.strip(".,;:，。；：)）]】"))
    return dedupe(paths)


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

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.engines.plan_research import qualify_repo_path
from coco_flow.prompts.design import build_design_repo_binding_agent_prompt, build_design_repo_binding_template_json

from .models import DesignPreparedInput, DesignRepoBinding, DesignRepoBindingEntry, EXECUTOR_NATIVE


def build_local_repo_binding(prepared: DesignPreparedInput) -> DesignRepoBinding:
    """在不依赖 agent 的情况下，生成最终 repo binding 决策。

    它会把 change points、repo research 和 responsibility matrix 合并起来，
    收敛成每个 repo 是否 in scope 以及属于哪个 scope tier 的结论。
    """
    repo_count = len(prepared.repo_scopes)
    change_point_ids = [int(item.get("id") or 0) for item in prepared.change_points_payload.get("change_points", []) if isinstance(item, dict)] or [1]
    matrix_by_repo = {
        str(item.get("repo_id") or ""): item
        for item in prepared.responsibility_matrix_payload.get("repos", [])
        if isinstance(item, dict) and str(item.get("repo_id") or "").strip()
    }
    research_by_repo = {
        str(item.get("repo_id") or ""): item
        for item in prepared.research_payload.get("repos", [])
        if isinstance(item, dict) and str(item.get("repo_id") or "").strip()
    }
    scored_items: list[tuple[int, int, DesignRepoBindingEntry]] = []
    for repo in prepared.repo_researches:
        matrix_entry = matrix_by_repo.get(repo.repo_id, {})
        research_entry = research_by_repo.get(repo.repo_id, {})
        tier = str(matrix_entry.get("recommended_scope_tier") or "reference_only")
        decision = "in_scope" if tier in {"must_change", "co_change", "validate_only", "reference_only"} else "out_of_scope"
        system_name = repo.finding.matched_terms[0].business if repo.finding.matched_terms else repo.repo_id
        candidate_dirs = [qualify_repo_path(repo.repo_id, item, repo_count) for item in repo.finding.candidate_dirs[:6]]
        candidate_files = [qualify_repo_path(repo.repo_id, item, repo_count) for item in repo.finding.candidate_files[:8]]
        entry = DesignRepoBindingEntry(
            repo_id=repo.repo_id,
            repo_path=repo.repo_path,
            decision=decision,
            scope_tier=tier,
            serves_change_points=[1],
            system_name=system_name,
            responsibility=_responsibility_from_matrix_or_summary(matrix_entry, research_entry, prepared, repo.repo_id),
            change_summary=_change_summary_from_scope_tier(tier, prepared, repo.repo_id),
            boundaries=(prepared.sections.non_goals[:3] or ["保持最小改动范围，不把无关仓库带入本次设计。"]),
            candidate_dirs=candidate_dirs,
            candidate_files=candidate_files,
            depends_on=[],
            parallelizable_with=[],
            confidence=str(research_entry.get("confidence") or "medium"),
            reason=str(matrix_entry.get("reasoning") or research_entry.get("summary") or "基于职责矩阵与仓库调研判定。"),
        )
        scored_items.append((_priority_from_scope_tier(tier), len(candidate_files), entry))
    scored_items.sort(key=lambda item: (-item[0], -item[1], item[2].repo_id))
    bindings: list[DesignRepoBindingEntry] = []
    must_change_assigned = 0
    for _, _, entry in scored_items:
        current = entry
        if current.scope_tier == "must_change":
            must_change_assigned += 1
            if must_change_assigned > 1:
                current.scope_tier = "co_change"
        bindings.append(current)
    must_change = [entry.repo_id for entry in bindings if entry.decision == "in_scope" and entry.scope_tier == "must_change"]
    co_change = [entry.repo_id for entry in bindings if entry.decision == "in_scope" and entry.scope_tier == "co_change"]
    validate_only = [entry.repo_id for entry in bindings if entry.decision == "in_scope" and entry.scope_tier == "validate_only"]
    reference_only = [entry.repo_id for entry in bindings if entry.decision == "in_scope" and entry.scope_tier == "reference_only"]
    summary_parts: list[str] = []
    if must_change:
        summary_parts.append("必须改动仓库：" + "、".join(must_change))
    if co_change:
        summary_parts.append("协同改动仓库：" + "、".join(co_change))
    if validate_only:
        summary_parts.append("联动验证仓库：" + "、".join(validate_only))
    if reference_only:
        summary_parts.append("参考链路仓库：" + "、".join(reference_only))
    summary = "；".join(summary_parts) if summary_parts else "当前未识别到明确 in_scope repo。"
    decision_meta = _derive_binding_decision_meta(prepared, bindings)
    return DesignRepoBinding(
        repo_bindings=bindings,
        missing_repos=[],
        decision_summary=summary,
        closure_mode=decision_meta["closure_mode"],
        selection_basis=decision_meta["selection_basis"],
        selection_note=decision_meta["selection_note"],
        mode="local",
    )


def build_repo_binding(prepared: DesignPreparedInput, settings: Settings, knowledge_brief_markdown: str, on_log) -> DesignRepoBinding:
    """确定 Design 阶段最终承诺的 repo 集合和 scope tier。

    native 模式会先让 agent 生成 binding 草稿，再和本地 responsibility
    matrix 的先验信息合并，避免结果发散。
    """
    fallback = build_local_repo_binding(prepared)
    if prepared.is_single_bound_repo:
        fallback.mode = "single_bound_fast_path"
        return fallback
    if settings.plan_executor.strip().lower() != EXECUTOR_NATIVE:
        return fallback
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_repo_binding_template(prepared.task_dir)
    try:
        repo_research_payload = prepared.research_payload
        if not isinstance(repo_research_payload, dict):
            repo_research_payload = {
                "repos": [
                    {
                        "repo_id": repo.repo_id,
                        "repo_path": repo.repo_path,
                        "matched_terms": [item.business for item in repo.finding.matched_terms],
                        "candidate_dirs": repo.finding.candidate_dirs[:6],
                        "candidate_files": repo.finding.candidate_files[:8],
                        "notes": repo.finding.notes[:4],
                    }
                    for repo in prepared.repo_researches
                ]
            }
        client.run_agent(
            build_design_repo_binding_agent_prompt(
                title=prepared.title,
                refined_markdown=prepared.refined_markdown,
                knowledge_brief_markdown=knowledge_brief_markdown,
                responsibility_matrix_payload=prepared.responsibility_matrix_payload,
                repo_research_payload=repo_research_payload,
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        if "__FILL__" in raw:
            raise ValueError("design_repo_binding_template_unfilled")
        payload = json.loads(raw)
        entries: list[DesignRepoBindingEntry] = []
        for item in payload.get("repo_bindings", []):
            if not isinstance(item, dict):
                continue
            entries.append(
                DesignRepoBindingEntry(
                    repo_id=str(item.get("repo_id") or ""),
                    repo_path=str(item.get("repo_path") or ""),
                    decision=str(item.get("decision") or "uncertain"),
                    scope_tier=str(item.get("scope_tier") or _infer_scope_tier_from_binding_item(item, prepared.responsibility_matrix_payload)),
                    serves_change_points=[int(value) for value in item.get("serves_change_points", []) if str(value).isdigit()],
                    system_name=str(item.get("system_name") or ""),
                    responsibility=str(item.get("responsibility") or ""),
                    change_summary=[str(value) for value in item.get("change_summary", []) if str(value).strip()],
                    boundaries=[str(value) for value in item.get("boundaries", []) if str(value).strip()],
                    candidate_dirs=[str(value) for value in item.get("candidate_dirs", []) if str(value).strip()],
                    candidate_files=[str(value) for value in item.get("candidate_files", []) if str(value).strip()],
                    depends_on=[str(value) for value in item.get("depends_on", []) if str(value).strip()],
                    parallelizable_with=[str(value) for value in item.get("parallelizable_with", []) if str(value).strip()],
                    confidence=str(item.get("confidence") or "medium"),
                    reason=str(item.get("reason") or ""),
                )
            )
        if not entries:
            raise ValueError("design_repo_binding_empty")
        entries = _merge_matrix_priors(entries, fallback.repo_bindings, prepared.responsibility_matrix_payload)
        return DesignRepoBinding(
            repo_bindings=entries,
            missing_repos=[str(value) for value in payload.get("missing_repos", []) if str(value).strip()],
            decision_summary=str(payload.get("decision_summary") or fallback.decision_summary),
            closure_mode=str(payload.get("closure_mode") or fallback.closure_mode or "unresolved"),
            selection_basis=str(payload.get("selection_basis") or fallback.selection_basis or "unresolved"),
            selection_note=str(payload.get("selection_note") or fallback.selection_note or ""),
            mode="llm",
        )
    except Exception as error:
        on_log(f"repo_binding_fallback: {error}")
        return fallback
    finally:
        if template_path.exists():
            template_path.unlink()


def _write_repo_binding_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".design-repo-binding-",
        suffix=".json",
        delete=False,
    ) as handle:
        handle.write(build_design_repo_binding_template_json())
        handle.flush()
        return Path(handle.name)


def _local_scope_tier(
    prepared: DesignPreparedInput,
    repo_id: str,
    candidate_dirs: list[str],
    candidate_files: list[str],
    primary_points: list[int],
    secondary_points: list[int],
    score: int,
) -> str:
    joined = " ".join([repo_id, *candidate_dirs, *candidate_files]).lower()
    refined_text = " ".join(
        [
            prepared.refined_markdown.lower(),
            prepared.refine_knowledge_read_markdown.lower(),
        ]
    )
    if len(prepared.repo_researches) == 1 and score > 0:
        return "must_change"
    if "abtest" in joined or "common" in repo_id.lower():
        if any(keyword in refined_text for keyword in ("ab", "实验", "灰度", "tcc", "开关", "配置")):
            return "validate_only"
        return "reference_only"
    if any(keyword in joined for keyword in ("bff", "pin_card", "schema", "formatter", "api", "handler")):
        return "validate_only" if score > 0 else "reference_only"
    if primary_points and any(keyword in joined for keyword in ("converter", "loader", "engine", "status", "pack")):
        return "must_change"
    if primary_points:
        all_primary_repo_ids = {
            str(item.get("repo_id") or "")
            for item in prepared.repo_assignment_payload.get("repo_briefs", [])
            if isinstance(item, dict) and item.get("primary_change_points")
        }
        if all_primary_repo_ids == {repo_id}:
            return "must_change"
    if primary_points:
        return "validate_only"
    if secondary_points:
        return "validate_only"
    return "reference_only"


def _infer_scope_tier_from_binding_item(item: dict[str, object], responsibility_matrix_payload: dict[str, object]) -> str:
    matrix_by_repo = {
        str(entry.get("repo_id") or ""): entry
        for entry in responsibility_matrix_payload.get("repos", [])
        if isinstance(entry, dict) and str(entry.get("repo_id") or "").strip()
    }
    matrix_entry = matrix_by_repo.get(str(item.get("repo_id") or ""), {})
    if matrix_entry:
        current = str(matrix_entry.get("recommended_scope_tier") or "").strip()
        if current in {"must_change", "co_change", "validate_only", "reference_only"}:
            return current
    repo_id = str(item.get("repo_id") or "").lower()
    candidate_text = " ".join(str(value) for value in [*(item.get("candidate_dirs") or []), *(item.get("candidate_files") or [])]).lower()
    if "abtest" in candidate_text or "common" in repo_id:
        return "reference_only"
    if any(keyword in candidate_text for keyword in ("converter", "loader", "engine", "status", "pack")):
        return "must_change"
    if candidate_text:
        return "validate_only"
    return "reference_only"


def _priority_from_scope_tier(scope_tier: str) -> int:
    if scope_tier == "must_change":
        return 4
    if scope_tier == "co_change":
        return 3
    if scope_tier == "validate_only":
        return 2
    if scope_tier == "reference_only":
        return 1
    return 0


def _responsibility_from_matrix_or_summary(
    matrix_entry: dict[str, object],
    research_entry: dict[str, object],
    prepared: DesignPreparedInput,
    repo_id: str,
) -> str:
    tier = str(matrix_entry.get("recommended_scope_tier") or "")
    if tier == "must_change":
        return f"{repo_id} 承担本次 change point 的状态定义或收敛职责。"
    if tier == "co_change":
        return f"{repo_id} 承担本次 change point 的协同改造职责，需要与主仓一起修改。"
    if tier == "validate_only":
        return f"{repo_id} 主要承担适配、联调或下游验证职责。"
    if tier == "reference_only":
        return f"{repo_id} 主要提供背景链路、配置或参考信息。"
    return str(research_entry.get("summary") or prepared.title)


def _change_summary_from_scope_tier(scope_tier: str, prepared: DesignPreparedInput, repo_id: str) -> list[str]:
    if scope_tier == "must_change":
        return prepared.sections.change_scope[:3] or [f"{repo_id} 承担本次核心改动。"]
    if scope_tier == "co_change":
        return [f"{repo_id} 需要配合主仓完成联动改造。"]
    if scope_tier == "validate_only":
        return [f"{repo_id} 需要确认适配、协议或展示层是否受影响。"]
    return [f"{repo_id} 作为参考链路保留，本次默认不改。"]


def _merge_matrix_priors(
    entries: list[DesignRepoBindingEntry],
    fallback_entries: list[DesignRepoBindingEntry],
    responsibility_matrix_payload: dict[str, object],
) -> list[DesignRepoBindingEntry]:
    matrix_by_repo = {
        str(item.get("repo_id") or ""): item
        for item in responsibility_matrix_payload.get("repos", [])
        if isinstance(item, dict) and str(item.get("repo_id") or "").strip()
    }
    merged: dict[str, DesignRepoBindingEntry] = {entry.repo_id: entry for entry in entries}
    fallback_by_repo = {entry.repo_id: entry for entry in fallback_entries}
    for repo_id, matrix_entry in matrix_by_repo.items():
        tier = str(matrix_entry.get("recommended_scope_tier") or "").strip()
        if tier not in {"must_change", "co_change", "validate_only", "reference_only"}:
            continue
        current = merged.get(repo_id) or fallback_by_repo.get(repo_id)
        if current is None:
            continue
        current.scope_tier = tier
        current.decision = "in_scope"
        current.reason = str(matrix_entry.get("reasoning") or current.reason or "")
        merged[repo_id] = current
    return sorted(merged.values(), key=lambda item: (-_priority_from_scope_tier(item.scope_tier), item.repo_id))


def _derive_binding_decision_meta(
    prepared: DesignPreparedInput,
    bindings: list[DesignRepoBindingEntry],
) -> dict[str, str]:
    in_scope = [entry for entry in bindings if entry.decision == "in_scope"]
    must_change = [entry for entry in in_scope if entry.scope_tier == "must_change"]
    co_change = [entry for entry in in_scope if entry.scope_tier == "co_change"]
    if len(in_scope) <= 1:
        return {
            "closure_mode": "single_repo",
            "selection_basis": "strong_signal",
            "selection_note": "当前仅识别到一个 in_scope 仓库，单仓即可闭合实现。",
        }
    if co_change or len(must_change) > 1:
        repos = "、".join(entry.repo_id for entry in must_change + co_change)
        return {
            "closure_mode": "multi_repo",
            "selection_basis": "strong_signal",
            "selection_note": f"当前需求需要多仓协同改造才能闭合，涉及：{repos}。",
        }
    if len(must_change) != 1:
        return {
            "closure_mode": "unresolved",
            "selection_basis": "unresolved",
            "selection_note": "当前尚未收敛出唯一主改仓，需要人工补充 repo adjudication 依据。",
        }

    chosen = must_change[0]
    research_items = prepared.research_payload.get("repos") if isinstance(prepared.research_payload, dict) else []
    research_by_repo = {
        str(item.get("repo_id") or ""): item
        for item in (research_items if isinstance(research_items, list) else [])
        if isinstance(item, dict) and str(item.get("repo_id") or "").strip()
    }
    chosen_research = research_by_repo.get(chosen.repo_id, {})
    chosen_score = int(chosen_research.get("prefilter_score") or 0)
    chosen_candidates = chosen.candidate_files or [str(value) for value in chosen_research.get("candidate_files", []) if str(value).strip()]
    ambiguous_alts: list[str] = []
    for entry in in_scope:
        if entry.repo_id == chosen.repo_id:
            continue
        alt_research = research_by_repo.get(entry.repo_id, {})
        alt_score = int(alt_research.get("prefilter_score") or 0)
        alt_candidates = entry.candidate_files or [str(value) for value in alt_research.get("candidate_files", []) if str(value).strip()]
        if not chosen_candidates or not alt_candidates:
            continue
        if alt_score >= max(chosen_score - 1, 0):
            ambiguous_alts.append(entry.repo_id)
    if ambiguous_alts:
        alt_text = "、".join(ambiguous_alts)
        return {
            "closure_mode": "single_repo",
            "selection_basis": "heuristic_tiebreak",
            "selection_note": f"{chosen.repo_id} 与 {alt_text} 都具备单仓闭合条件；当前默认选择 {chosen.repo_id} 作为起始实现仓，该选择属于启发式 tie-break，不代表其它仓无法承接实现。",
        }
    return {
        "closure_mode": "single_repo",
        "selection_basis": "strong_signal",
        "selection_note": f"{chosen.repo_id} 的落点信号最强，单仓即可闭合实现。",
    }

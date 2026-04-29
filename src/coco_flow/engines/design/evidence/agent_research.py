"""Native Research Agent loop for Design.

这里刻意不再复刻旧的程序化 candidate/excluded 打分。
native 模式下，代码线索、证据判断和下一轮搜索方向都交给 agent；
程序只负责有限轮次、JSON 形态归一化和失败显式暴露。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import re

from coco_flow.config import Settings
from coco_flow.engines.design.evidence.repo_index import build_repo_context_package
from coco_flow.engines.design.runtime import run_agent_json
from coco_flow.engines.design.support import as_str_list, dict_list
from coco_flow.engines.design.types import DesignInputBundle
from coco_flow.engines.shared.models import RepoScope
from coco_flow.prompts.design import (
    build_design_research_prompt,
    build_design_research_review_prompt,
    build_design_research_review_template_json,
    build_design_research_template_json,
)

MAX_RESEARCH_AGENT_ROUNDS = 2
MAX_RESEARCH_AGENT_WORKERS = 3


def run_agent_repo_research(
    prepared: DesignInputBundle,
    settings: Settings,
    *,
    on_log,
) -> dict[str, object]:
    """Run Research Agent and bounded Supervisor review.

    约束：
    - Research Agent 自己搜索/读文件/git，程序不替它做候选裁决。
    - Research Supervisor 只判断证据是否够 Design 使用。
    - 最多补查一轮，避免无限内部对话。
    """

    retry_by_repo: dict[str, list[str]] = {}
    repo_payloads: dict[str, dict[str, object]] = {}
    latest_review: dict[str, object] = {}
    for round_index in range(1, MAX_RESEARCH_AGENT_ROUNDS + 1):
        target_repos = _target_repos(prepared.repo_scopes, repo_payloads, retry_by_repo, round_index)
        if not target_repos:
            break
        on_log(f"design_research_agent_start: round={round_index} repos={','.join(repo.repo_id for repo in target_repos)}")
        for repo_payload in _run_repo_research_agents(prepared, settings, target_repos, retry_by_repo, on_log=on_log):
            repo_id = str(repo_payload.get("repo_id") or "").strip()
            if repo_id:
                repo_payloads[repo_id] = _merge_repo_research_payload(repo_payloads.get(repo_id), repo_payload)
        latest_payload = normalize_agent_research_payload({"repos": list(repo_payloads.values()), "summary": "Research Agent completed."})
        latest_payload = _apply_experiment_gate_repo_policy(prepared, latest_payload)
        on_log(
            "design_research_agent_ok: "
            f"round={round_index} repos={len(dict_list(latest_payload.get('repos')))} "
            f"candidate_files={int(latest_payload.get('candidate_file_count') or 0)}"
        )

        try:
            latest_review = _review_research_payload(prepared, settings, latest_payload, on_log=on_log)
            latest_review = _normalize_research_review(latest_review, latest_payload)
        except Exception as error:
            # Supervisor 只是审查层。它自身输出坏 JSON 或超时，不应抹掉前面 repo
            # Research Agent 已拿到的证据，否则用户只能看到“调研失败”而看不到可补救线索。
            latest_review = _research_supervisor_error_review(str(error))
            on_log(f"design_research_supervisor_failed: round={round_index} error={error}")
        latest_payload["research_review"] = latest_review
        on_log(
            "design_research_supervisor_ok: "
            f"round={round_index} decision={latest_review.get('decision')} passed={str(bool(latest_review.get('passed'))).lower()}"
        )
        if bool(latest_review.get("passed")):
            return latest_payload
        if str(latest_review.get("decision") or "") != "redo_research":
            return latest_payload
        retry_by_repo = _research_instructions_by_repo(prepared.repo_scopes, latest_review, latest_payload)
        if not retry_by_repo:
            return latest_payload

    return latest_payload


def normalize_agent_research_payload(payload: dict[str, object]) -> dict[str, object]:
    repos = dict_list(payload.get("repos"))
    normalized_repos: list[dict[str, object]] = []
    for repo in repos:
        repo_id = str(repo.get("repo_id") or "").strip()
        repo_path = str(repo.get("repo_path") or "").strip()
        candidate_files = _normalize_candidate_files(repo.get("candidate_files"))
        claims = dict_list(repo.get("claims"))
        related_files = _normalize_file_items(repo.get("related_files"))
        excluded_files = _normalize_file_items(repo.get("excluded_files"))
        rejected = _normalize_file_items(repo.get("rejected_candidates"))
        skill_usage = _normalize_skill_usage(repo.get("skill_usage"))
        normalized_repos.append(
            {
                "repo_id": repo_id,
                "repo_path": repo_path,
                "research_status": str(repo.get("research_status") or "ok"),
                "research_error": str(repo.get("research_error") or "").strip(),
                "work_hypothesis": _normalize_work_hypothesis(str(repo.get("work_hypothesis") or "")),
                "confidence": _normalize_confidence(str(repo.get("confidence") or "")),
                "skill_usage": skill_usage,
                "claims": claims,
                "candidate_files": candidate_files,
                "related_files": related_files,
                "excluded_files": excluded_files,
                "rejected_candidates": rejected,
                "boundaries": _normalize_text_items(repo.get("boundaries")),
                "unknowns": _normalize_text_items(repo.get("unknowns")),
                "next_search_suggestions": _normalize_text_items(repo.get("next_search_suggestions")),
            }
        )
    return {
        "source": "agent",
        "repos": normalized_repos,
        "summary": str(payload.get("summary") or "").strip(),
        "research_status": _research_status(normalized_repos),
        "unknowns": [
            f"{repo.get('repo_id')}: {unknown}"
            for repo in normalized_repos
            for unknown in as_str_list(repo.get("unknowns"))
        ],
        "candidate_file_count": sum(len(dict_list(repo.get("candidate_files"))) for repo in normalized_repos),
        "excluded_file_count": sum(len(dict_list(repo.get("excluded_files"))) for repo in normalized_repos),
        "git_evidence_count": 0,
        "git_command_count": 0,
    }


def _apply_experiment_gate_repo_policy(prepared: DesignInputBundle, payload: dict[str, object]) -> dict[str, object]:
    """实验门控需求不能提前排除公共实验/配置仓。

    如果 refined PRD 只写了“命中实验”但没给具体实验字段，Research Agent 不能把
    涉及 AB/实验/配置职责的 repo 判成 not_needed。它至少是 conditional：
    可能复用已有字段，也可能新增字段；这个判断应进入 Design 待确认项。
    """

    if not _needs_unspecified_experiment_gate(prepared):
        return payload
    repos = dict_list(payload.get("repos"))
    if not repos:
        return payload
    changed = False
    for repo in repos:
        if str(repo.get("work_hypothesis") or "") != "not_needed":
            continue
        if not _repo_mentions_experiment_config_role(repo):
            continue
        repo["work_hypothesis"] = "conditional"
        repo["confidence"] = "medium"
        unknowns = as_str_list(repo.get("unknowns"))
        unknown = "refined PRD 提到实验命中，但未指定实验 key；需确认复用现有实验字段还是新增公共实验/配置字段。"
        if unknown not in unknowns:
            unknowns.append(unknown)
        repo["unknowns"] = unknowns
        boundaries = as_str_list(repo.get("boundaries"))
        boundary = "未确认实验字段前，不能把公共实验/配置仓判定为确定不改。"
        if boundary not in boundaries:
            boundaries.append(boundary)
        repo["boundaries"] = boundaries
        changed = True
    if not changed:
        return payload
    result = normalize_agent_research_payload({"repos": repos, "summary": str(payload.get("summary") or "")})
    review = payload.get("research_review")
    if isinstance(review, dict):
        result["research_review"] = review
    return result


def _needs_unspecified_experiment_gate(prepared: DesignInputBundle) -> bool:
    text = "\n".join(
        [
            prepared.title,
            prepared.refined_markdown,
            *prepared.sections.change_scope,
            *prepared.sections.acceptance_criteria,
            *prepared.sections.key_constraints,
        ]
    ).lower()
    has_gate = any(marker in text for marker in ("命中实验", "未命中实验", "实验组", "ab", "a/b", "灰度"))
    if not has_gate:
        return False
    return not _mentions_specific_experiment_key(text)


def _mentions_specific_experiment_key(text: str) -> bool:
    if any(marker in text for marker in ("实验 key", "实验key", "ab key", "ab参数", "ab 参数", "实验参数", "实验字段")):
        return True
    return bool(re.search(r"`[A-Za-z][A-Za-z0-9_]{5,}`", text))


def _repo_mentions_experiment_config_role(repo: dict[str, object]) -> bool:
    parts: list[str] = [
        str(repo.get("repo_id") or ""),
        str(repo.get("repo_path") or ""),
        str(repo.get("summary") or ""),
        *as_str_list(repo.get("unknowns")),
        *as_str_list(repo.get("boundaries")),
        *as_str_list(repo.get("next_search_suggestions")),
    ]
    skill_usage = repo.get("skill_usage") if isinstance(repo.get("skill_usage"), dict) else {}
    parts.extend(as_str_list(skill_usage.get("applied_rules")))
    parts.extend(as_str_list(skill_usage.get("derived_search_hints")))
    for claim in dict_list(repo.get("claims")):
        parts.extend(str(value) for value in claim.values())
    text = "\n".join(parts).lower()
    return any(marker in text for marker in ("ab", "experiment", "实验", "配置", "config", "tcc", "公共"))


def _run_repo_research_agents(
    prepared: DesignInputBundle,
    settings: Settings,
    target_repos: list[RepoScope],
    retry_by_repo: dict[str, list[str]],
    *,
    on_log,
) -> list[dict[str, object]]:
    max_workers = min(MAX_RESEARCH_AGENT_WORKERS, max(1, len(target_repos)))
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="design-research-agent") as executor:
        futures = {
            executor.submit(
                _run_single_repo_research_agent,
                prepared,
                settings,
                repo,
                _retry_instructions_for_repo(retry_by_repo, repo.repo_id),
                on_log,
            ): repo
            for repo in target_repos
        }
        for future in as_completed(futures):
            repo = futures[future]
            try:
                result = future.result()
                result = normalize_single_repo_research_payload(result, repo)
                on_log(f"design_research_agent_repo_ok: repo={repo.repo_id} candidates={len(dict_list(result.get('candidate_files')))}")
            except Exception as error:
                # 单仓失败不应拖垮其他仓；但必须显式进入 research summary，
                # 后续 Research Supervisor / Design Supervisor 不能把它当成功证据。
                result = _repo_research_error_payload(repo, str(error))
                on_log(f"design_research_agent_repo_failed: repo={repo.repo_id} error={error}")
            results.append(result)
    return sorted(results, key=lambda item: str(item.get("repo_id") or ""))


def _run_single_repo_research_agent(
    prepared: DesignInputBundle,
    settings: Settings,
    repo: RepoScope,
    retry_instructions: list[str],
    on_log,
) -> dict[str, object]:
    context_package = build_repo_context_package(prepared, settings, repo, on_log=on_log)
    return run_agent_json(
        prepared,
        settings,
        build_design_research_template_json(),
        lambda template_path: build_design_research_prompt(
            title=prepared.title,
            refined_markdown=prepared.refined_markdown,
            repo_context_payload={"repo_id": repo.repo_id, "repo_path": repo.repo_path},
            repo_context_package=context_package,
            skills_index_markdown=prepared.design_skills_index_markdown,
            skills_fallback_markdown=prepared.design_skills_fallback_markdown,
            template_path=template_path,
            retry_instructions=retry_instructions,
        ),
        f".design-research-agent-{repo.repo_id}-",
        role=f"design_research:{repo.repo_id}",
        stage="repo_research",
        on_log=on_log,
    )


def _review_research_payload(
    prepared: DesignInputBundle,
    settings: Settings,
    research_payload: dict[str, object],
    *,
    on_log,
) -> dict[str, object]:
    return run_agent_json(
        prepared,
        settings,
        build_design_research_review_template_json(),
        lambda template_path: build_design_research_review_prompt(
            title=prepared.title,
            refined_markdown=prepared.refined_markdown,
            research_payload=research_payload,
            template_path=template_path,
            skills_index_markdown=prepared.design_skills_index_markdown,
        ),
        ".design-research-supervisor-",
        role="design_research_supervisor",
        stage="research_review",
        on_log=on_log,
    )


def normalize_single_repo_research_payload(payload: dict[str, object], repo: RepoScope) -> dict[str, object]:
    result = dict(payload)
    result["repo_id"] = str(result.get("repo_id") or repo.repo_id)
    result["repo_path"] = str(result.get("repo_path") or repo.repo_path)
    result["research_status"] = str(result.get("research_status") or "ok")
    return result


def _merge_repo_research_payload(previous: dict[str, object] | None, current: dict[str, object]) -> dict[str, object]:
    """合并同一 repo 的多轮调研结果。

    第二轮通常只是在 Supervisor 指令下补证据。若补查 agent 自身失败，不能用一个
    failed payload 覆盖第一轮已获得的核心 evidence；否则 design 会丢失可用线索。
    """

    if not previous:
        return current
    current_status = str(current.get("research_status") or "ok")
    previous_status = str(previous.get("research_status") or "ok")
    if current_status != "failed" or previous_status == "failed":
        return current

    result = dict(previous)
    retry_error = str(current.get("research_error") or "").strip()
    if retry_error:
        retry_errors = as_str_list(result.get("retry_errors"))
        retry_errors.append(retry_error)
        result["retry_errors"] = retry_errors
        unknowns = as_str_list(result.get("unknowns"))
        unknowns.append(f"Supplemental Research Agent retry failed: {retry_error}")
        result["unknowns"] = unknowns
    return result


def _normalize_candidate_files(raw: object) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in _raw_file_items(raw):
        if isinstance(item, str):
            result.append(
                {
                    "path": item,
                    "symbol": "",
                    "reason": "",
                    "confidence": "medium",
                    "line": None,
                    "evidence": [],
                    "context_notes": [],
                }
            )
            continue
        path = _file_path(item)
        if not path:
            continue
        line = _first_int(item.get("line"), item.get("line_start"), item.get("start_line"))
        result.append(
            {
                "path": path,
                "symbol": str(item.get("symbol") or "").strip(),
                "reason": str(item.get("reason") or "").strip(),
                "confidence": _normalize_confidence(str(item.get("confidence") or "")),
                "line": line,
                "evidence": _normalize_text_items(item.get("evidence")),
                "context_notes": _normalize_text_items(item.get("context_notes")),
            }
        )
    return result


def _normalize_file_items(raw: object) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in _raw_file_items(raw):
        if isinstance(item, str):
            result.append(
                {
                    "path": item,
                    "symbol": "",
                    "reason": "",
                    "confidence": "medium",
                    "line": None,
                    "evidence": [],
                }
            )
            continue
        path = _file_path(item)
        if not path:
            continue
        result.append(
            {
                "path": path,
                "symbol": str(item.get("symbol") or "").strip(),
                "reason": str(item.get("reason") or item.get("summary") or item.get("description") or "").strip(),
                "confidence": _normalize_confidence(str(item.get("confidence") or "")),
                "line": _first_int(item.get("line"), item.get("line_start"), item.get("start_line")),
                "evidence": _normalize_text_items(item.get("evidence")),
            }
        )
    return result


def _raw_file_items(raw: object) -> list[dict[str, object] | str]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, object] | str] = []
    for item in raw:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _file_path(item: dict[str, object]) -> str:
    return str(item.get("path") or item.get("file") or item.get("file_path") or item.get("filepath") or "").strip()


def _normalize_text_items(raw: object) -> list[str]:
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = _dict_text(item)
        else:
            text = str(item).strip()
        if text:
            result.append(text)
    return result


def _dict_text(item: dict[str, object]) -> str:
    for key in ("summary", "description", "question", "claim", "reason", "next_step", "next_steps"):
        value = str(item.get(key) or "").strip()
        if value:
            suffix = str(item.get("next_step") or item.get("next_steps") or "").strip()
            if suffix and suffix != value and key not in {"next_step", "next_steps"}:
                return f"{value}；下一步：{suffix}"
            return value
    return ""


def _first_int(*values: object) -> int | None:
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def _normalize_skill_usage(raw: object) -> dict[str, object]:
    payload = raw if isinstance(raw, dict) else {}
    return {
        "read_files": as_str_list(payload.get("read_files")),
        "applied_rules": as_str_list(payload.get("applied_rules")),
        "derived_search_hints": as_str_list(payload.get("derived_search_hints")),
    }


def _normalize_research_review(payload: dict[str, object], research_payload: dict[str, object] | None = None) -> dict[str, object]:
    decision = str(payload.get("decision") or "").strip()
    if decision not in {"pass", "redo_research", "needs_human", "degrade_design", "fail"}:
        decision = "needs_human"
    passed = bool(payload.get("passed")) and decision == "pass"
    result = {
        "passed": passed,
        "decision": "pass" if passed else decision,
        "confidence": _normalize_confidence(str(payload.get("confidence") or "")),
        "blocking_issues": dict_list(payload.get("blocking_issues")),
        "research_instructions": _normalize_research_instructions(payload.get("research_instructions")),
        "reason": str(payload.get("reason") or "").strip(),
    }
    failed_repos = _failed_repo_ids(research_payload or {})
    if failed_repos and result["decision"] == "pass":
        result["passed"] = False
        result["decision"] = "redo_research"
        result["confidence"] = "medium"
        result["blocking_issues"] = [
            *dict_list(result.get("blocking_issues")),
            *[
                {
                    "type": "repo_research_failed",
                    "summary": f"{repo_id} research failed; must retry or mark as unresolved before Design can pass.",
                    "evidence": [],
                }
                for repo_id in failed_repos
            ],
        ]
        existing_instructions = as_str_list(result.get("research_instructions"))
        result["research_instructions"] = [
            *existing_instructions,
            *[f"{repo_id}: 重新调研失败仓库；若确认不是实现责任仓，输出 reference_only/not_needed、空 candidate_files 和明确 boundaries。" for repo_id in failed_repos],
        ]
        base_reason = str(result.get("reason") or "").strip()
        failed_reason = "Research contains failed repo(s): " + ", ".join(failed_repos)
        result["reason"] = f"{base_reason} {failed_reason}".strip()
    if (
        not failed_repos
        and result["decision"] == "redo_research"
        and _research_payload_has_design_starting_point(research_payload or {})
    ):
        # Research 的职责是给 Design 提供可信起点，不是把所有配置名、文案 key、
        # 分隔符和实现细节都查到闭环。已有核心 repo、候选文件和 claims 时，
        # 继续补查应进入 design.md 待确认项，而不是再触发一整轮慢速 agent。
        base_reason = str(result.get("reason") or "").strip()
        result["passed"] = True
        result["decision"] = "pass"
        result["confidence"] = "medium"
        result["blocking_issues"] = []
        result["research_instructions"] = []
        result["reason"] = (
            f"{base_reason} Research already has candidate files and claims; "
            "remaining gaps should be carried as Design pending confirmations."
        ).strip()
    return result


def _research_payload_has_design_starting_point(research_payload: dict[str, object]) -> bool:
    repos = dict_list(research_payload.get("repos"))
    if not repos or _failed_repo_ids(research_payload):
        return False
    actionable_repos = [
        repo
        for repo in repos
        if str(repo.get("work_hypothesis") or "") in {"required", "conditional"}
    ]
    if not actionable_repos:
        return False
    for repo in actionable_repos:
        candidates = dict_list(repo.get("candidate_files"))
        claims = dict_list(repo.get("claims"))
        if str(repo.get("work_hypothesis") or "") == "required" and (not candidates or not claims):
            return False
        if str(repo.get("work_hypothesis") or "") == "required" and not _candidate_files_were_read(repo):
            return False
    return any(dict_list(repo.get("candidate_files")) and dict_list(repo.get("claims")) for repo in actionable_repos)


def _candidate_files_were_read(repo: dict[str, object]) -> bool:
    skill_usage = repo.get("skill_usage") if isinstance(repo.get("skill_usage"), dict) else {}
    read_files = [item.replace("\\", "/") for item in as_str_list(skill_usage.get("read_files"))]
    candidates = dict_list(repo.get("candidate_files"))
    if not read_files or not candidates:
        return False
    for candidate in candidates:
        path = str(candidate.get("path") or candidate.get("file") or "").strip().replace("\\", "/")
        if not path:
            return False
        if not any(read_file == path or read_file.endswith("/" + path) or path.endswith("/" + read_file) for read_file in read_files):
            return False
    return True


def _target_repos(
    repo_scopes: list[RepoScope],
    existing_payloads: dict[str, dict[str, object]],
    retry_by_repo: dict[str, list[str]],
    round_index: int,
) -> list[RepoScope]:
    if round_index == 1:
        return repo_scopes
    if not retry_by_repo:
        return []
    retry_all = "*" in retry_by_repo
    return [repo for repo in repo_scopes if retry_all or repo.repo_id in retry_by_repo or repo.repo_id not in existing_payloads]


def _research_instructions_by_repo(
    repo_scopes: list[RepoScope],
    review: dict[str, object],
    research_payload: dict[str, object] | None = None,
) -> dict[str, list[str]]:
    raw = as_str_list(review.get("research_instructions"))
    if not raw:
        return {}
    repo_ids = {repo.repo_id for repo in repo_scopes}
    default_retry_repo_ids = _default_retry_repo_ids(repo_scopes, research_payload or {})
    result: dict[str, list[str]] = {}
    for instruction in raw:
        matched = [repo_id for repo_id in repo_ids if repo_id in instruction]
        if not matched:
            for repo_id in default_retry_repo_ids:
                result.setdefault(repo_id, []).append(instruction)
            continue
        for repo_id in matched:
            result.setdefault(repo_id, []).append(instruction)
    return result


def _normalize_research_instructions(raw: object) -> list[str]:
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
            continue
        if not isinstance(item, dict):
            text = str(item).strip()
            if text:
                result.append(text)
            continue
        repo_id = str(item.get("repo_id") or item.get("repo") or "").strip()
        instructions = item.get("instructions") or item.get("research_instructions") or item.get("items")
        instruction_texts = as_str_list(instructions)
        if not instruction_texts:
            summary = str(item.get("instruction") or item.get("summary") or item.get("reason") or "").strip()
            instruction_texts = [summary] if summary else []
        for instruction in instruction_texts:
            result.append(f"{repo_id}: {instruction}" if repo_id else instruction)
    return result


def _default_retry_repo_ids(repo_scopes: list[RepoScope], research_payload: dict[str, object]) -> list[str]:
    """给未点名 repo 的补查指令选择默认目标。

    第二轮补查不应默认重跑全部仓库。已经判断为 not_needed / reference_only 且 high confidence
    的 repo 会被冻结；通用补查只投给仍可能需要实现、条件实现、职责未知、低置信或失败的 repo。
    """

    payload_by_repo = {
        str(repo.get("repo_id") or ""): repo
        for repo in dict_list(research_payload.get("repos"))
        if str(repo.get("repo_id") or "").strip()
    }
    candidates: list[str] = []
    for scope in repo_scopes:
        payload = payload_by_repo.get(scope.repo_id, {})
        status = str(payload.get("research_status") or "ok")
        hypothesis = str(payload.get("work_hypothesis") or "unknown")
        confidence = str(payload.get("confidence") or "medium")
        frozen = hypothesis in {"not_needed", "reference_only"} and confidence == "high" and status == "ok"
        if frozen:
            continue
        if status != "ok" or confidence != "high" or hypothesis in {"required", "conditional", "unknown"}:
            candidates.append(scope.repo_id)
    return candidates or [repo.repo_id for repo in repo_scopes]


def _failed_repo_ids(research_payload: dict[str, object]) -> list[str]:
    result: list[str] = []
    for repo in dict_list(research_payload.get("repos")):
        if str(repo.get("research_status") or "ok") != "failed":
            continue
        repo_id = str(repo.get("repo_id") or "").strip()
        if repo_id:
            result.append(repo_id)
    return result


def _retry_instructions_for_repo(retry_by_repo: dict[str, list[str]], repo_id: str) -> list[str]:
    """把通用补查指令合并给每个单仓 Research Agent。

    Research Supervisor 经常会给出不带 repo_id 的指令，例如 Starling key、git history、
    调用点一致性检查。它们会被归入 "*"，第二轮调研时必须传给每个目标 repo。
    """

    merged: list[str] = []
    seen: set[str] = set()
    for item in [*retry_by_repo.get("*", []), *retry_by_repo.get(repo_id, [])]:
        instruction = item.strip()
        if not instruction or instruction in seen:
            continue
        seen.add(instruction)
        merged.append(instruction)
    return merged


def _repo_research_error_payload(repo: RepoScope, error: str) -> dict[str, object]:
    return {
        "repo_id": repo.repo_id,
        "repo_path": repo.repo_path,
        "work_hypothesis": "unknown",
        "confidence": "low",
        "research_status": "failed",
        "research_error": error,
        "skill_usage": {"read_files": [], "applied_rules": [], "derived_search_hints": []},
        "claims": [],
        "candidate_files": [],
        "related_files": [],
        "excluded_files": [],
        "rejected_candidates": [],
        "boundaries": [],
        "unknowns": [f"Research Agent failed for repo {repo.repo_id}: {error}"],
        "next_search_suggestions": [],
        "updated_at": datetime.now().astimezone().isoformat(),
    }


def _research_supervisor_error_review(error: str) -> dict[str, object]:
    return {
        "passed": False,
        "decision": "needs_human",
        "confidence": "low",
        "blocking_issues": [
            {
                "type": "research_supervisor_failed",
                "summary": f"Research Supervisor failed while reviewing repo evidence: {error}",
                "evidence": [],
            }
        ],
        "research_instructions": [],
        "reason": f"Research Supervisor failed: {error}",
    }


def _research_status(repos: list[dict[str, object]]) -> str:
    if any(str(repo.get("research_status") or "ok") == "failed" for repo in repos):
        return "failed"
    return "ok"


def _normalize_work_hypothesis(value: str) -> str:
    normalized = value.strip()
    return normalized if normalized in {"required", "conditional", "reference_only", "not_needed", "unknown"} else "unknown"


def _normalize_confidence(value: str) -> str:
    normalized = value.strip()
    return normalized if normalized in {"high", "medium", "low"} else "medium"

from __future__ import annotations

import json
import re
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.design import build_design_change_points_agent_prompt, build_design_change_points_template_json

from .models import DesignPreparedInput, EXECUTOR_NATIVE

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")


def build_design_change_points_payload(
    prepared: DesignPreparedInput,
    settings: Settings,
    knowledge_brief_markdown: str,
    on_log,
) -> dict[str, object]:
    """抽取 Design 阶段围绕展开的那几个核心 change points。

    native 模式会让 agent 填一个 JSON 模板；local 模式则退回到基于
    refined sections 的启发式抽取。
    """
    fallback = build_local_design_change_points_payload(prepared)
    if settings.plan_executor.strip().lower() != EXECUTOR_NATIVE:
        return fallback

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_change_points_template(prepared.task_dir)
    try:
        client.run_agent(
            build_design_change_points_agent_prompt(
                title=prepared.title,
                refined_markdown=prepared.refined_markdown,
                knowledge_brief_markdown=knowledge_brief_markdown,
                seed_change_points=[item["title"] for item in fallback["change_points"] if isinstance(item, dict) and str(item.get("title") or "").strip()],
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        if "__FILL__" in raw:
            raise ValueError("design_change_points_template_unfilled")
        payload = json.loads(raw)
        normalized = _normalize_native_change_points_payload(payload, prepared)
        if not normalized["change_points"]:
            raise ValueError("design_change_points_empty")
        return normalized
    except Exception as error:
        on_log(f"design_change_points_fallback: {error}")
        return fallback
    finally:
        if template_path.exists():
            template_path.unlink()


def build_local_design_change_points_payload(prepared: DesignPreparedInput) -> dict[str, object]:
    candidates = [item.strip() for item in prepared.sections.change_scope if item.strip()]
    if not candidates:
        candidates = [prepared.title.strip() or "Primary design change"]

    change_points: list[dict[str, object]] = []
    for index, title in enumerate(candidates[:8], start=1):
        related_constraints = [item for item in prepared.sections.key_constraints if _shares_signal(title, item)][:3]
        related_acceptance = [item for item in prepared.sections.acceptance_criteria if _shares_signal(title, item)][:3]
        summary_parts = [title]
        if related_constraints:
            summary_parts.append("Constraints: " + " / ".join(related_constraints))
        if related_acceptance:
            summary_parts.append("Acceptance: " + " / ".join(related_acceptance))
        change_points.append(
            {
                "id": index,
                "title": title,
                "summary": " ".join(summary_parts),
                "constraints": related_constraints,
                "acceptance": related_acceptance,
            }
        )

    return {
        "mode": "local",
        "change_points": change_points,
    }


def build_design_repo_assignment_payload(
    prepared: DesignPreparedInput,
    change_points_payload: dict[str, object],
) -> dict[str, object]:
    """为每个 change point 找出可能的主负责 repo 和辅助 repo。

    这一步故意比最终 repo binding 更轻，只提供一个初步路由假设，后面的
    research 和 matrix 还会继续修正。
    """
    change_points = [item for item in change_points_payload.get("change_points", []) if isinstance(item, dict)]
    repos = prepared.repo_researches
    source = "attached_repos" if prepared.repo_scopes else "discovered_repos"

    if prepared.is_single_bound_repo and repos:
        repo = repos[0]
        change_point_ids = [int(item.get("id") or index + 1) for index, item in enumerate(change_points)] or [1]
        return {
            "mode": "single_bound_fast_path",
            "source": source,
            "assignments": [
                {
                    "change_point_id": change_point_id,
                    "change_point_title": str(change_point.get("title") or prepared.title).strip(),
                    "primary_candidate": repo.repo_id,
                    "secondary_candidates": [],
                    "confidence": "high",
                    "reason": "单仓且用户已绑定 repo，所有 change points 直接归属该仓库。",
                }
                for change_point_id, change_point in (
                    (int(item.get("id") or index + 1), item)
                    for index, item in enumerate(change_points)
                )
            ],
            "repo_briefs": [
                {
                    "repo_id": repo.repo_id,
                    "repo_path": repo.repo_path,
                    "primary_change_points": change_point_ids,
                    "secondary_change_points": [],
                    "reason": "Single bound repo fast path: all change points are assigned to the only bound repo.",
                }
            ],
        }

    repo_briefs: list[dict[str, object]] = []
    by_repo: dict[str, dict[str, object]] = {}
    for repo in repos:
        by_repo[repo.repo_id] = {
            "repo_id": repo.repo_id,
            "repo_path": repo.repo_path,
            "primary_change_points": [],
            "secondary_change_points": [],
            "reason": "",
        }

    assignments: list[dict[str, object]] = []
    for offset, change_point in enumerate(change_points):
        change_point_id = int(change_point.get("id") or offset + 1)
        title = str(change_point.get("title") or "").strip()
        scored = _score_change_point_against_repos(prepared, title)
        if not scored:
            continue

        primary_repo_id = scored[0]["repo_id"]
        secondary_candidates = [item["repo_id"] for item in scored[1:3] if item["score"] > 0]
        if not secondary_candidates and len(scored) > 1:
            secondary_candidates = [scored[1]["repo_id"]]

        by_repo[primary_repo_id]["primary_change_points"].append(change_point_id)
        for repo_id in secondary_candidates:
            by_repo[repo_id]["secondary_change_points"].append(change_point_id)

        confidence = "high" if scored[0]["score"] >= 6 else "medium" if scored[0]["score"] > 1 else "low"
        assignments.append(
            {
                "change_point_id": change_point_id,
                "change_point_title": title,
                "primary_candidate": primary_repo_id,
                "secondary_candidates": secondary_candidates,
                "confidence": confidence,
                "reason": scored[0]["reason"],
            }
        )

    for repo_id, brief in by_repo.items():
        reasons: list[str] = []
        if brief["primary_change_points"]:
            reasons.append(f"Primary for change points {', '.join(str(item) for item in brief['primary_change_points'])}")
        if brief["secondary_change_points"]:
            reasons.append(f"Secondary for change points {', '.join(str(item) for item in brief['secondary_change_points'])}")
        if not reasons:
            reasons.append("No strong change-point ownership yet; keep as low-priority reference repo.")
        brief["reason"] = " ".join(reasons)
        repo_briefs.append(brief)

    return {
        "mode": "local",
        "source": source,
        "assignments": assignments,
        "repo_briefs": repo_briefs,
    }


def _score_change_point_against_repos(prepared: DesignPreparedInput, change_point_title: str) -> list[dict[str, object]]:
    scored: list[dict[str, object]] = []
    for index, repo in enumerate(prepared.repo_researches):
        score = 0
        reasons: list[str] = []
        signals = _repo_signals(repo)
        lowered_title = change_point_title.lower()
        if any(term.lower() in lowered_title or lowered_title in term.lower() for term in signals["matched_terms"]):
            score += 5
            reasons.append("matched glossary term")
        if any(fragment in lowered_title for fragment in signals["path_fragments"]):
            score += 3
            reasons.append("matched path fragment")
        if any(fragment in lowered_title for fragment in signals["note_fragments"]):
            score += 2
            reasons.append("matched research note")
        if score == 0:
            score = max(0, signals["overall_score"] // 4)
            if score > 0:
                reasons.append("borrowed repo-level confidence")
        if score == 0 and prepared.repo_researches:
            # Fallback spread to avoid hard-routing all unknown points to the same repo.
            score = 1 if index == (len(scored) % max(len(prepared.repo_researches), 1)) else 0
        scored.append(
            {
                "repo_id": repo.repo_id,
                "score": score,
                "reason": ", ".join(reasons) or "fallback candidate",
            }
        )
    scored.sort(key=lambda item: (-int(item["score"]), str(item["repo_id"])))
    return scored


def _repo_signals(repo) -> dict[str, object]:
    matched_terms = [entry.business for entry in repo.finding.matched_terms]
    path_fragments = _tokenize(" ".join([*repo.finding.candidate_dirs, *repo.finding.candidate_files]))
    note_fragments = _tokenize(" ".join(repo.finding.notes))
    overall_score = len(repo.finding.matched_terms) * 4 + len(repo.finding.candidate_files) * 2 + len(repo.finding.candidate_dirs)
    return {
        "matched_terms": matched_terms,
        "path_fragments": path_fragments,
        "note_fragments": note_fragments,
        "overall_score": overall_score,
    }


def _tokenize(value: str) -> list[str]:
    ascii_tokens = [token.lower() for token in _ASCII_TOKEN_RE.findall(value)]
    chinese_chunks = [chunk for chunk in re.split(r"[^一-龥]+", value) if len(chunk) >= 2]
    return ascii_tokens + chinese_chunks


def _shares_signal(left: str, right: str) -> bool:
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    return bool(left_tokens & right_tokens)


def _write_change_points_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".design-change-points-",
        suffix=".json",
        delete=False,
    ) as handle:
        handle.write(build_design_change_points_template_json())
        handle.flush()
        return Path(handle.name)


def _normalize_native_change_points_payload(payload: object, prepared: DesignPreparedInput) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("design_change_points_output_not_object")
    raw_items = payload.get("change_points")
    if not isinstance(raw_items, list):
        raise ValueError("design_change_points_output_missing_list")
    change_points: list[dict[str, object]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        constraints = [str(value).strip() for value in item.get("constraints", []) if str(value).strip()][:3]
        acceptance = [str(value).strip() for value in item.get("acceptance", []) if str(value).strip()][:3]
        summary = str(item.get("summary") or title).strip() or title
        change_points.append(
            {
                "id": index,
                "title": title,
                "summary": summary,
                "constraints": constraints,
                "acceptance": acceptance,
            }
        )
    if not change_points:
        fallback_title = prepared.title.strip() or "Primary design change"
        change_points = [
            {
                "id": 1,
                "title": fallback_title,
                "summary": fallback_title,
                "constraints": [],
                "acceptance": [],
            }
        ]
    return {
        "mode": "llm",
        "change_points": change_points[:8],
    }

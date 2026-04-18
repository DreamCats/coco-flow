from __future__ import annotations

import re

from .models import DesignPreparedInput

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")


def build_design_change_points_payload(prepared: DesignPreparedInput) -> dict[str, object]:
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
    change_points = [item for item in change_points_payload.get("change_points", []) if isinstance(item, dict)]
    repos = prepared.repo_researches
    source = "attached_repos" if prepared.repo_scopes else "discovered_repos"

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

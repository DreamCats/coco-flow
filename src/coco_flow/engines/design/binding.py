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
    scored: list[tuple[int, DesignRepoBindingEntry]] = []
    repo_count = len(prepared.repo_scopes)
    change_point_ids = list(range(1, len(prepared.sections.change_scope) + 1)) or [1]
    for repo in prepared.repo_researches:
        score = len(repo.finding.candidate_files) * 3 + len(repo.finding.candidate_dirs) * 2 + len(repo.finding.matched_terms) * 3
        decision = "in_scope" if score > 0 else "out_of_scope"
        system_name = repo.finding.matched_terms[0].business if repo.finding.matched_terms else repo.repo_id
        candidate_dirs = [qualify_repo_path(repo.repo_id, item, repo_count) for item in repo.finding.candidate_dirs[:6]]
        candidate_files = [qualify_repo_path(repo.repo_id, item, repo_count) for item in repo.finding.candidate_files[:8]]
        entry = DesignRepoBindingEntry(
            repo_id=repo.repo_id,
            repo_path=repo.repo_path,
            decision=decision,
            role="reference",
            serves_change_points=change_point_ids[:],
            system_name=system_name,
            responsibility=(prepared.research_signals.system_summaries[0] if prepared.research_signals.system_summaries else f"承接 {repo.repo_id} 范围内的设计改造").strip(),
            change_summary=(prepared.sections.change_scope[:3] or [prepared.title]),
            boundaries=(prepared.sections.non_goals[:3] or ["保持最小改动范围，不把无关仓库带入本次设计。"]),
            candidate_dirs=candidate_dirs,
            candidate_files=candidate_files,
            depends_on=[],
            parallelizable_with=[],
            confidence="high" if score >= 6 else "medium" if score > 0 else "low",
            reason="基于术语命中、候选目录和候选文件的本地 research 判定。",
        )
        scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1].repo_id))
    primary_assigned = False
    previous_repo = ""
    bindings: list[DesignRepoBindingEntry] = []
    for score, entry in scored:
        current = entry
        if entry.decision == "in_scope":
            if not primary_assigned:
                current.role = "primary"
                primary_assigned = True
            else:
                current.role = "supporting"
                if previous_repo:
                    current.depends_on = [previous_repo]
            previous_repo = current.repo_id
        bindings.append(current)
    in_scope = [entry.repo_id for entry in bindings if entry.decision == "in_scope"]
    summary = "、".join(in_scope) + " 进入本次 Design 范围。" if in_scope else "当前未识别到明确 in_scope repo。"
    return DesignRepoBinding(repo_bindings=bindings, missing_repos=[], decision_summary=summary, mode="local")


def build_repo_binding(prepared: DesignPreparedInput, settings: Settings, knowledge_brief_markdown: str, on_log) -> DesignRepoBinding:
    fallback = build_local_repo_binding(prepared)
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
                    role=str(item.get("role") or "reference"),
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
        return DesignRepoBinding(
            repo_bindings=entries,
            missing_repos=[str(value) for value in payload.get("missing_repos", []) if str(value).strip()],
            decision_summary=str(payload.get("decision_summary") or fallback.decision_summary),
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

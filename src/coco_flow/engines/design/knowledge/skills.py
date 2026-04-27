"""Design Skills/SOP 选择与渐进式加载索引。

按 refined PRD、绑定仓库和业务术语筛选相关 Skill，将业务地图、仓库角色、
多仓联动和 SOP 规则整理成 native agent 可读取完整文件的索引。
fallback excerpt 只保留给 local fallback 使用。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.services.queries.skills import SkillPackage, SkillStore

from coco_flow.engines.design.support import as_str_list, dedupe
from coco_flow.engines.design.types import DesignInputBundle

_MAX_SELECTED_SKILLS = 3
_MAX_RECALL_CANDIDATES = 5
_MAX_TERMS = 40
_MAX_LINES_PER_BLOCK = 8
_OVERVIEW_MAX_LINES = 80
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "this",
    "that",
    "prd",
    "refined",
    "design",
}


@dataclass(frozen=True)
class _SkillDocument:
    package: SkillPackage
    body: str
    overview: str
    references: list[tuple[str, Path, str]]


def build_design_skills_bundle(
    prepared: DesignInputBundle,
    settings: Settings,
    *,
    native_ok: bool = False,
    on_log=None,
) -> tuple[str, str, dict[str, object], list[str]]:
    documents = [_package_to_document(package) for package in SkillStore(settings).list_packages()]
    scored: list[tuple[int, dict[str, object], _SkillDocument]] = []
    unmatched: list[dict[str, object]] = []
    for document in documents:
        payload = score_design_skill_document(document, prepared)
        score = int(payload.get("score") or 0)
        if score > 0:
            scored.append((score, payload, document))
        else:
            unmatched.append(payload)
    scored.sort(key=lambda item: (-item[0], item[2].package.name))
    recalled = scored[:_MAX_RECALL_CANDIDATES]
    selected = _program_selected_skills(recalled)
    selector_payload: dict[str, object] = {"source": "program"}
    _log_design_skill_candidates(on_log, "design_skills_candidates", recalled)
    if native_ok and recalled:
        agent_selection = _select_design_skills_with_agent(prepared, settings, recalled, on_log)
        if agent_selection is not None:
            selected_ids = as_str_list(agent_selection.get("selected_skill_ids"))[:_MAX_SELECTED_SKILLS]
            by_id = {item[2].package.id: item for item in recalled}
            agent_selected = [by_id[skill_id] for skill_id in selected_ids if skill_id in by_id]
            if agent_selected:
                selected = agent_selected
                selector_payload = {"source": "native", **agent_selection}
    selected_documents = [item[2] for item in selected]
    selection_payload = {
        "selected_skill_ids": [item[2].package.id for item in selected],
        "selected_skill_titles": [item[2].package.name for item in selected],
        "selected_skill_sources": [_skill_source_payload(item[2], item[1]) for item in selected],
        "selector": selector_payload,
        "candidates": [item[1] for item in scored] + unmatched,
    }
    if not selected:
        return "", "", selection_payload, []
    _log_selected_design_skills(on_log, selection_payload)
    index = render_design_skills_index(selected_documents, selection_payload["selected_skill_sources"])
    fallback = render_design_skills_fallback(selected_documents, prepared)
    return index, fallback, selection_payload, [item[2].package.id for item in selected]


def _program_selected_skills(
    recalled: list[tuple[int, dict[str, object], _SkillDocument]],
) -> list[tuple[int, dict[str, object], _SkillDocument]]:
    if len(recalled) < 2:
        return recalled[:_MAX_SELECTED_SKILLS]
    top_score = int(recalled[0][1].get("score") or 0)
    second_score = int(recalled[1][1].get("score") or 0)
    if top_score >= second_score * 3 or top_score - second_score >= 6:
        return recalled[:1]
    return recalled[:_MAX_SELECTED_SKILLS]


def _log_design_skill_candidates(on_log, event: str, items: list[tuple[int, dict[str, object], _SkillDocument]]) -> None:
    if not on_log:
        return
    parts = []
    for _score, payload, document in items:
        parts.append(f"{document.package.id}(score={payload.get('score')},keywords={','.join(as_str_list(payload.get('keyword_hits'))[:4])})")
    on_log(f"{event}: " + ("; ".join(parts) if parts else "none"))


def _log_selected_design_skills(on_log, selection_payload: dict[str, object]) -> None:
    if not on_log:
        return
    selector = selection_payload.get("selector") if isinstance(selection_payload.get("selector"), dict) else {}
    selected = ",".join(as_str_list(selection_payload.get("selected_skill_ids"))) or "none"
    on_log(f"design_skills_selected: source={selector.get('source') or 'program'} ids={selected}")
    rejected = ",".join(as_str_list(selector.get("rejected_skill_ids"))) if selector else ""
    if rejected:
        on_log(f"design_skills_rejected: ids={rejected}")
    reasons = selector.get("reasons") if isinstance(selector.get("reasons"), dict) else {}
    for skill_id, reason in reasons.items():
        value = str(reason).strip()
        if value:
            on_log(f"design_skills_reason: {skill_id}={value[:300]}")


def score_design_skill_document(document: _SkillDocument, prepared: DesignInputBundle) -> dict[str, object]:
    terms = _infer_design_skill_terms(prepared)
    searchable = "\n".join(
        [
            document.package.name,
            document.package.description,
            document.package.domain,
            document.overview,
            *[name for name, _path, _content in document.references],
        ]
    )
    keyword_hits = [
        term
        for term in terms
        if term.lower() in searchable.lower()
    ]
    repo_hits = _repo_hits(document, prepared)
    metadata_hits = _metadata_hits(document, terms)
    score = min(len(keyword_hits), 8) + len(repo_hits) + len(metadata_hits) * 3
    if keyword_hits:
        score += 2
    score = max(score, 0)
    return {
        "id": document.package.id,
        "title": document.package.name,
        "domain": document.package.domain,
        "score": score,
        "keyword_hits": keyword_hits[:10],
        "repo_hits": repo_hits,
        "metadata_hits": metadata_hits[:6],
        "selected_references": _selected_reference_names(document, terms),
    }


def render_design_skills_fallback(documents: list[_SkillDocument], prepared: DesignInputBundle) -> str:
    lines = [
        "# Design Skills Local Fallback",
        "",
        "- 用途：仅用于 Design 阶段判断业务 workflow、repo 角色、多仓联动、SOP 和风险边界。",
        "- 优先级：refined PRD 与 repo research 证据优先于 skills；skills 不得单独证明某仓必须改代码。",
        "",
    ]
    terms = _infer_design_skill_terms(prepared)
    for document in documents:
        lines.extend(
            [
                f"## {document.package.name}",
                "",
                f"- id: {document.package.id}",
                f"- domain: {document.package.domain or 'unknown'}",
                f"- description: {document.package.description or '无'}",
                "",
                "### Matched Excerpts",
                _render_block(_matched_excerpt_lines(document.body, terms)),
                "",
                "### Reference Files",
                _render_block([name for name, _path, _content in document.references]),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_design_skills_index(documents: list[_SkillDocument], sources: list[dict[str, object]]) -> str:
    lines = [
        "# Design Skills Index",
        "",
        "- 用途：给 native agent 做渐进式加载导航；这里不是事实摘要。",
        "- 规则：选中 skill 后，agent 必须读取下列完整文件，再把 Skills/SOP 作为稳定背景使用。",
        "",
    ]
    by_id = {document.package.id: document for document in documents}
    for source in sources:
        skill_id = str(source.get("id") or "")
        document = by_id.get(skill_id)
        if document is None:
            continue
        lines.extend(
            [
                f"## {document.package.name}",
                "",
                f"- id: {document.package.id}",
                f"- domain: {document.package.domain or 'unknown'}",
                f"- description: {document.package.description or '无'}",
                f"- match_reason: {_render_match_reason(source)}",
                "- files:",
            ]
        )
        for file_path in _skill_file_paths(document):
            lines.append(f"  - `{file_path}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _package_to_document(package: SkillPackage) -> _SkillDocument:
    references: list[tuple[str, Path, str]] = []
    for path in package.reference_paths:
        try:
            references.append((str(path.relative_to(package.root_path)), path, path.read_text(encoding="utf-8").strip()))
        except OSError:
            continue
    body_parts = [package.body.strip(), *(content for _name, _path, content in references)]
    body = "\n\n".join(part for part in body_parts if part)
    return _SkillDocument(package=package, body=body, overview=_overview_excerpt(package.body), references=references)


def _infer_design_skill_terms(prepared: DesignInputBundle) -> list[str]:
    values = [
        prepared.title,
        prepared.refined_markdown[:5000],
        *prepared.sections.change_scope,
        *prepared.sections.key_constraints,
        *prepared.sections.acceptance_criteria,
    ]
    terms: list[str] = []
    for value in values:
        for token in _WORD_RE.findall(value):
            lowered = token.lower()
            if lowered not in _STOPWORDS:
                terms.append(token)
        for token in re.findall(r"[\u4e00-\u9fff]{2,12}", value):
            terms.append(token)
            terms.extend(_chinese_ngrams(token))
    return dedupe(terms)[:_MAX_TERMS]


def _chinese_ngrams(value: str) -> list[str]:
    grams: list[str] = []
    for size in (2, 3, 4, 5, 6):
        if len(value) < size:
            continue
        grams.extend(value[index : index + size] for index in range(0, len(value) - size + 1))
    return grams


def _repo_hits(document: _SkillDocument, prepared: DesignInputBundle) -> list[str]:
    searchable = "\n".join([document.package.name, document.package.description, document.package.domain, document.overview]).lower()
    hits: list[str] = []
    for repo in prepared.repo_scopes:
        candidates = dedupe([repo.repo_id, *[part for part in re.split(r"[/\\]", repo.repo_path) if part]])
        if any(candidate and candidate.lower() in searchable for candidate in candidates):
            hits.append(repo.repo_id)
    return dedupe(hits)


def _selected_reference_names(document: _SkillDocument, terms: list[str]) -> list[str]:
    selected = ["SKILL.md"] if document.package.body.strip() else []
    for name, _path, content in document.references:
        if any(term.lower() in content.lower() for term in terms):
            selected.append(name)
    return dedupe(selected)[:6]


def _metadata_hits(document: _SkillDocument, terms: list[str]) -> list[str]:
    searchable = "\n".join([document.package.name, document.package.description, document.package.domain])
    return [term for term in terms if term.lower() in searchable.lower()]


def _skill_source_payload(document: _SkillDocument, score_payload: dict[str, object]) -> dict[str, object]:
    return {
        "id": document.package.id,
        "title": document.package.name,
        "domain": document.package.domain,
        "description": document.package.description,
        "score": score_payload.get("score"),
        "keyword_hits": score_payload.get("keyword_hits") or [],
        "repo_hits": score_payload.get("repo_hits") or [],
        "metadata_hits": score_payload.get("metadata_hits") or [],
        "files": _skill_file_paths(document),
    }


def _skill_file_paths(document: _SkillDocument) -> list[str]:
    files = [str(document.package.skill_path)]
    files.extend(str(path) for _name, path, _content in document.references)
    return dedupe(files)


def _render_match_reason(source: dict[str, object]) -> str:
    parts: list[str] = []
    repo_hits = as_str_list(source.get("repo_hits"))
    keyword_hits = as_str_list(source.get("keyword_hits"))
    metadata_hits = as_str_list(source.get("metadata_hits"))
    if metadata_hits:
        parts.append("metadata=" + ", ".join(metadata_hits[:4]))
    if repo_hits:
        parts.append("repo=" + ", ".join(repo_hits[:4]))
    if keyword_hits:
        parts.append("keywords=" + ", ".join(keyword_hits[:6]))
    return "; ".join(parts) or "programmatic selection"


def _matched_excerpt_lines(body: str, terms: list[str]) -> list[str]:
    result: list[str] = []
    for line in _meaningful_lines(body):
        if any(term.lower() in line.lower() for term in terms):
            result.append(line)
    if result:
        return dedupe(result)[:_MAX_LINES_PER_BLOCK]
    return _meaningful_lines(body)[: min(4, _MAX_LINES_PER_BLOCK)]


def _meaningful_lines(body: str) -> list[str]:
    lines = []
    for raw in body.splitlines():
        line = raw.strip().strip("-").strip()
        if len(line) < 4 or line in {"---", "# Overview"}:
            continue
        lines.append(line[:240])
    return lines


def _overview_excerpt(body: str) -> str:
    return "\n".join(_meaningful_lines(body)[:_OVERVIEW_MAX_LINES])


def _render_block(lines: list[str]) -> str:
    values = as_str_list(lines)
    if not values:
        return "- 无"
    return "\n".join(f"- {line}" for line in values[:_MAX_LINES_PER_BLOCK])


def _select_design_skills_with_agent(
    prepared: DesignInputBundle,
    settings: Settings,
    recalled: list[tuple[int, dict[str, object], _SkillDocument]],
    on_log,
) -> dict[str, object] | None:
    # 这里刻意使用一次性 fresh 调用，而不是复用 design_writer session。
    # selector 只应该依赖任务文本和候选 SKILL.md overview，避免被 writer/search 历史污染。
    candidate_payloads = [_selector_candidate_payload(document, score_payload) for _score, score_payload, document in recalled]
    template = {
        "selected_skill_ids": ["__FILL__"],
        "rejected_skill_ids": ["__FILL__"],
        "reasons": {"__skill_id__": "__FILL__"},
    }
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=prepared.task_dir, prefix=".design-skill-selector-", suffix=".json", delete=False) as handle:
        path = Path(handle.name)
        handle.write(json.dumps(template, ensure_ascii=False, indent=2))
        handle.flush()
    prompt = _build_skill_selector_prompt(prepared, candidate_payloads, str(path))
    client = CocoACPClient(settings.coco_bin, idle_timeout_seconds=settings.acp_idle_timeout_seconds, settings=settings)
    try:
        if on_log:
            on_log(f"design_skills_selector_start: candidates={','.join(str(item['id']) for item in candidate_payloads)}")
        client.run_agent(prompt, settings.native_query_timeout, cwd=str(prepared.task_dir), fresh_session=True)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("selector payload is not object")
        candidate_ids = {str(item["id"]) for item in candidate_payloads}
        selected_ids = [skill_id for skill_id in as_str_list(payload.get("selected_skill_ids")) if skill_id in candidate_ids]
        if not selected_ids:
            raise ValueError("selector returned no valid selected_skill_ids")
        rejected_ids = [skill_id for skill_id in as_str_list(payload.get("rejected_skill_ids")) if skill_id in candidate_ids]
        reasons = payload.get("reasons") if isinstance(payload.get("reasons"), dict) else {}
        result = {
            "selected_skill_ids": selected_ids[:_MAX_SELECTED_SKILLS],
            "rejected_skill_ids": rejected_ids,
            "reasons": reasons,
        }
        if on_log:
            on_log(f"design_skills_selector_ok: selected={','.join(result['selected_skill_ids'])}")
        return result
    except Exception as error:
        if on_log:
            on_log(f"design_skills_selector_fallback: {error}")
        return None
    finally:
        path.unlink(missing_ok=True)


def _selector_candidate_payload(document: _SkillDocument, score_payload: dict[str, object]) -> dict[str, object]:
    return {
        "id": document.package.id,
        "name": document.package.name,
        "description": document.package.description,
        "domain": document.package.domain,
        "overview_excerpt": document.overview,
        "reference_files": [name for name, _path, _content in document.references],
        "program_score": score_payload.get("score"),
        "program_hits": {
            "keyword_hits": score_payload.get("keyword_hits") or [],
            "repo_hits": score_payload.get("repo_hits") or [],
            "metadata_hits": score_payload.get("metadata_hits") or [],
        },
    }


def _build_skill_selector_prompt(prepared: DesignInputBundle, candidates: list[dict[str, object]], template_path: str) -> str:
    task_payload = {
        "title": prepared.title,
        "repo_ids": [scope.repo_id for scope in prepared.repo_scopes if scope.repo_id],
        "refined_prd_excerpt": prepared.refined_markdown[:4000],
    }
    return (
        "你是 coco-flow Design 阶段的 Skill Selector。你的任务是从候选 skills 中选择本次需求真正需要读取的 skill。\n\n"
        f"请直接编辑 JSON 模板文件：{template_path}\n"
        "约束：\n"
        "- 只能从 Candidate skills 的 id 中选择，不能发明 id。\n"
        "- 默认选择 1 个；只有需求明确跨多个业务方向时才选择 2-3 个。\n"
        "- 不要因为泛化 repo 命中或泛化业务词就选择相邻业务 skill。\n"
        "- 必须填写 rejected_skill_ids 和 reasons，说明为什么拒绝候选。\n"
        "- 输出必须是合法 JSON，不要在聊天回复里粘贴结果。\n\n"
        "Task:\n"
        f"{json.dumps(task_payload, ensure_ascii=False, indent=2)}\n\n"
        "Candidate skills:\n"
        f"{json.dumps(candidates, ensure_ascii=False, indent=2)}\n\n"
        "完成后只需简短回复已完成。"
    )

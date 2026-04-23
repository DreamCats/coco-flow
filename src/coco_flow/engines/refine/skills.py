from __future__ import annotations

import json
from math import ceil
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.refine import (
    build_refine_skills_read_agent_prompt,
    build_refine_skills_read_template_markdown,
    build_refine_shortlist_agent_prompt,
    build_refine_shortlist_template_json,
)
from coco_flow.services.queries.skills import SkillPackage, SkillStore

from .models import EXECUTOR_NATIVE, KnowledgeCard, RefineIntent, RefinePreparedInput, RefineSkillsRead, RefineSkillsSelection

SHORTLIST_CHUNK_SIZE = 8
SHORTLIST_BATCH_MAX_CARDS = 30


def build_refine_query(prepared: RefinePreparedInput, intent: RefineIntent) -> dict[str, object]:
    return {
        "title": prepared.title,
        "goal": intent.goal,
        "terms": intent.terms[:8],
        "change_points": intent.change_points[:5],
        "risks_seed": intent.risks_seed[:4],
        "discussion_seed": intent.discussion_seed[:4],
        "boundary_seed": intent.boundary_seed[:4],
    }


def shortlist_refine_skills(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    settings: Settings,
    on_log,
) -> tuple[list[SkillPackage], RefineSkillsSelection]:
    skill_store = SkillStore(settings)
    candidates = skill_store.list_packages()
    on_log(f"skills_shortlist_source: skills ({len(candidates)})")
    if not candidates:
        on_log("skills_shortlist_mode: empty")
        selection = RefineSkillsSelection(
            selected_skill_ids=[],
            rejected_skill_ids=[],
            reason="no_skill_packages",
            candidates=[],
            mode="empty",
        )
        return [], selection
    return _shortlist_refine_skills(
        prepared=prepared,
        intent=intent,
        settings=settings,
        on_log=on_log,
        candidates=candidates,
    )


def read_selected_skills(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    selected_documents: list[SkillPackage],
    settings: Settings,
    on_log,
) -> RefineSkillsRead:
    if not selected_documents:
        return RefineSkillsRead(markdown="", selected_skill_ids=[], selected_skill_titles=[])
    return _read_selected_skills(
        prepared=prepared,
        intent=intent,
        selected_skills=selected_documents,
        settings=settings,
        on_log=on_log,
    )


def _shortlist_refine_skills(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    settings: Settings,
    on_log,
    candidates: list[SkillPackage],
) -> tuple[list[SkillPackage], RefineSkillsSelection]:
    cards = [_skill_to_card(skill) for skill in candidates]
    scored_cards = _score_cards(cards, candidates, prepared, intent)
    on_log(f"skills_shortlist_card_count: {len(cards)}")
    if settings.refine_executor.strip().lower() != EXECUTOR_NATIVE:
        on_log("skills_shortlist_mode: rule")
        selection = _rule_select(cards, scored_cards)
        selected_skills = _selected_documents(candidates, selection.selected_skill_ids)
        return selected_skills, selection

    selection = _native_select(cards, candidates, scored_cards, prepared, intent, settings, on_log)
    selected_skills = _selected_documents(candidates, selection.selected_skill_ids)
    return selected_skills, selection


def _rule_select(cards: list[KnowledgeCard], scored_cards: list[tuple[int, KnowledgeCard]]) -> RefineSkillsSelection:
    selected_cards = [card for score, card in scored_cards if score > 0][:4]
    rejected_ids = [card.id for card in cards if card.id not in {item.id for item in selected_cards}]
    reason = "rule_scored_from_frontmatter"
    return RefineSkillsSelection(
        selected_skill_ids=[card.id for card in selected_cards],
        rejected_skill_ids=rejected_ids,
        reason=reason,
        candidates=[{"score": score, **card.to_payload()} for score, card in scored_cards],
        mode="rule",
    )


def _native_select(
    cards: list[KnowledgeCard],
    documents: list[SkillPackage],
    scored_cards: list[tuple[int, KnowledgeCard]],
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    settings: Settings,
    on_log,
) -> RefineSkillsSelection:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    if len(cards) <= SHORTLIST_BATCH_MAX_CARDS:
        try:
            on_log("skills_shortlist_mode: llm_batch")
            return _native_select_batch(cards, scored_cards, prepared, intent, settings, client, on_log)
        except ValueError as error:
            on_log(f"skills_shortlist_batch_fallback: {error}")
    on_log("skills_shortlist_mode: llm_chunked")
    return _native_select_chunked(cards, scored_cards, prepared, intent, settings, client, on_log)


def _native_select_batch(
    cards: list[KnowledgeCard],
    scored_cards: list[tuple[int, KnowledgeCard]],
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    settings: Settings,
    client: CocoACPClient,
    on_log,
) -> RefineSkillsSelection:
    template_path = _write_shortlist_template(prepared.task_dir)
    try:
        client.run_agent(
            build_refine_shortlist_agent_prompt(
                intent_payload=intent.to_payload(),
                knowledge_cards=_build_compact_card_payloads(cards, scored_cards),
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        if "__FILL__" in raw:
            raise ValueError("shortlist_template_unfilled")
        payload = _parse_shortlist_output(raw, cards)
        return _finalize_selection(
            selected_ids=payload["selected_skill_ids"],
            cards=cards,
            scored_cards=scored_cards,
            prepared=prepared,
            intent=intent,
            reason=str(payload["reason"] or "").strip() or "llm_batch_shortlist_from_frontmatter",
            mode="llm_batch",
            on_log=on_log,
        )
    finally:
        if template_path.exists():
            template_path.unlink()


def _native_select_chunked(
    cards: list[KnowledgeCard],
    scored_cards: list[tuple[int, KnowledgeCard]],
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    settings: Settings,
    client: CocoACPClient,
    on_log,
) -> RefineSkillsSelection:
    selected_ids: list[str] = []
    reasons: list[str] = []
    total_chunks = ceil(len(cards) / SHORTLIST_CHUNK_SIZE)
    for index in range(total_chunks):
        chunk_cards = cards[index * SHORTLIST_CHUNK_SIZE : (index + 1) * SHORTLIST_CHUNK_SIZE]
        template_path = _write_shortlist_template(prepared.task_dir)
        try:
            reply = client.run_agent(
                build_refine_shortlist_agent_prompt(
                    intent_payload=intent.to_payload(),
                    knowledge_cards=_build_compact_card_payloads(chunk_cards, scored_cards),
                    template_path=str(template_path),
                ),
                settings.native_query_timeout,
                cwd=str(prepared.task_dir),
                fresh_session=True,
            )
            raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
            if "__FILL__" in raw:
                raise ValueError("shortlist_template_unfilled")
            payload = _parse_shortlist_output(raw, chunk_cards)
            selected_ids.extend(payload["selected_skill_ids"])
            if payload["reason"]:
                reasons.append(str(payload["reason"]))
            _ = reply
        except ValueError as error:
            on_log(f"skills_shortlist_chunk_fallback: chunk={index + 1}/{total_chunks} error={error}")
            for card in chunk_cards[:2]:
                if _card_score_lookup(scored_cards, card.id) > 0:
                    selected_ids.append(card.id)
        finally:
            if template_path.exists():
                template_path.unlink()
    return _finalize_selection(
        selected_ids=selected_ids,
        cards=cards,
        scored_cards=scored_cards,
        prepared=prepared,
        intent=intent,
        reason="; ".join(_ordered_unique(reasons)) or "llm_shortlist_from_frontmatter",
        mode="llm_chunked",
        on_log=on_log,
    )


def _score_cards(
    cards: list[KnowledgeCard],
    documents: list[SkillPackage],
    prepared: RefinePreparedInput,
    intent: RefineIntent,
) -> list[tuple[int, KnowledgeCard]]:
    score_map: dict[str, int] = {}
    query_terms = [prepared.title, intent.goal, *intent.terms, *intent.change_points, *intent.boundary_seed]
    lowered_terms = [item.lower() for item in query_terms if item.strip()]
    for card, document in zip(cards, documents, strict=False):
        haystack = " ".join([card.title, card.desc, card.domain_name, _document_summary_text(document)]).lower()
        score = 0
        for term in lowered_terms:
            if term and term in haystack:
                score += 3
        if card.priority == "high":
            score += 1
        if card.confidence == "high":
            score += 1
        score_map[card.id] = score
    scored = [(score_map[card.id], card) for card in cards]
    scored.sort(key=lambda item: (-item[0], item[1].kind, item[1].title))
    return scored


def _read_selected_skills(
    *,
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    selected_skills: list[SkillPackage],
    settings: Settings,
    on_log,
) -> RefineSkillsRead:
    if not selected_skills:
        return RefineSkillsRead(markdown="", selected_skill_ids=[], selected_skill_titles=[])

    if settings.refine_executor.strip().lower() != EXECUTOR_NATIVE:
        return _read_skills_locally(selected_skills)

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    prompt_documents = _skill_prompt_documents(selected_skills)
    template_path = _write_knowledge_read_template(prepared.task_dir)
    try:
        reply = client.run_agent(
            build_refine_skills_read_agent_prompt(
                intent_payload=intent.to_payload(),
                knowledge_documents=prompt_documents,
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        markdown = template_path.read_text(encoding="utf-8").strip() if template_path.exists() else ""
        if _looks_like_unfilled_knowledge_read(markdown):
            raise ValueError("knowledge_read_template_unfilled")
        if not markdown:
            raise ValueError("empty_knowledge_read")
        on_log(f"skills_read_mode: agent ({len(prompt_documents)} docs)")
        _ = reply
        return RefineSkillsRead(
            markdown=markdown.rstrip() + "\n",
            selected_skill_ids=[skill.id for skill in selected_skills],
            selected_skill_titles=[skill.name for skill in selected_skills],
        )
    except ValueError as error:
        on_log(f"skills_read_fallback: {error}")
        return _read_skills_locally(selected_skills)
    finally:
        if template_path.exists():
            template_path.unlink()


def _read_skills_locally(selected_skills: list[SkillPackage]) -> RefineSkillsRead:
    lines = ["# Refine Skills Read", ""]
    for skill in selected_skills:
        lines.extend(
            [
                f"## {skill.name}",
                "",
                f"- id: {skill.id}",
                "- kind: skill",
                f"- domain: {skill.domain or 'unknown'}",
                f"- desc: {skill.description or '无'}",
                "",
                _extract_relevant_excerpt(_skill_combined_body(skill)),
                "",
            ]
        )
    return RefineSkillsRead(
        markdown="\n".join(lines).rstrip() + "\n",
        selected_skill_ids=[skill.id for skill in selected_skills],
        selected_skill_titles=[skill.name for skill in selected_skills],
    )


def _extract_relevant_excerpt(body: str) -> str:
    sections = _split_markdown_sections(body)
    for title in ("Summary", "summary", "术语定义", "稳定规则", "风险", "Dependencies"):
        if title in sections and sections[title].strip():
            return sections[title].strip()
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return "\n".join(lines[:8]) if lines else "- 无正文。"


def _split_markdown_sections(content: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = ""
    current_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(current_lines).strip()
            current = line.removeprefix("## ").strip()
            current_lines = []
            continue
        if current:
            current_lines.append(line)
    if current:
        sections[current] = "\n".join(current_lines).strip()
    return sections


def _write_shortlist_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".refine-shortlist-",
        suffix=".json",
        delete=False,
    ) as handle:
        handle.write(build_refine_shortlist_template_json())
        handle.flush()
        return Path(handle.name)


def _write_knowledge_read_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".refine-skills-read-",
        suffix=".md",
        delete=False,
    ) as handle:
        handle.write(build_refine_skills_read_template_markdown())
        handle.flush()
        return Path(handle.name)


def _looks_like_unfilled_knowledge_read(markdown: str) -> bool:
    return "待补充" in markdown


def _parse_shortlist_output(raw: str, cards: list[KnowledgeCard]) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid_shortlist_json: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("shortlist_output_is_not_object")
    if _payload_has_fill_marker(payload):
        raise ValueError("shortlist_output_contains_fill_marker")
    valid_ids = {card.id for card in cards}
    raw_selected = payload.get("selected_skill_ids")
    if not isinstance(raw_selected, list):
        raw_selected = payload.get("selected_ids", [])
    raw_rejected = payload.get("rejected_skill_ids")
    if not isinstance(raw_rejected, list):
        raw_rejected = payload.get("rejected_ids", [])
    selected_ids = [item for item in [str(item).strip() for item in raw_selected] if item in valid_ids]
    rejected_ids = [item for item in [str(item).strip() for item in raw_rejected] if item in valid_ids]
    return {
        "selected_skill_ids": _ordered_unique(selected_ids),
        "rejected_skill_ids": _ordered_unique(rejected_ids),
        "reason": str(payload.get("reason") or "").strip(),
    }


def _payload_has_fill_marker(value: object) -> bool:
    if isinstance(value, str):
        return "__FILL__" in value
    if isinstance(value, list):
        return any(_payload_has_fill_marker(item) for item in value)
    if isinstance(value, dict):
        return any(_payload_has_fill_marker(item) for item in value.values())
    return False


def _selected_documents(documents: list[SkillPackage], selected_ids: list[str]) -> list[SkillPackage]:
    selected_set = set(selected_ids)
    ordered = [document for document in documents if document.id in selected_set]
    ordered.sort(key=lambda item: selected_ids.index(item.id))
    return ordered


def _card_score_lookup(scored_cards: list[tuple[int, KnowledgeCard]], card_id: str) -> int:
    for score, card in scored_cards:
        if card.id == card_id:
            return score
    return 0


def _guard_selected_ids(
    selected_ids: list[str],
    cards: list[KnowledgeCard],
    scored_cards: list[tuple[int, KnowledgeCard]],
    prepared: RefinePreparedInput,
    intent: RefineIntent,
) -> tuple[list[str], list[str]]:
    if not selected_ids:
        return [], []
    query_terms = _selection_query_terms(prepared, intent)
    kept: list[str] = []
    rejected: list[str] = []
    card_by_id = {card.id: card for card in cards}
    for card_id in selected_ids:
        card = card_by_id.get(card_id)
        if card is None:
            continue
        score = _card_score_lookup(scored_cards, card_id)
        if score >= 3 and _card_has_term_overlap(card, query_terms):
            kept.append(card_id)
            continue
        rejected.append(card_id)
    return kept, rejected


def _selection_query_terms(prepared: RefinePreparedInput, intent: RefineIntent) -> list[str]:
    terms = [
        prepared.title,
        intent.goal,
        *intent.terms,
        *intent.change_points,
        *intent.boundary_seed,
    ]
    normalized: list[str] = []
    for term in terms:
        current = str(term).strip().lower()
        if len(current) < 2:
            continue
        normalized.append(current)
    return _ordered_unique(normalized)


def _card_has_term_overlap(card: KnowledgeCard, query_terms: list[str]) -> bool:
    haystack = " ".join([card.title, card.desc, card.domain_name]).lower()
    return any(term in haystack for term in query_terms if term and term not in {"需求", "功能", "问题"})


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _build_compact_card_payloads(
    cards: list[KnowledgeCard],
    scored_cards: list[tuple[int, KnowledgeCard]],
) -> list[dict[str, object]]:
    allowed_ids = {card.id for card in cards}
    return [
        {
            "id": card.id,
            "title": card.title,
            "kind": card.kind,
            "domain_name": card.domain_name,
            "summary": _compact_summary(card),
            "priority": card.priority,
            "confidence": card.confidence,
            "heuristic_score": score,
        }
        for score, card in scored_cards
        if card.id in allowed_ids
    ]


def _compact_summary(card: KnowledgeCard, limit: int = 120) -> str:
    parts = [str(item).strip() for item in [card.desc, card.domain_name] if str(item).strip()]
    summary = " | ".join(parts) or card.title
    if len(summary) <= limit:
        return summary
    return summary[: limit - 3].rstrip() + "..."


def _finalize_selection(
    *,
    selected_ids: list[str],
    cards: list[KnowledgeCard],
    scored_cards: list[tuple[int, KnowledgeCard]],
    prepared: RefinePreparedInput,
    intent: RefineIntent,
    reason: str,
    mode: str,
    on_log,
) -> RefineSkillsSelection:
    normalized_ids = _ordered_unique(selected_ids)[:4]
    guarded_ids, guard_rejections = _guard_selected_ids(normalized_ids, cards, scored_cards, prepared, intent)
    if guard_rejections:
        on_log(f"skills_guard_rejected_ids: {', '.join(guard_rejections)}")
    if not guarded_ids:
        return RefineSkillsSelection(
            selected_skill_ids=[],
            rejected_skill_ids=[card.id for card in cards],
            reason=reason or "llm_shortlist_empty",
            candidates=[{"score": score, **card.to_payload()} for score, card in scored_cards],
            mode="llm_empty" if mode.startswith("llm") else mode,
        )
    rejected_ids = [card.id for card in cards if card.id not in set(guarded_ids)]
    if guard_rejections:
        rejected_ids = _ordered_unique(rejected_ids + guard_rejections)
    return RefineSkillsSelection(
        selected_skill_ids=guarded_ids,
        rejected_skill_ids=rejected_ids,
        reason=reason,
        candidates=[{"score": score, **card.to_payload()} for score, card in scored_cards],
        mode=mode,
    )


def _skill_to_card(skill: SkillPackage) -> KnowledgeCard:
    return KnowledgeCard(
        id=skill.id,
        title=skill.name,
        desc=skill.description,
        kind="skill",
        domain_name=skill.domain.replace("_", " "),
        priority="high",
        confidence="high",
    )


def _document_summary_text(document: SkillPackage) -> str:
    return _skill_combined_body(document)[:600]


def _skill_combined_body(skill: SkillPackage) -> str:
    sections: list[str] = []
    if skill.body.strip():
        sections.append(skill.body.strip())
    for path in skill.reference_paths:
        content = path.read_text(encoding="utf-8").strip()
        if content:
            sections.append(content)
    return "\n\n".join(sections)


def _skill_prompt_documents(selected_skills: list[SkillPackage]) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    for skill in selected_skills:
        documents.append(
            {
                "id": skill.id,
                "title": f"{skill.name} / SKILL.md",
                "kind": "skill",
                "desc": skill.description or "无",
                "path": str(skill.skill_path),
            }
        )
        for path in skill.reference_paths:
            documents.append(
                {
                    "id": f"{skill.id}:{path.stem}",
                    "title": f"{skill.name} / {path.relative_to(skill.root_path)}",
                    "kind": "reference",
                    "desc": skill.domain or "无",
                    "path": str(path),
                }
            )
    return documents

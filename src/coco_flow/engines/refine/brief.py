from __future__ import annotations

import re

from coco_flow.engines.shared.manual_extract import parse_manual_extract_sections

from .models import ManualExtract, RefineBrief, RefinePreparedInput

_LIST_MARKER_RE = re.compile(r"^(?P<indent>\s*)(?:[-*+]\s+|\d+\.\s+|\[\s?[xX]?\s?\]\s*)")
_OPEN_QUESTION_HINTS = ("待确认", "确认", "是否", "?", "？", "待补充", "需补充")
_EDGE_CASE_HINTS = ("有人出价", "无人出价", "竞拍结束", "延时文案", "回退", "兼容", "缺失", "默认", "不变")
_PLACEHOLDER_HINTS = ("如无可写", "请写这里", "[必填]", "待补充")
_SOURCE_SKIP_HINTS = ("http", "Figma", "Legal", "Starling", "Must Have", "[图片", "[附件", "Traffic Allocation", "| **")


def parse_manual_extract(supplement: str) -> ManualExtract:
    # 这一步只做“把人工输入模板恢复成结构化字段”，不尝试从原始 PRD 猜主轴。
    sections = parse_manual_extract_sections(supplement)
    scope = _normalize_simple_entries(sections.get("本次范围", ""))
    change_points, extracted_gating = _parse_change_points(sections.get("人工提炼改动点", ""))
    out_of_scope = _normalize_simple_entries(sections.get("明确不做", ""))
    notes = _normalize_simple_entries(sections.get("前置条件 / 待确认项", ""))
    gating_conditions = _unique([*extracted_gating, *[item for item in notes if not _looks_like_open_question(item)]])
    open_questions = [item for item in notes if _looks_like_open_question(item)]
    return ManualExtract(
        scope=scope,
        change_points=change_points,
        out_of_scope=out_of_scope,
        notes=notes,
        gating_conditions=gating_conditions,
        open_questions=open_questions,
        raw_sections=sections,
    )


def build_refine_brief(prepared: RefinePreparedInput, manual_extract: ManualExtract) -> RefineBrief:
    # brief 是 refine 的单一事实源：后续 markdown 渲染、native agent 润色、verify 都围绕它展开。
    target_surface = _infer_target_surface(prepared, manual_extract)
    goal = _derive_goal(prepared, manual_extract)
    in_scope = manual_extract.change_points[:12]
    out_of_scope = manual_extract.out_of_scope[:8] or ["不扩大到人工提炼范围之外的 UI、动效、交互或相邻系统改动。"]
    gating_conditions = manual_extract.gating_conditions[:6]
    edge_cases = _derive_edge_cases(prepared, manual_extract)
    open_questions = _unique([*manual_extract.open_questions, *_derive_open_questions(prepared, manual_extract)])[:8]
    acceptance_criteria = _derive_acceptance_criteria(in_scope, gating_conditions, out_of_scope)
    return RefineBrief(
        target_surface=target_surface,
        goal=goal,
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        gating_conditions=gating_conditions,
        acceptance_criteria=acceptance_criteria,
        edge_cases=edge_cases,
        open_questions=open_questions,
    )


def build_source_excerpt(prepared: RefinePreparedInput, brief: RefineBrief) -> str:
    # excerpt 只给 agent 提供“与人工提炼范围相邻”的原文片段，避免再次被整份 PRD 带偏。
    keywords = _keyword_terms([*brief.in_scope, *brief.gating_conditions, brief.goal])
    lines: list[str] = []
    for raw_line in prepared.source_content.splitlines():
        line = raw_line.strip()
        if not _source_line_is_relevant(line, keywords):
            continue
        lines.append(line[:180])
    if not lines:
        return "# Refine Source Excerpt\n\n- 当前没有筛出额外相关原文片段。\n"
    body = "\n".join(f"- {line}" for line in _unique(lines)[:12])
    return f"# Refine Source Excerpt\n\n{body}\n"


def build_compat_intent_payload(prepared: RefinePreparedInput, brief: RefineBrief) -> dict[str, object]:
    return {
        "goal": brief.goal,
        "change_points": brief.in_scope,
        "acceptance_criteria": brief.acceptance_criteria,
        "terms": _extract_terms([prepared.title, *brief.in_scope, *brief.out_of_scope, *brief.gating_conditions]),
        "risks_seed": brief.edge_cases,
        "discussion_seed": brief.open_questions,
        "boundary_seed": brief.out_of_scope,
        "mode": "manual_first",
    }


def merge_brief_with_refined_markdown(brief: RefineBrief, refined_markdown: str) -> RefineBrief:
    refined_in_scope = _extract_bullet_section(refined_markdown, "具体变更点")
    refined_acceptance = _extract_bullet_section(refined_markdown, "验收标准")
    refined_boundaries = _extract_bullet_section(refined_markdown, "边界与非目标")
    refined_questions = _extract_bullet_section(refined_markdown, "待确认项")
    return RefineBrief(
        target_surface=brief.target_surface,
        goal=brief.goal,
        in_scope=_unique(refined_in_scope or brief.in_scope),
        out_of_scope=_unique(refined_boundaries or brief.out_of_scope),
        gating_conditions=brief.gating_conditions,
        acceptance_criteria=_unique(refined_acceptance or brief.acceptance_criteria),
        edge_cases=brief.edge_cases,
        open_questions=_unique(refined_questions),
    )


def _derive_goal(prepared: RefinePreparedInput, manual_extract: ManualExtract) -> str:
    if manual_extract.scope:
        return manual_extract.scope[0]
    if manual_extract.change_points:
        return f"围绕 {prepared.title} 收敛服务端需要落地的改动点。"
    return prepared.title


def _infer_target_surface(prepared: RefinePreparedInput, manual_extract: ManualExtract) -> str:
    haystack = " ".join([prepared.title, prepared.supplement, *manual_extract.change_points]).lower()
    if any(keyword in haystack for keyword in ("前端", "frontend", "ui", "交互", "样式", "动效")):
        return "frontend"
    return "backend"


def _derive_acceptance_criteria(in_scope: list[str], gating_conditions: list[str], out_of_scope: list[str]) -> list[str]:
    criteria: list[str] = []
    for item in in_scope[:8]:
        if gating_conditions:
            criteria.append(f"当{gating_conditions[0]}时，{item}正确生效。")
        else:
            criteria.append(f"{item}正确生效。")
    return _unique(criteria)[:10]


def _derive_edge_cases(prepared: RefinePreparedInput, manual_extract: ManualExtract) -> list[str]:
    keywords = _keyword_terms([*manual_extract.change_points, *manual_extract.gating_conditions])
    extracted: list[str] = []
    for raw_line in prepared.source_content.splitlines():
        line = raw_line.strip()
        if not line or any(hint in line for hint in _SOURCE_SKIP_HINTS):
            continue
        if not any(hint in line for hint in _EDGE_CASE_HINTS):
            continue
        if not _shares_keywords(line, keywords):
            continue
        extracted.append(line[:160])
    if extracted:
        return _unique(extracted)[:5]
    return ["未在人工提炼范围中点名的状态与链路默认不改，若需调整应回到 Input 阶段补充。"]


def _derive_open_questions(prepared: RefinePreparedInput, manual_extract: ManualExtract) -> list[str]:
    if manual_extract.open_questions:
        return []
    keywords = _keyword_terms([*manual_extract.change_points, *manual_extract.gating_conditions])
    extracted: list[str] = []
    for raw_line in prepared.source_content.splitlines():
        line = raw_line.strip()
        if not line or any(hint in line for hint in _SOURCE_SKIP_HINTS):
            continue
        if not _looks_like_open_question(line):
            continue
        if not _shares_keywords(line, keywords):
            continue
        extracted.append(line[:160])
    return _unique(extracted)[:5]


def _parse_change_points(body: str) -> tuple[list[str], list[str]]:
    entries: list[str] = []
    gating_conditions: list[str] = []
    headings: list[tuple[int, str]] = []
    for raw_line in body.splitlines():
        if not raw_line.strip():
            continue
        current = _clean_entry(raw_line)
        if not current:
            continue
        matched = _LIST_MARKER_RE.match(raw_line)
        if matched is None:
            if _looks_like_gating(current):
                gating_conditions.append(_normalize_gating(current))
            continue
        indent = len(matched.group("indent"))
        while headings and headings[-1][0] >= indent:
            headings.pop()
        if _is_heading_entry(current):
            headings.append((indent, current.rstrip(":：")))
            continue
        parents = [title for level, title in headings if level < indent or level == 0]
        combined = " / ".join([*parents, current])
        entries.append(combined)
    return _unique(entries), _unique(gating_conditions)


def _normalize_simple_entries(body: str) -> list[str]:
    items: list[str] = []
    for raw_line in body.splitlines():
        current = _clean_entry(raw_line)
        if current:
            items.append(current)
    return _unique(items)


def _clean_entry(raw_line: str) -> str:
    current = _LIST_MARKER_RE.sub("", raw_line.strip())
    current = current.replace("[必填]", "", 1).strip()
    if not current or current.lower() in {"无", "暂无"}:
        return ""
    if any(hint in current for hint in _PLACEHOLDER_HINTS):
        return ""
    return current[:180]


def _is_heading_entry(text: str) -> bool:
    if text.endswith(("：", ":")) and " + " not in text:
        return True
    if " / " in text and "：" not in text and ":" not in text:
        return True
    if text.lower() in {"surprise set", "temporary listing"}:
        return True
    return False


def _looks_like_gating(text: str) -> bool:
    lowered = text.lower()
    return "实验" in text or "命中" in text or "gate" in lowered or "bucket" in lowered or "variant" in lowered


def _normalize_gating(text: str) -> str:
    normalized = text.strip().rstrip(":：。")
    normalized = re.sub(r"[，,\s]*会改动以下$", "", normalized)
    return normalized.strip()


def _looks_like_open_question(text: str) -> bool:
    return any(hint in text for hint in _OPEN_QUESTION_HINTS)


def _source_line_is_relevant(line: str, keywords: set[str]) -> bool:
    if not line or any(hint in line for hint in _SOURCE_SKIP_HINTS):
        return False
    if len(line) < 4:
        return False
    return _shares_keywords(line, keywords)


def _shares_keywords(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords if len(keyword) >= 2)


def _keyword_terms(chunks: list[str]) -> set[str]:
    return {term.lower() for term in _extract_terms(chunks)}


def _extract_terms(chunks: list[str]) -> list[str]:
    terms: list[str] = []
    for chunk in chunks:
        for raw in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,12}", chunk):
            current = raw.strip()
            if len(current) < 2:
                continue
            terms.append(current)
    return _unique(terms)[:20]


def _extract_bullet_section(markdown: str, title: str) -> list[str]:
    pattern = rf"(?ms)^## {re.escape(title)}\n(.*?)(?=^## |\Z)"
    matched = re.search(pattern, markdown)
    if not matched:
        return []
    items: list[str] = []
    for raw_line in matched.group(1).splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        current = line[2:].strip()
        if not current or current in {"无", "当前无额外待确认项。"}:
            continue
        items.append(current)
    return _unique(items)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered

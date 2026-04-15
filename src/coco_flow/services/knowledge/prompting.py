from __future__ import annotations

import json

from .common import _as_string_list, extract_json_object, unique_strings


def build_term_mapping_prompt(intent_payload: dict[str, object], repo_candidates: list[dict[str, object]]) -> str:
    payload = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "query_terms": intent_payload["query_terms"],
        "repo_candidates": repo_candidates,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Term Mapping。\n"
        "目标：把用户语言映射成 repo 里的真实术语，供后续 discovery/research 使用。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 mapped_terms, search_terms, open_questions 三个字段。\n"
        "3. mapped_terms 中每个对象必须包含 user_term, repo_terms, repo_ids, confidence, reason。\n"
        "4. repo_terms 只允许使用输入里出现过的目录名、文件名、路由片段、符号名或 commit 关键词。\n"
        "5. search_terms 是给 discovery 用的最终检索词，优先放最有辨识度的 repo 术语。\n"
        "6. confidence 只能是 high、medium、low。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- 优先把业务词映射到 repo 内高信号符号，例如 route/path、enum、常量、handler、service、rpc 名。\n"
        "- 如果多个 repo 都有候选词，优先保留最贴近当前意图的 2~4 个 repo 术语。\n"
        "- 不要只重复用户原词；尽量补充 repo 内真实写法，例如 CamelCase、snake_case、目录名。\n"
        "- 不要优先选择 commit 里出现的改造词、rebuild 词；只有它被路径或符号再次印证时才可使用。\n"
        "- 如果证据不足，把问题写进 open_questions，不要硬凑映射。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- repo_terms、repo_ids 和路径保持原样。\n"
        "- reason 简短明确，说明为什么认为这些词相关。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"mapped_terms":[{"user_term":"达人秒杀","repo_terms":["ExclusiveFlashSale","CreatorPromotion","flash_sale"],'
        '"repo_ids":["live-promotion-api","live-promotion-core"],"confidence":"high",'
        '"reason":"repo 中同时出现 flash_sale 路由、CreatorPromotion 服务和 ExclusiveFlashSale 枚举"}],'
        '"search_terms":["达人秒杀","ExclusiveFlashSale","CreatorPromotion","flash_sale"],'
        '"open_questions":["是否还存在 seller 侧的秒杀分支需要并行扫描"]}\n'
        "</example_output>\n"
    )


def extract_term_mapping_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native term mapping did not return a JSON object")
    mapped_terms_raw = payload.get("mapped_terms")
    if not isinstance(mapped_terms_raw, list):
        raise ValueError("native term mapping did not return mapped_terms list")
    mapped_terms: list[dict[str, object]] = []
    search_terms: list[str] = []
    for item in mapped_terms_raw:
        if not isinstance(item, dict):
            continue
        user_term = str(item.get("user_term") or "").strip()
        repo_terms = _as_string_list(item.get("repo_terms"))[:8]
        repo_ids = _as_string_list(item.get("repo_ids"))[:6]
        confidence = str(item.get("confidence") or "low").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        reason = str(item.get("reason") or "").strip()
        if not user_term or not repo_terms:
            continue
        mapped_terms.append(
            {
                "user_term": user_term,
                "repo_terms": repo_terms,
                "repo_ids": repo_ids,
                "confidence": confidence,
                "reason": reason,
            }
        )
        search_terms.extend(repo_terms)
    search_terms.extend(_as_string_list(payload.get("search_terms")))
    open_questions = _as_string_list(payload.get("open_questions"))[:6]
    if not mapped_terms and not search_terms:
        raise ValueError("native term mapping returned empty structured content")
    return {"mapped_terms": mapped_terms, "search_terms": unique_strings(search_terms), "open_questions": open_questions}


def build_anchor_selection_prompt(intent_payload: dict[str, object], discovery: dict[str, object]) -> str:
    payload = {
        "normalized_intent": intent_payload["normalized_intent"],
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "repo_id": discovery["repo_id"],
        "candidate_dirs": discovery["candidate_dirs"],
        "candidate_files": discovery["candidate_files"],
        "route_hits": discovery.get("route_hits", []),
        "symbol_hits": discovery.get("symbol_hits", []),
        "commit_hits": discovery.get("commit_hits", []),
        "matched_keywords": discovery.get("matched_keywords", []),
        "commit_keywords": discovery.get("commit_keywords", []),
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Anchor Selection。\n"
        "目标：从单个 repo 的广召回候选里筛出最能代表业务主链路的锚点。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 strongest_terms, entry_files, business_symbols, route_signals, discarded_noise, reason, open_questions。\n"
        "3. strongest_terms 最多 8 条，entry_files 最多 4 条，business_symbols 最多 6 条，route_signals 最多 4 条，discarded_noise 最多 6 条。\n"
        "4. 只能从输入候选里选择，不要编造不存在的文件、路由或符号。\n"
        "5. 要主动区分主锚点和噪音词，显式把噪音放进 discarded_noise。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- route/path、handler、service、rpc、enum、常量优先级最高。\n"
        "- commit 改造词、rebuild、pack、flow_task、middleware 一般视作噪音，除非被 route/file/symbol 再次印证。\n"
        "- 入口文件优先选择真正承接动作的 handler/service/router 文件，不要优先选 spec、archive 或泛文档。\n"
        "- strongest_terms 优先保留业务类型词和核心动作词，例如枚举、领域对象、主接口名。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- 文件路径、路由、符号名保持原样。\n"
        "- reason 要说明为什么这些是主锚点、为什么某些候选被丢弃。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"strongest_terms":["ExclusiveFlashSale","CreatorPromotion","flash_sale"],'
        '"entry_files":["biz/router/live_serv/oec_live_promotion_api.go","biz/service/flash_sale/create_promotion.go"],'
        '"business_symbols":["CreatorPromotionType_ExclusiveFlashSale","PromotionType_ExclusiveFlashSale"],'
        '"route_signals":["biz/router/live_serv/oec_live_promotion_api.go#/flash_sale"],'
        '"discarded_noise":["flash_sale_rebuild","flow_task","pack链路"],'
        '"reason":"route、service 和业务枚举直接描述达人秒杀主链路，rebuild/flow_task/pack 更像改造背景或实现细节。",'
        '"open_questions":["启动动作对应的具体 API 子路径是什么"]}\n'
        "</example_output>\n"
    )


def extract_anchor_selection_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native anchor selection did not return a JSON object")
    strongest_terms = _as_string_list(payload.get("strongest_terms"))[:8]
    entry_files = _as_string_list(payload.get("entry_files"))[:4]
    business_symbols = _as_string_list(payload.get("business_symbols"))[:6]
    route_signals = _as_string_list(payload.get("route_signals"))[:4]
    discarded_noise = _as_string_list(payload.get("discarded_noise"))[:6]
    reason = str(payload.get("reason") or "").strip()
    open_questions = _as_string_list(payload.get("open_questions"))[:6]
    if not any([strongest_terms, entry_files, business_symbols, route_signals]):
        raise ValueError("native anchor selection returned empty structured content")
    return {
        "strongest_terms": strongest_terms,
        "entry_files": entry_files,
        "business_symbols": business_symbols,
        "route_signals": route_signals,
        "discarded_noise": discarded_noise,
        "reason": reason,
        "open_questions": open_questions,
    }


def build_repo_research_prompt(intent_payload: dict[str, object], discovery: dict[str, object], anchor_selection: dict[str, object]) -> str:
    discovery_payload = {
        "repo_id": discovery["repo_id"],
        "repo_path": discovery["repo_path"],
        "requested_path": discovery["requested_path"],
        "agents_present": discovery["agents_present"],
        "context_present": discovery["context_present"],
        "candidate_dirs": discovery["candidate_dirs"],
        "candidate_files": discovery["candidate_files"],
        "route_hits": discovery.get("route_hits", []),
        "symbol_hits": discovery.get("symbol_hits", []),
        "commit_hits": discovery.get("commit_hits", []),
        "matched_keywords": discovery["matched_keywords"],
        "context_hits": discovery["context_hits"],
    }
    anchor_payload = {
        "strongest_terms": anchor_selection.get("strongest_terms", []),
        "entry_files": anchor_selection.get("entry_files", []),
        "business_symbols": anchor_selection.get("business_symbols", []),
        "route_signals": anchor_selection.get("route_signals", []),
        "discarded_noise": anchor_selection.get("discarded_noise", []),
        "reason": anchor_selection.get("reason", ""),
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 repo research。\n"
        "目标：针对单个 repo，基于给定 discovery 结果，归纳它在当前需求中的角色。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 输出必须是一个可解析 JSON object，不要输出 markdown，不要输出解释，不要包 code fence。\n"
        "2. 必须严格包含这些字段：role, likely_modules, risks, facts, inferences, open_questions。\n"
        "3. role 只能是 primary、supporting、unknown 之一。\n"
        "4. facts 只能写输入里可直接观察到的事实；inferences 才能写推断。\n"
        "5. likely_modules 最多 6 条；risks/facts/inferences/open_questions 各最多 5 条。\n"
        "6. 不要复述 schema 说明，不要输出空洞话术，不要写“需要进一步分析”这类没有信息增量的句子。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- anchor_selection 里的 strongest_terms、entry_files、business_symbols 应视作主判断依据。\n"
        "- candidate_files、route_hits、symbol_hits、candidate_dirs、context_hits 越集中，越倾向 primary。\n"
        "- route/path、handler、service、rpc、enum 比 middleware、flow、pack、commit 改造词更能代表主链路。\n"
        "- 如果 repo 只命中少量外围目录且缺少高信号文件，可判为 supporting。\n"
        "- 优先引用输入里的真实路径和术语，避免泛化成抽象模块名。\n"
        "- 如果证据不足，明确写进 risks 或 open_questions，而不是把推断写成事实。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- 路径、repo_id、关键词保持原样。\n"
        "- 每条尽量简短、具体、可核对。\n"
        "</style>\n\n"
        "<intent>\n"
        f"{json.dumps({'normalized_intent': intent_payload['normalized_intent'], 'domain_candidate': intent_payload['domain_candidate'], 'notes': intent_payload['notes'] or '无'}, ensure_ascii=False, indent=2)}\n"
        "</intent>\n\n"
        "<repo_discovery>\n"
        f"{json.dumps(discovery_payload, ensure_ascii=False, indent=2)}\n"
        "</repo_discovery>\n\n"
        "<anchor_selection>\n"
        f"{json.dumps(anchor_payload, ensure_ascii=False, indent=2)}\n"
        "</anchor_selection>\n\n"
        "<example_output>\n"
        '{"role":"primary","likely_modules":["app/foo","service/bar"],'
        '"risks":["当前上下游边界仍需人工确认"],'
        '"facts":["candidate_files 命中 app/foo/handler.go"],'
        '"inferences":["该 repo 更可能承接主入口"],'
        '"open_questions":["是否还有未扫描的上游网关"]}\n'
        "</example_output>\n"
    )


def extract_repo_research_output(raw: str) -> dict[str, list[str] | str]:
    parsed = extract_json_object(raw, "native repo research did not return a JSON object")
    role = str(parsed.get("role") or "unknown").strip().lower()
    if role not in {"primary", "supporting", "unknown"}:
        role = "unknown"
    result = {
        "role": role,
        "likely_modules": _as_string_list(parsed.get("likely_modules"))[:6],
        "risks": _as_string_list(parsed.get("risks"))[:5],
        "facts": _as_string_list(parsed.get("facts"))[:5],
        "inferences": _as_string_list(parsed.get("inferences"))[:5],
        "open_questions": _as_string_list(parsed.get("open_questions"))[:5],
    }
    if not any(result[key] for key in ("likely_modules", "risks", "facts", "inferences", "open_questions")):
        raise ValueError("native repo research returned empty structured content")
    return result


def build_knowledge_synthesis_prompt(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    anchor_selection_payloads: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
    display_paths: list[str],
    requested_kinds: list[str],
) -> str:
    synthesis_input = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "domain_candidate": intent_payload["domain_candidate"],
        "domain_name": intent_payload["domain_name"],
        "requested_kinds": requested_kinds,
        "selected_paths": display_paths,
        "notes": intent_payload["notes"],
        "term_mapping": {
            "mapped_terms": term_mapping_payload.get("mapped_terms", []),
            "search_terms": term_mapping_payload.get("search_terms", []),
        },
        "anchor_selection": anchor_selection_payloads,
        "repo_anchors": [
            {"repo_id": item["repo_id"], "anchors": item.get("anchors", {}), "route_hits": item.get("route_hits", [])}
            for item in repo_research_payloads
        ],
        "repo_research": repo_research_payloads,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Knowledge Synthesis。\n"
        "目标：根据结构化 repo research，生成 flow/domain/rule 草稿正文。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown 解释，不要包 code fence。\n"
        '2. JSON 结构必须是 {"documents": [...]}。\n'
        "3. 每个 document 必须包含 kind, title, desc, body, open_questions。\n"
        "4. flow 的 body 必须包含：## Summary, ## Main Flow, ## Selected Paths, ## Dependencies, ## Repo Hints, ## Open Questions。\n"
        "5. domain 的 body 必须包含：## Summary, ## Repo Coverage, ## Open Questions。\n"
        "6. rule 的 body 必须包含：## Statement, ## Evidence Risks, ## Open Questions。\n"
        "7. open_questions 要与 body 里的 Open Questions 对齐。\n"
        "8. 不要输出空泛模板话术；要优先利用 repo research 里的 role、likely_modules、facts、risks、open_questions。\n"
        "</success_criteria>\n\n"
        "<grounding_rules>\n"
        "- 只能使用输入里已有的 repo_id、路径、模块线索、事实和风险。\n"
        "- 优先以 repo_anchors 里的 entry_files、business_symbols、route_hits 为主线，不要把实现细节模块当成主入口。\n"
        "- 如果证据弱，可以明确写“当前仅基于候选目录/文件推断”，但不要编造不存在的系统、接口或文件。\n"
        "- 优先写“这条链路如何经过这些 repo / 模块”，而不是重复意图描述。\n"
        "- 语言保持中文，代码路径和 repo_id 保持原样。\n"
        "- 避免使用“第一阶段草稿”“待补充”等程序味很重的话术，除非输入证据确实不足。\n"
        "</grounding_rules>\n\n"
        "<style>\n"
        "- Summary 用 2~4 句，直接说明链路或规则的核心。\n"
        "- Main Flow 用 3~6 条编号步骤，尽量写出 repo 角色或模块动作。\n"
        "- Dependencies / Repo Coverage / Evidence Risks 尽量引用具体 repo 和模块线索。\n"
        "- Open Questions 只保留真正未确认的问题，不要重复 Summary。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(synthesis_input, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"documents":[{"kind":"flow","title":"系统链路","desc":"归纳某能力的主链路和 repo hints。",'
        '"body":"## Summary\\n\\n该链路由 `repo-a` 承接入口，由 `repo-b` 提供下游能力。\\n\\n## Main Flow\\n\\n1. ...\\n\\n## Selected Paths\\n\\n- `/path/a`\\n\\n## Dependencies\\n\\n- `repo-a`: role=primary\\n\\n## Repo Hints\\n\\n### `repo-a`\\n\\n- role: `primary`\\n\\n## Open Questions\\n\\n- 是否存在额外上游网关",'
        '"open_questions":["是否存在额外上游网关"]}]}\n'
        "</example_output>\n"
    )


def extract_knowledge_synthesis_output(raw: str, requested_kinds: list[str]) -> dict[str, dict[str, object]]:
    payload = extract_json_object(raw, "native knowledge synthesis did not return a JSON object")
    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise ValueError("native knowledge synthesis did not return documents list")
    outputs: dict[str, dict[str, object]] = {}
    for item in documents:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind not in requested_kinds:
            continue
        outputs[kind] = {
            "title": str(item.get("title") or "").strip(),
            "desc": str(item.get("desc") or "").strip(),
            "body": str(item.get("body") or "").strip(),
            "open_questions": _as_string_list(item.get("open_questions")),
        }
    missing = [kind for kind in requested_kinds if kind not in outputs]
    if missing:
        raise ValueError(f"native knowledge synthesis missing kinds: {', '.join(missing)}")
    return outputs

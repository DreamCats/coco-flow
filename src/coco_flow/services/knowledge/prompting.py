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


def build_candidate_ranking_prompt(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
) -> str:
    payload = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "repo_id": discovery["repo_id"],
        "candidate_dirs": discovery["candidate_dirs"],
        "candidate_files": discovery["candidate_files"],
        "route_hits": discovery.get("route_hits", []),
        "symbol_hits": discovery.get("symbol_hits", []),
        "commit_hits": discovery.get("commit_hits", []),
        "matched_keywords": discovery.get("matched_keywords", []),
        "context_hits": discovery.get("context_hits", []),
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Candidate Ranking。\n"
        "目标：从 discovery 候选池里筛出主候选、次候选和噪音，供后续 anchor selection / repo research 使用。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 primary_files, secondary_files, primary_dirs, preferred_symbols, preferred_routes, discarded_noise, reason, open_questions。\n"
        "3. 只能从输入中选择，不要编造不存在的文件、目录、路由或符号。\n"
        "4. primary_files 最多 6 条，secondary_files 最多 6 条，primary_dirs 最多 4 条，preferred_symbols 最多 6 条，preferred_routes 最多 4 条，discarded_noise 最多 8 条。\n"
        "5. 主候选必须优先体现业务动作入口；次候选才放旁支或补充线索。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- route/path、handler、service、rpc、enum、常量优先；commit 改造词和实现细节词降权。\n"
        "- 优先保留能直接承接用户动作的候选，例如 create/update/launch/delete/status 对应入口文件。\n"
        "- callback、cycle、loader、legacy、billboard 这类词不一定是噪音，但只有在强证据支撑时才保留为主候选。\n"
        "- 如果证据不足，放进 open_questions，不要硬选。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- 路径、路由、符号名保持原样。\n"
        "- reason 简短说明保留和丢弃逻辑。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"primary_files":["biz/router/live_serv/oec_live_promotion_api.go","biz/service/flash_sale/create_promotion.go"],'
        '"secondary_files":["biz/service/flash_sale/update_promotion_status.go"],'
        '"primary_dirs":["biz/router/live_serv","biz/service/flash_sale"],'
        '"preferred_symbols":["CreatorPromotionType_ExclusiveFlashSale","CreateSellerFlashSalePromotions"],'
        '"preferred_routes":["biz/router/live_serv/oec_live_promotion_api.go#/flash_sale"],'
        '"discarded_noise":["flash_sale_rebuild","callback_create_next_cycle_promotion.go","billboard_operate_service"],'
        '"reason":"router/service/业务枚举直接承接达人秒杀主链路，callback/cycle/billboard 更像旁支或补充链路。",'
        '"open_questions":["删除动作对应的具体 API 子路径是什么"]}\n'
        "</example_output>\n"
    )


def extract_candidate_ranking_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native candidate ranking did not return a JSON object")
    primary_files = _as_string_list(payload.get("primary_files"))[:6]
    secondary_files = _as_string_list(payload.get("secondary_files"))[:6]
    primary_dirs = _as_string_list(payload.get("primary_dirs"))[:4]
    preferred_symbols = _as_string_list(payload.get("preferred_symbols"))[:6]
    preferred_routes = _as_string_list(payload.get("preferred_routes"))[:4]
    discarded_noise = _as_string_list(payload.get("discarded_noise"))[:8]
    reason = str(payload.get("reason") or "").strip()
    open_questions = _as_string_list(payload.get("open_questions"))[:6]
    if not any([primary_files, primary_dirs, preferred_symbols, preferred_routes]):
        raise ValueError("native candidate ranking returned empty structured content")
    return {
        "primary_files": primary_files,
        "secondary_files": secondary_files,
        "primary_dirs": primary_dirs,
        "preferred_symbols": preferred_symbols,
        "preferred_routes": preferred_routes,
        "discarded_noise": discarded_noise,
        "reason": reason,
        "open_questions": open_questions,
    }


def build_term_family_prompt(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    candidate_ranking_payloads: list[dict[str, object]],
    anchor_selection_payloads: list[dict[str, object]],
) -> str:
    payload = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "term_mapping": {
            "mapped_terms": term_mapping_payload.get("mapped_terms", []),
            "search_terms": term_mapping_payload.get("search_terms", []),
        },
        "candidate_ranking": candidate_ranking_payloads,
        "anchor_selection": anchor_selection_payloads,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Term Family。\n"
        "目标：把当前任务里属于同一条业务主线的一组词归成一个主族群，避免后续正文只跟着动作词走。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 primary_family, secondary_families, generic_terms, noise_terms, reason, open_questions。\n"
        "3. primary_family 最多 6 个词；secondary_families 最多 3 组，每组最多 4 个词；generic_terms 最多 4 个词；noise_terms 最多 8 个词。\n"
        "4. 只能从输入里出现过的词、符号、路由片段、文件名片段中选择，不要编造。\n"
        "5. primary_family 应优先选择跨 repo、跨文件、跨符号反复出现并共同描述同一业务主线的词。\n"
        "6. 不要让 create/update/list/detail 这类纯动作词单独成为主族群，除非没有更稳的业务词。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- 优先选择同时出现在 term_mapping、candidate_ranking、anchor_selection 中的词。\n"
        "- 业务类型词、领域对象词、主路由片段优先于单纯动作词。\n"
        "- 如果某个词过于宽泛，只能描述大类、不能稳定指向当前主链路，应放入 generic_terms，而不是 primary_family。\n"
        "- callback、cycle、loader、legacy、billboard 等如果只在少量旁支候选中出现，可放入 noise_terms 或 secondary_families。\n"
        "- 如果有多个可能族群，primary_family 只保留最能描述当前主链路的一组。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- 词保持原样，必要时可同时保留 CamelCase 和 snake_case。\n"
        "- reason 简短明确，说明为什么这些词是一伙、哪些只是噪音或旁支。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"primary_family":["flash_sale","CreatorPromotion","ExclusiveFlashSale"],'
        '"secondary_families":[["create","update_status"],["SellerFlashSale","cycle_promotion"]],'
        '"generic_terms":["promotion"],'
        '"noise_terms":["callback","loader","legacy","billboard"],'
        '"reason":"flash_sale、CreatorPromotion、ExclusiveFlashSale 在两个 repo 的 route、symbol 和 entry file 中反复共现，能共同描述达人秒杀主链路；create/update 是动作词，cycle/billboard 更像旁支。",'
        '"open_questions":["删除动作是否属于同一主族群，还是单独旁支链路"]}\n'
        "</example_output>\n"
    )


def extract_term_family_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native term family did not return a JSON object")
    primary_family = _as_string_list(payload.get("primary_family"))[:6]
    secondary_raw = payload.get("secondary_families")
    secondary_families: list[list[str]] = []
    if isinstance(secondary_raw, list):
        for item in secondary_raw[:3]:
            if isinstance(item, list):
                current = _as_string_list(item)[:4]
                if current:
                    secondary_families.append(current)
    generic_terms = _as_string_list(payload.get("generic_terms"))[:4]
    noise_terms = _as_string_list(payload.get("noise_terms"))[:8]
    reason = str(payload.get("reason") or "").strip()
    open_questions = _as_string_list(payload.get("open_questions"))[:6]
    if not primary_family:
        raise ValueError("native term family returned empty primary_family")
    return {
        "primary_family": primary_family,
        "secondary_families": secondary_families,
        "generic_terms": generic_terms,
        "noise_terms": noise_terms,
        "reason": reason,
        "open_questions": open_questions,
    }


def build_focus_boundary_prompt(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    term_family_payload: dict[str, object],
    anchor_selection_payloads: list[dict[str, object]],
    candidate_ranking_payloads: list[dict[str, object]],
) -> str:
    payload = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "term_mapping": {
            "mapped_terms": term_mapping_payload.get("mapped_terms", []),
            "search_terms": term_mapping_payload.get("search_terms", []),
        },
        "term_family": term_family_payload,
        "anchor_selection": anchor_selection_payloads,
        "candidate_ranking": candidate_ranking_payloads,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Focus Boundary。\n"
        "目标：判断当前知识草稿真正的主题边界，区分主主题、补充主题和应排除的旁支。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 canonical_subject, in_scope_terms, supporting_terms, out_of_scope_terms, reason, open_questions。\n"
        "3. in_scope_terms 最多 8 条，supporting_terms 最多 6 条，out_of_scope_terms 最多 8 条。\n"
        "4. 只能从输入里出现过的词、符号、路由片段、目录片段中选择，不要编造新术语。\n"
        "5. 只把真正描述当前主主题的词放进 in_scope_terms；相关但不是当前知识焦点的旁支必须放进 out_of_scope_terms。\n"
        "6. 动作词、灰度词、实验词、技术实现词、相邻场景词，如果不能稳定代表主主题，不要放进 in_scope_terms。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- canonical_subject 要尽量贴近用户原始目标，不要被相邻子场景带偏。\n"
        "- in_scope_terms 优先选择领域对象词、主链路词、主接口词、核心展示对象词。\n"
        "- supporting_terms 可以保留帮助理解上下游的辅助概念，但不能抢占主线。\n"
        "- out_of_scope_terms 用来放相邻能力、伴生场景、灰度开关、实验项、实现细节或容易误导主线的词。\n"
        "- 如果某个词只在少量 repo 或提交里出现，但会让主题明显跑偏，应优先放入 out_of_scope_terms。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- 词保持原样。\n"
        "- reason 用 2~4 句说明边界判断依据。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"canonical_subject":"竞拍讲解卡系统链路",'
        '"in_scope_terms":["auction","popcard","AuctionData","preview"],'
        '"supporting_terms":["lynx","schema","wallet_check"],'
        '"out_of_scope_terms":["auction_bag","benefit_package","gray_release"],'
        '"reason":"auction 和 popcard 在多个 repo 的 route、symbol 和 entry file 中共同指向当前主主题；lynx/schema 更像展示补充概念；auction_bag 和 benefit_package 属于相邻场景，不应主导系统链路文档。",'
        '"open_questions":["是否还存在另一个与 popcard 同义的主术语需要并入"]}\n'
        "</example_output>\n"
    )


def extract_focus_boundary_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native focus boundary did not return a JSON object")
    canonical_subject = str(payload.get("canonical_subject") or "").strip()
    in_scope_terms = _as_string_list(payload.get("in_scope_terms"))[:8]
    supporting_terms = _as_string_list(payload.get("supporting_terms"))[:6]
    out_of_scope_terms = _as_string_list(payload.get("out_of_scope_terms"))[:8]
    reason = str(payload.get("reason") or "").strip()
    open_questions = _as_string_list(payload.get("open_questions"))[:6]
    if not canonical_subject or not in_scope_terms:
        raise ValueError("native focus boundary returned empty canonical_subject or in_scope_terms")
    return {
        "canonical_subject": canonical_subject,
        "in_scope_terms": in_scope_terms,
        "supporting_terms": supporting_terms,
        "out_of_scope_terms": out_of_scope_terms,
        "reason": reason,
        "open_questions": open_questions,
    }


def build_anchor_selection_prompt(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    candidate_ranking: dict[str, object],
) -> str:
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
        "candidate_ranking": candidate_ranking,
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


def build_repo_research_prompt(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    candidate_ranking: dict[str, object],
    anchor_selection: dict[str, object],
    term_family: dict[str, object],
    focus_boundary: dict[str, object],
) -> str:
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
    candidate_ranking_payload = {
        "primary_files": candidate_ranking.get("primary_files", []),
        "secondary_files": candidate_ranking.get("secondary_files", []),
        "primary_dirs": candidate_ranking.get("primary_dirs", []),
        "preferred_symbols": candidate_ranking.get("preferred_symbols", []),
        "preferred_routes": candidate_ranking.get("preferred_routes", []),
        "discarded_noise": candidate_ranking.get("discarded_noise", []),
        "reason": candidate_ranking.get("reason", ""),
    }
    term_family_payload = {
        "primary_family": term_family.get("primary_family", []),
        "secondary_families": term_family.get("secondary_families", []),
        "generic_terms": term_family.get("generic_terms", []),
        "noise_terms": term_family.get("noise_terms", []),
        "reason": term_family.get("reason", ""),
    }
    focus_boundary_payload = {
        "canonical_subject": focus_boundary.get("canonical_subject", ""),
        "in_scope_terms": focus_boundary.get("in_scope_terms", []),
        "supporting_terms": focus_boundary.get("supporting_terms", []),
        "out_of_scope_terms": focus_boundary.get("out_of_scope_terms", []),
        "reason": focus_boundary.get("reason", ""),
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
        "- term_family 里的 primary_family 是当前任务的主术语族群，应优先沿它来判断主链路。\n"
        "- term_family 里的 generic_terms 只能作为背景词，不应成为主模块或主链路判断的中心。\n"
        "- term_family 里的 secondary_families 更像旁支、补充链路或动作分支，不要把它们提升成主入口。\n"
        "- focus_boundary 里的 in_scope_terms 是当前文档必须聚焦的主题，out_of_scope_terms 是相关但不应主导正文的旁支。\n"
        "- 如果某些高频命中明显描述的是相邻子场景、伴生能力或配置开关，而不是用户标题描述的主对象，应把它们视作旁支，而不是主模块。\n"
        "- anchor_selection 里的 strongest_terms、entry_files、business_symbols 应视作主判断依据。\n"
        "- candidate_files、route_hits、symbol_hits、candidate_dirs、context_hits 越集中，越倾向 primary。\n"
        "- route/path、handler、service、rpc、enum 比 middleware、flow、pack、commit 改造词更能代表主链路。\n"
        "- 如果 repo 只命中少量外围目录且缺少高信号文件，可判为 supporting。\n"
        "- 优先输出模块级职责，不要因为某个 symbol 或开关命中很多次，就把该开关对应的相邻场景当成主主题。\n"
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
        "<candidate_ranking>\n"
        f"{json.dumps(candidate_ranking_payload, ensure_ascii=False, indent=2)}\n"
        "</candidate_ranking>\n\n"
        "<term_family>\n"
        f"{json.dumps(term_family_payload, ensure_ascii=False, indent=2)}\n"
        "</term_family>\n\n"
        "<focus_boundary>\n"
        f"{json.dumps(focus_boundary_payload, ensure_ascii=False, indent=2)}\n"
        "</focus_boundary>\n\n"
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


def build_topic_adjudication_prompt(
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
) -> str:
    payload = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "focus_boundary": focus_boundary_payload,
        "repo_research": repo_research_payloads,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Topic Adjudication。\n"
        "目标：在多 repo 证据下判断主主题、相邻主题和需要压制的旁支信号。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 primary_subject, related_subjects, adjacent_subjects, suppressed_terms, suppressed_modules, suppressed_routes, reason, open_questions。\n"
        "3. related_subjects 最多 10 条，adjacent_subjects / suppressed_terms 最多 8 条，suppressed_modules / suppressed_routes 最多 10 条。\n"
        "4. 只能使用输入里出现过的术语、模块或路由，不要编造新的业务名。\n"
        "5. 被判为 adjacent/suppressed 的内容，代表相邻场景或伴生能力，不能主导后续 flow 正文。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- primary_subject 必须尽量贴近用户标题和描述，不要被高频配置词或相邻场景带偏。\n"
        "- related_subjects 只能保留业务对象、主链路动作或用户显式关心的概念；不要把配置词、开关词、schema、实验词放进 related_subjects。\n"
        "- adjacent_subjects 是相关但不应主导正文的概念。\n"
        "- 如果某些高频词更多对应配置开关、伴生能力、相邻子场景、技术实现条件或测试痕迹，应优先进入 suppressed_terms。\n"
        "- suppressed_modules / suppressed_routes 只保留真正会带偏主主题的模块和路由。\n"
        "</heuristics>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n"
    )


def extract_topic_adjudication_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native topic adjudication did not return a JSON object")
    primary_subject = str(payload.get("primary_subject") or "").strip()
    if not primary_subject:
        raise ValueError("native topic adjudication missing primary_subject")
    return {
        "primary_subject": primary_subject,
        "related_subjects": _as_string_list(payload.get("related_subjects"))[:10],
        "adjacent_subjects": _as_string_list(payload.get("adjacent_subjects"))[:8],
        "suppressed_terms": _as_string_list(payload.get("suppressed_terms"))[:8],
        "suppressed_modules": _as_string_list(payload.get("suppressed_modules"))[:10],
        "suppressed_routes": _as_string_list(payload.get("suppressed_routes"))[:10],
        "reason": str(payload.get("reason") or "").strip(),
        "open_questions": _as_string_list(payload.get("open_questions"))[:6],
    }


def build_repo_role_signals_prompt(
    intent_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
) -> str:
    payload = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "topic_adjudication": topic_adjudication_payload,
        "repo_research": repo_research_payloads,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Repo Role Signals。\n"
        "目标：先判断每个 repo 的证据类型，再映射成稳定的角色标签。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 repos 数组。\n"
        "3. repos 每项必须包含 repo_id, has_external_entry_signal, has_http_api_signal, has_orchestration_signal, has_frontend_assembly_signal, has_shared_capability_signal, has_runtime_update_signal, signal_notes, resolved_role_label, open_questions。\n"
        "4. resolved_role_label 只能是：服务聚合入口、HTTP/API 入口、数据编排层、前端/BFF 装配层、公共能力底座、系统支撑仓库。\n"
        "5. 先做信号判断，再给角色；不要直接跳过信号判断。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- 相邻主题命中再多，也不能单独把 repo 提升成主入口。\n"
        "- shared_capability_signal 强且 external/http 信号弱时，应更偏公共能力底座。\n"
        "- orchestration_signal 强时，更偏数据编排层。\n"
        "- frontend_assembly_signal 强时，更偏前端/BFF 装配层。\n"
        "- signal_notes 说明为什么给出这些信号，不要写空泛话术。\n"
        "</heuristics>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n"
    )


def extract_repo_role_signals_output(raw: str) -> list[dict[str, object]]:
    payload = extract_json_object(raw, "native repo role signals did not return a JSON object")
    repos = payload.get("repos")
    if not isinstance(repos, list):
        raise ValueError("native repo role signals missing repos")
    results: list[dict[str, object]] = []
    for item in repos:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("repo_id") or "").strip()
        if not repo_id:
            continue
        results.append(
            {
                "repo_id": repo_id,
                "has_external_entry_signal": bool(item.get("has_external_entry_signal")),
                "has_http_api_signal": bool(item.get("has_http_api_signal")),
                "has_orchestration_signal": bool(item.get("has_orchestration_signal")),
                "has_frontend_assembly_signal": bool(item.get("has_frontend_assembly_signal")),
                "has_shared_capability_signal": bool(item.get("has_shared_capability_signal")),
                "has_runtime_update_signal": bool(item.get("has_runtime_update_signal")),
                "signal_notes": _as_string_list(item.get("signal_notes"))[:6],
                "resolved_role_label": str(item.get("resolved_role_label") or "").strip(),
                "open_questions": _as_string_list(item.get("open_questions"))[:4],
            }
        )
    if not results:
        raise ValueError("native repo role signals returned empty repos")
    return results


def build_flow_slot_extraction_prompt(
    intent_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
) -> str:
    payload = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "topic_adjudication": topic_adjudication_payload,
        "repo_role_signals": repo_role_signal_payloads,
        "repo_research": repo_research_payloads,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Flow Slot Extraction。\n"
        "目标：把系统链路拆进固定场景槽位，而不是自由写步骤。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含这些键：sync_entry_or_init, async_preview_or_pre_enter, data_orchestration, runtime_update_or_notification, frontend_bff_transform, config_or_experiment_support, open_questions。\n"
        "3. 每个槽位要么是空对象，要么包含 repos, primary_repos, action, output, summary, evidence。\n"
        "4. summary 必须是系统场景描述，而不是 repo 列表。\n"
        "5. 只在输入证据支持时填充槽位；不确定时留空对象。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- sync_entry_or_init 优先描述同步入口或初始化。\n"
        "- async_preview_or_pre_enter 优先描述异步预览、进房前或 preview/pop 场景。\n"
        "- data_orchestration 优先描述主数据编排和状态收敛。\n"
        "- runtime_update_or_notification 优先描述运行时刷新、事件或通知。\n"
        "- frontend_bff_transform 优先描述前端/BFF 形态转换。\n"
        "- config_or_experiment_support 只描述配置、AB、schema 等支撑层。\n"
        "- 非 config_or_experiment_support 槽位的 summary，不要让配置词、实验词、schema、相邻子场景词做主语。\n"
        "- 如果某个词更像配置开关或伴生场景，只能放在 evidence，不要写进 summary 主句。\n"
        "</heuristics>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n"
    )


def extract_flow_slot_extraction_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native flow slot extraction did not return a JSON object")
    result: dict[str, object] = {"open_questions": _as_string_list(payload.get("open_questions"))[:6]}
    for slot in (
        "sync_entry_or_init",
        "async_preview_or_pre_enter",
        "data_orchestration",
        "runtime_update_or_notification",
        "frontend_bff_transform",
        "config_or_experiment_support",
    ):
        current = payload.get(slot)
        if not isinstance(current, dict):
            result[slot] = {}
            continue
        result[slot] = {
            "repos": _as_string_list(current.get("repos"))[:4],
            "primary_repos": _as_string_list(current.get("primary_repos"))[:3],
            "action": str(current.get("action") or "").strip(),
            "output": str(current.get("output") or "").strip(),
            "summary": str(current.get("summary") or "").strip(),
            "evidence": _as_string_list(current.get("evidence"))[:6],
        }
    return result


def build_storyline_outline_prompt(
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
) -> str:
    payload = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "focus_boundary": focus_boundary_payload,
        "topic_adjudication": topic_adjudication_payload,
        "repo_role_signals": repo_role_signal_payloads,
        "flow_slots": flow_slot_payload,
        "repo_research": repo_research_payloads,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Storyline Outline。\n"
        "目标：把多 repo research 收敛成系统级知识文档的叙事骨架，而不是 research 过程记录。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 system_summary, main_flow_steps, dependencies, repo_hints, domain_summary, open_questions。\n"
        "3. system_summary 最多 4 条，main_flow_steps 最多 6 条，dependencies 最多 8 条，open_questions 最多 8 条。\n"
        "4. repo_hints 必须是数组；每项必须包含 repo_id, role_label, key_modules, responsibilities, upstream, downstream, notes。\n"
        "5. 只能使用输入里已有的 repo、模块、事实和推断，不要编造新系统或新接口。\n"
        "6. main_flow_steps 必须描述业务系统链路，不要写成意图收敛、扫描目录、术语映射这类生成过程。\n"
        "7. repo_hints 只写稳定认知，不要输出 candidate files、symbol hits、commit hits 这类 trace 痕迹。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- system_summary 先回答“这是什么系统、由哪些层组成”。\n"
        "- main_flow_steps 优先按场景组织，而不是按 repo 顺序罗列。优先槽位是：同步/初始化、异步预览或进房前链路、数据编排、运行时刷新、前端/BFF 转换、配置/实验支撑。仅在输入证据支持时填充这些槽位。\n"
        "- role_label 要尽量用业务语义，例如“服务聚合入口”“数据编排层”“前端/BFF 装配层”“公共能力底座”，而不是 primary/supporting。\n"
        "- key_modules 应使用模块级表达，而不是文件级表达。\n"
        "- upstream / downstream 只写真正帮助理解链路的依赖方向，不要为了凑数重复 repo 名。\n"
        "- open_questions 只保留真正会影响知识正确性的未确认点，不要保留 search/debug 类问题。\n"
        "- 如果 evidence 中混有相邻子场景、伴生能力或配置开关，只有在解释主链路所必需时才可提及，且不能进入 system_summary 的主句。\n"
        "- 不要轻易把某个入口仓库写成“承接全部核心业务逻辑”；除非输入明确显示它同时拥有入口、状态编排和下游权威源职责。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- repo_id 和模块名保持原样。\n"
        "- 每一条都要短、稳、可维护。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"system_summary":["该链路由 `repo-a` 承接入口，由 `repo-b` 完成业务数据编排，由 `repo-c` 负责前端装配。"],'
        '"main_flow_steps":["客户端先通过 `repo-a` 进入入口接口，再由 `repo-b` 拉配置和状态数据，最后由 `repo-c` 转成前端展示结构。"],'
        '"dependencies":["`repo-a` 依赖 `repo-b` 提供主数据。"],'
        '"repo_hints":[{"repo_id":"repo-a","role_label":"服务入口","key_modules":["handler","service"],"responsibilities":["承接入口请求并聚合场景参数"],"upstream":[],"downstream":["repo-b"],"notes":["更偏入口而非核心数据编排。"]}],'
        '"domain_summary":["该业务方向围绕某核心对象的入口、状态和展示链路展开。"],'
        '"open_questions":["`repo-a` 和 `repo-b` 的生产边界是否还有兼容层。"]}\n'
        "</example_output>\n"
    )


def extract_storyline_outline_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native storyline outline did not return a JSON object")
    system_summary = _as_string_list(payload.get("system_summary"))[:4]
    main_flow_steps = _as_string_list(payload.get("main_flow_steps"))[:6]
    dependencies = _as_string_list(payload.get("dependencies"))[:8]
    domain_summary = _as_string_list(payload.get("domain_summary"))[:4]
    open_questions = _as_string_list(payload.get("open_questions"))[:8]
    repo_hints_raw = payload.get("repo_hints")
    repo_hints: list[dict[str, object]] = []
    if isinstance(repo_hints_raw, list):
        for item in repo_hints_raw[:10]:
            if not isinstance(item, dict):
                continue
            repo_id = str(item.get("repo_id") or "").strip()
            if not repo_id:
                continue
            repo_hints.append(
                {
                    "repo_id": repo_id,
                    "role_label": str(item.get("role_label") or "").strip(),
                    "key_modules": _as_string_list(item.get("key_modules"))[:6],
                    "responsibilities": _as_string_list(item.get("responsibilities"))[:6],
                    "upstream": _as_string_list(item.get("upstream"))[:6],
                    "downstream": _as_string_list(item.get("downstream"))[:6],
                    "notes": _as_string_list(item.get("notes"))[:6],
                }
            )
    if not system_summary and not main_flow_steps:
        raise ValueError("native storyline outline returned empty system_summary and main_flow_steps")
    return {
        "system_summary": system_summary,
        "main_flow_steps": main_flow_steps,
        "dependencies": dependencies,
        "repo_hints": repo_hints,
        "domain_summary": domain_summary,
        "open_questions": open_questions,
    }


def build_knowledge_synthesis_prompt(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    term_family_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    storyline_outline_payload: dict[str, object],
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
        "term_family": term_family_payload,
        "focus_boundary": focus_boundary_payload,
        "storyline_outline": storyline_outline_payload,
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
        "4. flow 的 body 必须包含：## Summary, ## Main Flow, ## Dependencies, ## Repo Hints, ## Open Questions。\n"
        "5. domain 的 body 必须包含：## Summary, ## Repo Coverage, ## Open Questions。\n"
        "6. rule 的 body 必须包含：## Statement, ## Evidence Risks, ## Open Questions。\n"
        "7. open_questions 要与 body 里的 Open Questions 对齐。\n"
        "8. 不要输出空泛模板话术；要优先利用 repo research 里的 role、likely_modules、facts、risks、open_questions。\n"
        "</success_criteria>\n\n"
        "<grounding_rules>\n"
        "- 只能使用输入里已有的 repo_id、路径、模块线索、事实和风险。\n"
        "- 优先沿 storyline_outline 写正文，不要回退成 discovery/scan 过程记录。\n"
        "- focus_boundary.out_of_scope_terms 对应的相邻场景不能主导正文。\n"
        "- 即使 out_of_scope_terms 在 evidence 中高频出现，也只能把它们当成旁支或配置背景，不能写进 system summary 或 main flow 主步骤。\n"
        "- 优先沿 term_family.primary_family 和 repo_anchors 里的 entry_files、business_symbols、route_hits 写主线，不要只跟着 create/update 这类动作词走。\n"
        "- generic_terms 只能作为背景描述，不要把它们单独写成主族群结论。\n"
        "- secondary_families 更像旁支或补充链路，只有在确有必要时才简短提及，不要让它们抢主线。\n"
        "- 如果证据弱，可以明确写“当前仅基于候选目录/文件推断”，但不要编造不存在的系统、接口或文件。\n"
        "- 优先写“这条链路如何经过这些 repo / 模块”，而不是重复意图描述。\n"
        "- Main Flow 应优先写成业务场景阶段，不要写成 repo 列表，也不要让相邻子场景替代用户真正关心的主对象。\n"
        "- 语言保持中文，代码路径和 repo_id 保持原样。\n"
        "- 避免使用“第一阶段草稿”“待补充”等程序味很重的话术，除非输入证据确实不足。\n"
        "</grounding_rules>\n\n"
        "<style>\n"
        "- Summary 用 2~4 句，直接说明链路或规则的核心。\n"
        "- Main Flow 用 3~6 条编号步骤，尽量写出 repo 角色或模块动作。\n"
        "- Dependencies / Repo Coverage / Evidence Risks 尽量引用具体 repo 和模块线索。\n"
        "- Repo Hints 应偏向 role、key_modules、responsibilities、upstream/downstream，不要列 candidate files。\n"
        "- Open Questions 只保留真正未确认的问题，不要重复 Summary。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(synthesis_input, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"documents":[{"kind":"flow","title":"系统链路","desc":"归纳某能力的主链路和 repo hints。",'
        '"body":"## Summary\\n\\n该链路由 `repo-a` 承接入口，由 `repo-b` 提供下游能力。\\n\\n## Main Flow\\n\\n1. ...\\n\\n## Dependencies\\n\\n- `repo-a`：负责入口聚合。\\n\\n## Repo Hints\\n\\n### `repo-a`\\n\\n- repo: `repo-a`\\n- role: `服务入口`\\n\\n#### Key Modules\\n- handler\\n\\n## Open Questions\\n\\n- 是否存在额外上游网关",'
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
    return outputs


def build_flow_final_editor_prompt(
    document: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
    storyline_outline_payload: dict[str, object],
    flow_judge_payload: dict[str, object],
) -> str:
    payload = {
        "document": document,
        "topic_adjudication": topic_adjudication_payload,
        "repo_role_signals": repo_role_signal_payloads,
        "flow_slots": flow_slot_payload,
        "storyline_outline": storyline_outline_payload,
        "flow_judge": flow_judge_payload,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Flow Final Editor。\n"
        "目标：在不新增事实的前提下，把 flow 文档最后润成更像系统知识文档的版本。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown 解释，不要包 code fence。\n"
        "2. JSON 必须包含 summary_lines, main_flow_steps, dependency_lines, open_questions。\n"
        "3. 只能重写 Summary、Main Flow、Dependencies、Open Questions，不要新增 repo、路由、文件、接口或事实。\n"
        "4. summary_lines 最多 3 条，main_flow_steps 最多 5 条，dependency_lines 最多 6 条，open_questions 最多 6 条。\n"
        "5. 必须遵守 repo_role_signals、flow_slots 和 flow_judge findings；被压制主题不能重新进入主句。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- Summary 优先写 repo-role 直述，不要泛泛说“多个层次共同组成”。\n"
        "- Main Flow 优先写 repo + 场景动作 + 产出：同步进房初始化、异步 preview/pop、数据编排、前端/BFF 装配；运行时刷新/通知只能作为可选补充步骤。\n"
        "- Dependencies 优先写系统依赖面：配置源、session 源、relation 源、通知/过滤出口、前端消费方；不要只写 A 依赖 B。\n"
        "- Open Questions 只保留系统边界类问题，例如 repo 分工边界、权威数据源、新旧架构或 region 兼容边界；不要写 handler/文件/实现定位问题。\n"
        "- 不要把公共能力底座写成主链路步骤。\n"
        "</heuristics>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n"
    )


def extract_flow_final_editor_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "flow final editor did not return a JSON object")
    return {
        "summary_lines": _as_string_list(payload.get("summary_lines"))[:3],
        "main_flow_steps": _as_string_list(payload.get("main_flow_steps"))[:5],
        "dependency_lines": _as_string_list(payload.get("dependency_lines"))[:6],
        "open_questions": _as_string_list(payload.get("open_questions"))[:6],
    }


def build_flow_final_polisher_prompt(
    document: dict[str, object],
    flow_final_edit_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_judge_payload: dict[str, object],
) -> str:
    payload = {
        "document": document,
        "flow_final_edit": flow_final_edit_payload,
        "topic_adjudication": topic_adjudication_payload,
        "repo_role_signals": repo_role_signal_payloads,
        "flow_judge": flow_judge_payload,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Flow Final Polisher。\n"
        "目标：对已经编辑过的 flow 文档做最后一次克制化润色，让它更像资深工程师写的系统知识文档。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown 解释，不要包 code fence。\n"
        "2. JSON 必须包含 summary_lines, main_flow_steps, dependency_lines, open_questions。\n"
        "3. 不能新增事实、repo、路由、接口、文件或具体实现细节。\n"
        "4. 允许做的事情只有：降重、收敛、改写句式、删去低价值问题。\n"
        "5. 仍然必须遵守 suppressed topics、repo roles 和 judge findings。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- 去掉“核心服务、主入口、核心实现、关键环节”这类重词，改成入口、聚合、编排、装配、支撑等中性表达。\n"
        "- Main Flow 保持 repo + 动作 + 产出，不要重新变成抽象阶段名。\n"
        "- Dependencies 保持系统依赖面，不要退回 repo 邻接表。\n"
        "- Open Questions 最多保留 2~3 条最值钱的系统边界问题。\n"
        "</heuristics>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n"
    )


def extract_flow_final_polisher_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "flow final polisher did not return a JSON object")
    return {
        "summary_lines": _as_string_list(payload.get("summary_lines"))[:3],
        "main_flow_steps": _as_string_list(payload.get("main_flow_steps"))[:5],
        "dependency_lines": _as_string_list(payload.get("dependency_lines"))[:6],
        "open_questions": _as_string_list(payload.get("open_questions"))[:6],
    }


def build_flow_judge_prompt(
    documents: list[dict[str, object]],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
) -> str:
    payload = {
        "documents": documents,
        "topic_adjudication": topic_adjudication_payload,
        "repo_role_signals": repo_role_signal_payloads,
        "flow_slots": flow_slot_payload,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Flow Judge。\n"
        "目标：对已经生成的 flow 文档做反证检查，指出主线偏移、角色过重或被压制主题重新进入正文的问题。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 passed 和 findings。\n"
        "3. findings 每项必须包含 severity, code, document_id, message。\n"
        "4. severity 只能是 high、medium、low。\n"
        "5. 只在发现明显问题时返回 findings；没有问题时 findings 为空数组。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- 如果 suppressed topic 或 adjacent topic 再次进入 Summary/Main Flow 主句，应判为 high。\n"
        "- 如果公共能力底座被写成主入口，应至少判为 medium。\n"
        "- 如果 Open Questions 围绕被压制主题或相邻主题展开，应判为 medium。\n"
        "- 如果 Main Flow 槽位覆盖明显不足，可提示为 medium。\n"
        "- 不要因为风格偏好报问题，只抓会影响知识正确性的偏差。\n"
        "</heuristics>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n"
    )


def extract_flow_judge_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native flow judge did not return a JSON object")
    findings_raw = payload.get("findings")
    findings: list[dict[str, object]] = []
    if isinstance(findings_raw, list):
        for item in findings_raw:
            if not isinstance(item, dict):
                continue
            code = normalize_flow_judge_code(str(item.get("code") or "").strip())
            findings.append(
                {
                    "severity": str(item.get("severity") or "low").strip().lower(),
                    "code": code,
                    "document_id": str(item.get("document_id") or "").strip(),
                    "message": str(item.get("message") or "").strip(),
                }
            )
    codes = {item["code"] for item in findings if item["code"]}
    return {
        "passed": bool(payload.get("passed")) if "passed" in payload else not findings,
        "findings": [
            item
            for item in findings
            if item["code"] and item["document_id"] and item["message"]
        ],
        "must_rewrite_summary": bool(payload.get("must_rewrite_summary")) or bool(
            codes & {"suppressed_topic_in_mainline", "suppressed_topic_in_summary"}
        ),
        "must_rewrite_flow_steps": bool(payload.get("must_rewrite_flow_steps")) or bool(
            codes & {"suppressed_topic_in_mainline", "suppressed_topic_in_summary", "shared_repo_as_entry"}
        ),
        "must_prune_open_questions": bool(payload.get("must_prune_open_questions")) or bool(
            codes & {"suppressed_topic_in_questions"}
        ),
    }


def normalize_flow_judge_code(code: str) -> str:
    normalized = code.strip().lower()
    if not normalized:
        return ""
    if normalized in {"suppressed_topic_in_summary", "suppressed_topic_in_main_flow", "suppressed_topic_in_mainline"}:
        return "suppressed_topic_in_mainline"
    if normalized in {"open_questions_on_suppressed_topics", "suppressed_topic_in_questions"}:
        return "suppressed_topic_in_questions"
    if normalized == "shared_repo_as_entry":
        return normalized
    if normalized == "flow_slots_too_sparse":
        return normalized
    return normalized

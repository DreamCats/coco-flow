from __future__ import annotations

import json
import re

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.engines.business_memory import BusinessMemoryContext

from .intent import render_intent_summary
from .models import (
    EXECUTOR_LOCAL,
    EXECUTOR_NATIVE,
    RefineEngineResult,
    RefineIntent,
    RefinePreparedInput,
    STATUS_INITIALIZED,
    STATUS_REFINED,
)

_refined_heading = re.compile(r"(?m)^#\s+PRD Refined\s*$")


def generate_pending_refine(
    prepared: RefinePreparedInput,
    memory: BusinessMemoryContext,
    refined_markdown: str,
    artifacts: dict[str, str | dict[str, object]],
) -> RefineEngineResult:
    return build_refine_engine_result(
        status=STATUS_INITIALIZED,
        refined_markdown=refined_markdown,
        memory=memory,
        artifacts=artifacts,
    )


def generate_local_refine(
    prepared: RefinePreparedInput,
    memory: BusinessMemoryContext,
    intent: RefineIntent,
    knowledge_brief: str,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> RefineEngineResult:
    _log_source_details(prepared, on_log)
    on_log("fallback_local_refine: true")
    refined = build_fallback_refined_content(
        title=prepared.title,
        source_content=prepared.source_content,
        memory=memory,
        intent=intent,
        knowledge_brief=knowledge_brief,
    )
    on_log(f"status: {STATUS_REFINED}")
    return build_refine_engine_result(
        status=STATUS_REFINED,
        refined_markdown=refined,
        memory=memory,
        artifacts=artifacts,
    )


def generate_native_refine(
    prepared: RefinePreparedInput,
    settings: Settings,
    memory: BusinessMemoryContext,
    intent: RefineIntent,
    knowledge_brief: str,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> RefineEngineResult:
    _log_source_details(prepared, on_log)
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    on_log(f"prompt_start: timeout={settings.native_query_timeout}")
    raw = client.run_prompt_only(
        build_refine_prompt(prepared, intent, knowledge_brief),
        settings.native_query_timeout,
        cwd=prepared.repo_root,
        fresh_session=True,
    )
    on_log(f"prompt_ok: {len(raw)} bytes")
    refined = extract_refined_content(raw)
    if not refined:
        raise ValueError("native refine returned empty content")
    on_log(f"verify_start: timeout={settings.native_query_timeout}")
    verify_raw = client.run_prompt_only(
        build_refine_verify_prompt(prepared, intent, refined),
        settings.native_query_timeout,
        cwd=prepared.repo_root,
        fresh_session=True,
    )
    on_log(f"verify_ok: {len(verify_raw)} bytes")
    verify_payload = parse_refine_verify_output(verify_raw)
    artifacts["refine-verify.json"] = verify_payload
    if not bool(verify_payload.get("ok")):
        issues = verify_payload.get("issues")
        issue_text = "; ".join(str(item) for item in issues[:3]) if isinstance(issues, list) else "unknown"
        on_log(f"verify_failed: {issue_text}")
        raise ValueError(f"native refine verify failed: {issue_text}")
    on_log("verify_passed: true")
    on_log(f"status: {STATUS_REFINED}")
    return build_refine_engine_result(
        status=STATUS_REFINED,
        refined_markdown=refined.rstrip() + "\n",
        memory=memory,
        artifacts=artifacts,
    )


def build_refine_prompt(prepared: RefinePreparedInput, intent: RefineIntent, knowledge_brief: str) -> str:
    knowledge_instruction = (
        "10. 如提供了 refine knowledge brief，你只能将它用于术语消歧、补充历史约束和识别冲突，不能让其覆盖当前 PRD。\n"
        "11. 对于基于知识 brief 才能推断出的内容，请尽量放入“业务规则”或“待确认问题”，不要伪装成 PRD 明确给出的事实。\n"
        if knowledge_brief.strip()
        else "10. 当前未提供 refine knowledge brief；遇到术语或业务规则不明确时，请在“待确认问题”中明确指出，不要自行脑补。\n"
    )
    return f"""你是一名严谨的产品需求梳理助手。请根据给定 PRD 原文，输出一份适合进入后续代码调研的 refined PRD。

要求：
1. 输出使用中文 Markdown。
2. 你只能基于下面提供的 PRD 原文、意图骨架和 knowledge brief 工作，不要查看仓库、代码、已有实现，也不要提及这些动作。
3. 不要解释你在做什么，不要输出任何思考过程、前言、说明、分析或“让我先看看”之类的话。
4. 输出必须直接从 # PRD Refined 开始，前面不能有任何额外文字。
5. 结构必须包含以下一级/二级标题：
   - # PRD Refined
   - ## 需求概述
   - ## 功能点
   - ## 边界条件
   - ## 交互与展示
   - ## 验收标准
   - ## 业务规则
   - ## 待确认问题
6. 如果信息缺失，请在“待确认问题”中列出，不要编造。
7. 保持内容紧凑，尽量把原文信息结构化整理出来。
8. 优先遵循当前 PRD 原文。
9. 意图骨架只是帮助你收敛结构，不代表额外事实。
{knowledge_instruction}

PRD 标题：{prepared.title}

## 当前 PRD 原文

{prepared.source_content}

## 意图骨架

{render_intent_summary(intent)}

## Refine Knowledge Brief

{knowledge_brief.strip() or "- 当前无可用业务知识 brief。"}
"""


def build_refine_verify_prompt(prepared: RefinePreparedInput, intent: RefineIntent, refined_markdown: str) -> str:
    return f"""你在做 coco-flow refine verifier。

目标：检查生成的 PRD Refined 是否满足结构和内容约束。

要求：
1. 只输出 JSON 对象，不要输出其它文字。
2. JSON 格式：
{{
  "ok": true,
  "issues": ["问题1"],
  "missing_sections": ["缺失章节"],
  "reason": "一句话结论"
}}
3. 如果内容满足要求，ok=true，issues 和 missing_sections 可以为空数组。
4. 重点检查：
   - 是否以 # PRD Refined 开头
   - 是否包含固定章节
   - 是否把明显缺失信息放进“待确认问题”
   - 是否出现了代码实现细节或脱离 PRD 的臆测

任务标题：{prepared.title}
需求目标：{intent.goal or prepared.title}

生成结果：
{refined_markdown}
"""


def parse_refine_verify_output(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid_verify_json: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("verify_output_is_not_object")
    return {
        "ok": bool(payload.get("ok")),
        "issues": [str(item) for item in payload.get("issues", []) if str(item).strip()],
        "missing_sections": [str(item) for item in payload.get("missing_sections", []) if str(item).strip()],
        "reason": str(payload.get("reason") or ""),
    }


def build_fallback_refined_content(
    *,
    title: str,
    source_content: str,
    memory: BusinessMemoryContext,
    intent: RefineIntent,
    knowledge_brief: str,
) -> str:
    context_note = (
        "- 当前未加载业务历史上下文，术语理解、历史规则和默认约束可能不完整，建议补充业务背景后再复核。\n"
        if not memory.used
        else f"- 已加载业务历史上下文（mode={memory.mode}），建议重点核对是否与当前 PRD 存在冲突。\n"
    )
    brief_note = (
        "- 已生成 refine knowledge brief，可作为术语消歧和历史规则核对的依据。\n"
        if knowledge_brief.strip()
        else "- 当前未生成额外 knowledge brief，需更多依赖原始 PRD 进行确认。\n"
    )
    return (
        "# PRD Refined\n\n"
        "> 状态：fallback\n"
        "> 原因：当前使用 coco-flow 本地模板 refine，未调用 AI refine。\n\n"
        "## 需求概述\n\n"
        f"- 标题：{title}\n"
        f"- 目标：{intent.goal or '请基于原始 PRD 补充需求目标。'}\n\n"
        "## 功能点\n\n"
        f"{_render_list(intent.potential_features, '- 请基于原始 PRD 拆分主要功能点。')}\n\n"
        "## 边界条件\n\n"
        f"{_render_list(intent.constraints, '- 请补充异常场景、空状态和结束态。')}\n\n"
        "## 交互与展示\n\n"
        "- 请补充 UI 位置、状态变化和特殊展示要求。\n\n"
        "## 验收标准\n\n"
        "- 请补充“如何算完成”和“如何验证通过”。\n\n"
        "## 业务规则\n\n"
        f"{_render_list(intent.constraints, '- 请补充适用范围、过滤条件、端侧差异等规则。')}\n\n"
        "## 待确认问题\n\n"
        f"{_render_list(intent.open_questions, '- 当前为本地兜底稿，后续可替换为 AI refine。')}\n"
        f"{context_note}"
        f"{brief_note}\n"
        "## 原始 PRD\n\n"
        f"{source_content or '当前未检测到 PRD 正文，请先补充 prd.source.md。'}\n"
    )


def build_refine_engine_result(
    *,
    status: str,
    refined_markdown: str,
    memory: BusinessMemoryContext,
    artifacts: dict[str, str | dict[str, object]],
) -> RefineEngineResult:
    return RefineEngineResult(
        status=status,
        refined_markdown=refined_markdown,
        context_mode=memory.mode,
        business_memory_used=memory.used,
        business_memory_provider=memory.provider,
        business_memory_documents=[
            {
                "kind": document.kind,
                "name": document.name,
                "path": document.path,
            }
            for document in memory.documents
        ],
        risk_flags=memory.risk_flags,
        intermediate_artifacts=artifacts,
    )


def extract_refined_content(raw: str) -> str:
    normalized = raw.replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    match = _refined_heading.search(normalized)
    if match:
        return normalized[match.start() :].strip()
    if normalized.startswith("# "):
        return normalized
    return ""


def _log_source_details(prepared: RefinePreparedInput, on_log) -> None:
    if prepared.source_meta:
        on_log(f"source_type: {prepared.source_meta.get('type') or prepared.source_type or ''}")
        if prepared.source_meta.get("path"):
            on_log(f"source_path: {prepared.source_meta.get('path')}")
        if prepared.source_meta.get("url"):
            on_log(f"source_url: {prepared.source_meta.get('url')}")
        if prepared.source_meta.get("doc_token"):
            on_log(f"source_doc_token: {prepared.source_meta.get('doc_token')}")
    on_log(f"source_length: {len(prepared.source_content)}")


def _render_list(items: list[str], default: str) -> str:
    if not items:
        return default
    return "\n".join(f"- {item}" for item in items)

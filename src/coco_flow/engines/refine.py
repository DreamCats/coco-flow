from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Callable

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.engines.business_memory import (
    BusinessMemoryContext,
    load_business_memory,
    render_business_memory_context,
)
from coco_flow.services.queries.task_detail import read_json_file
from coco_flow.services.tasks.create import classify_source_fetch_error

STATUS_INITIALIZED = "initialized"
STATUS_REFINED = "refined"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"
SOURCE_TYPE_LARK_DOC = "lark_doc"
_refined_heading = re.compile(r"(?m)^#\s+PRD Refined\s*$")
LogHandler = Callable[[str], None]


@dataclass
class RefineEngineResult:
    status: str
    refined_markdown: str
    context_mode: str
    business_memory_used: bool
    business_memory_provider: str
    business_memory_documents: list[dict[str, str]]
    risk_flags: list[str]


def run_refine_engine(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    on_log: LogHandler,
) -> RefineEngineResult:
    repos_meta = read_json_file(task_dir / "repos.json")
    repo_root = resolve_primary_repo_root(repos_meta)
    memory = load_business_memory(repo_root)
    on_log(f"context_mode: {memory.mode}")
    on_log(f"business_memory_provider: {memory.provider}")
    on_log(f"business_memory_used: {str(memory.used).lower()}")
    on_log(f"business_memory_documents: {len(memory.documents)}")
    if memory.documents:
        on_log("business_memory_files: " + ", ".join(document.name for document in memory.documents[:6]))
    if memory.risk_flags:
        on_log("business_memory_risk_flags: " + ", ".join(memory.risk_flags))

    source_meta = read_json_file(task_dir / "source.json")
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    source_content = extract_source_content(source_markdown).strip()
    source_type = str((source_meta or {}).get("type") or task_meta.get("source_type") or "")
    if source_type == SOURCE_TYPE_LARK_DOC and is_pending_lark_source(source_meta or {}, source_content):
        return refine_task_pending(task_dir, task_meta, source_meta or {}, memory, on_log=on_log)

    executor = settings.refine_executor.strip().lower()
    if executor == EXECUTOR_NATIVE:
        try:
            return refine_task_native(task_dir, task_meta, settings, memory, on_log=on_log)
        except ValueError as error:
            on_log(f"native_refine_error: {error}")
            return refine_task_local(task_dir, task_meta, memory, on_log=on_log)
    if executor == EXECUTOR_LOCAL:
        return refine_task_local(task_dir, task_meta, memory, on_log=on_log)
    raise ValueError(f"unknown refine executor: {settings.refine_executor}")


def refine_task_pending(
    task_dir: Path,
    task_meta: dict[str, object],
    source_meta: dict[str, object],
    memory: BusinessMemoryContext,
    on_log: LogHandler,
) -> RefineEngineResult:
    title = str(task_meta.get("title") or task_dir.name)
    refined = build_pending_refined_content(
        task_id=task_dir.name,
        title=title,
        source_url=str(source_meta.get("url") or ""),
        doc_token=str(source_meta.get("doc_token") or ""),
        fetch_error=str(source_meta.get("fetch_error") or ""),
        fetch_error_code=str(source_meta.get("fetch_error_code") or ""),
    )
    on_log("pending_refine: true")
    if source_meta.get("fetch_error"):
        on_log(f"fetch_error: {source_meta.get('fetch_error')}")
    on_log(f"status: {STATUS_INITIALIZED}")
    return build_refine_engine_result(
        status=STATUS_INITIALIZED,
        refined_markdown=refined,
        memory=memory,
    )


def refine_task_local(
    task_dir: Path,
    task_meta: dict[str, object],
    memory: BusinessMemoryContext,
    on_log: LogHandler,
) -> RefineEngineResult:
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    source_content = extract_source_content(source_markdown).strip()
    title = str(task_meta.get("title") or task_dir.name)
    source_meta = read_json_file(task_dir / "source.json")
    if source_meta:
        on_log(f"source_type: {source_meta.get('type') or task_meta.get('source_type') or ''}")
        if source_meta.get("path"):
            on_log(f"source_path: {source_meta.get('path')}")
        if source_meta.get("url"):
            on_log(f"source_url: {source_meta.get('url')}")
        if source_meta.get("doc_token"):
            on_log(f"source_doc_token: {source_meta.get('doc_token')}")
    on_log(f"source_length: {len(source_content)}")
    on_log("fallback_local_refine: true")

    refined = build_fallback_refined_content(title, source_content, memory)
    on_log(f"status: {STATUS_REFINED}")
    return build_refine_engine_result(
        status=STATUS_REFINED,
        refined_markdown=refined,
        memory=memory,
    )


def refine_task_native(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    memory: BusinessMemoryContext,
    on_log: LogHandler,
) -> RefineEngineResult:
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    source_content = extract_source_content(source_markdown).strip()
    title = str(task_meta.get("title") or task_dir.name)
    repos_meta = read_json_file(task_dir / "repos.json")
    source_meta = read_json_file(task_dir / "source.json")
    if source_meta:
        on_log(f"source_type: {source_meta.get('type') or task_meta.get('source_type') or ''}")
        if source_meta.get("path"):
            on_log(f"source_path: {source_meta.get('path')}")
        if source_meta.get("url"):
            on_log(f"source_url: {source_meta.get('url')}")
        if source_meta.get("doc_token"):
            on_log(f"source_doc_token: {source_meta.get('doc_token')}")
    on_log(f"source_length: {len(source_content)}")

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    on_log(f"prompt_start: timeout={settings.native_query_timeout}")
    raw = client.run_prompt_only(
        build_refine_prompt(title, source_content, memory),
        settings.native_query_timeout,
        cwd=resolve_primary_repo_root(repos_meta),
    )
    on_log(f"prompt_ok: {len(raw)} bytes")
    refined = extract_refined_content(raw)
    if not refined:
        raise ValueError("native refine returned empty content")
    on_log(f"status: {STATUS_REFINED}")
    return build_refine_engine_result(
        status=STATUS_REFINED,
        refined_markdown=refined.rstrip() + "\n",
        memory=memory,
    )


def locate_task_dir(task_id: str, settings: Settings) -> Path | None:
    primary = settings.task_root / task_id
    if primary.is_dir():
        return primary
    return None


def extract_source_content(markdown: str) -> str:
    separator = "\n---\n"
    if separator in markdown:
        return markdown.split(separator, 1)[1].strip()
    return markdown.strip()


def resolve_primary_repo_root(repos_meta: dict[str, object]) -> str | None:
    repos = repos_meta.get("repos")
    if not isinstance(repos, list) or not repos:
        return None
    first = repos[0]
    if not isinstance(first, dict):
        return None
    path = str(first.get("path") or "").strip()
    return path or None


def build_fallback_refined_content(title: str, source_content: str, memory: BusinessMemoryContext) -> str:
    context_note = (
        "- 当前未加载业务历史上下文，术语理解、历史规则和默认约束可能不完整，建议补充业务背景后再复核。\n"
        if not memory.used
        else f"- 已加载业务历史上下文（mode={memory.mode}），建议重点核对是否与当前 PRD 存在冲突。\n"
    )
    return (
        "# PRD Refined\n\n"
        "> 状态：fallback\n"
        "> 原因：当前使用 coco-flow 本地模板 refine，尚未接入 AI refine。\n\n"
        "## 需求概述\n\n"
        f"- 标题：{title}\n"
        "- 当前版本先基于原始 PRD 生成最小结构化稿，便于继续进入后续 plan/code 流程。\n\n"
        "## 功能点\n\n"
        "- 请基于原始 PRD 拆分主要功能点。\n\n"
        "## 边界条件\n\n"
        "- 请补充异常场景、空状态和结束态。\n\n"
        "## 交互与展示\n\n"
        "- 请补充 UI 位置、状态变化和特殊展示要求。\n\n"
        "## 验收标准\n\n"
        "- 请补充“如何算完成”和“如何验证通过”。\n\n"
        "## 业务规则\n\n"
        "- 请补充适用范围、过滤条件、端侧差异等规则。\n\n"
        "## 待确认问题\n\n"
        "- 当前为本地兜底稿，后续可替换为 AI refine。\n"
        f"{context_note}\n"
        "## 原始 PRD\n\n"
        f"{source_content or '当前未检测到 PRD 正文，请先补充 prd.source.md。'}\n"
    )


def build_pending_refined_content(
    task_id: str,
    title: str,
    source_url: str,
    doc_token: str,
    fetch_error: str,
    fetch_error_code: str = "",
) -> str:
    reason = fetch_error or "当前未成功拉取飞书文档正文。"
    reason_code = fetch_error_code or classify_source_fetch_error(reason)
    install_guide = (
        "## 安装 lark-cli\n\n"
        "检测到当前环境缺少 `lark-cli`。请先按下面步骤安装并登录，再重新执行 refine。\n\n"
        "```bash\n"
        "# Install CLI\n"
        "npm install -g @larksuite/cli\n\n"
        "# Install CLI SKILL (required)\n"
        "npx skills add larksuite/cli -y -g\n\n"
        "# Configure & login\n"
        "lark-cli config init\n"
        "lark-cli auth login --recommend\n"
        "```\n\n"
        "- 文档：[larksuite/cli](https://github.com/larksuite/cli)\n\n"
        if reason_code == "missing_lark_cli"
        else ""
    )
    return (
        "# PRD Refined\n\n"
        "> 状态：待补充源内容\n"
        f"> task_id: {task_id}\n"
        f"> source: {source_url or 'unknown'}\n\n"
        "## 说明\n\n"
        "当前任务已创建，并已记录飞书文档来源，但暂未获得正文内容。\n\n"
        "请将 PRD 正文补充到 `prd.source.md` 后，再重新执行 refine。\n\n"
        "## 来源信息\n\n"
        f"- 标题：{title}\n"
        f"- 飞书链接：{source_url or 'unknown'}\n"
        f"- doc token：{doc_token or 'unknown'}\n"
        f"- 拉取失败原因：{reason}\n"
        f"- 错误码：{reason_code or 'unknown'}\n\n"
        f"{install_guide}"
        "## 待确认问题\n\n"
        "- 需要补充 PRD 正文后，才能继续做结构化 refine。\n"
    )


def is_pending_lark_source(source_meta: dict[str, object], source_content: str) -> bool:
    if str(source_meta.get("type") or "") != SOURCE_TYPE_LARK_DOC:
        return False
    if not source_content:
        return True
    if source_meta.get("fetch_error") and "尚未自动拉取该来源的正文内容" in source_content:
        return True
    return False


def build_refine_prompt(title: str, source_content: str, memory: BusinessMemoryContext) -> str:
    memory_block = render_business_memory_context(memory)
    memory_instruction = (
        "8. 如提供了业务历史上下文，你只能将它用于术语消歧、补充历史约束和识别冲突，不能让历史上下文覆盖当前 PRD。\n"
        "9. 对于基于历史上下文才能推断出的内容，请尽量放入“业务规则”或“待确认问题”，不要伪装成 PRD 明确给出的事实。\n"
        if memory_block
        else "8. 当前未提供业务历史上下文；遇到术语或业务规则不明确时，请在“待确认问题”中明确指出，不要自行脑补。\n"
    )
    return f"""你是一名严谨的产品需求梳理助手。请根据给定 PRD 原文，输出一份适合进入后续代码调研的 refined PRD。

要求：
1. 输出使用中文 Markdown。
2. 你只能基于下面提供的 PRD 原文工作，不要查看仓库、代码、已有实现，也不要提及这些动作。
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
{memory_instruction}

PRD 标题：{title}

PRD 原文：

{source_content}

{memory_block}
"""


def build_refine_engine_result(
    *,
    status: str,
    refined_markdown: str,
    memory: BusinessMemoryContext,
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


def append_refine_log(task_dir: Path, message: str) -> None:
    log_path = task_dir / "refine.log"
    with log_path.open("a", encoding="utf-8") as file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file.write(f"{timestamp} {message}\n")

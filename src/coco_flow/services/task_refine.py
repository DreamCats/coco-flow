from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re

from coco_flow.clients import CocoCliClient
from coco_flow.config import Settings, load_settings
from coco_flow.services.task_detail import read_json_file

STATUS_INITIALIZED = "initialized"
STATUS_REFINED = "refined"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"
_refined_heading = re.compile(r"(?m)^#\s+PRD Refined\s*$")


def refine_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {STATUS_INITIALIZED, STATUS_REFINED}:
        raise ValueError(f"task status {status} does not allow refine")

    executor = cfg.refine_executor.strip().lower()
    if executor == EXECUTOR_NATIVE:
        try:
            return refine_task_native(task_dir, task_meta, cfg)
        except ValueError:
            return refine_task_local(task_dir, task_meta)
    if executor == EXECUTOR_LOCAL:
        return refine_task_local(task_dir, task_meta)
    raise ValueError(f"unknown refine executor: {cfg.refine_executor}")


def refine_task_local(task_dir: Path, task_meta: dict[str, object]) -> str:
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    source_content = extract_source_content(source_markdown).strip()
    title = str(task_meta.get("title") or task_dir.name)

    refined = build_fallback_refined_content(title, source_content)
    (task_dir / "prd-refined.md").write_text(refined)
    append_refine_log(task_dir, f"refined locally at {datetime.now().astimezone().isoformat()}")

    task_meta["status"] = STATUS_REFINED
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
    return STATUS_REFINED


def refine_task_native(task_dir: Path, task_meta: dict[str, object], settings: Settings) -> str:
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    source_content = extract_source_content(source_markdown).strip()
    title = str(task_meta.get("title") or task_dir.name)

    client = CocoCliClient(settings.coco_bin)
    raw = client.run_prompt_only(build_refine_prompt(title, source_content), settings.native_query_timeout)
    refined = extract_refined_content(raw)
    if not refined:
        raise ValueError("native refine returned empty content")
    (task_dir / "prd-refined.md").write_text(refined.rstrip() + "\n")
    append_refine_log(task_dir, f"refined by native coco at {datetime.now().astimezone().isoformat()}")
    task_meta["status"] = STATUS_REFINED
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
    return STATUS_REFINED


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


def build_fallback_refined_content(title: str, source_content: str) -> str:
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
        "- 当前为本地兜底稿，后续可替换为 AI refine。\n\n"
        "## 原始 PRD\n\n"
        f"{source_content or '当前未检测到 PRD 正文，请先补充 prd.source.md。'}\n"
    )


def build_refine_prompt(title: str, source_content: str) -> str:
    return f"""你是一名严谨的产品需求梳理助手。请根据给定 PRD 原文，输出一份适合进入后续代码调研的 refined PRD。

要求：
1. 输出使用中文 Markdown。
2. 不要提及仓库、代码、工具调用或任何执行过程。
3. 输出必须直接从 # PRD Refined 开始。
4. 必须包含以下一级/二级标题：
   - # PRD Refined
   - ## 需求概述
   - ## 功能点
   - ## 边界条件
   - ## 交互与展示
   - ## 验收标准
   - ## 业务规则
   - ## 待确认问题
5. 如果信息缺失，请在“待确认问题”中列出，不要编造。

PRD 标题：{title}

PRD 原文：

{source_content}
"""


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
        file.write(message + "\n")

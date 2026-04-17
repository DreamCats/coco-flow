from __future__ import annotations

from pathlib import Path

from coco_flow.config import Settings
from coco_flow.services.queries.task_detail import read_json_file
from coco_flow.services.tasks.create import classify_source_fetch_error

from .models import RefinePreparedInput, SOURCE_TYPE_LARK_DOC


def locate_task_dir(task_id: str, settings: Settings) -> Path | None:
    primary = settings.task_root / task_id
    if primary.is_dir():
        return primary
    return None


def prepare_refine_input(task_dir: Path, task_meta: dict[str, object]) -> RefinePreparedInput:
    repos_meta = read_json_file(task_dir / "repos.json")
    source_meta = read_json_file(task_dir / "source.json")
    source_markdown = (task_dir / "prd.source.md").read_text() if (task_dir / "prd.source.md").exists() else ""
    source_content = extract_source_content(source_markdown).strip()
    return RefinePreparedInput(
        task_dir=task_dir,
        task_id=task_dir.name,
        title=str(task_meta.get("title") or task_dir.name),
        source_type=str((source_meta or {}).get("type") or task_meta.get("source_type") or ""),
        source_meta=source_meta or {},
        source_markdown=source_markdown,
        source_content=source_content,
        repos_meta=repos_meta,
        repo_root=resolve_primary_repo_root(repos_meta),
    )


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


def is_pending_lark_source(source_meta: dict[str, object], source_content: str) -> bool:
    if str(source_meta.get("type") or "") != SOURCE_TYPE_LARK_DOC:
        return False
    if not source_content:
        return True
    if source_meta.get("fetch_error") and "尚未自动拉取该来源的正文内容" in source_content:
        return True
    return False


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

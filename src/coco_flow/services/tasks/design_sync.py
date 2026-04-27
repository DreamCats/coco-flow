from __future__ import annotations

from datetime import datetime
import json

from coco_flow.config import Settings, load_settings
from coco_flow.engines.design import locate_task_dir
from coco_flow.engines.shared.contracts import build_design_contracts_payload
from coco_flow.engines.shared.research import parse_repo_scopes, read_text_if_exists
from coco_flow.services.queries.task_detail import read_json_file
from coco_flow.services.tasks.design import STATUS_DESIGNED, build_design_sync_payload


def sync_design_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    status = str(task_meta.get("status") or "")
    if status not in {STATUS_DESIGNED, "planned"}:
        raise ValueError("只有 designed / planned 状态可以同步 Design 契约")

    design_markdown = read_text_if_exists(task_dir / "design.md")
    if not design_markdown.strip():
        raise ValueError("design.md 为空，无法同步 Design 契约")
    repo_scopes = parse_repo_scopes(read_json_file(task_dir / "repos.json"))
    if not repo_scopes:
        raise ValueError("当前没有绑定仓库，无法同步 Design 契约")

    contracts_payload = build_design_contracts_payload(design_markdown, repo_scopes)
    (task_dir / "design-contracts.json").write_text(json.dumps(contracts_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (task_dir / "design-sync.json").write_text(
        json.dumps(build_design_sync_payload(design_markdown, status="synced_from_markdown"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status

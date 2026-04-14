from __future__ import annotations

from pathlib import Path
import json
import os

from coco_flow.config import Settings, load_settings
from coco_flow.models import TaskDetail, TaskSummary, WorkspaceInfo
from coco_flow.services.repo_state import (
    read_repo_code_log,
    read_repo_code_result_raw,
    read_repo_diff_patch,
    read_repo_diff_summary,
)
from coco_flow.services.task_detail import (
    build_task_detail,
    read_artifact_content,
    read_json_file,
)

class TaskStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def workspace_info(self) -> WorkspaceInfo:
        return WorkspaceInfo(
            product_name="coco-flow",
            config_root=str(self.settings.config_root),
            task_root=str(self.settings.task_root),
            cwd=os.getcwd(),
        )

    def active_task_root(self) -> Path:
        return self.settings.task_root

    def list_tasks(self, limit: int = 50) -> list[TaskSummary]:
        root = self.settings.task_root
        tasks: list[TaskSummary] = []
        if not root.exists():
            return tasks
        for task_dir in root.iterdir():
            if not task_dir.is_dir():
                continue
            summary = self._load_task_summary(task_dir, "primary")
            if summary is None:
                continue
            tasks.append(summary)
        tasks.sort(
            key=lambda item: (item.updated_at or item.created_at or "", item.task_id),
            reverse=True,
        )
        return tasks[:limit]

    def get_task(self, task_id: str) -> TaskDetail | None:
        task_dir = self.settings.task_root / task_id
        if not task_dir.is_dir():
            return None
        metadata = read_json_file(task_dir / "task.json")
        if not metadata:
            return None
        source_meta = read_json_file(task_dir / "source.json")
        repos_meta = read_json_file(task_dir / "repos.json")
        return build_task_detail(task_dir, "primary", metadata, source_meta, repos_meta)

    def get_artifact(self, task_id: str, name: str, repo_id: str | None = None) -> str | None:
        task_dir = self.settings.task_root / task_id
        if not task_dir.is_dir():
            return None
        if repo_id:
            try:
                if name == "code.log":
                    return read_repo_code_log(task_dir, repo_id)
                if name == "code-result.json":
                    return read_repo_code_result_raw(task_dir, repo_id)
                if name == "diff.patch":
                    return read_repo_diff_patch(task_dir, repo_id)
                if name == "diff.json":
                    return json.dumps(read_repo_diff_summary(task_dir, repo_id), ensure_ascii=False, indent=2)
            except OSError:
                if name == "code.log":
                    return f"repo `{repo_id}` 当前没有可用的 code.log。可能尚未执行实现，或日志尚未生成。"
                if name == "code-result.json":
                    return f"repo `{repo_id}` 当前没有可用的 code-result.json。可能尚未执行实现。"
                if name in {"diff.patch", "diff.json"}:
                    return f"repo `{repo_id}` 当前没有可用的 {name}。可能尚未生成提交差异。"
                return f"repo `{repo_id}` 的 `{name}` 当前为空。"
            if name in {"code.log", "code-result.json", "diff.patch", "diff.json"}:
                return None
            return f"repo 级 artifact 暂不支持 {name}"
        if task_dir.is_dir():
            return read_artifact_content(task_dir, name)
        return None

    def ensure_primary_task_root(self) -> Path:
        self.settings.task_root.mkdir(parents=True, exist_ok=True)
        return self.settings.task_root

    def _load_task_summary(self, task_dir: Path, label: str) -> TaskSummary | None:
        task_json_path = task_dir / "task.json"
        payload: dict[str, object] = {}
        if task_json_path.exists():
            try:
                payload = json.loads(task_json_path.read_text())
            except (OSError, json.JSONDecodeError):
                payload = {}

        task_id = str(payload.get("task_id") or task_dir.name)
        title = str(payload.get("title") or task_id)
        status = str(payload.get("status") or "unknown")
        created_at = _optional_str(payload.get("created_at"))
        updated_at = _optional_str(payload.get("updated_at"))
        source_type = _optional_str(payload.get("source_type"))

        return TaskSummary(
            task_id=task_id,
            title=title,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            source_type=source_type,
            task_dir=str(task_dir),
            source_root=str(task_dir.parent),
            source_label=label,
        )

    def _has_task_dirs(self, root: Path) -> bool:
        if not root.exists():
            return False
        for child in root.iterdir():
            if child.is_dir():
                return True
        return False

def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _sort_key(item: TaskSummary) -> tuple[str, str]:
    return (item.updated_at or item.created_at or "", item.task_id)

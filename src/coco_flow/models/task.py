from __future__ import annotations

from pydantic import BaseModel


class TaskSummary(BaseModel):
    task_id: str
    title: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    source_type: str | None = None
    task_dir: str
    source_root: str
    source_label: str


class TaskListResponse(BaseModel):
    tasks: list[TaskSummary]


class RepoBinding(BaseModel):
    repo_id: str
    path: str
    status: str | None = None
    branch: str | None = None
    worktree: str | None = None
    commit: str | None = None
    build: str | None = None
    failure_type: str | None = None
    failure_hint: str | None = None
    failure_action: str | None = None
    files_written: list[str] | None = None
    diff_summary: dict[str, object] | None = None


class TimelineItem(BaseModel):
    label: str
    state: str
    detail: str


class ArtifactItem(BaseModel):
    name: str
    path: str
    exists: bool
    content: str | None = None


class TaskDetail(BaseModel):
    task_id: str
    title: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    source_type: str | None = None
    source_value: str | None = None
    source_fetch_error: str | None = None
    source_fetch_error_code: str | None = None
    repo_count: int = 0
    task_dir: str
    source_label: str
    next_action: str
    repos: list[RepoBinding]
    timeline: list[TimelineItem]
    artifacts: list[ArtifactItem]


class ArtifactContentResponse(BaseModel):
    task_id: str
    name: str
    content: str
    repo_id: str | None = None


class UpdateArtifactRequest(BaseModel):
    content: str


class UpdateArtifactResponse(BaseModel):
    task_id: str
    name: str
    status: str
    content: str


class CreateTaskRequest(BaseModel):
    input: str
    title: str | None = None
    repos: list[str]


class CreateTaskResponse(BaseModel):
    task_id: str
    status: str


class TaskActionResponse(BaseModel):
    task_id: str
    status: str


class WorkspaceInfo(BaseModel):
    product_name: str
    config_root: str
    task_root: str
    cwd: str

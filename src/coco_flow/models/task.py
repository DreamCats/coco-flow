from __future__ import annotations

from pydantic import BaseModel, Field


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
    scope_tier: str | None = None
    execution_mode: str | None = None
    batch_id: str | None = None
    batch_status: str | None = None
    work_item_ids: list[str] | None = None
    depends_on_batch_ids: list[str] | None = None
    branch: str | None = None
    worktree: str | None = None
    commit: str | None = None
    build: str | None = None
    failure_type: str | None = None
    failure_hint: str | None = None
    failure_action: str | None = None
    files_written: list[str] | None = None
    diff_summary: dict[str, object] | None = None
    verify_result: dict[str, object] | None = None


class TimelineItem(BaseModel):
    label: str
    state: str
    detail: str


class DiagnosisSummary(BaseModel):
    stage: str
    ok: bool
    severity: str
    failure_type: str = ""
    next_action: str
    reason: str = ""
    issue_count: int = 0


class ArtifactItem(BaseModel):
    name: str
    path: str
    exists: bool
    content: str | None = None


class CodeProgressSummary(BaseModel):
    status: str | None = None
    total_batches: int = 0
    completed_batches: int = 0
    running_batches: int = 0
    blocked_batches: int = 0
    failed_batches: int = 0
    total_work_items: int = 0
    completed_work_items: int = 0


class CodeDispatchSummary(BaseModel):
    total_batches: int = 0
    repo_ids: list[str] = Field(default_factory=list)
    batch_ids: list[str] = Field(default_factory=list)


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
    code_dispatch: CodeDispatchSummary | None = None
    code_progress: CodeProgressSummary | None = None
    diagnosis: DiagnosisSummary | None = None
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
    supplement: str | None = None
    repos: list[str] = Field(default_factory=list)


class CreateTaskResponse(BaseModel):
    task_id: str
    status: str


class TaskActionResponse(BaseModel):
    task_id: str
    status: str


class UpdateTaskReposRequest(BaseModel):
    repos: list[str] = Field(default_factory=list)


class WorkspaceInfo(BaseModel):
    product_name: str
    config_root: str
    task_root: str
    cwd: str

from __future__ import annotations

from pathlib import Path
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from coco_flow.models import (
    ArtifactContentResponse,
    CheckoutSkillSourceRequest,
    CreateSkillSourceRequest,
    CreateTaskRequest,
    CreateTaskResponse,
    SkillFileResponse,
    SkillSourceActionResponse,
    SkillSourcesResponse,
    SkillTreeResponse,
    TaskDetail,
    TaskActionResponse,
    TaskListResponse,
    UpdateTaskReposRequest,
    UpdateArtifactRequest,
    UpdateArtifactResponse,
)
from coco_flow.services import TaskStore
from coco_flow.engines.input import STATUS_INPUT_PROCESSING
from coco_flow.services.tasks.background import start_background_code, start_background_design, start_background_input, start_background_plan, start_background_refine
from coco_flow.services.tasks.input import create_task
from coco_flow.services.tasks.edit import update_artifact
from coco_flow.services.runtime.fs_tools import list_fs_entries, list_fs_roots
from coco_flow.services.runtime.build_meta import current_build_meta
from coco_flow.services.tasks.lifecycle import archive_task, reset_task
from coco_flow.services.tasks.code import start_coding_task
from coco_flow.services.tasks.design import start_designing_task
from coco_flow.services.tasks.design_sync import sync_design_task
from coco_flow.services.tasks.plan import start_planning_task
from coco_flow.services.tasks.plan_sync import sync_plan_task
from coco_flow.services.queries.repos import list_recent_repos, validate_repo_path
from coco_flow.services.tasks.repos import update_task_repos
from coco_flow.services.tasks.refine import start_refining_task
from coco_flow.api.presenters import task_detail_item, task_list_item
from coco_flow.services.queries.skills import SkillStore
from coco_flow.services.queries.workspace import workspace_summary


def create_app(task_store: TaskStore | None = None, static_dir: str | None = None) -> FastAPI:
    store = task_store or TaskStore()
    skill_store = SkillStore(store.settings)
    static_root = Path(static_dir).expanduser().resolve() if static_dir else None
    static_index = static_root / "index.html" if static_root else None
    app = FastAPI(
        title="coco-flow",
        summary="Workflow product layer for PRD, task, and worktree orchestration.",
        version="0.1.0",
    )
    app.state.started_at = datetime.now().astimezone().isoformat()
    app.state.build_meta = current_build_meta(started_at=app.state.started_at)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root():
        if static_index and static_index.exists():
            return FileResponse(static_index)
        return {
            "name": "coco-flow",
            "message": "coco-flow API is running",
        }

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/meta")
    def app_meta() -> dict[str, object]:
        return dict(app.state.build_meta)

    @app.get("/api/workspace")
    def workspace():
        return workspace_summary(store)

    @app.get("/api/tasks")
    def list_tasks(limit: int = 50):
        summaries = store.list_tasks(limit=limit)
        items = [task_list_item(summary, store.get_task(summary.task_id)) for summary in summaries]
        return {"tasks": items}

    @app.get("/api/skills/tree", response_model=SkillTreeResponse)
    def skills_tree(source: str) -> SkillTreeResponse:
        try:
            skill_source, nodes = skill_store.list_tree_for_source(source)
            return SkillTreeResponse(rootPath=str(skill_source.local_path), sourceId=skill_source.id, nodes=nodes)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/skills/file", response_model=SkillFileResponse)
    def read_skill_file(path: str, source: str) -> SkillFileResponse:
        try:
            source_id, resolved_path, content = skill_store.read_file(path, source_id=source)
            return SkillFileResponse(path=resolved_path, sourceId=source_id, content=content)
        except ValueError as error:
            message = str(error)
            status_code = 404 if "not found" in message else 400
            raise HTTPException(status_code=status_code, detail=message) from error

    @app.get("/api/skills/sources", response_model=SkillSourcesResponse)
    def skills_sources() -> SkillSourcesResponse:
        return SkillSourcesResponse(sources=skill_store.list_sources())

    @app.post("/api/skills/sources", response_model=SkillSourceActionResponse, status_code=201)
    def add_skill_source(payload: CreateSkillSourceRequest) -> SkillSourceActionResponse:
        try:
            source = skill_store.add_git_source(name=payload.name, url=payload.url, branch=payload.branch)
            return SkillSourceActionResponse(source=source)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/skills/sources/{source_id}/clone", response_model=SkillSourceActionResponse)
    def clone_skill_source(source_id: str) -> SkillSourceActionResponse:
        try:
            source, output = skill_store.clone_source(source_id)
            return SkillSourceActionResponse(source=source, output=output)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/skills/sources/{source_id}/pull", response_model=SkillSourceActionResponse)
    def pull_skill_source(source_id: str) -> SkillSourceActionResponse:
        try:
            source, output = skill_store.pull_source(source_id)
            return SkillSourceActionResponse(source=source, output=output)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/skills/sources/{source_id}/checkout", response_model=SkillSourceActionResponse)
    def checkout_skill_source(source_id: str, payload: CheckoutSkillSourceRequest) -> SkillSourceActionResponse:
        try:
            source, output = skill_store.checkout_source_branch(source_id, payload.branch)
            return SkillSourceActionResponse(source=source, output=output)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/api/skills/sources/{source_id}", response_model=SkillSourceActionResponse)
    def remove_skill_source(source_id: str) -> SkillSourceActionResponse:
        try:
            source = skill_store.remove_source(source_id)
            return SkillSourceActionResponse(source=source)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/tasks", response_model=CreateTaskResponse, status_code=202)
    def create_task_handler(payload: CreateTaskRequest) -> CreateTaskResponse:
        try:
            store.ensure_primary_task_root()
            task_id, status = create_task(
                raw_input=payload.input,
                title=payload.title,
                supplement=payload.supplement,
                repos=payload.repos,
                settings=store.settings,
                defer_lark_resolution=True,
            )
            if status == STATUS_INPUT_PROCESSING:
                start_background_input(task_id, store.settings)
            return CreateTaskResponse(task_id=task_id, status=status)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except FileExistsError as error:
            raise HTTPException(status_code=409, detail="task 已存在，请重试") from error

    @app.get("/api/repos/recent")
    def recent_repos():
        return {"repos": list_recent_repos(store)}

    @app.post("/api/repos/validate")
    def validate_repo(payload: dict[str, str]):
        path = str(payload.get("path") or "").strip()
        try:
            return validate_repo_path(path)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.put("/api/tasks/{task_id}/repos", response_model=TaskActionResponse)
    def update_task_repos_handler(task_id: str, payload: UpdateTaskReposRequest) -> TaskActionResponse:
        try:
            status = update_task_repos(task_id, payload.repos, settings=store.settings)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.get("/api/fs/roots")
    def fs_roots():
        return {"roots": list_fs_roots()}

    @app.get("/api/fs/list")
    def fs_list(path: str):
        try:
            resolved = str(Path(path).expanduser().resolve())
            return {
                "path": resolved,
                "parentPath": str(Path(resolved).parent),
                "entries": list_fs_entries(path),
            }
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        task = store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
        return task_detail_item(task)

    @app.delete("/api/tasks/{task_id}", response_model=TaskActionResponse)
    def delete_task(task_id: str) -> TaskActionResponse:
        task = store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
        if task.status not in {"initialized", "input_processing", "input_ready", "input_failed", "refined", "designing", "designed", "planned", "failed"}:
            raise HTTPException(status_code=409, detail=f"当前状态为 {task.status}，仅允许删除未进入 code 的 task")
        task_dir = store.settings.task_root / task_id
        if task_dir.exists():
            import shutil
            shutil.rmtree(task_dir)
        return TaskActionResponse(task_id=task_id, status="deleted")

    @app.post("/api/tasks/{task_id}/refine", response_model=TaskActionResponse, status_code=202)
    def refine_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = start_refining_task(task_id, settings=store.settings)
            start_background_refine(task_id, store.settings)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/design", response_model=TaskActionResponse, status_code=202)
    def design_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = start_designing_task(task_id, settings=store.settings)
            start_background_design(task_id, store.settings)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/plan", response_model=TaskActionResponse, status_code=202)
    def plan_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = start_planning_task(task_id, settings=store.settings)
            start_background_plan(task_id, store.settings)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/design/sync", response_model=TaskActionResponse)
    def sync_design_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = sync_design_task(task_id, settings=store.settings)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/plan/sync", response_model=TaskActionResponse)
    def sync_plan_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = sync_plan_task(task_id, settings=store.settings)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/code", response_model=TaskActionResponse, status_code=202)
    def code_task_handler(task_id: str, repo: str = "") -> TaskActionResponse:
        try:
            status = start_coding_task(task_id, settings=store.settings, repo_id=repo)
            start_background_code(task_id, store.settings, repo_id=repo)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/code-all", response_model=TaskActionResponse, status_code=202)
    def code_all_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = start_coding_task(task_id, settings=store.settings, all_repos=True)
            start_background_code(task_id, store.settings, all_repos=True)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/reset", response_model=TaskActionResponse)
    def reset_task_handler(task_id: str, repo: str = "") -> TaskActionResponse:
        try:
            status = reset_task(task_id, settings=store.settings, repo_id=repo)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/archive", response_model=TaskActionResponse)
    def archive_task_handler(task_id: str, repo: str = "") -> TaskActionResponse:
        try:
            status = archive_task(task_id, settings=store.settings, repo_id=repo)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.get("/api/tasks/{task_id}/artifact", response_model=ArtifactContentResponse)
    def get_task_artifact(task_id: str, name: str, repo: str = "") -> ArtifactContentResponse:
        content = store.get_artifact(task_id, name, repo_id=repo or None)
        if content is None:
            raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
        return ArtifactContentResponse(task_id=task_id, repo_id=repo or None, name=name, content=content)

    @app.put("/api/tasks/{task_id}/artifact", response_model=UpdateArtifactResponse)
    def update_task_artifact(
        task_id: str, name: str, payload: UpdateArtifactRequest, repo: str = ""
    ) -> UpdateArtifactResponse:
        try:
            status, content = update_artifact(
                task_id=task_id,
                name=name,
                content=payload.content,
                settings=store.settings,
                repo_id=repo or None,
            )
            return UpdateArtifactResponse(
                task_id=task_id,
                name=name,
                status=status,
                content=content,
            )
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    if static_root and static_root.is_dir():
        assets_dir = static_root / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{path_name:path}")
        def spa_fallback(path_name: str):
            if static_index and static_index.exists():
                return FileResponse(static_index)
            raise HTTPException(status_code=404, detail=f"path not found: {path_name}")

    return app

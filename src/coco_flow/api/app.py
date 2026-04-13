from __future__ import annotations

from pathlib import Path
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from coco_flow.models import (
    ArtifactContentResponse,
    CreateTaskRequest,
    CreateTaskResponse,
    TaskDetail,
    TaskActionResponse,
    TaskListResponse,
    UpdateArtifactRequest,
    UpdateArtifactResponse,
)
from coco_flow.services import TaskStore
from coco_flow.services.task_background import start_background_plan, start_background_refine
from coco_flow.services.task_code import code_task
from coco_flow.services.task_create import create_task
from coco_flow.services.task_edit import update_artifact
from coco_flow.services.fs_tools import list_fs_entries, list_fs_roots
from coco_flow.services.task_lifecycle import archive_task, reset_task
from coco_flow.services.task_plan import start_planning_task
from coco_flow.services.repo_tools import list_recent_repos, validate_repo_path
from coco_flow.services.task_refine import refine_task
from coco_flow.services.view_compat import task_detail_item, task_list_item
from coco_flow.services.workspace_tools import workspace_summary


def create_app(task_store: TaskStore | None = None, static_dir: str | None = None) -> FastAPI:
    store = task_store or TaskStore()
    static_root = Path(static_dir).expanduser().resolve() if static_dir else None
    static_index = static_root / "index.html" if static_root else None
    app = FastAPI(
        title="coco-flow",
        summary="Workflow product layer for PRD, task, and worktree orchestration.",
        version="0.1.0",
    )
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

    @app.get("/api/workspace")
    def workspace():
        return workspace_summary(store)

    @app.get("/api/tasks")
    def list_tasks(limit: int = 50):
        summaries = store.list_tasks(limit=limit)
        items = [task_list_item(summary, store.get_task(summary.task_id)) for summary in summaries]
        return {"tasks": items}

    @app.post("/api/tasks", response_model=CreateTaskResponse, status_code=202)
    def create_task_handler(payload: CreateTaskRequest) -> CreateTaskResponse:
        try:
            store.ensure_primary_task_root()
            task_id, status = create_task(
                raw_input=payload.input,
                title=payload.title,
                repos=payload.repos,
                settings=store.settings,
            )
            start_background_refine(task_id, store.settings)
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
        if task.status not in {"initialized", "refined", "planned", "failed"}:
            raise HTTPException(status_code=409, detail=f"当前状态为 {task.status}，仅允许删除未进入 code 的 task")
        task_dir = store.settings.task_root / task_id
        if task_dir.exists():
            import shutil
            shutil.rmtree(task_dir)
        return TaskActionResponse(task_id=task_id, status="deleted")

    @app.post("/api/tasks/{task_id}/refine", response_model=TaskActionResponse)
    def refine_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = refine_task(task_id, settings=store.settings)
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

    @app.post("/api/tasks/{task_id}/code", response_model=TaskActionResponse)
    def code_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = code_task(task_id, settings=store.settings)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/code-all", response_model=TaskActionResponse)
    def code_all_task_handler(task_id: str) -> TaskActionResponse:
        return code_task_handler(task_id)

    @app.post("/api/tasks/{task_id}/reset", response_model=TaskActionResponse)
    def reset_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = reset_task(task_id, settings=store.settings)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.post("/api/tasks/{task_id}/archive", response_model=TaskActionResponse)
    def archive_task_handler(task_id: str) -> TaskActionResponse:
        try:
            status = archive_task(task_id, settings=store.settings)
            return TaskActionResponse(task_id=task_id, status=status)
        except ValueError as error:
            message = str(error)
            if "not found" in message:
                raise HTTPException(status_code=404, detail=message) from error
            raise HTTPException(status_code=409, detail=message) from error

    @app.get("/api/tasks/{task_id}/artifact", response_model=ArtifactContentResponse)
    def get_task_artifact(task_id: str, name: str) -> ArtifactContentResponse:
        content = store.get_artifact(task_id, name)
        if content is None:
            raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
        return ArtifactContentResponse(task_id=task_id, name=name, content=content)

    @app.put("/api/tasks/{task_id}/artifact", response_model=UpdateArtifactResponse)
    def update_task_artifact(
        task_id: str, name: str, payload: UpdateArtifactRequest
    ) -> UpdateArtifactResponse:
        try:
            status, content = update_artifact(
                task_id=task_id,
                name=name,
                content=payload.content,
                settings=store.settings,
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

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import threading
import uuid

from coco_flow.config import Settings
from coco_flow.models import KnowledgeGenerationJob
from coco_flow.services.knowledge.generation import KnowledgeDraftInput
from coco_flow.services.queries.knowledge import KnowledgeStore

JOB_DIR_NAME = "jobs"


def start_background_generation(payload: KnowledgeDraftInput, settings: Settings) -> KnowledgeGenerationJob:
    store = KnowledgeStore(settings)
    store.ensure_root()
    now = datetime.now().astimezone().isoformat()
    job = KnowledgeGenerationJob(
        job_id=f"knowledge-job-{datetime.now().astimezone():%Y%m%d}-{uuid.uuid4().hex[:8]}",
        status="queued",
        progress=0,
        stage_label="等待开始",
        message="已创建生成任务，等待后台线程启动。",
        created_at=now,
        updated_at=now,
    )
    _write_job(settings, job, payload)
    worker = threading.Thread(
        target=_run_generation_job,
        args=(settings, job.job_id),
        name=f"coco-flow-knowledge-{job.job_id}",
        daemon=True,
    )
    worker.start()
    return job


def get_generation_job(job_id: str, settings: Settings) -> KnowledgeGenerationJob:
    job_path = _job_path(settings, job_id)
    if not job_path.is_file():
        raise ValueError(f"knowledge generation job not found: {job_id}")
    payload = json.loads(job_path.read_text(encoding="utf-8"))
    return KnowledgeGenerationJob(**payload["job"])


def retry_background_generation(job_id: str, settings: Settings) -> KnowledgeGenerationJob:
    payload = _read_job_payload(settings, job_id)
    return start_background_generation(KnowledgeDraftInput(**payload["payload"]), settings)


def _run_generation_job(settings: Settings, job_id: str) -> None:
    job_payload = _read_job_payload(settings, job_id)
    payload = KnowledgeDraftInput(**job_payload["payload"])
    store = KnowledgeStore(settings)
    try:
        _update_job(
            settings,
            job_id,
            status="running",
            progress=5,
            stage_label="准备中",
            message="后台知识生成任务已启动。",
        )
        result = store.create_drafts(
            payload,
            on_progress=lambda status, progress, message: _update_job(
                settings,
                job_id,
                status=status,
                progress=progress,
                stage_label=_stage_label(status),
                message=message,
            ),
        )
        _update_job(
            settings,
            job_id,
            status="completed",
            progress=100,
            stage_label="已完成",
            message="知识草稿已生成完成。",
            trace_id=result.trace_id,
            document_ids=[document.id for document in result.documents],
            open_questions=result.open_questions,
            error="",
        )
    except Exception as error:
        _update_job(
            settings,
            job_id,
            status="failed",
            progress=100,
            stage_label="失败",
            message="知识草稿生成失败。",
            error=str(error),
        )


def _write_job(settings: Settings, job: KnowledgeGenerationJob, payload: KnowledgeDraftInput) -> None:
    target = _job_path(settings, job.job_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "job": job.model_dump(),
                "payload": {
                    "description": payload.description,
                    "selected_paths": payload.selected_paths,
                    "kinds": payload.kinds,
                    "notes": payload.notes,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_job_payload(settings: Settings, job_id: str) -> dict[str, object]:
    path = _job_path(settings, job_id)
    if not path.is_file():
        raise ValueError(f"knowledge generation job not found: {job_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _update_job(
    settings: Settings,
    job_id: str,
    *,
    status: str,
    progress: int,
    stage_label: str,
    message: str,
    trace_id: str | None = None,
    document_ids: list[str] | None = None,
    open_questions: list[str] | None = None,
    error: str | None = None,
) -> None:
    payload = _read_job_payload(settings, job_id)
    current = KnowledgeGenerationJob(**payload["job"])
    updated = current.model_copy(
        update={
            "status": status,
            "progress": progress,
            "stage_label": stage_label,
            "message": message,
            "updated_at": datetime.now().astimezone().isoformat(),
            "trace_id": trace_id if trace_id is not None else current.trace_id,
            "document_ids": document_ids if document_ids is not None else current.document_ids,
            "open_questions": open_questions if open_questions is not None else current.open_questions,
            "error": error if error is not None else current.error,
        }
    )
    payload["job"] = updated.model_dump()
    _job_path(settings, job_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _job_path(settings: Settings, job_id: str) -> Path:
    return settings.knowledge_root / JOB_DIR_NAME / f"{job_id}.json"


def _stage_label(status: str) -> str:
    return {
        "queued": "排队中",
        "running": "准备中",
        "intent_normalizing": "意图收敛",
        "repo_discovering": "Repo 发现",
        "repo_researching": "Repo 研究",
        "synthesizing": "草稿生成",
        "validating": "结果校验",
        "persisting": "落盘中",
        "completed": "已完成",
        "failed": "失败",
    }.get(status, status)

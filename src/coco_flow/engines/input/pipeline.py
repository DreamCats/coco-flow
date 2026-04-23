from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from coco_flow.config import Settings
from coco_flow.engines.shared.manual_extract import require_manual_extract
from coco_flow.services.queries.task_detail import read_json_file

from .models import InputSections
from .models import InputTaskResult, ResolvedSource, STATUS_INPUT_FAILED, STATUS_INPUT_PROCESSING, STATUS_INPUT_READY, SOURCE_TYPE_LARK_DOC
from .persist import build_task_id, derive_repo_id, write_json
from .render import build_source_markdown
from .sources import classify_source_fetch_error, fetch_lark_doc_markdown, normalize_repo_paths, resolve_lark_doc_token, resolve_source, split_input_sections

LogHandler = Callable[[str], None]


def create_input_task(
    raw_input: str,
    title: str | None,
    supplement: str | None,
    repos: list[str],
    settings: Settings,
    defer_lark_resolution: bool,
) -> InputTaskResult:
    sections = split_input_sections(raw_input, supplement)
    normalized_source_input = sections.source_input.strip()
    if not normalized_source_input:
        raise ValueError("input 不能为空")
    normalized_manual_extract = require_manual_extract(sections.supplement)
    sections = InputSections(source_input=normalized_source_input, supplement=normalized_manual_extract)
    normalized_repos = normalize_repo_paths(repos)

    resolved_source = resolve_source(
        normalized_source_input,
        title,
        defer_lark_resolution=defer_lark_resolution,
    )
    task_id = build_task_id(resolved_source.title)
    task_dir = settings.task_root / task_id
    task_dir.mkdir(parents=True, exist_ok=False)
    now = datetime.now().astimezone()
    status = initial_input_status(resolved_source)
    write_initial_artifacts(
        task_dir=task_dir,
        task_id=task_id,
        title=resolved_source.title,
        explicit_title=bool(title and title.strip()),
        sections=sections,
        resolved_source=resolved_source,
        repos=normalized_repos,
        status=status,
        now=now,
    )
    if status == STATUS_INPUT_READY:
        append_input_log(task_dir, "=== INPUT START ===")
        append_input_log(task_dir, f"task_id: {task_id}")
        append_input_log(task_dir, f"status: {status}")
        append_input_log(task_dir, f"source_type: {resolved_source.source_type}")
        append_input_log(task_dir, "result: input ready")
        append_input_log(task_dir, "=== INPUT END ===")
    elif status == STATUS_INPUT_PROCESSING:
        append_input_log(task_dir, f"queued: input processing for {resolved_source.source_type}")
    return InputTaskResult(task_id=task_id, status=status)


def run_input_engine(task_id: str, settings: Settings, on_log: LogHandler | None = None) -> str:
    task_dir = settings.task_root / task_id
    if not task_dir.is_dir():
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    input_meta = read_json_file(task_dir / "input.json")
    source_meta = read_json_file(task_dir / "source.json")
    if not task_meta or not input_meta or not source_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    logger = on_log or (lambda line: append_input_log(task_dir, line))
    source_type = str(source_meta.get("type") or task_meta.get("source_type") or "")
    current_status = str(task_meta.get("status") or "")
    if source_type != SOURCE_TYPE_LARK_DOC:
        if current_status != STATUS_INPUT_READY:
            update_input_task_status(task_dir, task_meta, input_meta, source_meta, status=STATUS_INPUT_READY)
        logger("result: input ready")
        return STATUS_INPUT_READY

    raw_input = str(input_meta.get("source_input") or task_meta.get("source_value") or "").strip()
    explicit_title = bool(input_meta.get("title_explicit"))
    explicit_title_value = str(task_meta.get("title") or "").strip() if explicit_title else None
    supplement = str(input_meta.get("supplement") or "")
    try:
        doc_token, inferred_title = resolve_lark_doc_token(raw_input)
        content, fetched_title = fetch_lark_doc_markdown(doc_token)
        final_title = explicit_title_value or fetched_title or inferred_title or str(task_meta.get("title") or task_id)
        resolved_source = ResolvedSource(
            source_type=SOURCE_TYPE_LARK_DOC,
            title=final_title,
            source_value=raw_input,
            content=content.strip(),
            url=raw_input,
            doc_token=doc_token,
        )
        source_meta.update(
            {
                "title": final_title,
                "url": raw_input,
                "doc_token": doc_token,
                "fetch_error": "",
                "fetch_error_code": "",
                "captured_at": datetime.now().astimezone().isoformat(),
            }
        )
        input_meta["source_type"] = SOURCE_TYPE_LARK_DOC
        input_meta["resolved_title"] = final_title
        task_meta["title"] = final_title
        (task_dir / "prd.source.md").write_text(
            build_source_markdown(resolved_source, supplement, datetime.now().astimezone()),
            encoding="utf-8",
        )
        update_input_task_status(task_dir, task_meta, input_meta, source_meta, status=STATUS_INPUT_READY)
        logger(f"source_doc_token: {doc_token}")
        logger("result: input ready")
        return STATUS_INPUT_READY
    except ValueError as error:
        message = str(error)
        source_meta["fetch_error"] = message
        source_meta["fetch_error_code"] = classify_source_fetch_error(message)
        source_meta["captured_at"] = datetime.now().astimezone().isoformat()
        task_meta["updated_at"] = datetime.now().astimezone().isoformat()
        input_meta["status"] = STATUS_INPUT_FAILED
        write_json(task_dir / "source.json", source_meta)
        write_json(task_dir / "input.json", input_meta)
        (task_dir / "prd.source.md").write_text(
            build_source_markdown(
                ResolvedSource(
                    source_type=SOURCE_TYPE_LARK_DOC,
                    title=str(task_meta.get("title") or task_id),
                    source_value=raw_input,
                    content="",
                    url=raw_input,
                    doc_token=str(source_meta.get("doc_token") or ""),
                    fetch_error=message,
                    fetch_error_code=str(source_meta.get("fetch_error_code") or ""),
                ),
                supplement,
                datetime.now().astimezone(),
            ),
            encoding="utf-8",
        )
        update_input_task_status(task_dir, task_meta, input_meta, source_meta, status=STATUS_INPUT_FAILED)
        logger(f"error: {message}")
        return STATUS_INPUT_FAILED


def initial_input_status(resolved_source: ResolvedSource) -> str:
    if resolved_source.needs_async_processing:
        return STATUS_INPUT_PROCESSING
    if resolved_source.fetch_error:
        return STATUS_INPUT_FAILED
    return STATUS_INPUT_READY


def write_initial_artifacts(
    task_dir: Path,
    task_id: str,
    title: str,
    explicit_title: bool,
    sections: InputSections,
    resolved_source: ResolvedSource,
    repos: list[str],
    status: str,
    now: datetime,
) -> None:
    supplement = sections.supplement
    source_input = sections.source_input
    write_json(
        task_dir / "task.json",
        {
            "task_id": task_id,
            "title": title,
            "status": status,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "source_type": resolved_source.source_type,
            "source_value": resolved_source.source_value,
            "repo_count": len(repos),
        },
    )
    write_json(
        task_dir / "input.json",
        {
            "title": title,
            "title_explicit": explicit_title,
            "source_input": source_input,
            "supplement": supplement,
            "source_type": resolved_source.source_type,
            "status": status,
            "captured_at": now.isoformat(),
        },
    )
    source_payload: dict[str, object] = {
        "type": resolved_source.source_type,
        "title": title,
        "captured_at": now.isoformat(),
    }
    if resolved_source.path:
        source_payload["path"] = resolved_source.path
    if resolved_source.url:
        source_payload["url"] = resolved_source.url
    if resolved_source.doc_token:
        source_payload["doc_token"] = resolved_source.doc_token
    if resolved_source.fetch_error:
        source_payload["fetch_error"] = resolved_source.fetch_error
    if resolved_source.fetch_error_code:
        source_payload["fetch_error_code"] = resolved_source.fetch_error_code
    write_json(task_dir / "source.json", source_payload)
    write_json(
        task_dir / "repos.json",
        {
            "repos": [
                {
                    "id": derive_repo_id(path),
                    "path": path,
                    "status": STATUS_INITIALIZED,
                }
                for path in repos
            ]
        },
    )
    (task_dir / "prd.source.md").write_text(
        build_source_markdown(resolved_source, supplement, now),
        encoding="utf-8",
    )


def update_input_task_status(
    task_dir: Path,
    task_meta: dict[str, object],
    input_meta: dict[str, object],
    source_meta: dict[str, object],
    status: str,
) -> None:
    now = datetime.now().astimezone().isoformat()
    task_meta["status"] = status
    task_meta["updated_at"] = now
    input_meta["status"] = status
    source_meta["captured_at"] = now
    write_json(task_dir / "task.json", task_meta)
    write_json(task_dir / "input.json", input_meta)
    write_json(task_dir / "source.json", source_meta)


def append_input_log(task_dir: Path, line: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    log_path = task_dir / "input.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{timestamp} {line}\n")

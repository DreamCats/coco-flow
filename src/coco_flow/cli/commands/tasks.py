from __future__ import annotations

import json

import typer

from coco_flow.services import TaskStore
from coco_flow.services.tasks.code import code_task
from coco_flow.services.tasks.design import design_task
from coco_flow.services.tasks.lifecycle import archive_task, reset_task
from coco_flow.services.tasks.plan import plan_task
from coco_flow.services.tasks.refine import refine_task

from ..app import tasks_app


@tasks_app.command("list")
def list_tasks(
    limit: int = typer.Option(20, min=1, max=500, help="Max number of tasks to show."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
    status: str = typer.Option("", help="Filter by task status."),
) -> None:
    store = TaskStore()
    summaries = store.list_tasks(limit=500)
    if status.strip():
        summaries = [task for task in summaries if task.status == status.strip()]
    tasks = [task.model_dump() for task in summaries[:limit]]
    if as_json:
        typer.echo(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2))
        return

    if not tasks:
        typer.echo("No tasks found.")
        return

    for task in tasks:
        typer.echo(
            f"{task['task_id']} [{task['status']}] {task['title']} "
            f"({task['source_label']}:{task['source_root']})"
        )


@tasks_app.command("roots")
def task_roots() -> None:
    store = TaskStore()
    workspace = store.workspace_info()
    typer.echo(f"config_root: {workspace.config_root}")
    typer.echo(f"task_root: {workspace.task_root}")


@tasks_app.command("refine")
def refine_task_cmd(task_id: str) -> None:
    try:
        status = refine_task(task_id)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"{task_id}: {status}")


@tasks_app.command("design")
def design_task_cmd(task_id: str) -> None:
    try:
        status = design_task(task_id)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"{task_id}: {status}")


@tasks_app.command("plan")
def plan_task_cmd(task_id: str) -> None:
    try:
        status = plan_task(task_id)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"{task_id}: {status}")


@tasks_app.command("code")
def code_task_cmd(
    task_id: str,
    repo: str = typer.Option("", help="Run code for a specific repo in a multi-repo task."),
    all_repos: bool = typer.Option(False, help="Run remaining repos in order for a multi-repo task."),
) -> None:
    try:
        status = code_task(task_id, repo_id=repo, all_repos=all_repos)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"{task_id}: {status}")


@tasks_app.command("reset")
def reset_task_cmd(task_id: str) -> None:
    try:
        status = reset_task(task_id)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"{task_id}: {status}")


@tasks_app.command("archive")
def archive_task_cmd(task_id: str) -> None:
    try:
        status = archive_task(task_id)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"{task_id}: {status}")

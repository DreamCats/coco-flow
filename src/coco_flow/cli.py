from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import subprocess

import typer
import uvicorn

from coco_flow.api import create_app
from coco_flow.config import load_settings
from coco_flow.daemon_client import shutdown as shutdown_daemon, start_daemon, status as daemon_status, wait_for_daemon
from coco_flow.daemon_server import run_daemon_server
from coco_flow.services import TaskStore
from coco_flow.services.task_code import code_task
from coco_flow.services.task_lifecycle import archive_task, reset_task
from coco_flow.services.task_plan import plan_task
from coco_flow.services.task_refine import refine_task

app = typer.Typer(
    help="coco-flow: workflow product layer for PRD, task, worktree, and local API.",
    no_args_is_help=True,
)
api_app = typer.Typer(help="Run the local FastAPI service.")
tasks_app = typer.Typer(help="Inspect task roots and task summaries.")
ui_app = typer.Typer(help="Serve the built web UI together with the local API.")
daemon_app = typer.Typer(help="Manage the local coco-flow ACP daemon.")
app.add_typer(api_app, name="api")
app.add_typer(tasks_app, name="tasks")
app.add_typer(ui_app, name="ui")
app.add_typer(daemon_app, name="daemon")


@app.command("version")
def version_cmd() -> None:
    typer.echo(f"coco-flow {package_version()}")


@tasks_app.command("list")
def list_tasks(
    limit: int = typer.Option(20, min=1, max=500, help="Max number of tasks to show."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    store = TaskStore()
    tasks = [task.model_dump() for task in store.list_tasks(limit=limit)]
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


@tasks_app.command("plan")
def plan_task_cmd(task_id: str) -> None:
    try:
        status = plan_task(task_id)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"{task_id}: {status}")


@tasks_app.command("code")
def code_task_cmd(task_id: str) -> None:
    try:
        status = code_task(task_id)
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


@api_app.command("serve")
def serve_api(
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(4318, min=1, max=65535, help="Bind port."),
    reload: bool = typer.Option(False, help="Enable reload for local development."),
) -> None:
    uvicorn.run(
        "coco_flow.api:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@ui_app.command("serve")
def serve_ui(
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(4318, min=1, max=65535, help="Bind port."),
    web_dir: str = typer.Option("", help="Override the static web directory."),
    build_web: bool = typer.Option(True, "--build/--no-build", help="Build the web UI before serving."),
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    resolved_web_dir = Path(web_dir).expanduser().resolve() if web_dir else project_root / "web" / "dist"
    source_web_dir = project_root / "web"

    if build_web:
        ensure_web_build(source_web_dir)

    if not resolved_web_dir.is_dir():
        raise typer.BadParameter(f"web dir does not exist: {resolved_web_dir}")

    typer.echo(f"coco-flow ui serve")
    typer.echo(f"  host: {host}")
    typer.echo(f"  port: {port}")
    typer.echo(f"  web: {resolved_web_dir}")
    uvicorn.run(
        create_app(static_dir=str(resolved_web_dir)),
        host=host,
        port=port,
    )


@daemon_app.command("serve")
def serve_daemon() -> None:
    run_daemon_server(load_settings())


@daemon_app.command("start")
def start_daemon_cmd() -> None:
    settings = load_settings()
    start_daemon(settings)
    wait_for_daemon(settings)
    typer.echo("coco-flow daemon started")


@daemon_app.command("status")
def daemon_status_cmd() -> None:
    info = daemon_status(load_settings())
    typer.echo(json.dumps(info, ensure_ascii=False, indent=2))


@daemon_app.command("stop")
def stop_daemon_cmd() -> None:
    shutdown_daemon(load_settings())
    typer.echo("coco-flow daemon stopped")


def package_version() -> str:
    try:
        return version("coco-flow")
    except PackageNotFoundError:
        return "0.1.0"


def main() -> None:
    app()


def ensure_web_build(web_root: Path) -> None:
    if not web_root.is_dir():
        raise typer.BadParameter(f"web source directory not found: {web_root}")

    node_modules = web_root / "node_modules"
    if not node_modules.is_dir():
        install = subprocess.run(
            ["npm", "install"],
            cwd=web_root,
            check=False,
        )
        if install.returncode != 0:
            raise typer.Exit(code=install.returncode)

    build = subprocess.run(
        ["npm", "run", "build"],
        cwd=web_root,
        check=False,
    )
    if build.returncode != 0:
        raise typer.Exit(code=build.returncode)

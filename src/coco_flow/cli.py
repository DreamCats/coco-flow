from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import subprocess

import typer
import uvicorn

from coco_flow.api import create_app
from coco_flow.config import load_settings
from coco_flow.daemon.client import shutdown as shutdown_daemon, start_daemon, status as daemon_status, wait_for_daemon
from coco_flow.daemon.server import run_daemon_server
from coco_flow.services import TaskStore
from coco_flow.services.queries.knowledge import KnowledgeStore
from coco_flow.services.tasks.code import code_task
from coco_flow.services.tasks.design import design_task
from coco_flow.services.tasks.lifecycle import archive_task, reset_task
from coco_flow.services.tasks.plan import plan_task
from coco_flow.services.tasks.refine import refine_task

app = typer.Typer(
    help="coco-flow: workflow product layer for PRD, task, worktree, and local API.",
    no_args_is_help=True,
)
api_app = typer.Typer(help="Run the local FastAPI service.")
tasks_app = typer.Typer(help="Inspect task roots and task summaries.")
ui_app = typer.Typer(help="Serve the built web UI together with the local API.")
daemon_app = typer.Typer(help="Manage the local coco-flow ACP daemon.")
knowledge_app = typer.Typer(help="Manage knowledge documents.")
app.add_typer(api_app, name="api")
app.add_typer(tasks_app, name="tasks")
app.add_typer(ui_app, name="ui")
app.add_typer(daemon_app, name="daemon")
app.add_typer(knowledge_app, name="knowledge")

_PROJECT_MARKERS = ("pyproject.toml", "src/coco_flow/cli.py")
_PYTHON_VERSION = "3.13"


@app.command("version")
def version_cmd(
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    version_value = package_version()
    if as_json:
        typer.echo(json.dumps({"name": "coco-flow", "version": version_value}, ensure_ascii=False, indent=2))
        return
    typer.echo(f"coco-flow {version_value}")


@app.command("install")
def install_cmd(
    path: str = typer.Option(".", "--path", help="coco-flow repo root."),
    with_ui: bool = typer.Option(False, "--with-ui/--no-ui", help="Install web dependencies under web/."),
    install_python: bool = typer.Option(True, "--install-python/--skip-python", help="Install Python 3.13 with uv first."),
) -> None:
    project_root = resolve_project_root(path)
    if install_python:
        run_project_command(["uv", "python", "install", _PYTHON_VERSION], cwd=project_root)
    install_tool_from_project(project_root)
    if with_ui:
        run_project_command(["npm", "install"], cwd=project_root / "web")
    typer.echo(f"installed tool: coco-flow ({project_root})")
    typer.echo(f"bin dir: {tool_bin_dir(project_root)}")


@app.command("update")
def update_cmd(
    path: str = typer.Option(".", "--path", help="coco-flow repo root."),
    pull: bool = typer.Option(True, "--pull/--no-pull", help="Run git pull --ff-only before syncing."),
    with_ui: bool = typer.Option(False, "--with-ui/--no-ui", help="Refresh web dependencies under web/."),
) -> None:
    project_root = resolve_project_root(path)
    if pull:
        ensure_git_checkout(project_root)
        run_project_command(["git", "pull", "--ff-only"], cwd=project_root)
    run_project_command(["uv", "python", "upgrade", _PYTHON_VERSION], cwd=project_root)
    install_tool_from_project(project_root)
    if with_ui:
        run_project_command(["npm", "install"], cwd=project_root / "web")
    typer.echo(f"updated tool: coco-flow ({project_root})")
    typer.echo(f"bin dir: {tool_bin_dir(project_root)}")


@app.command("start")
def start_cmd(
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(4318, min=1, max=65535, help="Bind port."),
    web_dir: str = typer.Option("", help="Override the static web directory."),
    build_web: bool = typer.Option(True, "--build/--no-build", help="Build the web UI before serving."),
    api_only: bool = typer.Option(False, "--api-only", help="Start API only without the bundled UI."),
    reload: bool = typer.Option(False, help="Enable reload when using --api-only."),
) -> None:
    if api_only:
        serve_api(host=host, port=port, reload=reload)
        return
    serve_ui(host=host, port=port, web_dir=web_dir, build_web=build_web)


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


@knowledge_app.command("list")
def knowledge_list_cmd(
    limit: int = typer.Option(50, min=1, max=500, help="Max number of documents to show."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
    status: str = typer.Option("", help="Filter by knowledge status."),
    kind: str = typer.Option("", help="Filter by knowledge kind."),
) -> None:
    store = KnowledgeStore(load_settings())
    documents = store.list_documents()
    if status.strip():
        documents = [document for document in documents if document.status == status.strip()]
    if kind.strip():
        documents = [document for document in documents if document.kind == kind.strip()]
    documents = documents[:limit]
    if as_json:
        typer.echo(json.dumps({"documents": [document.model_dump() for document in documents]}, ensure_ascii=False, indent=2))
        return
    if not documents:
        typer.echo("No knowledge documents found.")
        return
    for document in documents:
        typer.echo(f"{document.id} [{document.status}] {document.domainName} / {document.kind} / {document.title}")


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


def resolve_project_root(raw_path: str) -> Path:
    project_root = Path(raw_path).expanduser().resolve()
    if not all((project_root / marker).exists() for marker in _PROJECT_MARKERS):
        raise typer.BadParameter(f"not a coco-flow project root: {project_root}")
    return project_root


def ensure_git_checkout(project_root: Path) -> None:
    if not (project_root / ".git").exists():
        raise typer.BadParameter(f"git checkout not found: {project_root}")


def install_tool_from_project(project_root: Path) -> None:
    run_project_command(
        ["uv", "tool", "install", "--force", "--python", _PYTHON_VERSION, "--editable", str(project_root)],
        cwd=project_root,
    )
    run_project_command(["uv", "tool", "update-shell"], cwd=project_root)


def tool_bin_dir(project_root: Path) -> str:
    result = subprocess.run(
        ["uv", "tool", "dir", "--bin"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
    return result.stdout.strip()


def run_project_command(args: list[str], cwd: Path) -> None:
    typer.echo(f"$ {' '.join(args)}")
    result = subprocess.run(args, cwd=cwd, check=False)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)

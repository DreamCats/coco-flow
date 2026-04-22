from __future__ import annotations

import json

import typer

from coco_flow.config import load_settings

from ..app import api_app, app, ui_app
from .. import project as cli_project
from .. import server as cli_server


@app.command("version")
def version_cmd(
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    version_value = cli_project.package_version()
    if as_json:
        typer.echo(json.dumps({"name": "coco-flow", "version": version_value}, ensure_ascii=False, indent=2))
        return
    typer.echo(f"coco-flow {version_value}")


@app.command("install")
def install_cmd(
    path: str = typer.Option(".", "--path", help="coco-flow repo root."),
    no_ui: bool = typer.Option(False, "--no-ui", help="Skip web dependencies under web/."),
    install_python: bool = typer.Option(True, "--install-python/--skip-python", help="Install Python 3.13 with uv first."),
) -> None:
    project_root = cli_project.resolve_project_root(path)
    if install_python:
        cli_project.run_project_command(["uv", "python", "install", cli_project._PYTHON_VERSION], cwd=project_root)
    cli_project.install_tool_from_project(project_root)
    if not no_ui:
        cli_project.run_project_command(["npm", "install"], cwd=project_root / "web")
    typer.echo(f"installed tool: coco-flow ({project_root})")
    typer.echo(f"bin dir: {cli_project.tool_bin_dir(project_root)}")


@app.command("update")
def update_cmd(
    path: str = typer.Option("", "--path", help="coco-flow repo root. Defaults to the installed repo."),
    pull: bool = typer.Option(True, "--pull/--no-pull", help="Run git pull --ff-only before syncing."),
    no_ui: bool = typer.Option(False, "--no-ui", help="Skip web dependencies under web/."),
) -> None:
    project_root = cli_project.resolve_project_root(path or str(cli_project.installed_repo_root()))
    if pull:
        cli_project.ensure_git_checkout(project_root)
        cli_project.run_project_command(["git", "pull", "--ff-only"], cwd=project_root)
    cli_project.run_project_command(["uv", "python", "upgrade", cli_project._PYTHON_VERSION], cwd=project_root)
    cli_project.install_tool_from_project(project_root)
    if not no_ui:
        cli_project.run_project_command(["npm", "install"], cwd=project_root / "web")
    typer.echo(f"updated tool: coco-flow ({project_root})")
    typer.echo(f"bin dir: {cli_project.tool_bin_dir(project_root)}")


@app.command("start")
def start_cmd(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(4318, min=1, max=65535, help="Bind port."),
    web_dir: str = typer.Option("", help="Override the static web directory."),
    build_web: bool = typer.Option(True, "--build/--no-build", help="Build the web UI before serving."),
    api_only: bool = typer.Option(False, "--api-only", help="Start API only without the bundled UI."),
    reload: bool = typer.Option(False, help="Enable reload when using --api-only."),
    detach: bool = typer.Option(False, "--detach", help="Run the server in background."),
) -> None:
    if detach:
        cli_server.start_server_in_background(
            host=host,
            port=port,
            web_dir=web_dir,
            build_web=build_web,
            api_only=api_only,
            reload=reload,
        )
        return
    if api_only:
        cli_server.serve_api(host=host, port=port, reload=reload)
        return
    cli_server.serve_ui(host=host, port=port, web_dir=web_dir, build_web=build_web)


@app.command("status")
def server_status_cmd() -> None:
    typer.echo(json.dumps(cli_server.server_status(load_settings()), ensure_ascii=False, indent=2))


@app.command("stop")
def stop_server_cmd() -> None:
    cfg = load_settings()
    info = cli_server.server_status(cfg)
    if not info["running"]:
        typer.echo("coco-flow server not running")
        return
    cli_server.stop_server(cfg)
    typer.echo("coco-flow server stopped")


@api_app.command("serve")
def serve_api_cmd(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(4318, min=1, max=65535, help="Bind port."),
    reload: bool = typer.Option(False, help="Enable reload for local development."),
) -> None:
    cli_server.serve_api(host=host, port=port, reload=reload)


@ui_app.command("serve")
def serve_ui_cmd(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(4318, min=1, max=65535, help="Bind port."),
    web_dir: str = typer.Option("", help="Override the static web directory."),
    build_web: bool = typer.Option(True, "--build/--no-build", help="Build the web UI before serving."),
) -> None:
    cli_server.serve_ui(host=host, port=port, web_dir=web_dir, build_web=build_web)

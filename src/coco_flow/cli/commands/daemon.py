from __future__ import annotations

import json

import typer

from coco_flow.config import load_settings
from coco_flow.daemon.client import shutdown as shutdown_daemon, start_daemon, status as daemon_status, wait_for_daemon
from coco_flow.daemon.server import run_daemon_server

from ..app import daemon_app


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

from __future__ import annotations

import json

import typer

from coco_flow.config import load_settings
from coco_flow.gateway import DEFAULT_GATEWAY_HOST, DEFAULT_GATEWAY_PORT, gateway_status, serve_gateway, start_gateway_in_background, stop_gateway

from ..app import gateway_app


@gateway_app.command("start")
def start_gateway_cmd(
    host: str = typer.Option(DEFAULT_GATEWAY_HOST, help="Bind host."),
    port: int = typer.Option(DEFAULT_GATEWAY_PORT, min=1, max=65535, help="Bind port."),
    detach: bool = typer.Option(False, "--detach", "-d", help="Run the gateway in background."),
) -> None:
    if detach:
        start_gateway_in_background(host=host, port=port, settings=load_settings())
        return
    serve_gateway(host=host, port=port)


@gateway_app.command("status")
def gateway_status_cmd(
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    info = gateway_status(load_settings())
    if as_json:
        typer.echo(json.dumps(info, ensure_ascii=False, indent=2))
        return
    typer.echo(json.dumps(info, ensure_ascii=False, indent=2))


@gateway_app.command("stop")
def stop_gateway_cmd() -> None:
    cfg = load_settings()
    info = gateway_status(cfg)
    if not info["running"]:
        typer.echo("coco-flow gateway not running")
        return
    stop_gateway(cfg)
    typer.echo("coco-flow gateway stopped")

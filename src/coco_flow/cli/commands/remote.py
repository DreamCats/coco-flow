from __future__ import annotations

import json

import typer

from ..app import remote_app
from .. import remote_runtime


@remote_app.command("connect")
def remote_connect_cmd(
    host_or_ip: str,
    user: str | None = typer.Option(None, "--user", help="SSH username override."),
    local_port: int | None = typer.Option(None, "--local-port", min=1, max=65535, help="Local forwarded port."),
    remote_port: int | None = typer.Option(None, "--remote-port", min=1, max=65535, help="Remote coco-flow port."),
    restart: bool = typer.Option(False, "--restart", help="Restart remote coco-flow before reconnecting."),
    reconnect_tunnel: bool = typer.Option(False, "--reconnect-tunnel", help="Recreate only the local SSH tunnel."),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open the local URL in a browser."),
    build_web: bool = typer.Option(True, "--build/--no-build", help="Build the remote web UI before starting."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    try:
        result = remote_runtime.connect_remote(
            host_or_ip,
            user=user,
            local_port=local_port,
            remote_port=remote_port,
            restart=restart,
            reconnect_tunnel=reconnect_tunnel,
            open_browser=not no_open,
            build_web=build_web,
            on_log=lambda line: None if as_json else typer.echo(line),
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    if as_json:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    typer.echo(f"connected: {result['ssh_target']}")
    typer.echo(f"url: {result['local_url']}")


@remote_app.command("add")
def remote_add_cmd(
    name: str,
    host: str = typer.Option(..., "--host", help="Remote host or SSH alias."),
    user: str = typer.Option("", "--user", help="Default SSH username."),
    local_port: int = typer.Option(4318, "--local-port", min=1, max=65535, help="Default local forwarded port."),
    remote_port: int = typer.Option(4318, "--remote-port", min=1, max=65535, help="Default remote coco-flow port."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    try:
        result = remote_runtime.add_remote(
            name,
            host=host,
            user=user,
            local_port=local_port,
            remote_port=remote_port,
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    if as_json:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    action = "updated" if result["updated"] else "added"
    typer.echo(f"{action}: {result['name']} -> {result['host']}")


@remote_app.command("list")
def remote_list_cmd(
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    result = remote_runtime.list_remotes()
    if as_json:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    remotes = result["remotes"]
    if not remotes:
        typer.echo("no saved remotes")
        return
    for remote in remotes:
        typer.echo(
            f"{remote['name']} "
            f"host={remote['host']} "
            f"user={remote.get('user') or '-'} "
            f"local={remote.get('local_port') or 4318} "
            f"remote={remote.get('remote_port') or 4318}"
        )


@remote_app.command("remove")
def remote_remove_cmd(
    name: str,
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    try:
        result = remote_runtime.remove_remote(name)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    if as_json:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    typer.echo(f"removed: {result['removed']}")


@remote_app.command("disconnect")
def remote_disconnect_cmd(
    host_or_ip: str = typer.Argument("", help="Remote host, alias, or blank to disconnect all managed tunnels."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    try:
        result = remote_runtime.disconnect_remote(
            host_or_ip,
            on_log=lambda line: None if as_json else typer.echo(line),
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    if as_json:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    typer.echo(f"disconnected: {', '.join(result['targets'])}")


@remote_app.command("status")
def remote_status_cmd(
    host_or_ip: str = typer.Argument("", help="Remote host or alias. Omit to inspect managed tunnels."),
    user: str | None = typer.Option(None, "--user", help="SSH username override when probing a specific remote."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    result = remote_runtime.remote_status(host_or_ip, user=user)
    if as_json:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    remotes = result.get("remotes") or []
    if remotes:
        typer.echo("saved remotes:")
        for remote in remotes:
            typer.echo(
                f"  {remote['name']} "
                f"host={remote['host']} "
                f"user={remote.get('user') or '-'} "
                f"local={remote.get('local_port') or 4318} "
                f"remote={remote.get('remote_port') or 4318}"
            )
    if not result["connections"]:
        typer.echo("no managed remote tunnels")
        return
    for connection in result["connections"]:
        typer.echo(
            f"{connection['target']} "
            f"host={connection['host']} "
            f"local={connection['local_port']} "
            f"remote={connection['remote_port']} "
            f"healthy={connection['local_healthy']} "
            f"tunnel_alive={connection['tunnel_alive']}"
        )

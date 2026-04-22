from __future__ import annotations

from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import typer

from coco_flow.cli import project as cli_project
from coco_flow.cli import remote_runtime
from coco_flow.cli import server as cli_server
from coco_flow.config import Settings, load_settings

from .server import DEFAULT_GATEWAY_HOST, DEFAULT_GATEWAY_PORT

LOCAL_DEFAULT_HOST = "127.0.0.1"
LOCAL_DEFAULT_PORT = 4318


class LocalStartRequest(BaseModel):
    host: str = LOCAL_DEFAULT_HOST
    port: int = LOCAL_DEFAULT_PORT
    build_web: bool = True


class RemoteCreateRequest(BaseModel):
    name: str
    host: str
    user: str = ""
    local_port: int = 4318
    remote_port: int = 4318


class RemoteConnectRequest(BaseModel):
    restart: bool = False
    reconnect_tunnel: bool = False
    build_web: bool = True


def create_gateway_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or load_settings()
    app = FastAPI(
        title="coco-flow gateway",
        summary="Local HTTP gateway for browser and lightweight launcher entrypoints.",
        version=cli_project.package_version(),
    )

    @app.get("/")
    def root() -> dict[str, object]:
        return {
            "name": "coco-flow-gateway",
            "message": "coco-flow gateway is running",
            "version": cli_project.package_version(),
        }

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {
            "ok": True,
            "service": "coco-flow-gateway",
            "version": cli_project.package_version(),
        }

    @app.get("/preflight")
    def preflight() -> dict[str, object]:
        return {
            "ok": True,
            "gateway": {
                "host": DEFAULT_GATEWAY_HOST,
                "port": DEFAULT_GATEWAY_PORT,
                "version": cli_project.package_version(),
            },
            "local": _local_status_payload(cfg, port=LOCAL_DEFAULT_PORT),
        }

    @app.get("/local/status")
    def local_status(port: int = LOCAL_DEFAULT_PORT) -> dict[str, object]:
        return _local_status_payload(cfg, port=port)

    @app.post("/local/start")
    def local_start(payload: LocalStartRequest) -> dict[str, object]:
        try:
            cli_server.start_server_in_background(
                host=payload.host,
                port=payload.port,
                web_dir="",
                build_web=payload.build_web,
                api_only=False,
                reload=False,
            )
        except typer.Exit as error:
            raise HTTPException(status_code=400, detail=f"failed to start local coco-flow: exit={error.exit_code}") from error
        return _local_status_payload(cfg, port=payload.port)

    @app.post("/local/stop")
    def local_stop() -> dict[str, object]:
        info = cli_server.server_status(cfg)
        if not info["running"]:
            return {
                "stopped": False,
                "message": "coco-flow server not running",
                "url": f"http://{LOCAL_DEFAULT_HOST}:{LOCAL_DEFAULT_PORT}",
            }
        cli_server.stop_server(cfg)
        return {
            "stopped": True,
            "message": "coco-flow server stopped",
            "url": f"http://{LOCAL_DEFAULT_HOST}:{LOCAL_DEFAULT_PORT}",
        }

    @app.get("/remote/list")
    def remote_list() -> dict[str, Any]:
        return remote_runtime.list_remotes(settings=cfg)

    @app.post("/remote")
    def remote_create(payload: RemoteCreateRequest) -> dict[str, Any]:
        try:
            return remote_runtime.add_remote(
                payload.name,
                host=payload.host,
                user=payload.user,
                local_port=payload.local_port,
                remote_port=payload.remote_port,
                settings=cfg,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.delete("/remote/{name}")
    def remote_delete(name: str) -> dict[str, Any]:
        try:
            return remote_runtime.remove_remote(name, settings=cfg)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/remote/{name}/status")
    def remote_status(name: str) -> dict[str, Any]:
        return remote_runtime.remote_status(name, settings=cfg)

    @app.post("/remote/{name}/connect")
    def remote_connect(name: str, payload: RemoteConnectRequest) -> dict[str, Any]:
        try:
            return remote_runtime.connect_remote(
                name,
                restart=payload.restart,
                reconnect_tunnel=payload.reconnect_tunnel,
                open_browser=False,
                build_web=payload.build_web,
                settings=cfg,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/remote/{name}/disconnect")
    def remote_disconnect(name: str) -> dict[str, Any]:
        try:
            return remote_runtime.disconnect_remote(name, settings=cfg)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    return app


def _local_status_payload(settings: Settings, *, port: int) -> dict[str, object]:
    info = cli_server.server_status(settings)
    return {
        "running": bool(info["running"]),
        "pid": info["pid"],
        "pid_file": info["pid_file"],
        "log_file": info["log_file"],
        "url": f"http://{LOCAL_DEFAULT_HOST}:{port}",
        "healthy": _probe_health(f"http://{LOCAL_DEFAULT_HOST}:{port}/healthz"),
    }


def _probe_health(url: str, timeout: float = 1.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", "ignore").lower()
            status = getattr(response, "status", 0) or 0
        return status == 200 and "ok" in body
    except (OSError, URLError, ValueError):
        return False

from __future__ import annotations

from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import typer

from coco_flow.cli import project as cli_project
from coco_flow.cli import remote_runtime
from coco_flow.cli import server as cli_server
from coco_flow.config import Settings, load_settings

from .operations import OperationStore
from .server import DEFAULT_GATEWAY_HOST, DEFAULT_GATEWAY_PORT

LOCAL_DEFAULT_HOST = "127.0.0.1"
LOCAL_DEFAULT_PORT = 4318
CLIENT_HEADER_NAME = "X-Coco-Flow-Client"
CLIENT_HEADER_VALUE = "chrome-extension"
PUBLIC_PATHS = {"/", "/healthz"}


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
    app.state.operations = OperationStore()
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^chrome-extension://.*$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", CLIENT_HEADER_NAME],
    )

    @app.middleware("http")
    async def guard_extension_requests(request: Request, call_next):
        client_host = (request.client.host if request.client else "") or ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            return JSONResponse(status_code=403, content={"detail": "gateway only accepts loopback requests"})

        origin = (request.headers.get("origin") or "").strip()
        if origin and not origin.startswith("chrome-extension://"):
            return JSONResponse(status_code=403, content={"detail": f"origin not allowed: {origin}"})

        if request.method == "OPTIONS":
            return await call_next(request)

        if request.url.path not in PUBLIC_PATHS:
            client_tag = (request.headers.get(CLIENT_HEADER_NAME) or "").strip()
            if client_tag != CLIENT_HEADER_VALUE:
                return JSONResponse(status_code=403, content={"detail": "missing chrome extension client header"})

        return await call_next(request)

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

    @app.get("/operations/{operation_id}")
    def operation_status(operation_id: str) -> dict[str, Any]:
        operation = _operations(app).get(operation_id)
        if operation is None:
            raise HTTPException(status_code=404, detail=f"operation not found: {operation_id}")
        return operation

    @app.get("/local/status")
    def local_status(port: int = LOCAL_DEFAULT_PORT) -> dict[str, object]:
        return _local_status_payload(cfg, port=port)

    @app.post("/local/start")
    def local_start(payload: LocalStartRequest) -> dict[str, object]:
        operation = _operations(app).create(
            kind="local.start",
            steps=[
                ("prepare", "Preparing local service"),
                ("start", "Starting coco-flow"),
                ("ready", "Ready"),
            ],
            message="Queued local start",
        )

        def runner() -> None:
            store = _operations(app)
            store.begin(operation["id"], message="Preparing local service")
            store.set_step(operation["id"], "prepare", "running")
            store.set_step(operation["id"], "prepare", "done")
            store.set_step(operation["id"], "start", "running", message=f"Binding {payload.host}:{payload.port}")
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
                raise RuntimeError(f"failed to start local coco-flow: exit={error.exit_code}") from error
            status = _local_status_payload(cfg, port=payload.port)
            store.set_step(operation["id"], "start", "done")
            store.set_step(operation["id"], "ready", "done", message=status["url"])
            store.succeed(operation["id"], result=status, message="Local coco-flow is ready")

        _operations(app).start(operation["id"], runner)
        return {"operation_id": operation["id"]}

    @app.post("/local/stop")
    def local_stop() -> dict[str, object]:
        operation = _operations(app).create(
            kind="local.stop",
            steps=[
                ("stop", "Stopping coco-flow"),
                ("done", "Stopped"),
            ],
            message="Queued local stop",
        )

        def runner() -> None:
            store = _operations(app)
            store.begin(operation["id"], message="Stopping coco-flow")
            store.set_step(operation["id"], "stop", "running")
            info = cli_server.server_status(cfg)
            if info["running"]:
                cli_server.stop_server(cfg)
                result = {
                    "stopped": True,
                    "message": "coco-flow server stopped",
                    "url": f"http://{LOCAL_DEFAULT_HOST}:{LOCAL_DEFAULT_PORT}",
                }
            else:
                result = {
                    "stopped": False,
                    "message": "coco-flow server not running",
                    "url": f"http://{LOCAL_DEFAULT_HOST}:{LOCAL_DEFAULT_PORT}",
                }
            store.set_step(operation["id"], "stop", "done")
            store.set_step(operation["id"], "done", "done")
            store.succeed(operation["id"], result=result, message=result["message"])

        _operations(app).start(operation["id"], runner)
        return {"operation_id": operation["id"]}

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
        operation = _operations(app).create(
            kind="remote.connect",
            steps=[
                ("remote_check", "Checking remote"),
                ("remote_start", "Starting remote service"),
                ("tunnel", "Opening tunnel"),
                ("ready", "Ready"),
            ],
            message=f"Queued remote connect for {name}",
        )

        def runner() -> None:
            store = _operations(app)
            store.begin(operation["id"], message=f"Checking remote {name}")
            store.set_step(operation["id"], "remote_check", "running")

            def on_log(line: str) -> None:
                _update_remote_connect_operation(store, operation["id"], line)

            try:
                result = remote_runtime.connect_remote(
                    name,
                    restart=payload.restart,
                    reconnect_tunnel=payload.reconnect_tunnel,
                    open_browser=False,
                    build_web=payload.build_web,
                    settings=cfg,
                    on_log=on_log,
                )
            except ValueError as error:
                raise RuntimeError(str(error)) from error

            store.set_step(operation["id"], "remote_check", "done")
            store.set_step(operation["id"], "remote_start", "done")
            store.set_step(operation["id"], "tunnel", "done")
            store.set_step(operation["id"], "ready", "done", message=str(result.get("local_url") or ""))
            store.succeed(operation["id"], result=result, message=f"Remote ready: {result.get('local_url') or ''}".strip())

        _operations(app).start(operation["id"], runner)
        return {"operation_id": operation["id"]}

    @app.post("/remote/{name}/disconnect")
    def remote_disconnect(name: str) -> dict[str, Any]:
        operation = _operations(app).create(
            kind="remote.disconnect",
            steps=[
                ("tunnel", "Closing tunnel"),
                ("done", "Disconnected"),
            ],
            message=f"Queued remote disconnect for {name}",
        )

        def runner() -> None:
            store = _operations(app)
            store.begin(operation["id"], message=f"Closing tunnel for {name}")
            store.set_step(operation["id"], "tunnel", "running")
            try:
                result = remote_runtime.disconnect_remote(name, settings=cfg)
            except ValueError as error:
                raise RuntimeError(str(error)) from error
            store.set_step(operation["id"], "tunnel", "done")
            store.set_step(operation["id"], "done", "done")
            store.succeed(operation["id"], result=result, message="Remote tunnel disconnected")

        _operations(app).start(operation["id"], runner)
        return {"operation_id": operation["id"]}

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


def _operations(app: FastAPI) -> OperationStore:
    return app.state.operations  # type: ignore[no-any-return]


def _update_remote_connect_operation(store: OperationStore, operation_id: str, line: str) -> None:
    normalized = line.strip()
    if not normalized:
        return
    if normalized.startswith("remote_start:"):
        store.set_step(operation_id, "remote_check", "done")
        store.set_step(operation_id, "remote_start", "running", message=normalized)
        store.set_message(operation_id, "Starting remote service")
        return
    if normalized.startswith("remote_reuse:"):
        store.set_step(operation_id, "remote_check", "done")
        store.set_step(operation_id, "remote_start", "done")
        store.set_message(operation_id, "Remote service already running")
        return
    if normalized.startswith("tunnel_prepare:"):
        store.set_step(operation_id, "remote_check", "done")
        store.set_step(operation_id, "remote_start", "done")
        store.set_step(operation_id, "tunnel", "running", message=normalized)
        store.set_message(operation_id, "Opening SSH tunnel")
        return
    if normalized.startswith("tunnel_start:") or normalized.startswith("tunnel_reuse:"):
        store.set_step(operation_id, "tunnel", "done", message=normalized)
        store.set_message(operation_id, "Tunnel ready")
        return
    if normalized.startswith("remote_version_") or normalized.startswith("remote_meta_"):
        store.set_message(operation_id, normalized.replace(":", ": ", 1))

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from threading import Lock, Thread
from typing import Any
from uuid import uuid4


_RETENTION = timedelta(minutes=30)


class OperationStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._operations: dict[str, dict[str, Any]] = {}

    def create(self, *, kind: str, steps: list[tuple[str, str]], message: str = "") -> dict[str, Any]:
        now = _now_iso()
        operation_id = uuid4().hex
        operation = {
            "id": operation_id,
            "kind": kind,
            "state": "pending",
            "message": message,
            "created_at": now,
            "updated_at": now,
            "steps": [
                {
                    "key": key,
                    "label": label,
                    "state": "pending",
                    "message": "",
                }
                for key, label in steps
            ],
            "result": None,
            "error": None,
        }
        with self._lock:
            self._purge_locked()
            self._operations[operation_id] = operation
            return deepcopy(operation)

    def get(self, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            operation = self._operations.get(operation_id)
            return deepcopy(operation) if operation else None

    def start(self, operation_id: str, runner) -> None:
        thread = Thread(target=self._run, args=(operation_id, runner), name=f"coco-flow-operation-{operation_id[:8]}", daemon=True)
        thread.start()

    def begin(self, operation_id: str, *, message: str = "") -> None:
        with self._lock:
            operation = self._require_locked(operation_id)
            operation["state"] = "running"
            if message:
                operation["message"] = message
            operation["updated_at"] = _now_iso()

    def set_message(self, operation_id: str, message: str) -> None:
        with self._lock:
            operation = self._require_locked(operation_id)
            operation["message"] = message
            operation["updated_at"] = _now_iso()

    def set_step(self, operation_id: str, key: str, state: str, *, message: str = "") -> None:
        with self._lock:
            operation = self._require_locked(operation_id)
            for step in operation["steps"]:
                if step["key"] != key:
                    continue
                step["state"] = state
                if message:
                    step["message"] = message
                operation["updated_at"] = _now_iso()
                return
            raise KeyError(f"operation step not found: {key}")

    def succeed(self, operation_id: str, *, result: Any = None, message: str = "") -> None:
        with self._lock:
            operation = self._require_locked(operation_id)
            operation["state"] = "succeeded"
            if message:
                operation["message"] = message
            operation["result"] = result
            operation["error"] = None
            operation["updated_at"] = _now_iso()

    def fail(self, operation_id: str, error: str) -> None:
        with self._lock:
            operation = self._require_locked(operation_id)
            operation["state"] = "failed"
            operation["error"] = error
            operation["message"] = error
            operation["updated_at"] = _now_iso()

    def _run(self, operation_id: str, runner) -> None:
        try:
            runner()
        except Exception as error:  # noqa: BLE001
            self.fail(operation_id, str(error))

    def _require_locked(self, operation_id: str) -> dict[str, Any]:
        operation = self._operations.get(operation_id)
        if operation is None:
            raise KeyError(f"operation not found: {operation_id}")
        return operation

    def _purge_locked(self) -> None:
        threshold = datetime.now().astimezone() - _RETENTION
        expired: list[str] = []
        for operation_id, operation in self._operations.items():
            updated_at = _parse_iso(str(operation.get("updated_at") or ""))
            if updated_at is None or updated_at >= threshold:
                continue
            expired.append(operation_id)
        for operation_id in expired:
            self._operations.pop(operation_id, None)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None

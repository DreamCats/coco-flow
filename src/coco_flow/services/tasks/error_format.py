from __future__ import annotations

import traceback


def format_exception_log_lines(error: BaseException) -> list[str]:
    lines = [
        f"error_type: {type(error).__name__}",
        f"error: {error}",
    ]
    chain = _format_exception_chain(error)
    if len(chain) > 1:
        lines.append(f"error_chain: {' <- '.join(chain)}")
    for raw_line in traceback.format_exception(type(error), error, error.__traceback__):
        for line in raw_line.rstrip().splitlines():
            lines.append(f"traceback: {line}")
    return lines


def _format_exception_chain(error: BaseException) -> list[str]:
    result: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        result.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return result

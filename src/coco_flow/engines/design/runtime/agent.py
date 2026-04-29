"""Design 阶段 agent I/O 封装。

保留两类能力：短任务 JSON 调用用于搜索线索生成，以及 Markdown session 调用用于
native writer 编辑 design.md 模板。旧 schema 多角色 JSON session 已删除。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import tempfile
import time

from coco_flow.clients import AgentSessionHandle, CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.design import build_design_bootstrap_prompt

from coco_flow.engines.design.types import DesignInputBundle


@dataclass
class DesignAgentSession:
    client: CocoACPClient
    handle: AgentSessionHandle


def run_agent_json(
    prepared: DesignInputBundle,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
    *,
    role: str = "design_json",
    stage: str = "json",
    on_log=None,
) -> dict[str, object]:
    raw = _run_agent_template(
        prepared,
        settings,
        template,
        prompt_builder,
        prefix,
        ".json",
        role=role,
        stage=stage,
        on_log=on_log,
    )
    if "__FILL__" in raw or not raw.strip():
        failed_path = _write_failed_agent_output(prepared.task_dir, prefix, ".json", raw, "design_agent_template_unfilled")
        raise ValueError(f"design_agent_template_unfilled: failed_output={failed_path}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        repaired = _repair_common_agent_json(raw)
        if repaired != raw:
            try:
                payload = json.loads(repaired)
            except json.JSONDecodeError:
                failed_path = _write_failed_agent_output(prepared.task_dir, prefix, ".json", raw, "design_agent_payload_invalid_json")
                raise ValueError(f"design_agent_payload_invalid_json: failed_output={failed_path}") from error
        else:
            failed_path = _write_failed_agent_output(prepared.task_dir, prefix, ".json", raw, "design_agent_payload_invalid_json")
            raise ValueError(f"design_agent_payload_invalid_json: failed_output={failed_path}") from error
    if not isinstance(payload, dict):
        failed_path = _write_failed_agent_output(prepared.task_dir, prefix, ".json", raw, "design_agent_payload_not_object")
        raise ValueError(f"design_agent_payload_not_object: failed_output={failed_path}")
    return payload


def run_agent_markdown_with_new_session(
    prepared: DesignInputBundle,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
    *,
    role: str,
    stage: str,
    on_log,
) -> str:
    session = new_design_agent_session(prepared, settings, role=role, on_log=on_log, bootstrap=False)
    try:
        raw = _run_agent_template_in_session(
            prepared,
            template,
            prompt_builder,
            prefix,
            ".md",
            session,
            stage=stage,
            inline_bootstrap=True,
            on_log=on_log,
        )
        if not raw.strip():
            raise ValueError("design_agent_markdown_empty")
        return raw.rstrip() + "\n"
    finally:
        close_design_agent_session(session, on_log)


def new_design_agent_session(
    prepared: DesignInputBundle,
    settings: Settings,
    *,
    role: str,
    on_log,
    bootstrap: bool,
) -> DesignAgentSession:
    client = CocoACPClient(settings.coco_bin, idle_timeout_seconds=settings.acp_idle_timeout_seconds, settings=settings)
    on_log(f"session_role: {role}")
    handle = client.new_agent_session(
        query_timeout=settings.native_query_timeout,
        cwd=str(prepared.task_dir),
        role=role,
    )
    session = DesignAgentSession(client=client, handle=handle)
    if bootstrap:
        try:
            on_log(f"bootstrap_prompt: true role={role}")
            _prompt_agent_session_logged(
                session,
                build_design_bootstrap_prompt(skills_index_markdown=_skills_index_markdown(prepared)),
                stage="bootstrap",
                on_log=on_log,
                task_dir=prepared.task_dir,
            )
        except Exception:
            close_design_agent_session(session, on_log)
            raise
    return session


def close_design_agent_session(session: DesignAgentSession, on_log) -> None:
    try:
        session.client.close_agent_session(session.handle)
    except Exception as error:
        on_log(f"session_close_warning: role={session.handle.role} error={error}")


def _run_agent_template(
    prepared: DesignInputBundle,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
    suffix: str,
    *,
    role: str,
    stage: str,
    on_log,
) -> str:
    path = _write_template(prepared.task_dir, prefix, suffix, template)
    client = CocoACPClient(settings.coco_bin, idle_timeout_seconds=settings.acp_idle_timeout_seconds, settings=settings)
    prompt = prompt_builder(str(path))
    started = time.perf_counter()
    started_at = datetime.now().astimezone().isoformat()
    raw = ""
    error_text = ""
    if on_log:
        on_log(f"agent_prompt_start: role={role} stage={stage}")
    try:
        client.run_agent(
            prompt,
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        return raw
    except Exception as error:
        error_text = str(error)
        if on_log:
            duration_ms = int((time.perf_counter() - started) * 1000)
            on_log(f"agent_prompt_failed: role={role} stage={stage} duration_ms={duration_ms} error={error}")
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        if on_log and not error_text:
            on_log(f"agent_prompt_done: role={role} stage={stage} duration_ms={duration_ms}")
        _append_agent_transcript(
            prepared.task_dir,
            {
                "kind": "json",
                "role": role,
                "stage": stage,
                "prefix": prefix,
                "status": "failed" if error_text else "ok",
                "started_at": started_at,
                "duration_ms": duration_ms,
                "prompt": prompt,
                "response": raw,
                "error": error_text,
            },
        )
        if path.exists():
            path.unlink()


def _run_agent_template_in_session(
    prepared: DesignInputBundle,
    template: str,
    prompt_builder,
    prefix: str,
    suffix: str,
    session: DesignAgentSession,
    *,
    stage: str,
    inline_bootstrap: bool,
    on_log,
) -> str:
    path = _write_template(prepared.task_dir, prefix, suffix, template)
    try:
        prompt = prompt_builder(str(path))
        if inline_bootstrap:
            on_log(f"bootstrap_prompt: inline role={session.handle.role}")
            prompt = _join_prompts(
                build_design_bootstrap_prompt(
                    skills_index_markdown=_skills_index_markdown(prepared),
                    standalone=False,
                ),
                prompt,
            )
        _prompt_agent_session_logged(session, prompt, stage=stage, on_log=on_log, task_dir=prepared.task_dir)
        return path.read_text(encoding="utf-8") if path.exists() else ""
    finally:
        if path.exists():
            path.unlink()


def _write_template(task_dir: Path, prefix: str, suffix: str, content: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=task_dir, prefix=prefix, suffix=suffix, delete=False) as handle:
        handle.write(content)
        handle.flush()
        return Path(handle.name)


def _repair_common_agent_json(raw: str) -> str:
    """修复 agent 常见的轻微 JSON 形态问题。

    这里不做语义修订，只处理明显的 JSON 语法瑕疵。例如 agent 常把行号范围写成
    `"line": 983-1017`，这在 JSON 中会被解析成非法表达式；修成字符串后仍可进入
    后续 normalizer，由 normalizer 决定是否采纳。
    """

    repaired = re.sub(
        r'("(?:line|line_number|line_start|start_line)"\s*:\s*)(\d+)\s*-\s*(\d+)(\s*[,}])',
        r'\1"\2-\3"\4',
        raw,
    )
    return _escape_control_chars_in_json_strings(repaired)


def _escape_control_chars_in_json_strings(raw: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    for char in raw:
        if not in_string:
            result.append(char)
            if char == '"':
                in_string = True
            continue
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\":
            result.append(char)
            escaped = True
            continue
        if char == '"':
            result.append(char)
            in_string = False
            continue
        if char == "\n":
            result.append("\\n")
        elif char == "\r":
            result.append("\\r")
        elif char == "\t":
            result.append("\\t")
        elif ord(char) < 0x20:
            result.append(f"\\u{ord(char):04x}")
        else:
            result.append(char)
    return "".join(result)


def _write_failed_agent_output(task_dir: Path, prefix: str, suffix: str, raw: str, reason: str) -> Path:
    safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix.strip(".-") or "design-agent")
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    path = task_dir / f".{safe_prefix}-{timestamp}-failed{suffix}"
    payload = raw if raw.strip() else f'{{"error": "{reason}", "raw": ""}}\n'
    path.write_text(payload, encoding="utf-8")
    return path


def _append_agent_transcript(task_dir: Path, payload: dict[str, object]) -> None:
    path = task_dir / "design-agent-transcript.jsonl"
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _prompt_agent_session_logged(
    session: DesignAgentSession,
    prompt: str,
    *,
    stage: str,
    on_log,
    task_dir: Path,
) -> str:
    role = session.handle.role
    started = time.perf_counter()
    started_at = datetime.now().astimezone().isoformat()
    content = ""
    error_text = ""
    on_log(f"agent_prompt_start: role={role} stage={stage}")
    try:
        content = session.client.prompt_agent_session(session.handle, prompt)
    except Exception as error:
        error_text = str(error)
        duration_ms = int((time.perf_counter() - started) * 1000)
        on_log(f"agent_prompt_failed: role={role} stage={stage} duration_ms={duration_ms} error={error}")
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        if not error_text:
            on_log(f"agent_prompt_done: role={role} stage={stage} duration_ms={duration_ms}")
        _append_agent_transcript(
            task_dir,
            {
                "kind": "session",
                "role": role,
                "stage": stage,
                "status": "failed" if error_text else "ok",
                "started_at": started_at,
                "duration_ms": duration_ms,
                "prompt": prompt,
                "response": content,
                "error": error_text,
            },
        )
    return content


def _join_prompts(*parts: str) -> str:
    return "\n\n---\n\n".join(part.strip() for part in parts if part.strip()).rstrip() + "\n"


def _skills_index_markdown(prepared: DesignInputBundle) -> str:
    lines: list[str] = []
    if prepared.design_selected_skill_ids:
        lines.append("Selected Design skills:")
        lines.extend(f"- {skill_id}" for skill_id in prepared.design_selected_skill_ids)
    index = prepared.design_skills_index_markdown.strip()
    if index:
        if lines:
            lines.append("")
        lines.append("Design Skills Index:")
        lines.append(index)
    return "\n".join(lines)

"""Design 阶段 agent I/O 封装。

保留两类能力：短任务 JSON 调用用于搜索线索生成，以及 Markdown session 调用用于
native writer 编辑 design.md 模板。旧 schema 多角色 JSON session 已删除。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

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
) -> dict[str, object]:
    raw = _run_agent_template(prepared, settings, template, prompt_builder, prefix, ".json")
    if "__FILL__" in raw or not raw.strip():
        raise ValueError("design_agent_template_unfilled")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("design_agent_payload_not_object")
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
) -> str:
    path = _write_template(prepared.task_dir, prefix, suffix, template)
    client = CocoACPClient(settings.coco_bin, idle_timeout_seconds=settings.acp_idle_timeout_seconds, settings=settings)
    try:
        client.run_agent(
            prompt_builder(str(path)),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        return path.read_text(encoding="utf-8") if path.exists() else ""
    finally:
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
        _prompt_agent_session_logged(session, prompt, stage=stage, on_log=on_log)
        return path.read_text(encoding="utf-8") if path.exists() else ""
    finally:
        if path.exists():
            path.unlink()


def _write_template(task_dir: Path, prefix: str, suffix: str, content: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=task_dir, prefix=prefix, suffix=suffix, delete=False) as handle:
        handle.write(content)
        handle.flush()
        return Path(handle.name)


def _prompt_agent_session_logged(
    session: DesignAgentSession,
    prompt: str,
    *,
    stage: str,
    on_log,
) -> str:
    role = session.handle.role
    on_log(f"agent_prompt_start: role={role} stage={stage}")
    try:
        content = session.client.prompt_agent_session(session.handle, prompt)
    except Exception as error:
        on_log(f"agent_prompt_failed: role={role} stage={stage} error={error}")
        raise
    on_log(f"agent_prompt_done: role={role} stage={stage}")
    return content


def _join_prompts(*parts: str) -> str:
    return "\n\n---\n\n".join(part.strip() for part in parts if part.strip()).rstrip() + "\n"


def _skills_index_markdown(prepared: DesignInputBundle) -> str:
    lines: list[str] = []
    if prepared.design_selected_skill_ids:
        lines.append("Selected Design skills:")
        lines.extend(f"- {skill_id}" for skill_id in prepared.design_selected_skill_ids)
    brief = prepared.design_skills_brief_markdown.strip()
    if brief:
        if lines:
            lines.append("")
        lines.append("Design Skills Brief:")
        lines.append(brief[:6000])
    return "\n".join(lines)

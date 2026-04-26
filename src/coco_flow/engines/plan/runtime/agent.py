"""Plan 阶段 agent I/O 封装。

当前只保留 Markdown session 写作能力，用于 native writer 编辑 plan.md 模板；
旧结构化 JSON agent 调用已随 Plan schema 删除。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from coco_flow.clients import AgentSessionHandle, CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.plan import build_plan_bootstrap_prompt

from coco_flow.engines.plan.types import PlanPreparedInput


@dataclass
class PlanAgentSession:
    client: CocoACPClient
    handle: AgentSessionHandle


def run_plan_agent_markdown_with_new_session(
    prepared: PlanPreparedInput,
    settings: Settings,
    template: str,
    prompt_builder,
    prefix: str,
    *,
    role: str,
    stage: str,
    on_log,
) -> str:
    session = new_plan_agent_session(prepared, settings, role=role, on_log=on_log, bootstrap=False)
    try:
        return run_plan_agent_markdown_in_session(
            prepared,
            template,
            prompt_builder,
            prefix,
            session,
            stage=stage,
            inline_bootstrap=True,
            on_log=on_log,
        )
    finally:
        close_plan_agent_session(session, on_log)


def run_plan_agent_markdown_in_session(
    prepared: PlanPreparedInput,
    template: str,
    prompt_builder,
    prefix: str,
    session: PlanAgentSession,
    *,
    stage: str,
    inline_bootstrap: bool,
    on_log,
) -> str:
    raw = _run_plan_agent_template_in_session(
        prepared,
        template,
        prompt_builder,
        prefix,
        ".md",
        session,
        stage=stage,
        inline_bootstrap=inline_bootstrap,
        on_log=on_log,
    )
    if not raw.strip():
        raise ValueError("plan_agent_markdown_empty")
    return raw.rstrip() + "\n"


def new_plan_agent_session(
    prepared: PlanPreparedInput,
    settings: Settings,
    *,
    role: str,
    on_log,
    bootstrap: bool,
) -> PlanAgentSession:
    client = CocoACPClient(settings.coco_bin, idle_timeout_seconds=settings.acp_idle_timeout_seconds, settings=settings)
    on_log(f"session_role: {role}")
    handle = client.new_agent_session(
        query_timeout=settings.native_query_timeout,
        cwd=str(prepared.task_dir),
        role=role,
    )
    session = PlanAgentSession(client=client, handle=handle)
    if bootstrap:
        try:
            on_log(f"bootstrap_prompt: true role={role}")
            _prompt_plan_agent_session_logged(
                session,
                build_plan_bootstrap_prompt(skills_index_markdown=_skills_index_markdown(prepared)),
                stage="bootstrap",
                on_log=on_log,
            )
        except Exception:
            close_plan_agent_session(session, on_log)
            raise
    return session


def close_plan_agent_session(session: PlanAgentSession, on_log) -> None:
    try:
        session.client.close_agent_session(session.handle)
    except Exception as error:
        on_log(f"session_close_warning: role={session.handle.role} error={error}")


def _run_plan_agent_template_in_session(
    prepared: PlanPreparedInput,
    template: str,
    prompt_builder,
    prefix: str,
    suffix: str,
    session: PlanAgentSession,
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
                build_plan_bootstrap_prompt(
                    skills_index_markdown=_skills_index_markdown(prepared),
                    standalone=False,
                ),
                prompt,
            )
        _prompt_plan_agent_session_logged(session, prompt, stage=stage, on_log=on_log)
        return path.read_text(encoding="utf-8") if path.exists() else ""
    finally:
        if path.exists():
            path.unlink()


def _write_template(task_dir: Path, prefix: str, suffix: str, content: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=task_dir, prefix=prefix, suffix=suffix, delete=False) as handle:
        handle.write(content)
        handle.flush()
        return Path(handle.name)


def _prompt_plan_agent_session_logged(
    session: PlanAgentSession,
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


def _skills_index_markdown(prepared: PlanPreparedInput) -> str:
    lines: list[str] = []
    if prepared.selected_skill_ids:
        lines.append("Selected Plan skills:")
        lines.extend(f"- {skill_id}" for skill_id in prepared.selected_skill_ids)
    index = prepared.skills_index_markdown.strip()
    if index:
        if lines:
            lines.append("")
        lines.append("Plan Skills Index:")
        lines.append(index)
    return "\n".join(lines)

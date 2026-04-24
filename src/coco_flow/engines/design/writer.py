from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.prompts.design import build_writer_prompt

from .agent_io import run_agent_markdown_with_new_session
from .models import DesignInputBundle
from .utils import as_str_list, dict_list


def write_design_markdown(
    prepared: DesignInputBundle,
    decision_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> str:
    if native_ok:
        try:
            return run_agent_markdown_with_new_session(
                prepared,
                settings,
                build_local_design_markdown(prepared, decision_payload),
                lambda template_path: build_writer_prompt(
                    title=prepared.title,
                    decision_payload=decision_payload,
                    template_path=template_path,
                ),
                ".design-writer-",
                role="design_writer",
                stage="writer",
                on_log=on_log,
            )
        except Exception as error:
            on_log(f"design_v3_writer_degraded: {error}")
    return build_local_design_markdown(prepared, decision_payload)


def build_local_design_markdown(prepared: DesignInputBundle, decision_payload: dict[str, object]) -> str:
    blocking_count = int(decision_payload.get("review_blocking_count") or 0)
    finalized = bool(decision_payload.get("finalized"))
    parts = [
        f"# {prepared.title} Design",
        "",
        "## 结论",
        _local_design_conclusion(decision_payload, blocking_count, finalized),
        "",
        "## 核心改造点",
    ]
    for index, item in enumerate(as_str_list(decision_payload.get("core_change_points")) or prepared.sections.change_scope or [prepared.title], start=1):
        parts.append(f"{index}. {item}")
    parts.extend(["", "## 分仓库方案"])
    for item in dict_list(decision_payload.get("repo_decisions")):
        repo_id = str(item.get("repo_id") or "")
        work_type = str(item.get("work_type") or "")
        action = "主要代码改造" if work_type in {"must_change", "co_change"} else "联动检查" if work_type == "validate_only" else "参考"
        parts.extend(["", f"### {repo_id}", f"- 主要事项：{action}。{str(item.get('responsibility') or '').strip()}"])
        files = as_str_list(item.get("candidate_files"))
        if files:
            parts.append("- 候选文件：" + "、".join(files[:8]))
        boundaries = as_str_list(item.get("boundaries"))
        if boundaries:
            parts.append("- 边界：" + "；".join(boundaries[:4]))
    risks = as_str_list(decision_payload.get("risks"))
    unresolved = as_str_list(decision_payload.get("unresolved_questions"))
    parts.extend(["", "## 风险与待确认"])
    if risks or unresolved:
        for item in [*risks, *unresolved]:
            parts.append(f"- {item}")
    else:
        parts.append("- 暂无阻塞性待确认项。")
    if blocking_count > 0 and not finalized:
        parts.extend(["", "## 当前阻断", "- Skeptic review 仍存在阻塞问题，当前 Design 不能进入 Plan。"])
    if prepared.sections.non_goals:
        parts.extend(["", "## 明确不做"])
        parts.extend(f"- {item}" for item in prepared.sections.non_goals)
    return "\n".join(parts).rstrip() + "\n"


def _local_design_conclusion(decision_payload: dict[str, object], blocking_count: int, finalized: bool) -> str:
    summary = str(decision_payload.get("decision_summary") or "本阶段已形成初版设计裁决。").strip()
    if blocking_count > 0 and not finalized:
        return f"当前不能进入 Plan。{summary}"
    return summary

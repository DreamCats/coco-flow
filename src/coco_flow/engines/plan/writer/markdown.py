"""Plan Markdown 生成器。

负责生成 doc-only plan.md：native 模式让 agent 直接编辑 Markdown 模板，
失败时使用本地草稿。这里不再生成 work-items、执行图或验证矩阵 JSON。
"""

from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.prompts.plan import build_doc_only_plan_prompt, build_plan_template_markdown

from coco_flow.engines.plan.runtime import run_plan_agent_markdown_with_new_session
from coco_flow.engines.plan.types import EXECUTOR_NATIVE, PlanPreparedInput


def generate_doc_only_plan_markdown(
    prepared: PlanPreparedInput,
    settings: Settings,
    on_log,
) -> tuple[str, str]:
    if settings.plan_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            raw = run_plan_agent_markdown_with_new_session(
                prepared,
                settings,
                build_plan_template_markdown(),
                lambda template_path: build_doc_only_plan_prompt(
                    title=prepared.title,
                    repo_ids=[scope.repo_id for scope in prepared.repo_scopes if scope.repo_id],
                    refined_markdown=prepared.refined_markdown,
                    design_markdown=prepared.design_markdown,
                    skills_index_markdown=prepared.skills_index_markdown,
                    skills_fallback_markdown=prepared.skills_fallback_markdown,
                    template_path=template_path,
                ),
                ".plan-template-",
                role="plan_writer",
                stage="write_doc_only",
                on_log=on_log,
            )
            on_log("plan_writer_mode: native_doc_only")
            return _normalize_native_plan_markdown(raw), "native"
        except Exception as error:
            on_log(f"plan_writer_fallback: {error}")
    on_log("plan_writer_mode: local_doc_only")
    return generate_local_doc_only_plan_markdown(prepared), "local"


def generate_local_doc_only_plan_markdown(prepared: PlanPreparedInput) -> str:
    repos = [scope.repo_id for scope in prepared.repo_scopes if scope.repo_id]
    change_scope = prepared.refined_sections.change_scope or [prepared.title]
    acceptance = prepared.refined_sections.acceptance_criteria or ["完成与 Design 文档一致的最小验证。"]
    non_goals = prepared.refined_sections.non_goals
    lines = [
        "# Plan",
        "",
        f"- task_id: {prepared.task_id}",
        f"- title: {prepared.title}",
        "",
        "## 任务清单",
        "",
    ]
    for index, repo_id in enumerate(repos or ["未绑定仓库"], start=1):
        lines.extend(
            [
                f"### W{index} [{repo_id}] 执行 Design 方案",
                f"- 目标：在 {repo_id} 按 design.md 和 prd-refined.md 完成本次需求范围内的改动。",
                "- 输入：prd-refined.md、design.md、业务 Skills/SOP。",
                "- 具体做什么：",
            ]
        )
        lines.extend(f"  - {item}" for item in change_scope[:5])
        lines.extend(
            [
                "- 完成标准：",
                f"  - {repo_id} 的改动不超出 Design 文档确认范围。",
                "  - 关键链路完成最小验证。",
                "",
            ]
        )
    lines.extend(["## 执行顺序", ""])
    if len(repos) > 1:
        lines.append("- 按 design.md 中描述的仓库依赖和发布顺序执行；未声明硬依赖的仓库可并行推进。")
    else:
        lines.append("- 单仓执行，无额外跨仓排序要求。")
    lines.extend(["", "## 验证策略", ""])
    lines.extend(f"- {item}" for item in acceptance[:6])
    if non_goals:
        lines.append("- 回归边界：")
        lines.extend(f"  - 不引入非目标：{item}" for item in non_goals[:4])
    lines.extend(["", "## 风险与阻塞项", ""])
    lines.append("- 如果执行时发现 design.md 与真实代码职责不一致，先回到 Design 文档修正后再继续。")
    return "\n".join(lines).rstrip() + "\n"

def _normalize_native_plan_markdown(raw: str) -> str:
    content = raw.strip()
    if not content or "待补充" in content or not content.startswith("# Plan"):
        raise ValueError("plan_template_unfilled")
    for required in ("depends_on", "hard_dependencies", "coordination_points", "acceptance_mapping", "blockers"):
        if required not in content:
            raise ValueError(f"plan_contract_missing:{required}")
    return content.rstrip() + "\n"

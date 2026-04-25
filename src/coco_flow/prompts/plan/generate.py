from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import (
    PLAN_OUTPUT_CONTRACT,
    build_plan_decision_section,
    build_plan_execution_graph_section,
    build_plan_input_section,
    build_plan_validation_section,
    build_plan_work_items_section,
)


def build_plan_template_markdown() -> str:
    return (
        "# Plan\n\n"
        "## 任务清单\n"
        "### W1 [repo_id] 任务标题\n"
        "- repo: `repo_id`\n"
        "- goal: 待补充\n"
        "- change_scope:\n"
        "  - 待补充\n"
        "- specific_steps:\n"
        "  - 待补充\n"
        "- done_definition:\n"
        "  - 待补充\n"
        "- depends_on: none\n"
        "- blocks: none\n"
        "- verify:\n"
        "  - 待补充\n\n"
        "## 执行顺序\n"
        "- hard_dependencies: 待补充；如果没有硬依赖，写 `none` 并说明原因。\n"
        "- parallel_groups: 待补充；如果不能并行，写 `none` 并说明原因。\n"
        "- coordination_points: 待补充；跨仓联调、字段名、配置、发布窗口等写在这里。\n\n"
        "## 验证策略\n"
        "- minimum_checks:\n"
        "  - 待补充\n"
        "- acceptance_mapping:\n"
        "  - 待补充\n"
        "- regression_checks:\n"
        "  - 待补充\n\n"
        "## 风险与阻塞项\n"
        "- blockers: 待补充；会阻止进入 Code 的未知项必须写在这里。\n"
        "- risks: 待补充；不阻止执行但需要注意的问题写在这里。\n"
    )


def build_doc_only_plan_prompt(
    *,
    title: str,
    repo_ids: list[str],
    refined_markdown: str,
    design_markdown: str,
    skills_brief_markdown: str,
    template_path: str,
) -> str:
    skills = skills_brief_markdown.strip() or "当前没有额外 Skills/SOP 摘要。"
    repos_text = ", ".join(repo_id for repo_id in repo_ids if repo_id) or "未绑定"
    return (
        "你在做 coco-flow Plan 阶段。当前第一版采用文档流，不使用结构化 Plan schema。\n\n"
        f"请直接编辑模板文件：{template_path}\n"
        "保留模板的一级标题与章节顺序，输出可交给研发执行的 plan.md。\n"
        "只允许依据 prd-refined.md、design.md、绑定仓库与 Skills/SOP；不要发明新仓库、新需求或新业务规则。\n\n"
        "硬性要求：\n"
        "1. 任务清单必须拆成可执行 work items，每个任务都要有稳定 id（W1、W2...）、repo、goal、change_scope、specific_steps、done_definition、depends_on、blocks、verify。\n"
        "2. depends_on 只能引用已有任务 id；没有依赖时写 none，不要省略字段。\n"
        "3. 跨仓字段、公共模型、接口契约、配置、发布顺序会影响下游任务时，必须写 hard dependency。\n"
        "4. 跨仓联调、配置确认、文案 key、实验字段名、发布窗口等不属于任务先后依赖时，必须写 coordination_points 或 blockers，不要混成普通风险。\n"
        "5. 如果存在进入 Code 前必须确认的信息，必须写入 blockers，并明确阻塞哪些 W 任务。\n"
        "6. 验证策略必须包含 acceptance_mapping，映射 prd-refined.md 的每条验收标准，并写出最小验证命令或检查方式；不能只写泛泛的“验证符合预期”。\n"
        "7. 执行顺序只写真正有约束的关系，不要把叙述顺序伪造成依赖；可并行任务要明确写 parallel_groups。\n\n"
        f"## 任务标题\n{title}\n\n"
        f"## 绑定仓库\n{repos_text}\n\n"
        f"## prd-refined.md\n{refined_markdown.strip()}\n\n"
        f"## design.md\n{design_markdown.strip()}\n\n"
        f"## Skills/SOP 摘要\n{skills}\n\n"
        "完成后只需简短回复已完成。"
    )


def build_plan_generate_agent_prompt(
    *,
    title: str,
    design_markdown: str,
    refined_markdown: str,
    skills_brief_markdown: str,
    work_items_payload: dict[str, object],
    execution_graph_payload: dict[str, object],
    validation_payload: dict[str, object],
    template_path: str,
    regeneration_issues: list[str] | None = None,
    previous_plan_markdown: str = "",
) -> str:
    regeneration_items = [str(item).strip() for item in (regeneration_issues or []) if str(item).strip()]
    requirements = [
        "必须直接编辑指定模板文件，不要只在回复里输出 Markdown。",
        "保留模板中的一级标题和章节顺序，不要擅自删改章节名。",
        "plan.md 必须是结构化 artifacts 的可读派生结果，不能反向发明新的 repo、任务、依赖或验证方案。",
        "“任务清单”只展开 work items 中已有任务，不要把 supporting 背景写成新的主任务。",
        "每个任务都要写 goal、改动范围、specific_steps、完成标准和依赖。",
        "“执行顺序”必须与 execution graph 保持一致，只写真正有约束的关系。",
        "“验证策略”必须与 validation contract 保持一致，优先写最小验证链路和联动验证路径。",
        "内容要像人写的执行方案，但不能偏离结构化结果。",
    ]
    if regeneration_items:
        requirements.append("这是修订模式：必须优先修正“需要修正的问题”中的每一项，再做其他润色。")
    requirements.append("完成后只需简短回复已完成。")
    document = PromptDocument(
        intro="你在做 coco-flow Plan V2 的文档生成。",
        goal="基于结构化的 Plan artifacts，直接编辑指定 Markdown 模板文件，产出最终 plan.md。",
        requirements=requirements,
        output_contract=PLAN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(title="需要编辑的模板文件", body=f"- file: {template_path}\n- 只修改这个 Markdown 文件。"),
            *(
                [PromptSection(title="需要修正的问题", body="\n".join(f"- {item}" for item in regeneration_items))]
                if regeneration_items else []
            ),
            *(
                [PromptSection(title="上一版 Plan 草稿", body=previous_plan_markdown.strip())]
                if previous_plan_markdown.strip() else []
            ),
            build_plan_input_section(
                title=title,
                design_markdown=design_markdown,
                refined_markdown=refined_markdown,
                skills_brief_markdown=skills_brief_markdown,
            ),
            build_plan_work_items_section(work_items_payload),
            build_plan_execution_graph_section(execution_graph_payload),
            build_plan_validation_section(validation_payload),
        ],
    )
    return render_prompt(document)


def build_plan_writer_agent_prompt(
    *,
    title: str,
    decision_payload: dict[str, object],
    template_path: str,
    regeneration_issues: list[str] | None = None,
    previous_plan_markdown: str = "",
) -> str:
    regeneration_items = [str(item).strip() for item in (regeneration_issues or []) if str(item).strip()]
    requirements = [
        "必须直接编辑指定模板文件，不要只在回复里输出 Markdown。",
        "只消费 Plan Decision，不要读取或采信未列出的 draft、聊天历史或旧方案。",
        "保留模板中的一级标题和章节顺序，不要擅自删改章节名。",
        "plan.md 必须是 plan-decision.json 的可读投影，不能反向发明新的 repo、任务、依赖或验证方案。",
        "如果 finalized=false 或 review_blocking_count>0，必须在风险与阻塞项中明确写出不能进入 Code 的原因。",
        "完成后只需简短回复已完成。",
    ]
    if regeneration_items:
        requirements.append("这是修订模式：必须优先修正“需要修正的问题”中的每一项，再做其他润色。")
    return render_prompt(
        PromptDocument(
            intro="你在做 coco-flow Plan Open Harness 的 Writer 角色。",
            goal="基于最终结构化 Plan Decision，直接编辑指定 Markdown 模板文件，产出最终 plan.md。",
            requirements=requirements,
            output_contract=PLAN_OUTPUT_CONTRACT,
            sections=[
                PromptSection(title="需要编辑的模板文件", body=f"- file: {template_path}\n- 只修改这个 Markdown 文件。"),
                *(
                    [PromptSection(title="需要修正的问题", body="\n".join(f"- {item}" for item in regeneration_items))]
                    if regeneration_items else []
                ),
                *(
                    [PromptSection(title="上一版 Plan 草稿", body=previous_plan_markdown.strip())]
                    if previous_plan_markdown.strip() else []
                ),
                PromptSection(title="任务标题", body=title),
                build_plan_decision_section(decision_payload),
            ],
        )
    )

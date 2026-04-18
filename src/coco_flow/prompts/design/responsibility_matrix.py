from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt
from coco_flow.prompts.sections import render_json_block

from .shared import DESIGN_OUTPUT_CONTRACT, build_design_input_section


def build_design_responsibility_matrix_template_json() -> str:
    return (
        '{\n'
        '  "change_points": [\n'
        '    {"id": 1, "title": "__FILL__"}\n'
        '  ],\n'
        '  "repos": [\n'
        '    {\n'
        '      "repo_id": "__FILL__",\n'
        '      "state_definition": "__FILL__",\n'
        '      "state_aggregation": "__FILL__",\n'
        '      "adapter_or_transform": "__FILL__",\n'
        '      "presentation_only": "__FILL__",\n'
        '      "config_or_ab": "__FILL__",\n'
        '      "runtime_notification": "__FILL__",\n'
        '      "must_change_if_goal_holds": false,\n'
        '      "can_goal_ship_without_this_repo": true,\n'
        '      "more_likely_primary_repos": [],\n'
        '      "recommended_scope_tier": "__FILL__",\n'
        '      "reasoning": "__FILL__",\n'
        '      "evidence": ["__FILL__"]\n'
        '    }\n'
        '  ],\n'
        '  "summary": "__FILL__"\n'
        '}\n'
    )


def build_design_responsibility_matrix_agent_prompt(
    *,
    title: str,
    refined_markdown: str,
    knowledge_brief_markdown: str,
    change_points_payload: dict[str, object],
    research_payload: dict[str, object],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Design 的 cross-repo responsibility matrix 汇总。",
        goal="基于 change points 和并发 repo exploration 结果，直接编辑指定 JSON 模板文件，输出跨仓职责矩阵。",
        requirements=[
            "必须直接编辑指定 JSON 文件，不要只在回复里输出结果。",
            "先做职责判断，再做 recommended_scope_tier 判断，不要过早只按相关性打分。",
            "职责强度只使用 high / medium / low / none。",
            "recommended_scope_tier 只使用 must_change / co_change / validate_only / reference_only。",
            "state_definition / state_aggregation 优先级高于 adapter_or_transform。",
            "adapter_or_transform 默认不是主改仓，除非证据显示状态语义只在该层被真正改写。",
            "config_or_ab 默认不是主改仓，除非 refined 明确要求修改实验、开关或配置。",
            "如果单仓可闭合，不要扩成多仓 must_change；必要时可把下游适配层判成 co_change 或 validate_only。",
            "不要引入 research 中没有出现的仓库、文件或模块。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=DESIGN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(title="需要编辑的模板文件", body=f"- file: {template_path}\n- 直接编辑这个 JSON 文件，替换所有 __FILL__ 占位符。"),
            build_design_input_section(title=title, refined_markdown=refined_markdown, knowledge_brief_markdown=knowledge_brief_markdown),
            PromptSection(title="Change Points", body=render_json_block(change_points_payload)),
            PromptSection(title="Repo Research", body=render_json_block(research_payload)),
        ],
    )
    return render_prompt(document)

from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt
from coco_flow.prompts.sections import render_json_block

from .shared import DESIGN_OUTPUT_CONTRACT, build_design_input_section


def build_design_repo_binding_template_json() -> str:
    return (
        '{\n'
        '  "repo_bindings": [\n'
        '    {\n'
        '      "repo_id": "__FILL__",\n'
        '      "repo_path": "__FILL__",\n'
        '      "decision": "__FILL__",\n'
        '      "scope_tier": "__FILL__",\n'
        '      "serves_change_points": [1],\n'
        '      "system_name": "__FILL__",\n'
        '      "responsibility": "__FILL__",\n'
        '      "change_summary": ["__FILL__"],\n'
        '      "boundaries": ["__FILL__"],\n'
        '      "candidate_dirs": ["__FILL__"],\n'
        '      "candidate_files": ["__FILL__"],\n'
        '      "depends_on": [],\n'
        '      "parallelizable_with": [],\n'
        '      "confidence": "__FILL__",\n'
        '      "reason": "__FILL__"\n'
        '    }\n'
        '  ],\n'
        '  "missing_repos": [],\n'
        '  "decision_summary": "__FILL__",\n'
        '  "closure_mode": "__FILL__",\n'
        '  "selection_basis": "__FILL__",\n'
        '  "selection_note": "__FILL__"\n'
        '}\n'
    )


def build_design_repo_binding_agent_prompt(
    *,
    title: str,
    refined_markdown: str,
    knowledge_brief_markdown: str,
    responsibility_matrix_payload: dict[str, object],
    repo_research_payload: dict[str, object],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Design 的 repo binding 裁决。",
        goal="基于 refined 需求、继承知识和 repo research，直接编辑指定 JSON 模板文件，产出正式 repo binding。",
        requirements=[
            "必须直接编辑指定 JSON 文件，不要只在回复里输出结果。",
            "只使用 in_scope / out_of_scope / uncertain 作为 decision。",
            "scope_tier 只使用 must_change / co_change / validate_only / reference_only。",
            "不要引入当前 research 中没有出现的仓库或文件。",
            "只要候选 repo 数量大于 1，也不要假设串行探索顺序本身就是依赖关系。",
            "默认优先最小可闭合改动集；如果单仓可闭合，不要扩成多仓 must_change。",
            "closure_mode 只使用 single_repo / multi_repo / unresolved。",
            "selection_basis 只使用 strong_signal / heuristic_tiebreak / unresolved。",
            "single_repo 只表示实现可以在单仓闭合，不等于已经证明为什么必须选该仓。",
            "如果多个仓库都能单仓闭合，但当前只是默认选一个起始实现仓，selection_basis 必须写 heuristic_tiebreak，并在 selection_note 里说明另一个仓也可承接实现。",
            "消费者/BFF/API/格式化适配层默认先判 validate_only，除非有明确证据说明必须改。",
            "AB/TCC/配置仓默认先判 reference_only，除非 refined 需求明确要求改实验、开关或配置。",
            "领域链路相关不等于本次必须修改；不要因为知识卡提到了某仓就判成 must_change。",
            "通常 must_change 仓库不应超过 2 个，除非 repo research 明确给出强证据。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=DESIGN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(title="需要编辑的模板文件", body=f"- file: {template_path}\n- 直接编辑这个 JSON 文件，替换所有 __FILL__ 占位符。"),
            build_design_input_section(title=title, refined_markdown=refined_markdown, knowledge_brief_markdown=knowledge_brief_markdown),
            PromptSection(title="Responsibility Matrix", body=render_json_block(responsibility_matrix_payload)),
            PromptSection(title="Repo Research", body=render_json_block(repo_research_payload)),
        ],
    )
    return render_prompt(document)

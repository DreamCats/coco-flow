from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT, build_design_input_section


def build_design_repo_research_template_json() -> str:
    return (
        '{\n'
        '  "repo_id": "__FILL__",\n'
        '  "repo_path": "__FILL__",\n'
        '  "decision": "__FILL__",\n'
        '  "role_hint": "__FILL__",\n'
        '  "serves_change_points": [1],\n'
        '  "summary": "__FILL__",\n'
        '  "matched_terms": ["__FILL__"],\n'
        '  "candidate_dirs": ["__FILL__"],\n'
        '  "candidate_files": ["__FILL__"],\n'
        '  "dependencies": [],\n'
        '  "parallelizable_with": [],\n'
        '  "evidence": ["__FILL__"],\n'
        '  "notes": ["__FILL__"],\n'
        '  "confidence": "__FILL__"\n'
        '}\n'
    )


def build_design_repo_research_agent_prompt(
    *,
    title: str,
    refined_markdown: str,
    knowledge_brief_markdown: str,
    repo_id: str,
    repo_path: str,
    prefilter_score: int,
    prefilter_reasons: list[str],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Design 阶段的单仓库 exploration 子任务。",
        goal="只分析当前 cwd 对应仓库，并直接编辑指定 JSON 模板文件，输出当前仓库对 Design 是否重要的结构化结论。",
        requirements=[
            "必须直接编辑指定 JSON 文件，不要只在回复里输出结果。",
            "只分析当前 cwd 仓库，不要替别的仓库下结论。",
            "可以自由使用搜索、读取、命令等工具，但不要改业务代码。",
            "candidate_dirs 和 candidate_files 必须使用当前仓库内的相对路径。",
            "decision 只使用 in_scope_candidate / out_of_scope / uncertain。",
            "role_hint 只使用 primary / supporting / reference。",
            "如果没有明确证据，不要臆造依赖关系；parallelizable_with 只写有明确可并行依据的 repo id。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=DESIGN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(
                title="需要编辑的模板文件",
                body=f"- file: {template_path}\n- 直接编辑这个 JSON 文件，替换所有 __FILL__ 占位符。",
            ),
            build_design_input_section(
                title=title,
                refined_markdown=refined_markdown,
                knowledge_brief_markdown=knowledge_brief_markdown,
            ),
            PromptSection(
                title="当前仓库",
                body="\n".join(
                    [
                        f"- repo_id: {repo_id}",
                        f"- repo_path: {repo_path}",
                        f"- prefilter_score: {prefilter_score}",
                        "- prefilter_reasons:",
                        *(f"  - {item}" for item in prefilter_reasons),
                    ]
                ),
            ),
        ],
    )
    return render_prompt(document)

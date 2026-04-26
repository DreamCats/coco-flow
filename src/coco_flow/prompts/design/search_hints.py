from __future__ import annotations

# Search Hints Agent：只读取 refined PRD，把自然语言需求转成结构化搜索线索。
# 它不读取仓库代码、不做设计裁决，只为本地 rg/git evidence prefilter 降低召回噪音。

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT


def build_search_hints_template_json() -> str:
    return json.dumps(
        {
            "search_terms": ["__FILL__"],
            "likely_symbols": ["__FILL__"],
            "likely_file_patterns": ["__FILL__"],
            "negative_terms": ["__FILL__"],
            "confidence": "medium",
            "rationale": "__FILL__",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_search_hints_prompt(
    *,
    title: str,
    refined_markdown: str,
    design_skills_brief_markdown: str,
    repo_context_payload: list[dict[str, object]],
    template_path: str,
    design_skills_index_markdown: str = "",
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design V3 的 Search Hints Agent。",
            goal="只根据 refined PRD 提取代码搜索线索，直接编辑指定 JSON 文件。",
            requirements=[
                "不要读取、遍历或推断仓库代码内容；本阶段只处理 PRD 和 repo 标识信息。",
                "不要做架构设计、repo 职责判断或 candidate_files 裁决。",
                "Design Skills Index 中的文件可以按需读取完整内容，用于补充稳定术语、常见模块名和 SOP 检查点。",
                "Design Skills Brief 只是 local fallback 摘要，不得替代完整 skill 文件，不得扩写 refined PRD。",
                "不要使用固定业务词特判；只从 PRD 的实体、动作、状态、接口名、字段名、验收点中提取线索。",
                "search_terms 放适合 rg/git 搜索的业务词、英文词、状态值、接口/字段片段。",
                "likely_symbols 放可能出现在函数、类型、常量、组件、API 或字段名里的标识符片段。",
                "likely_file_patterns 放可能出现在文件名或目录名里的短片段，不要写宽泛后缀如 *.go、*.ts。",
                "negative_terms 放容易造成误召回、且 PRD 明确排除的词。",
                "confidence 只能是 high / medium / low；证据来自 PRD 越明确，confidence 越高。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Design Skills Index", design_skills_index_markdown.strip() or "- 当前没有 Design skills index。"),
                PromptSection("Design Skills Local Fallback", design_skills_brief_markdown.strip() or "- 当前没有 Design skills fallback。"),
                PromptSection("Repo 标识信息", json.dumps(repo_context_payload, ensure_ascii=False, indent=2)),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )

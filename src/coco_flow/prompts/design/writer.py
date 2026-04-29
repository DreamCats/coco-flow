from __future__ import annotations

# Writer Agent：把最终结构化 decision 转写成人可读的 design.md。
# 它可以改善表达和结构，但不能新增 repo、文件或范围裁决。

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT


def build_doc_only_design_prompt(
    *,
    title: str,
    refined_markdown: str,
    repo_scope_markdown: str,
    research_summary_markdown: str,
    skills_fallback_markdown: str,
    template_path: str,
    skills_index_markdown: str = "",
) -> str:
    skills_index = skills_index_markdown.strip() or "当前没有额外 Skills/SOP 索引。"
    skills_fallback = skills_fallback_markdown.strip() or "当前没有 local fallback 摘要。"
    return (
        "你在做 coco-flow Design 阶段。当前第一版采用文档流，不使用结构化 Design schema。\n\n"
        f"请直接编辑模板文件：{template_path}\n"
        "保留 Markdown 文档形态，输出可给研发评审和后续 Plan 使用的 design.md。\n"
        "只允许依据 prd-refined.md、绑定仓库代码证据、仓库职责和 Skills/SOP；不要输出 JSON，不要发明新需求。\n"
        "如果 Skills/SOP 索引列出了文件路径，必须先读取这些完整文件，再引用其中的稳定规则、术语、repo role 和 SOP。\n"
        "Skills local fallback 摘要只能在文件不可读时辅助判断，不得替代完整 skill 文件。\n\n"
        "design.md 必须可直接进入研发评审，不能只复述核心改造点或搜索结果。\n"
        "必须保留或补齐这些章节：结论、核心改造点、方案设计、分仓库职责、验收与验证、风险与待确认、明确不做。\n"
        "方案设计要写业务层设计结论：用户可见变化、服务端策略、实验与回退、影响范围隔离；不要写成搜索摘要。\n"
        "每个涉及仓库只写人需要判断的信息：职责、是否改造、改造层级、边界和回退策略。\n"
        "仓库职责优先使用这些语义：必改、条件改、仅作为参考、不改、职责待确认。公共仓/配置仓/协议仓只有在缺少公共字段或共享能力时才写成条件改，不要默认写成必改。\n"
        "候选文件、函数名、搜索命中原因、confidence/kind/core_evidence 等机器证据只能作为内部判断依据，不要展开到 design.md。\n"
        "Repo research summary 中的排除文件代表命中 PRD 非目标，不能写成主改造落点。\n"
        "模板或输入中已有的待确认项必须保留；如果发现 PRD 口径冲突，要补到“风险与待确认”。\n"
        "改造方案必须覆盖 refined PRD 的关键验收约束，例如实验命中条件、本地化取值、空值回退、分隔符、未命中实验保持不变等；如果某项不适用，写明原因。\n"
        "如果 repo research 只有相关性证据而不能证明必须修改，应写成待确认或仅需验证，不要把搜索命中包装成确定改造点。\n\n"
        f"## 任务标题\n{title}\n\n"
        f"## prd-refined.md\n{refined_markdown.strip()}\n\n"
        f"## 绑定仓库\n{repo_scope_markdown.strip() or '- 未绑定仓库'}\n\n"
        f"## Repo research summary\n{research_summary_markdown.strip() or '- 暂无代码调研摘要。'}\n\n"
        f"## Skills/SOP 索引\n{skills_index}\n\n"
        f"## Skills local fallback 摘要\n{skills_fallback}\n\n"
        "写入 design.md 时只保留对研发有用的自然语言信息；不要复制 Python dict、JSON payload、候选文件清单、搜索命中原因或内部字段。\n"
        "完成后只需简短回复已完成。"
    )


def build_writer_prompt(
    *,
    title: str,
    decision_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            goal="本次任务：把 design-decision.json 转写成设计文档，只编辑指定 Markdown 文件。",
            requirements=[
                "不要新增 repo 裁决、候选文件或需求。",
                "结论先行，使用自然语言，不暴露 must_change/confidence 等内部标签。",
                "每个涉及仓库都说明主要做什么、候选文件或模块、边界是什么。",
                "如果 Design Decision 含 repo_dependencies，必须单独写“仓库依赖与发布顺序”，说明上游 producer、下游 consumer、依赖原因和前置关系。",
                "只需检查的仓库不要写成本次代码改造项。",
                "待确认项只写会影响研发判断的问题。",
                "如果 finalized=false 或 review_blocking_count>0，必须在结论中明确写“当前不能进入 Plan”，并列出阻断原因。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 直接覆盖为最终 Markdown。"),
                PromptSection("任务标题", title),
                PromptSection("Design Decision", json.dumps(decision_payload, ensure_ascii=False, indent=2)),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )

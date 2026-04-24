from __future__ import annotations

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

DESIGN_OUTPUT_CONTRACT = (
    "你必须直接编辑指定 JSON 或 Markdown 模板文件。不要只在回复中输出结果。"
    "不得引入 refined PRD、repo research 或 skills brief 之外的新需求。"
)


def build_architect_template_json() -> str:
    return json.dumps(
        {
            "decision_summary": "__FILL__",
            "core_change_points": ["__FILL__"],
            "repo_decisions": [
                {
                    "repo_id": "__FILL__",
                    "work_type": "must_change",
                    "responsibility": "__FILL__",
                    "candidate_files": ["__FILL__"],
                    "candidate_dirs": ["__FILL__"],
                    "boundaries": ["__FILL__"],
                    "risks": ["__FILL__"],
                    "unresolved_questions": ["__FILL__"],
                    "confidence": "medium",
                    "evidence_refs": ["__FILL__"],
                }
            ],
            "system_boundaries": ["__FILL__"],
            "risks": ["__FILL__"],
            "unresolved_questions": ["__FILL__"],
        },
        ensure_ascii=False,
        indent=2,
    )


def build_skeptic_template_json() -> str:
    return json.dumps(
        {
            "ok": False,
            "issues": [
                {
                    "severity": "blocking",
                    "failure_type": "__FILL__",
                    "target": "__FILL__",
                    "expected": "__FILL__",
                    "actual": "__FILL__",
                    "suggested_action": "__FILL__",
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def build_revision_template_json() -> str:
    return json.dumps(
        {
            "issue_resolutions": [
                {
                    "failure_type": "__FILL__",
                    "target": "__FILL__",
                    "resolution": "accepted",
                    "reason": "__FILL__",
                    "decision_change": "__FILL__",
                }
            ],
            "decision": json.loads(build_architect_template_json()),
        },
        ensure_ascii=False,
        indent=2,
    )


def build_semantic_gate_template_json() -> str:
    return json.dumps(
        {
            "ok": False,
            "gate_status": "needs_human",
            "issues": [],
            "reason": "__FILL__",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_architect_prompt(
    *,
    title: str,
    refined_markdown: str,
    skills_brief_markdown: str,
    research_plan_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design V3 的 Architect Agent。",
            goal="基于 refined PRD 和 repo research 证据做跨仓设计裁决，直接编辑指定 JSON 文件。",
            requirements=[
                "只做设计裁决，不写 design.md。",
                "不要把相关仓库直接等同于必须修改；必须有 evidence 才能判为 must_change。",
                "证据不足时写 unresolved_questions，不要为了流程通过隐藏不确定性。",
                "work_type 只使用 must_change / co_change / validate_only / reference_only。",
                "candidate_files 必须来自 repo research 的 candidate_files，且 evidence 必须能说明该文件承接本需求；不得只因为关键词命中就使用。",
                "validate_only / reference_only 仓库不要写 candidate_files；只写需要验证的问题、边界和 evidence_refs。",
                "如果 evidence 只证明“相关”而不能证明“需要改”，应降级为 validate_only 或写 unresolved_questions。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Skills Brief", skills_brief_markdown),
                PromptSection("Research Plan", json.dumps(research_plan_payload, ensure_ascii=False, indent=2)),
                PromptSection("Research Summary", json.dumps(research_summary_payload, ensure_ascii=False, indent=2)),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )


def build_skeptic_prompt(
    *,
    title: str,
    refined_markdown: str,
    adjudication_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design V3 的 Skeptic Agent。",
            goal="反向审查 Architect 裁决是否被 PRD 和 repo evidence 支撑，直接编辑指定 JSON 文件。",
            requirements=[
                "只输出结构化审查结果，不重写方案。",
                "重点找误选 repo、遗漏核心 repo、候选文件无证据、PRD 未覆盖。",
                "blocking issue 必须给出 target、expected、actual 和 suggested_action。",
                "无证据的反对只能标为 warning 或 info。",
                "如果没有 blocking 或 warning，ok=true 且 issues=[]。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Architect Adjudication", json.dumps(adjudication_payload, ensure_ascii=False, indent=2)),
                PromptSection("Research Summary", json.dumps(research_summary_payload, ensure_ascii=False, indent=2)),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )


def build_revision_prompt(
    *,
    title: str,
    refined_markdown: str,
    adjudication_payload: dict[str, object],
    review_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design V3 的 Architect Revision Agent。",
            goal="根据 skeptic 的 blocking/warning issues 对架构裁决做一次有界修订，并直接编辑指定 JSON 文件。",
            requirements=[
                "必须逐条处理 review issues，在 issue_resolutions 中写 accepted / rejected。",
                "accepted 的 issue 必须实际修改 decision；不能只追加到 unresolved_questions。",
                "如果 issue 指出候选文件场景不符、字段不存在、与 non-goal 冲突，应删除该候选文件或降级仓库职责。",
                "rejected 必须引用 research evidence 证明原判断成立。",
                "不得扩大 refined PRD 范围，不得新增 research 中不存在的文件。",
                "validate_only / reference_only 仓库不要携带 candidate_files。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Original Adjudication", json.dumps(adjudication_payload, ensure_ascii=False, indent=2)),
                PromptSection("Skeptic Review", json.dumps(review_payload, ensure_ascii=False, indent=2)),
                PromptSection("Research Summary", json.dumps(research_summary_payload, ensure_ascii=False, indent=2)),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )


def build_writer_prompt(
    *,
    title: str,
    decision_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design V3 的 Writer Agent。",
            goal="只把 design-decision.json 写成高质量 design.md，直接编辑指定 Markdown 文件。",
            requirements=[
                "不要新增 repo 裁决、候选文件或需求。",
                "结论先行，使用自然语言，不暴露 must_change/confidence 等内部标签。",
                "每个涉及仓库都说明主要做什么、候选文件或模块、边界是什么。",
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


def build_semantic_gate_prompt(
    *,
    title: str,
    refined_markdown: str,
    decision_payload: dict[str, object],
    design_markdown: str,
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design V3 的 Semantic Gate。",
            goal="检查 design.md 是否真实表达 design-decision.json 且能支撑 refined PRD，直接编辑指定 JSON 文件。",
            requirements=[
                "同时检查 contract gate 和 semantic gate。",
                "gate_status 只使用 passed / passed_with_warnings / needs_human / degraded / failed。",
                "证据不足、关键仓职责冲突、PRD 未覆盖时不要通过。",
                "仅有非阻塞风险时使用 passed_with_warnings。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Design Decision", json.dumps(decision_payload, ensure_ascii=False, indent=2)),
                PromptSection("Design Markdown", design_markdown),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )

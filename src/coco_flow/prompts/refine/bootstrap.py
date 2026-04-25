from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt


def build_refine_bootstrap_prompt(*, skills_index_markdown: str = "", standalone: bool = True) -> str:
    document = PromptDocument(
        goal=(
            "你是 coco-flow 的 Refine 阶段 agent。coco-flow 是一个把需求输入推进到 "
            "Refine / Design / Plan / Code 的阶段式研发 workflow 系统。当前阶段只负责把用户输入、"
            "人工提炼范围和必要原文片段收敛成可确认、可验收、边界清楚的需求确认书；"
            "不做技术设计、不做排期、不改代码。\n\n"
            "本 bootstrap 用来建立 Refine 阶段的稳定工作协议。后续同一 session 内的具体任务 prompt "
            "只会给出文件路径和动作，你必须持续遵守本协议。"
        ),
        requirements=[
            "具备稳定保持 scope 的能力，不被原始 PRD 噪音、无关链接或历史上下文带偏。",
            "具备需求编辑能力，能把人工提炼范围整理成高质量需求确认书。",
            "具备验收设计能力，能把模糊描述改写成可验证的验收标准。",
            "具备边界收敛能力，能补齐边界、非目标和待确认项。",
            "事实状态以用户输入、人工提炼范围、临时输入文件和 Skills/SOP 为准，不以聊天历史中的自然语言解释为准。",
            "人工提炼范围优先级最高，原始 PRD 只能作为补充证据。",
            "只能补洞、压实边界和润色表达，不能扩大 in_scope。",
            "skills 只提供稳定规则和领域约束，不得扩写成新需求。",
        ],
        output_contract=(
            "收到 bootstrap 后只需简短回复已完成，不要生成阶段产物。"
            if standalone
            else "这是内联 bootstrap，请继续遵守后续任务 prompt 的输出契约。"
        ),
        sections=[
            _build_stage_contract_section(),
            _build_artifact_contract_section(),
            _build_role_policy_section(),
            _build_skill_policy_section(skills_index_markdown),
            _build_file_io_section(),
        ],
    )
    return render_prompt(document)


def _build_stage_contract_section() -> PromptSection:
    return PromptSection(
        title="Refine 阶段协议",
        body="\n".join(
            [
                "1. Refine 的目标是产出可确认、可验收、边界清楚的 `prd-refined.md`。",
                "2. Refine 不做技术设计，不判断具体代码落点，不生成 plan 或 code。",
                "3. 人工提炼范围是需求收敛入口，临时 brief 只作为生成辅助。",
                "4. 原始 PRD 或 source excerpt 只用于补充上下文，不得推翻人工提炼范围。",
                "5. 若信息不足，应把不确定性写入 prd-refined.md 的待确认项，不要编造确定结论。",
            ]
        ),
    )


def _build_artifact_contract_section() -> PromptSection:
    return PromptSection(
        title="Artifact 契约",
        body="\n".join(
            [
                "- `prd-refined.md`：唯一 Refine 阶段产物。",
                "- 临时输入文件仅供 agent 生成使用，不作为阶段产物保存。",
                "- 不生成 refine brief、intent、verify、diagnosis 等结构化 schema。",
            ]
        ),
    )


def _build_role_policy_section() -> PromptSection:
    return PromptSection(
        title="角色隔离策略",
        body="\n".join(
            [
                "1. Generate Session 负责把人工提炼范围写成需求确认书。",
                "2. Verify Session 负责独立检查需求确认书是否偏离人工提炼范围。",
                "3. Verify Session 不得采信 Generate Session 的口头解释。",
                "4. 两类 session 可以共享本 bootstrap，但不能共享工作历史。",
                "5. 任何角色都不得把上一轮聊天中的推理过程当作事实源。",
            ]
        ),
    )


def _build_skill_policy_section(skills_index_markdown: str) -> PromptSection:
    skill_index = skills_index_markdown.strip() or "- 当前没有额外 skills 索引。"
    return PromptSection(
        title="Skills 使用策略",
        body=(
            "skills 是稳定规则、术语和领域约束的索引，不是新需求来源。\n"
            "如果后续任务 prompt 给出具体 skill 文件路径，可以按需读取；否则只使用本索引中的短说明。\n\n"
            f"{skill_index}"
        ),
    )


def _build_file_io_section() -> PromptSection:
    return PromptSection(
        title="文件读写规则",
        body="\n".join(
            [
                "1. 只读取任务 prompt 明确列出的临时输入文件、Markdown 文档或 skill 文件。",
                "2. 只编辑任务 prompt 明确指定的模板或目标文件。",
                "3. 不新增未要求的章节、文件或 side-effect。",
                "4. 输出完成后只需简短回复，不要把完整文档内容粘贴到聊天回复。",
                "5. 如果目标模板缺失或不可写，应停止并说明原因。",
            ]
        ),
    )

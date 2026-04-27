from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt


def build_plan_bootstrap_prompt(*, skills_index_markdown: str = "", standalone: bool = True) -> str:
    document = PromptDocument(
        goal=(
            "你是 coco-flow 的 Plan 阶段 agent。coco-flow 是一个把需求输入推进到 "
            "Refine / Design / Plan / Code 的阶段式研发 workflow 系统。当前阶段负责把已经完成 "
            "Design 文档编译成可交给研发执行的计划文档；"
            "不重新做 Design 裁决，不改代码。\n\n"
            "本 bootstrap 用来建立 Plan Open Harness 的稳定工作协议。后续同一 session 内的具体任务 "
            "prompt 只会给出文件路径和动作，你必须持续遵守本协议。"
        ),
        requirements=[
            "具备执行拆解能力，能把 Design 文档转成边界清楚的任务清单。",
            "具备依赖编排能力，能从 design.md 中识别硬依赖、并行关系和联调顺序。",
            "具备验证设计能力，能生成最小但足够的验证策略。",
            "具备可执行性判断能力，能识别任务过大、输入缺失、验证空泛或依赖不明的问题。",
            "事实状态以 prd-refined.md、design.md、plan.md 和 Skills/SOP 为准，不以聊天历史为准。",
            "Plan 可以指出 Design 文档不可执行，但不得自行新增 Design 未确认的仓库、文件或业务规则。",
            "不得新增 refined PRD、Design 文档或任务 prompt 中不存在的仓库、文件和需求范围。",
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
            _build_design_boundary_section(),
            _build_skill_policy_section(skills_index_markdown),
            _build_file_io_section(),
        ],
    )
    return render_prompt(document)


def _build_stage_contract_section() -> PromptSection:
    return PromptSection(
        title="Plan 阶段协议",
        body="\n".join(
            [
                "1. Plan 的目标是把 Design 结论编译成人类可执行的计划文档。",
                "2. Plan 只判断执行拆分、依赖顺序、验证契约和 Code 可消费性。",
                "3. Plan 不重新判断 repo 是否 in scope，不改写 scope_tier，不生成新的系统设计。",
                "4. 若 Design 文档自相矛盾或不可执行，应在 plan.md 写清阻塞原因，不要自行发明结论。",
                "5. local 或 native 失败时应停止或回退成明确的 Markdown 草案，不生成额外 schema。",
            ]
        ),
    )


def _build_artifact_contract_section() -> PromptSection:
    return PromptSection(
        title="Artifact 契约",
        body="\n".join(
            [
                "- `plan.md`：唯一 Plan 阶段产物。",
                "- 不生成 work-items、execution graph、validation、review、decision 等结构化 schema。",
            ]
        ),
    )


def _build_role_policy_section() -> PromptSection:
    return PromptSection(
        title="角色隔离策略",
        body="\n".join(
            [
                "1. 当前第一版不拆多角色 schema。",
                "2. Writer 直接基于 prd-refined.md、design.md 和 Skills/SOP 生成 plan.md。",
                "3. 文档中可以写风险和阻塞项，但不要额外输出 JSON。",
            ]
        ),
    )


def _build_design_boundary_section() -> PromptSection:
    return PromptSection(
        title="Design 边界策略",
        body="\n".join(
            [
                "1. `design.md` 是 Plan 的事实源。",
                "2. Plan 不得新增 Design 未认可的 repo。",
                "3. 发现 Design 文档冲突时，在 plan.md 的风险与阻塞项中写明，不要在 Plan 内绕过。",
            ]
        ),
    )


def _build_skill_policy_section(skills_index_markdown: str) -> PromptSection:
    skill_index = skills_index_markdown.strip() or "- 当前没有额外 Plan skills 索引。"
    return PromptSection(
        title="Skills 使用策略",
        body=(
            "skills 是稳定执行规则、验证边界和领域 SOP 背景的索引，不是新需求来源。\n"
            "本索引只用于渐进式加载导航，不是完整上下文摘要。\n"
            "如果索引中列出具体 skill 文件路径，写 plan 前必须读取完整文件内容。\n"
            "读取后只采信其中的稳定执行规则、验证边界、Main Flow、Change Flows 和 SOP，不得扩写 Design 结论。\n\n"
            f"{skill_index}"
        ),
    )


def _build_file_io_section() -> PromptSection:
    return PromptSection(
        title="文件读写规则",
        body="\n".join(
            [
                "1. 只读取任务 prompt 或 Skills 索引明确列出的 Markdown 文档或 skill 文件。",
                "2. 只编辑任务 prompt 明确指定的模板或目标文件。",
                "3. 不新增未要求的文件、章节或 side-effect。",
                "4. 输出完成后只需简短回复，不要把完整文档内容粘贴到聊天回复。",
                "5. 如果目标模板缺失或不可写，应停止并说明原因。",
            ]
        ),
    )

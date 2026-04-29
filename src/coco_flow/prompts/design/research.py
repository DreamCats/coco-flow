from __future__ import annotations

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT


def build_design_research_template_json() -> str:
    return json.dumps(
        {
            "repo_id": "",
            "repo_path": "",
            "work_hypothesis": "unknown",
            "confidence": "medium",
            "skill_usage": {
                "read_files": [],
                "applied_rules": [],
                "derived_search_hints": [],
            },
            "claims": [],
            "candidate_files": [],
            "rejected_candidates": [],
            "boundaries": [],
            "unknowns": [],
            "next_search_suggestions": [],
            "summary": "",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_design_research_prompt(
    *,
    title: str,
    refined_markdown: str,
    repo_context_payload: dict[str, object],
    skills_index_markdown: str,
    skills_fallback_markdown: str,
    template_path: str,
    repo_context_package: dict[str, object] | None = None,
    retry_instructions: list[str] | None = None,
) -> str:
    retry_text = "\n".join(f"- {item}" for item in retry_instructions or [] if item.strip()) or "- 首轮调研，无额外重试指令。"
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design 阶段的 Research Agent。你可以自己搜索仓库、读取文件和查看 git 历史。",
            goal="基于 refined PRD、当前单个 repo 和 Skills/SOP，找出可审计的代码证据，并直接编辑指定 JSON 模板文件。",
            requirements=[
                "本次只调研“当前 repo”，不要跨到其他 repo 做判断。",
                "如果 Skills/SOP 索引列出文件路径，必须先读取相关完整 skill 文件；并在 skill_usage.read_files 写明读取了哪些文件。",
                "必须在 skill_usage.applied_rules 写明哪些规则真正用于本 repo 判断；没有读取或没有适用规则时也要明确说明。",
                "必须在 skill_usage.derived_search_hints 写明从 PRD 和 Skills/SOP 推导出的搜索入口。",
                "如果提供了 Research Context Engine 线索，优先用它缩小搜索空间；但它只是候选线索，不可替代实际读文件和证据判断。",
                "必须自己读取仓库证据；不要只根据文件名、聊天历史或猜测判断。",
                "凡是写入 claims/candidate_files 的代码文件，都必须同步写入 skill_usage.read_files；否则会被视为未读证据。",
                "每个 candidate 都必须有具体文件路径、行号或符号，以及能支撑 claim 的简短证据。",
                "不要把弱相关搜索命中包装成主改造落点；证据不足时写入 unknowns 或 rejected_candidates。",
                "必须显式处理 refined PRD 的非目标；混合职责文件不要整文件排除，要说明哪些函数/链路在范围内、哪些不在范围内。",
                "必须检查实现动作所需上下文是否可达，例如 request context、AB/experiment、locale、TCC/config；不可达时写入 unknowns 或 context_notes。",
                "如果 refined PRD 只写“命中实验/未命中实验”但没有给具体实验 key，涉及 AB/实验/公共配置职责的 repo 不能写成 not_needed；应写 conditional，并把“复用已有实验字段还是新增字段”放入 unknowns。",
                "work_hypothesis 只使用 required / conditional / reference_only / not_needed / unknown。",
                "candidate_files 只放可作为 Plan 起点的文件；背景文件、入口 handler、公共配置可以放入 claims 或 context_notes，但不要硬标主落点。",
                "如果当前 repo 只是 reference_only / not_needed，claims、candidate_files、rejected_candidates 可以写空数组，但必须写清 boundaries / unknowns / summary。",
                "所有数组字段都允许为空数组；没有证据或不适用时写 []，不要写占位字符串。",
                "不要在输出 JSON 中写入 __FILL__；不确定的信息写入 unknowns 或留空字符串。",
                "输出必须是严格合法 JSON：字符串里的换行、tab 和代码片段要转义或改成数组项；行号范围必须写成字符串，例如 \"120-128\"。",
                "如果一轮搜索无法支撑需求改动点，写 next_search_suggestions，供 Supervisor 触发下一轮。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 直接编辑这个 JSON 文件；不要新增 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("当前 repo", json.dumps(repo_context_payload, ensure_ascii=False, indent=2)),
                PromptSection(
                    "Research Context Engine 线索",
                    json.dumps(repo_context_package or {}, ensure_ascii=False, indent=2)
                    if repo_context_package
                    else "- 当前没有预计算线索。",
                ),
                PromptSection("Skills/SOP 索引", skills_index_markdown.strip() or "- 当前没有 Skills/SOP 索引。"),
                PromptSection("Skills local fallback", skills_fallback_markdown.strip() or "- 当前没有 local fallback 摘要。"),
                PromptSection("Supervisor 重试指令", retry_text),
                PromptSection("合法 JSON 示例", _research_json_format_example()),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )


def build_design_research_review_template_json() -> str:
    return json.dumps(
        {
            "passed": False,
            "decision": "redo_research",
            "confidence": "medium",
            "blocking_issues": [],
            "research_instructions": [],
            "reason": "",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_design_research_review_prompt(
    *,
    title: str,
    refined_markdown: str,
    research_payload: dict[str, object],
    template_path: str,
    skills_index_markdown: str = "",
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design 阶段的 Research Supervisor，负责审查 Research Agent 的证据是否足够。",
            goal="判断 research evidence 是否足以支撑后续 design.md；不够就给出下一轮搜索指令，并直接编辑指定 JSON 模板文件。",
            requirements=[
                "decision 只使用 pass / redo_research / needs_human / degrade_design / fail。",
                "如果 candidate 缺少具体文件、符号、行号或 claim 证据，不能 pass。",
                "如果任一 repo 的 research_status=failed，不能 pass；通常应对失败 repo redo_research。若失败 repo 确认不影响核心实现，也必须 decision=needs_human 或 degrade_design，并把该 repo 写入待确认原因。",
                "如果 selected Skills/SOP 存在，但 repo 的 skill_usage.read_files 为空，不能 high confidence pass；通常应 redo_research。",
                "如果 required repo 的 candidate_files 没有出现在 skill_usage.read_files 中，或 claims 引用的代码文件没有被读取，不能 pass。",
                "如果 skill_usage.applied_rules 或 derived_search_hints 为空，必须判断是否影响定位；影响时 redo_research。",
                "如果 evidence 无法覆盖 refined PRD 的核心改动点，不能 pass。",
                "如果 non-goal 处理不清楚，尤其是混合职责文件被整文件误排或弱相关文件被当主落点，不能 pass。",
                "如果实现动作需要 request context、AB/experiment、locale、TCC/config 等上下文，但 research 未说明可达性，不能 pass。",
                "如果 refined PRD 提到实验命中但未明确实验 key，而涉及 AB/实验/公共配置职责的 repo 被标为 not_needed，不能 pass；应改为 conditional 并进入 Design 待确认项。",
                "如果已确认实现落点、上下文可达性和同类实现方式，只缺具体 AB 参数 key、Starling key、TCC key 或配置字段命名，这属于 Design 待确认项，不要因此 redo_research。",
                "redo_research 时必须给出具体搜索方向、要读的文件/符号、要验证的调用链或 git 线索；如果只需要某个 repo 补查，指令里必须明确写 repo_id。",
                "输出必须是严格合法 JSON：blocking_issues 必须是对象数组，research_instructions 必须是字符串数组；不要输出裸字符串列表、Python dict 或未转义代码片段。",
                "最多只要求补足 Design 所需证据，不要要求进入 Plan 或写代码。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 直接编辑这个 JSON 文件；不要新增 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("已选 Skills/SOP 索引", skills_index_markdown.strip() or "- 当前没有已选 Skills/SOP。"),
                PromptSection("Research Payload", json.dumps(research_payload, ensure_ascii=False, indent=2)),
                PromptSection("合法 JSON 示例", _research_review_json_format_example()),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )


def _research_json_format_example() -> str:
    return json.dumps(
        {
            "repo_id": "repo_id",
            "repo_path": "/repo/path",
            "work_hypothesis": "required",
            "confidence": "high",
            "skill_usage": {
                "read_files": [
                    "/skills/example/SKILL.md",
                    "src/module/file.go",
                ],
                "applied_rules": ["已读取相关 SOP，并确认当前 repo 是主要实现仓。"],
                "derived_search_hints": ["从 PRD 和 SOP 推导出入口函数 buildSomething。"],
            },
            "claims": [
                {
                    "claim": "核心逻辑在 buildSomething 中生成用户可见字段。",
                    "evidence": [
                        "src/module/file.go:120-128 定义 buildSomething。",
                        "不要把多行代码原样粘进 JSON；请写成短句或数组项。",
                    ],
                    "file_path": "src/module/file.go",
                    "line_start": 120,
                    "line_end": 128,
                }
            ],
            "candidate_files": [
                {
                    "path": "src/module/file.go",
                    "symbol": "buildSomething",
                    "reason": "直接生成本次需求要调整的用户可见字段。",
                    "confidence": "high",
                    "line": 120,
                    "evidence": ["读取该文件后确认函数和调用点均在本 repo 内。"],
                    "context_notes": ["如果仍缺配置名或文案 key，写入 unknowns。"],
                }
            ],
            "rejected_candidates": [],
            "boundaries": ["不在本次范围内的相邻链路不要写入 candidate_files。"],
            "unknowns": ["配置字段名待确认。"],
            "next_search_suggestions": [],
            "summary": "已定位主要实现入口，剩余配置名进入 Design 待确认。",
        },
        ensure_ascii=False,
        indent=2,
    )


def _research_review_json_format_example() -> str:
    return json.dumps(
        {
            "passed": False,
            "decision": "redo_research",
            "confidence": "medium",
            "blocking_issues": [
                {
                    "type": "missing_candidate_evidence",
                    "summary": "required repo 的 candidate file 未出现在 skill_usage.read_files 中。",
                    "evidence": ["repo_id=repo_id candidate_files[0].path=src/module/file.go"],
                }
            ],
            "research_instructions": [
                "repo_id=repo_id: 读取 src/module/file.go，确认 buildSomething 的调用链和上下文可达性。"
            ],
            "reason": "缺少候选文件读取证据，暂不能支撑 design.md。",
        },
        ensure_ascii=False,
        indent=2,
    )

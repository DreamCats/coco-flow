from __future__ import annotations

# Design V3 角色 prompt 的共享输出契约。
# 每个角色都直接编辑 controller 管理的 artifact 文件，模型回复本身不是事实源。

DESIGN_OUTPUT_CONTRACT = (
    "你必须直接编辑指定 JSON 或 Markdown 模板文件。不要只在回复中输出结果。"
    "不得引入 refined PRD、repo research 或 Skills/SOP 之外的新需求。"
)

from __future__ import annotations

# Shared contract for Design V3 role prompts. Each role edits a controller-owned
# artifact file, so the model response is never the source of truth by itself.

DESIGN_OUTPUT_CONTRACT = (
    "你必须直接编辑指定 JSON 或 Markdown 模板文件。不要只在回复中输出结果。"
    "不得引入 refined PRD、repo research 或 skills brief 之外的新需求。"
)


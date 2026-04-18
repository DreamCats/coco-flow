# Refine V2 Implementation Slices

本文用于把 `Refine V2` 的实现拆成可连续落地的小任务。

## Slice 1: Prompt 基础设施

目标：

- 建立统一 `src/coco_flow/prompts/` 目录
- 建立 Prompt 文档对象与 section 工具
- 落 `Refine V2` 的 prompt builders

完成标志：

- `Refine V2` 的 prompt 不再散落在 engine 文件里
- 后续 `Plan / Code` 可以复用同一体系

## Slice 2: Refine V2 输入模型

目标：

- 建立 `Refine V2` 专用输入模型
- 只依赖 `prd.source.md + input.json + source.json`
- 删除 repo context 依赖

完成标志：

- `Refine V2` 输入不再读取 repo
- Input Bundle 契约稳定

## Slice 3: 知识候选筛选

目标：

- 程序先筛 `approved + refine`
- frontmatter 渐进式加载
- LLM 分块 shortlist

完成标志：

- 产出 `refine-knowledge-selection.json`
- 能解释为什么选了某些知识文档

## Slice 4: 知识深读

目标：

- 对 shortlisted knowledge 做全文深读
- 提取术语解释、稳定规则、冲突提醒

完成标志：

- 产出 `refine-knowledge-read.md`

## Slice 5: 意图提炼

目标：

- 以 Input Bundle 为基础提炼核心诉求、风险 seed、讨论点 seed、边界 seed

完成标志：

- 产出 `refine-intent.json`

## Slice 6: 生成与校验

目标：

- 按新 5 章结构生成 `prd-refined.md`
- verifier 检查结构、风险、讨论点、边界、臆测

完成标志：

- 产出 `prd-refined.md`
- 产出 `refine-verify.json`

## Slice 7: 替换旧 Refine

目标：

- 新 `Refine V2` 成为默认实现
- 旧 `engines/refine/` prompt 与旧动作删除

完成标志：

- `services/tasks/refine.py` 只调用新实现
- 旧 `refine` prompt builders 不再保留

## 当前建议顺序

按下面顺序推进：

1. Slice 1
2. Slice 2
3. Slice 3
4. Slice 5
5. Slice 4
6. Slice 6
7. Slice 7

原因：

- 先有 Prompt 基础设施
- 再稳定输入契约
- 然后完成知识筛选
- 意图提炼与知识深读可以并行推进
- 最后再切主链路与删除旧实现

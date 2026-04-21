# Prompt System Design

本文定义 `coco-flow` 后续统一的 Prompt 模块化方案。

目标不是“把 prompt 换个目录放”，而是把 prompt 从 engine 代码里系统地拆出来，让 `Refine / Design / Plan / Code` 都能共用一套组织方式。

## 目标

统一 Prompt 系统需要解决 4 个问题：

1. Prompt 不能继续散落在 engine 文件里。
2. 每一步 prompt 要能单独演进、单独测试。
3. 各阶段需要共享一些公共片段与渲染能力。
4. 同一种任务类型要有一致的命名和目录结构。

## 目录约定

统一放在：

```text
src/coco_flow/prompts/
```

一级目录按阶段或领域拆分：

```text
src/coco_flow/prompts/
├── __init__.py
├── core.py
├── sections.py
├── refine/
├── design/
├── plan/
└── code/
```

说明：

- `core.py`：Prompt 文档对象与统一渲染入口
- `sections.py`：公共 section / list / fenced block 组装工具
- `refine/`：Refine 各步骤 prompt
- `design/`、`plan/`、`code/`：后续阶段逐步迁移到同一体系

## 模块粒度

每个 prompt 文件只负责一个明确子任务。

例如 `Refine V2`：

```text
src/coco_flow/prompts/refine/
├── __init__.py
├── shared.py
├── intent.py
├── shortlist.py
├── knowledge_read.py
├── generate.py
└── verify.py
```

含义：

- `shared.py`：Refine V2 共用说明、输出契约、上下文拼装
- `intent.py`：意图提炼 prompt
- `shortlist.py`：知识候选筛选 prompt
- `knowledge_read.py`：知识深读 prompt
- `generate.py`：Refined 文档生成 prompt
- `verify.py`：校验与批注 prompt

## 命名约定

builder 统一采用：

- `build_<stage>_<step>_prompt(...)`

例如：

- `build_refine_intent_prompt(...)`
- `build_refine_shortlist_prompt(...)`
- `build_plan_scope_prompt(...)`
- `build_code_retry_prompt(...)`

禁止继续出现过于宽泛的命名，例如：

- `build_prompt`
- `build_ai_prompt`
- `make_prompt`

## Prompt 对象模型

Prompt 不直接手写成巨型三引号字符串，而是先组装成统一对象，再统一 render。

建议最小对象：

- `PromptSection`
- `PromptDocument`

这样做的原因：

1. 各 prompt 可以共享统一结构
2. 可以更容易插拔 section
3. 更容易做测试和 diff

## 统一渲染原则

最终给模型的仍然是字符串，但内部先按结构组装。

建议的统一结构：

1. 背景 / 角色
2. 目标
3. 要求
4. 输出契约
5. 输入材料
6. 附加上下文

不是每个 prompt 都必须包含全部 6 块，但顺序应尽量稳定。

## 公共 section 能力

`sections.py` 里建议统一提供：

1. bullet list 渲染
2. numbered list 渲染
3. JSON fenced block
4. YAML fenced block
5. Markdown section 包装
6. 空值兜底

这样后续就不需要每个 prompt builder 重复写格式化逻辑。

## Engine 与 Prompt 的边界

### engine 负责

- 输入读取
- 中间 artifact 组织
- LLM 调用时机
- 错误处理与降级
- 结果落盘

### prompt module 负责

- 如何向模型表达任务
- 输出契约如何写清楚
- 各输入材料如何拼接
- 哪些要求需要重复强调

一句话：

- engine 管流程
- prompts 管表达

## 渐进式迁移原则

不能一次性把所有 prompt 全重构。

建议迁移顺序：

1. `Refine V2`
2. `Plan`
3. `Code`

原因：

- `Refine V2` 本来就要重写
- `Plan` 当前 prompt 拆得最多，最适合接入统一体系
- `Code` 变化风险最大，最后迁移更稳

## 本轮实施边界

本轮先做到：

1. 搭建 `src/coco_flow/prompts/` 基础骨架
2. 把 `Refine V2` prompt builders 单独落文件
3. 不在本轮直接重写旧 `plan` / `code`

## 一句话结论

统一 Prompt 系统的关键不是“集中存放”，而是：

- 按子任务拆文件
- 按结构组装
- 按阶段统一命名
- 让 engine 不再直接维护大段 prompt 字符串

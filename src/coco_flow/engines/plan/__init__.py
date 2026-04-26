"""Plan 引擎对外入口。

Plan 阶段的目标是把上游的人类可读产物编译成 Code 阶段可消费的执行契约。
输入侧主要读取：

- ``prd-refined.md``：明确本次需求范围、验收标准和待确认项。
- ``design.md``：明确技术方案、分仓职责、依赖关系和风险。
- ``repos.json``：明确本次任务绑定哪些仓库。
- ``.livecoding/context`` 与 Skills/SOP：补充仓库知识、术语和执行规则。

输出侧同时保留面向人的 Markdown 和面向机器的结构化 artifact：

- ``plan.md``：任务级总计划，给用户整体审阅。
- ``plan-repos/<repo>.md``：仓库级任务清单，给用户按仓编辑和确认。
- ``plan-work-items.json``：Code V2 使用的任务拆分。
- ``plan-execution-graph.json``：跨仓/跨任务依赖图与执行顺序。
- ``plan-validation.json``：给 Code 阶段使用的验证焦点。
- ``plan-sync.json``：记录 Markdown 与结构化 artifact 是否同步。
- ``plan-result.json``：Plan gate，决定是否允许直接进入 Code。

主流程由 ``pipeline.run_plan_engine`` 编排：

1. ``input.prepare_plan_input`` 读取 task 目录、解析 refined/design、加载 repo scope。
2. ``knowledge.build_plan_skills_bundle`` 基于任务和仓库挑选 Skills/SOP，生成完整文件路径索引。
3. ``writer.generate_doc_only_plan_markdown`` 尝试让 native writer 写 ``plan.md``；
   native 不可用或输出不可用时回退到 local 渲染。
4. ``compiler.build_structured_plan_artifacts`` 从 refined/design/repo scope 编译结构化
   work items、execution graph、validation、gate result 和 repo plan markdown。
5. ``compiler.validate_plan_artifacts`` 做最低限度的结构校验，避免缺 repo、缺任务、
   依赖引用错误这类会阻断 Code 的问题。

目录职责边界：

- ``pipeline.py``：唯一主编排入口，按 input -> knowledge -> compiler -> writer 串联。
- ``types.py``：Plan 阶段的数据模型、状态常量和 executor 常量。
- ``input/``：只负责读取和整理输入材料，不做计划决策。
- ``knowledge/``：只负责选择可用知识，生成渐进式加载索引和 local fallback excerpt，不写 artifact。
- ``writer/``：只负责生成任务级 ``plan.md`` 文本。
- ``compiler/``：只负责结构化 artifact、repo plan markdown 和 Sync Plan 的构建/校验。
- ``runtime/``：封装 native ACP session 与 ``plan.log``，避免核心逻辑依赖 client 细节。

``services.tasks.plan`` 是 workflow 壳：负责状态流转、落盘、写日志和 repo status 同步；
本包只承担 Plan 引擎本身的输入准备、生成和结构化编译。

架构思路是“LLM 负责读语义和写人看的文档，程序规则负责稳定产物和执行约束”。
Plan 的核心问题不是能否生成一篇长文，而是能否稳定回答三个问题：

- 每个仓库到底要做什么？
- 仓库之间谁依赖谁，执行顺序是什么？
- 当前信息是否足够让 Code 阶段安全开工？

因此本阶段不把所有责任都交给一次 LLM 写作，而是拆成两条产物线：

- 面向人的 Markdown：保留可读、可编辑、方便 UI 分 tab 展示的 plan 文档。
- 面向机器的 JSON：保留 Code 阶段需要的 work item、依赖图、验证焦点和 gate。

这样做解决了旧 Plan 的几个问题：

- 长文档不适合 UI 交互：用户很难在一个巨大的 ``plan.md`` 里找到某个仓的任务。
- 多仓依赖容易丢：LLM 写了“先改 A 再改 B”，但 Code 阶段未必能稳定解析出来。
- fallback 质量不稳定：native 失败后如果只渲染空泛模板，会得到“planned”但不能指导执行。
- 人工编辑和机器执行混在一起：用户改 Markdown 后，不应让 Code 阶段误以为结构化契约也同步变化。
  ``plan-sync.json`` 会在编辑后标记未同步，Code 阶段必须等待 Sync Plan。
  Sync Plan 会保留用户编辑后的 Markdown，只刷新结构化 JSON 契约。

当前边界：

- 使用 LLM 的部分：
  - ``writer`` 在 native executor 下调用 ACP writer 生成任务级 ``plan.md``。
  - LLM 只被用来整理语义、生成自然语言计划，不直接作为 Code gate 的唯一来源。
- 使用程序规则的部分：
  - ``input`` 读取文件、解析 refined/design、聚合 repo scope。
  - ``knowledge`` 选择 Skills/SOP，并提供完整文件路径索引；不把完整上下文提前压缩给 native LLM。
  - ``compiler`` 从已知输入构建 work items、依赖边、repo markdown 和 gate result。
  - ``compiler.validate_plan_artifacts`` 校验任务覆盖、repo 覆盖、依赖引用、validation 覆盖。
  - ``services.tasks.plan`` 负责 artifact 落盘、状态更新和 repo 状态同步。

程序规则不是为了替代 LLM，而是给 LLM 输出加“可执行骨架”：即使 native writer
失败，也能基于 refined/design/repo scope 生成保底可用的分仓任务、依赖图和 gate。
LLM 擅长解释意图和写作；程序规则擅长保证结构完整、引用一致、Code 阶段可消费。
"""

from .input import locate_task_dir
from .pipeline import run_plan_engine
from .runtime import append_plan_log
from .types import EXECUTOR_NATIVE, LogHandler, STATUS_FAILED, STATUS_PLANNED, STATUS_PLANNING

__all__ = [
    "EXECUTOR_NATIVE",
    "LogHandler",
    "STATUS_FAILED",
    "STATUS_PLANNED",
    "STATUS_PLANNING",
    "append_plan_log",
    "locate_task_dir",
    "run_plan_engine",
]

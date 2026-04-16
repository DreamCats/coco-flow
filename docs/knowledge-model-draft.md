# Knowledge Model Draft

这份草稿只回答 5 个问题：

1. `.livecoding/context` 该怎么看
2. 新知识库应该放哪里
3. 最小知识模型是什么
4. 知识文件应该长什么样
5. 它具体怎样帮助 `refine` 和 `plan`

目标是先把方向说清楚，不把模型说复杂。

## 先说结论

### 1. `.livecoding/context` 可以保留，但不是未来主模型

当前每个 repo 下的 `.livecoding/context`，更像：

- repo 本地的 LLM 上下文
- 面向单仓库的辅助知识
- 类似“可检索版 AGENTS”

它有价值，但它不是 `coco-flow` 想要建设的主知识库。

原因很简单：

- 它是单仓库视角
- 我们要的是 workflow product 上层的通用知识
- 后续知识库可能需要团队共享，而不是散在各个 repo 里

所以建议是：

- 短期：引擎仍然可以参考 `.livecoding/context`
- 中期：把它降级为一种“补充上下文来源”
- 长期：必要时可以在 `AGENTS.md` 里引用它，但不把它当成主存储

### 2. 新知识库不要存到 `.livecoding/context`

这点我同意。

新的知识库应该独立于 repo 本地上下文，默认放在 `tasks` 同级目录，和 `task_root` 一样支持配置。

基于当前配置结构：

- `config_root`: 默认 `~/.config/coco-flow`
- `task_root`: 默认 `~/.config/coco-flow/tasks`

建议新增：

- `knowledge_root`: 默认 `~/.config/coco-flow/knowledge`

也就是：

```text
~/.config/coco-flow/
├── tasks/
└── knowledge/
```

后续支持通过配置或环境变量覆盖路径，比如：

- `COCO_FLOW_KNOWLEDGE_ROOT`

这样做有几个直接好处：

- 不绑定单仓库
- 方便未来独立 git 管理和团队共享
- 和 `tasks` 生命周期解耦
- 引擎更容易同时读取“全局知识”和“repo 局部上下文”

### 3. 不把方向做成 RAG 项目

这点也同意。

这件事现阶段不该叫“上 RAG”，而应该叫：

- 定义适合引擎消费的知识结构
- 做好倒排索引和定向召回
- 做好渐进式加载

也就是说，我们先不讨论向量库，先把“知识文件格式”和“召回路径”定义对。

### 4. 借 `SKILL.md` 的形式，不借它的指令语气

这是一个很好的方向。

`skills` 最值得借的不是正文风格，而是：

- 文件开头有稳定、简短、可索引的 metadata
- 模型可以先看摘要，再决定是否继续加载正文

知识文件可以借这个形式，但不要写成 `skill` 那种“教模型怎么做事”的 instruction。

知识文件应当写：

- 业务事实
- 系统链路
- 业务规则
- 代码落点

而不是写：

- 你应该如何推理
- 你应该如何调用工具
- 你必须按什么步骤行动

一句话：

- 借 `skill` 的 frontmatter 结构
- 不把知识文件写成 `skill`

## 最小知识模型

我建议先只保留 3 类对象，够用就行。

### 1. Domain

表示一个业务方向。

例如：

- 竞拍讲解卡
- 竞拍购物袋

最小字段：

- `id`
- `name`
- `aliases`
- `summary`
- `owners`

它回答的问题是：

- 这是什么业务方向
- 常见别名是什么
- 这个方向谁负责

### 2. Flow

表示一个系统链路。

这是最重要的对象。

例如：

- 竞拍讲解卡表达层链路
- 竞拍购物袋状态流转链路

最小字段：

- `id`
- `domain_id`
- `name`
- `summary`
- `entry`
- `steps`
- `dependencies`
- `risks`

它回答的问题是：

- 从哪里开始
- 经过哪些系统
- 哪些环节会联动
- 风险通常在哪里

### 3. Rule

表示业务规则。

最小字段：

- `id`
- `domain_id`
- `flow_id`
- `statement`
- `exceptions`
- `priority`

它回答的问题是：

- 默认规则是什么
- 哪些情况例外
- 哪些规则优先级更高

### 可选元信息

每类对象都可以带少量元信息：

- `source`
- `updated_at`
- `owner`

先到这里就够了，不需要再拆太细。

## 知识文件格式建议

建议每个知识文件都采用：

- Markdown 正文
- 文件开头一小段 frontmatter

这样做有两个直接好处：

1. 头部 metadata 适合做倒排索引和第一跳召回
2. 正文适合在真正命中后再加载，避免一次性灌太多上下文

建议的最小头部字段：

```md
---
kind: flow
id: auction_explain_card_render
title: 竞拍讲解卡表达层链路
desc: 说明竞拍讲解卡在表达层的渲染入口、依赖模块、状态变化和常见风险。
engines: [plan, refine]
domains: [auction_explain_card]
keywords: [讲解卡, 表达层, 渲染, 卡片]
repos: [live_pack, live_sdk]
paths: [app/explain_card, sdk/render]
priority: high
updated_at: 2026-04-15
owner: maifeng
---
```

字段解释：

- `kind`
  表示它是哪类对象，例如 `domain / flow / rule`
- `id`
  稳定标识
- `title`
  给人看的一句话标题
- `desc`
  给引擎做第一跳判断的短描述
- `engines`
  这个文件优先给 `refine`、`plan` 还是都可用
- `domains`
  归属的业务方向
- `keywords`
  倒排索引的主入口
- `repos`
  可能关联的 repo
- `paths`
  可能关联的目录或代码区域，用来表达轻量 repo hints，不是长期维护的精确代码映射
- `priority`
  候选排序时可参考

正文建议保持固定 section，但不必复杂。比如：

- `## Summary`
- `## Main Flow`
- `## Rules`
- `## Risks`
- `## Repo Hints`

不同对象可以略有差异：

- `domain` 文件偏 `Summary / Terms / Rules / Related Flows`
- `flow` 文件偏 `Main Flow / Dependencies / Risks / Repo Hints`
- `rule` 文件偏 `Statement / Exceptions / Scope`

## 渐进式加载建议

我建议把知识加载做成三段，而不是一上来全量读全文。

### 第一步：只看头部 metadata

引擎先读取知识目录里所有文件的 frontmatter，不读正文。

这一层只做：

- 建倒排索引
- 做粗召回
- 找候选文件

主要使用的字段：

- `desc`
- `keywords`
- `domains`
- `repos`
- `paths`
- `engines`

### 第二步：让模型在候选文件里做精选

先通过倒排索引、关键词匹配、domain 命中等规则，筛出 top N 文件。

然后把下面这些输入交给 LLM：

- PRD 或 refined PRD
- 其他补充文件
- 候选知识文件的头部摘要

让模型判断：

- 哪些文件最值得继续加载
- 当前更需要 `domain / flow / rule` 中的哪几类

这一步不是让模型在全库里瞎选，而是在已粗筛的候选里做精选。

### 第三步：只加载被选中的正文

只有真正命中的文件，才加载正文 section。

这样可以避免：

- token 浪费
- 不相关知识干扰
- 单次 prompt 过重

一句话就是：

- 规则先粗筛
- 模型再细判
- 命中后再读全文

## 存储建议

建议先用文件化存储，但不放在 repo 里。

例如：

```text
knowledge/
├── domains/
│   ├── auction-explain-card.md
│   └── auction-shopping-bag.md
├── flows/
│   ├── auction-explain-card-render.md
│   └── shopping-bag-lifecycle.md
├── rules/
│   ├── auction-explain-card.md
│   └── auction-shopping-bag.md
```

这样足够简单，也方便后续单独建 git 仓库。

如果后面要做共享，可以有两种方式：

1. `knowledge_root` 指向本地 checkout 的团队知识库目录
2. `coco-flow` 提供同步能力，把远程知识库拉到本地目录

现阶段优先第 1 种，简单直接。

## `.livecoding/context` 在新模型里的位置

建议把 `.livecoding/context` 定义成“补充上下文来源”，不是“主知识库”。

也就是说：

- 主知识库：`knowledge_root`
- repo 局部上下文：`.livecoding/context`

两者分工：

- `knowledge_root` 负责通用业务知识和系统知识
- `.livecoding/context` 负责 repo 局部背景、实现习惯、局部术语

这样引擎就不会被单仓库限制住。

## 这 3 类对象怎样帮助引擎

### 对 refine 的帮助

`refine` 不需要太多代码细节，它需要的是：

- 术语别名
- 默认业务规则
- 哪些地方容易歧义

所以 `refine` 主要吃：

- `Domain`
- `Rule`

必要时补一点 `Flow` 摘要。

推荐加载策略：

1. 先基于 PRD 用倒排索引粗筛候选知识文件
2. 再让 LLM 根据 `desc` 判断优先加载哪些 `domain / rule / flow`
3. 最后加载少量正文 section

最直接的收益：

- 减少术语理解错误
- 更容易补出边界条件
- 更容易识别“这里需要待确认”

### 对 plan 的帮助

`plan` 需要的是系统链路和代码落点。

所以 `plan` 主要吃：

- `Flow`
- `Anchor`
- 部分 `Rule`

推荐加载策略：

1. 先基于 refined PRD 和 repo 信息粗筛候选知识文件
2. 让 LLM 依据候选头部摘要挑选更相关的 `flow / rule`
3. 再加载这些文件的正文，最后进入 repo research

最直接的收益：

- 更容易判断涉及哪些系统
- 更容易知道涉及哪些 repo 以及每个 repo 大概要做什么
- 不再只是靠 glossary + `rg` 猜文件

## 推荐的引擎读取顺序

### refine

建议顺序：

1. 先读 task 输入
2. 用知识文件头部 metadata 做粗筛
3. 让模型判断应该加载哪些 `Domain + Rule`
4. 必要时补一点 `Flow` 摘要
5. 再参考 repo 下 `.livecoding/context`

一句话：

- 先用全局业务知识校准语义
- 再用 repo 局部上下文补细节

### plan

建议顺序：

1. 读 refined PRD
2. 用头部 metadata 做粗筛
3. 让模型判断应优先加载哪些 `Flow + Rule`
4. 再到目标 repo 做本地搜索
5. 必要时参考 `.livecoding/context`

一句话：

- 先理解链路
- 再搜代码

## 为什么这样更合适

因为我们真正需要的不是“更多上下文”，而是“更适合引擎工作的上下文”。

如果继续把所有东西堆在 `.livecoding/context`：

- 视角太偏单仓库
- 不利于跨 repo / 跨系统复用
- 不利于团队共享
- 不利于构建产品层知识能力

如果先做一个很轻的独立知识库：

- 概念简单
- 存储简单
- 引擎收益直接
- 后续可继续演进

## 近期建议

我建议先做最小试点，不要一次做大。

第一步只做：

1. 新增 `knowledge_root` 配置
2. 定义知识文件 frontmatter 格式
3. 定义 3 类最小对象
4. 先手工写 1 个领域
5. 先接入 `plan`

为什么先接 `plan`：

- `Flow + Anchor` 的收益最直观
- 更容易验证有没有帮助
- 比 `refine` 更容易看出 candidate files 和链路判断是否变准

试点领域建议还是：

- 竞拍讲解卡

因为你已经明确指出它的“表达层系统链路”对引擎很有帮助，这就是一个很好的试点对象。

## 最后一句

这件事不该做成一个复杂知识平台。

现阶段最合理的版本是：

- 独立知识目录
- 统一 frontmatter
- 3 类最小对象
- 倒排粗筛 + LLM 精选 + 正文渐进加载
- 主打 `Flow`
- `.livecoding/context` 只做补充来源

先把这一步做对，后面再谈索引、共享和治理。

# 知识工作台 Skill 化迁移规划与执行方案

本文记录把当前 `knowledge workbench` 直接切换为 `skills workbench` 的目标方案、收口边界和执行步骤。

当前前提：

- 现有 knowledge 模型还没有稳定用户和外部依赖。
- 可以直接删除旧的 `knowledge` 存储/API/UI/engine 消费链路，不做兼容层。
- 新模型目标不是“继续维护一堆 Markdown 卡片”，而是“维护 skill package”。

如本文与代码不一致，以代码为准。

## 目标结论

这次迁移的结论明确如下：

1. 收掉旧 knowledge 模型，不保留 `KnowledgeDocument` 这套文档中心设计。
2. Web UI 左侧从“知识卡片列表”改成“skill 文件浏览器”。
3. 右侧改成“文件查看 + 编辑”，面向 skill package 内的 `SKILL.md`、`references/*`、可选 `agents/openai.yaml`。
4. `refine` / `plan` 不再扫描 `knowledge_root/domains|flows|rules/*.md`，改为扫描 `skills_root/**/SKILL.md`。
5. `refine` / `plan` 先只基于 `SKILL.md` 的最小 frontmatter 信息做 shortlist，再按路径深读被选中的 skill 包。
6. `wiki-test` 里现有的 domain / flow 文档不再当最终知识文档，而是转成某个业务 skill 的 `references/` 内容。

## 为什么直接切

当前代码里的 knowledge 已经是完整模型，不只是 UI：

- API：`/api/knowledge*`
- Web：`web/src/routes/knowledge.tsx`
- 存储：`src/coco_flow/services/queries/knowledge.py`
- Refine：`src/coco_flow/engines/refine/knowledge.py`
- Plan：`src/coco_flow/engines/plan_knowledge.py`
- Model：`src/coco_flow/models/knowledge.py`

如果继续沿着旧模型迭代，最终会同时维护两套抽象：

- 产品层：想维护的是 skill package
- engine 层：消费的还是 knowledge document

这会让 Web UI、落盘结构和 engine 选择逻辑长期错位。既然现在没有用户和兼容压力，应该直接切到最终想要的模型，而不是先补一个“更像文件浏览器的 knowledge UI”。

## 当前问题

当前 knowledge 工作台的主要问题不是样式，而是对象建模不对。

现状：

- 左侧是卡片列表，适合“选文档”，不适合“维护一个 package”。
- 右侧虽然支持源码编辑，但底层对象仍然是单文档。
- `kind=domain|flow|rule` 把知识拆成离散卡片，适合 LLM 评分，不适合人维护。
- `refine` 和 `plan` 当前都默认知识源是 `approved knowledge docs`，不是 skill package。

结果是：

- 维护侧想按业务域组织内容
- engine 侧想按短卡片评分
- 两边组织方式不一致

## 目标模型

### 根目录

已归档说明：当前实现已不再使用单一本地 `skills_root`，Skills 只从 `skills-sources.json` 配置的 Git source 读取，并缓存到 `~/.config/coco-flow/skills-sources/<source_id>/`。

历史迁移计划曾提出 skill 根目录：

```text
~/.config/coco-flow/skills/
```

对应配置改为：

- 新增 `skills_root`
- 废弃并删除 `knowledge_root`
- 该方案已废弃，不再提供 skills root 环境变量

本次迁移不保留兼容别名。

### Package 结构

每个业务知识单元不是单篇文档，而是一个 skill package：

```text
auction-popcard/
├── SKILL.md
├── references/
│   ├── domain.md
│   ├── main-flow.md
│   ├── change-workflows.md
│   ├── repos/
│   │   ├── live_shop.md
│   │   ├── live_shopapi.md
│   │   ├── live_pack.md
│   │   └── content_live_bff_lib.md
│   └── rules.md
└── agents/
    └── openai.yaml   # 可选，v1 可不强制
```

`SKILL.md` 负责：

- 触发元信息
- 使用边界
- 选择参考资料的导航
- 输出约束

`references/` 负责：

- 领域背景
- 主链路
- repo 责任分层
- 稳定规则
- 历史兼容点

### `SKILL.md` frontmatter 约定

skill 规范里必填的是 `name` 和 `description`。这里不想把 skill 变成一套 `coco-flow` 私有 schema，所以 v1 只额外增加一个 `domain` 字段，不再补 `stages`、`repos`、`tags`、`priority` 之类的定制字段。

推荐约定：

```md
---
name: auction-popcard
description: 处理直播电商竞拍讲解卡相关需求，适用于 refine/plan 阶段判断主链路、责任 repo、边界和验证点。
domain: auction_pop_card
---
```

说明：

- `name` / `description` 继续兼容 Codex skill 规范。
- `domain` 是唯一新增字段，用来补一层业务域路由信息。
- 当前阶段是 `refine` 还是 `plan`，由引擎自己知道，不需要再写进 frontmatter。
- repo、tag、priority、owner 等信息先不入模，避免 skill metadata 过度定制化。

## `wiki-test` 的映射方式

`/Users/bytedance/go/src/code.byted.org/coco-flow-wiki-test/auction_pop_card_render/` 里的现有文档，不建议继续按“知识卡”形态原样引入，而应映射成一个业务 skill package。

推荐映射：

- `domain-auction-popcard-reference.md` -> `auction-popcard/references/domain.md`
- `flow-auction-popcard-render-reference.md` -> `auction-popcard/references/main-flow.md`
- 后续 repo 调研内容 -> `auction-popcard/references/repos/*.md`
- 若有稳定兼容规则 -> `auction-popcard/references/rules.md`

也就是说，当前 `wiki-test` 更像 skill 的 `references` 原料，不是最终结构。

## Web UI 目标

### 左侧

左侧不再展示知识卡片列表，改为 skill 文件浏览器。

推荐结构：

- 按 skill package 展开
- 展示目录树和文件树
- 默认突出 `SKILL.md`
- 支持新建 package / 新建文件 / 新建目录 / 删除 / 重命名

左侧示例：

```text
Skills
├── auction-popcard
│   ├── SKILL.md
│   ├── references
│   │   ├── domain.md
│   │   ├── main-flow.md
│   │   ├── change-workflows.md
│   │   └── repos
│   │       ├── live_shop.md
│   │       └── live_pack.md
│   └── agents
│       └── openai.yaml
└── protocol-driven-live-shopapi
    ├── SKILL.md
    └── references
```

### 右侧

右侧按文件类型提供查看与编辑：

- `SKILL.md`
  - Markdown 源码编辑
  - frontmatter 折叠查看
  - 渲染预览
- `references/*.md`
  - Markdown 源码编辑
  - 渲染预览
- `agents/openai.yaml`
  - YAML 源码编辑

不再围绕“文档状态切换”和“单文档 metadata 卡片”设计。

### 产品语义

路由和导航建议从：

- `/knowledge`
- “知识工作台”

改成：

- `/skills`
- “Skills 工作台”

如果希望保留中文语义，也建议叫：

- “业务 Skills”
- “Skills 工作台”

而不是继续叫“知识工作台”，避免产品名和数据模型继续错位。

## API 目标

当前 `/api/knowledge*` 整套接口应该删除。

新增 skill workbench API：

- `GET /api/skills/tree`
  返回 skill 根目录下的 package / dir / file 树。
- `GET /api/skills/file?path=...`
  读取某个文件内容。
- `PUT /api/skills/file?path=...`
  保存某个文件内容。
- `POST /api/skills/package`
  新建一个 skill package 骨架。
- `POST /api/skills/node`
  新建文件或目录。
- `DELETE /api/skills/node?path=...`
  删除文件或目录。
- `POST /api/skills/rename`
  重命名文件或目录。

如果想压缩首版范围，可以先只做：

- tree
- read file
- write file
- create package

其余操作后补。

## Refine / Plan 的新接入方式

这是这次迁移最核心的部分。

### 基本原则

`refine` / `plan` 不直接扫 skill 全文，而是分两段：

1. 只扫 `SKILL.md` 的最小 frontmatter，形成 shortlist 候选。
2. 选中后，再把 skill 路径交给后续步骤去深读 `SKILL.md` 和必要的 `references/`。

这样做的原因：

- 元信息扫描便宜，适合全量遍历。
- skill 正文和 references 可能很长，不适合全量塞进上下文。
- 符合 skill 的 progressive disclosure 设计。

### Refine 新流程

替换当前：

- `shortlist_refine_knowledge()`
- `read_selected_knowledge()`

为：

1. `list_refine_skill_candidates()`
   - 扫描 `skills_root/**/SKILL.md`
   - 解析 `name` / `description` / `domain`

2. `shortlist_refine_skills()`
   - 规则打分：name/description/domain/term 命中
   - LLM 基于最小 frontmatter 做 0..N shortlist
   - 输出 `refine-skills-selection.json`

3. `read_selected_skills_for_refine()`
   - 给 agent 选中的 skill 路径
   - 先读 `SKILL.md`
   - 再按 `SKILL.md` 导航读取对应 references
   - 输出 `refine-skills-read.md`

4. refine 生成阶段消费 `refine-skills-read.md`

### Plan 新流程

替换当前：

- `build_plan_knowledge_brief()`

为：

1. `list_plan_skill_candidates()`
2. `shortlist_plan_skills()`
3. `build_plan_skill_brief()`

核心区别与 refine 相同：

- shortlist 用最小 frontmatter
- brief 用 selected skill 的正文和 references

输出 artifacts 建议改名：

- `plan-skills-selection.json`
- `plan-skills-brief.md`

## 选择算法建议

用户提出的思路基本对，这里只补一个边界：

> 不需要设计一套很厚的 metadata，v1 只在 `name` / `description` 之外补一个 `domain` 即可。

建议 score 维度先收敛为：

- `name` 是否命中需求术语
- `description` 是否命中关键业务词
- `domain` 是否命中需求术语或业务域词
- 当前输入物料里的 repo / 术语是否与该 skill 的正文导航相符

推荐流程：

1. 规则先过滤出高相关候选
2. 再让 LLM 只看候选 `name` / `description` / `domain` 做 shortlist
3. 最终再读被选中的 skill 包

这样比“全量 LLM 看所有 skill 正文”更稳，也不会把 metadata 做得太重。

## 代码改动范围

### 需要删除

- `src/coco_flow/models/knowledge.py`
- `src/coco_flow/services/queries/knowledge.py`
- `src/coco_flow/cli/commands/knowledge.py`
- `web/src/routes/knowledge.tsx`
- `web/src/knowledge/types.ts`
- `/api/knowledge*` 相关 API

### 需要重写或替换

- `src/coco_flow/engines/refine/knowledge.py`
- `src/coco_flow/engines/plan_knowledge.py`
- `src/coco_flow/api/app.py` 中 knowledge 相关部分
- `web/src/router.tsx` 的 knowledge route / nav
- `web/src/api.ts` 的 knowledge client
- `src/coco_flow/config.py` 中 `knowledge_root`
- `src/coco_flow/services/queries/workspace.py` 中 `knowledgeRoot`

### 需要新增

- `src/coco_flow/services/queries/skills.py`
- `src/coco_flow/engines/refine/skills.py`
- `src/coco_flow/engines/plan_skills.py`
- `web/src/routes/skills.tsx`
- `web/src/skills/types.ts`

## 执行顺序

### Slice 1: 配置与存储层

目标：

- 引入 `skills_root`
- 实现 skill tree / file store
- 删掉 `knowledge_root`

产物：

- `Settings.skills_root`
- `SkillStore`

验收：

- 能列出 `skills_root` 下的 package/tree
- 能读取和保存 `SKILL.md`

### Slice 2: Web UI 改成 Skills 工作台

目标：

- 路由切换到 `/skills`
- 左侧文件树
- 右侧文件查看/编辑/预览

验收：

- 能打开 skill tree
- 能编辑 `SKILL.md`
- 能编辑 `references/*.md`
- 不再依赖旧 knowledge card schema

### Slice 3: API 切换

目标：

- 删除 `/api/knowledge*`
- 接上 `/api/skills*`

验收：

- Web skills 工作台只走新 API
- 后端不再 import `KnowledgeDocument`

### Slice 4: Refine 接 skill shortlist / read

目标：

- shortlist 改为 skill 最小 frontmatter
- deep read 改为 skill package

验收：

- refine log 不再出现 `knowledge_*`
- 新 log 改为 `skills_*`
- 输出新的 refine skill artifacts

### Slice 5: Plan 接 skill shortlist / brief

目标：

- plan brief 来源改为 skills

验收：

- plan log 不再出现 `plan_knowledge_*`
- 改为 `plan_skills_*`
- 输出新的 plan skill artifacts

### Slice 6: 清理与文档收口

目标：

- 删掉旧 knowledge dead code
- 更新 README / AGENTS / docs

验收：

- 仓库内不再保留旧 knowledge API/UI/model/store
- README / AGENTS 不再描述 knowledge documents

## artifact 与日志命名

既然本次是直接切模型，artifact 和日志也应该同步换名，不保留旧名字。

建议替换：

- `refine-knowledge-selection.json` -> `refine-skills-selection.json`
- `refine-knowledge-read.md` -> `refine-skills-read.md`
- `design-knowledge-brief.md` -> `design-skills-brief.md`
- `plan-knowledge-selection.json` -> `plan-skills-selection.json`
- `plan-knowledge-brief.md` -> `plan-skills-brief.md`

日志替换：

- `knowledge_shortlist_*` -> `skills_shortlist_*`
- `knowledge_read_*` -> `skills_read_*`
- `plan_knowledge_*` -> `plan_skills_*`

## 非目标

这次迁移不做：

- skill marketplace / 远程同步
- 自动发布到 `$CODEX_HOME/skills`
- 复杂权限系统
- skill 版本管理
- knowledge 与 skills 双写

## 风险与控制

### 风险 1：最小 frontmatter 太薄，skill shortlist 不准

控制：

- 保持 `name` / `description` / `domain` 足够清晰
- 先规则筛，再 LLM 筛

### 风险 2：SKILL.md 写太厚，读包成本高

控制：

- 强制 `SKILL.md` 保持导航型
- 详细内容放 `references/`

### 风险 3：Web UI 文件树复杂度上升

控制：

- v1 只支持 markdown/yaml 文件
- 不做复杂拖拽和多选

### 风险 4：Refine / Plan 改动面大

控制：

- 按 slice 拆
- 每个阶段先做定向 `py_compile` 和最小 smoke

## 验收标准

迁移完成时，应满足：

1. Web 不再存在旧 knowledge card 工作台。
2. skill package 可以在 UI 中被浏览、打开、编辑。
3. refine 能基于 `SKILL.md` 的 `name` / `description` / `domain` 选 skill，并基于选中路径深读 skill。
4. plan 能基于 `SKILL.md` 的 `name` / `description` / `domain` 选 skill，并生成 skill brief。
5. 仓库内不再存在旧 `KnowledgeDocument` 主模型和 `/api/knowledge*`。
6. `wiki-test` 的竞拍讲解卡资料可以整理进一个标准 skill package，而不是散落成单文档知识卡。

## 推荐首个样板 skill

建议直接用竞拍讲解卡做第一个样板：

```text
auction-popcard/
├── SKILL.md
├── references/domain.md
├── references/main-flow.md
├── references/repos/live_shop.md
├── references/repos/live_shopapi.md
├── references/repos/live_pack.md
└── references/repos/content_live_bff_lib.md
```

这个样板应验证三件事：

1. skill 最小 frontmatter 是否足够支持 refine / plan shortlist
2. references 拆分是否便于人工维护
3. Web 文件树编辑是否比旧知识卡片更顺手

## 最终建议

这次迁移不建议做成“旧 knowledge UI 的增强版”，而应直接作为一次模型切换来做。

也就是说，不是：

- 卡片列表改得更像文件列表

而是：

- 直接把知识对象从 `knowledge document` 改成 `skill package`
- 直接把 engine 的输入对象从 `knowledge shortlist` 改成 `skill shortlist`

这样产品、存储、UI 和引擎消费模型才能统一。

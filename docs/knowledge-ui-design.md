# Knowledge UI Design

本文描述 `coco-flow` 的第一版知识工作台设计，目标不是做完整知识库产品，而是先解决一件事：

- 让知识上下文可以被生成
- 可以被人审核
- 可以被发布给 `refine / plan`

核心原则：

- LLM 可以生成草稿
- 不能直接无审核进入主链路
- 默认只有 `approved` 的知识参与 `refine / plan`

## 目标

第一版 UI 只解决 4 个问题：

1. 用户怎么发起知识草稿生成
2. 系统怎么展示“为什么生成这些文件”
3. 用户怎么修改和确认草稿
4. 哪些知识允许进入引擎主链路

非目标：

- 不做完整 wiki
- 不做复杂权限系统
- 不做多人协作编辑
- 不做在线知识图谱
- 不做自动发布到远程仓库

## 产品定位

这个页面不是“知识库首页”，而是：

- `Knowledge Workbench`
- 更接近“知识草稿生成 + 审核发布台”

它背后的核心能力是：

- 知识上下文生成引擎

也就是：

- 前台负责输入、预览、编辑、确认
- 后台负责召回 repo、扫描证据、生成草稿、产出待确认项

## 导航建议

基于当前 Web 已有两个一级入口：

- `任务推进`
- `路径视图`

建议未来改成：

- `任务推进`
- `知识工作台`
- `诊断 / 环境`

其中：

- 当前 `路径视图` 更适合降级为 `诊断 / 环境`
- 新增 `知识工作台` 承接知识生成和审核

第一版即使不立刻删除 `路径视图`，也建议先新增：

- `Knowledge`

## 页面结构

第一版页面建议沿用当前任务页的“双栏工作台”思路：

- 左侧：列表和筛选
- 右侧：阅读 / 编辑 / 证据查看工作台

### 左栏：知识列表

用途：

- 查看已有知识文件
- 筛选状态
- 发起新建

主视图建议按 `domain` 聚合，而不是直接按文件平铺。

原因：

- 用户天然先关心“我在看哪个业务方向”
- 再关心这个方向下面有哪些 `flow / anchor / rule`
- `kind` 和 `status` 更适合作为单条文件的 badge，不适合作为一级分组

建议信息：

- 搜索框
- `kind` 筛选
  - `domain`
  - `flow`
  - `rule`
  - `anchor`
- `status` 筛选
  - `draft`
  - `approved`
  - `archived`
- `engine` 筛选
  - `refine`
  - `plan`
- `domain` 筛选
- `group by` 视图切换
  - `按 domain`
  - `按文件`

默认使用：

- `按 domain`

### 按 domain 聚合的列表结构

每个 `domain` 分组展示：

- `domain` 标题
- 该 `domain` 下的知识文件数量
- 最近更新时间
- 展开后显示该 `domain` 下的知识文件

每条知识文件只显示最关键的信息：

- 标题
- `kind` badge
- `status` badge
- `updated_at`

例如：

```text
竞拍讲解卡
  3 个知识文件 · 最近更新 2026-04-15
  - 表达层链路 [flow] [draft]
  - 表达层代码映射 [anchor] [approved]
  - 默认业务规则 [rule] [draft]
```

### 按文件平铺的列表结构

这个视图主要给维护者用，用于排查和批量处理。

每条记录直接展示：

- 标题
- `domain`
- `kind`
- `status`
- `updated_at`

左栏顶部保留一个显眼的入口：

- `新建知识草稿`

### 右栏：Knowledge Workbench

右栏建议分成 4 个 tab：

- `摘要`
- `正文`
- `证据`
- `发布`

#### 1. 摘要

展示 frontmatter 的关键字段：

- `kind`
- `id`
- `title`
- `desc`
- `engines`
- `domains`
- `repos`
- `paths`
- `priority`
- `status`
- `confidence`

这里需要支持直接编辑。

#### 2. 正文

展示 Markdown 正文，并支持编辑。

不同 `kind` 有不同模板：

- `domain`
  - `Summary`
  - `Terms`
  - `Rules`
  - `Related Flows`
- `flow`
  - `Summary`
  - `Main Flow`
  - `Dependencies`
  - `Risks`
  - `Code Anchors`
  - `Open Questions`
- `rule`
  - `Statement`
  - `Exceptions`
  - `Scope`
  - `Open Questions`
- `anchor`
  - `Repos`
  - `Paths`
  - `Search Terms`
  - `Adjacent Modules`
  - `Open Questions`

#### 3. 证据

这是第一版里非常重要的 tab。

它必须回答：

- 为什么系统生成了这份草稿
- 哪些内容来自 repo 扫描
- 哪些内容只是 LLM 推断

建议展示：

- 输入描述
- 选中的 repo
- 触发命中的关键词
- 候选知识文件
- 相关目录 / 文件
- 抽取到的检索词
- 相关代码片段或文件路径
- `.livecoding/context` 命中情况
- 待确认问题

这一页的目标不是展示所有日志，而是建立信任。

#### 4. 发布

负责控制这份知识是否进入主链路。

建议展示：

- 当前状态
  - `draft`
  - `approved`
  - `archived`
- 当前信心等级
  - `low`
  - `medium`
  - `high`
- 可见引擎
  - `refine`
  - `plan`
- 发布说明

关键操作：

- `保存草稿`
- `标记为已确认`
- `撤回到草稿`
- `归档`

默认规则：

- `draft` 不参与主链路
- `approved` 才会被 `refine / plan` 默认加载

## 新建草稿交互

第一版建议使用抽屉或全屏弹层，不建议单独跳新页面。

表单字段建议最小化：

- `描述`
  - 多行文本
  - 例如：`竞拍讲解卡表达层`
- `相关 repo`
  - 多选
- `生成类型`
  - `flow`
  - `anchor`
  - `rule`
  - `domain`
- `补充材料`
  - 可选
  - 例如 PRD、设计说明、备注

默认行为建议：

- 用户输入某个业务方向 + 场景时
- 系统默认优先生成：
  - `flow`
  - `anchor`

只有在以下情况才补 `domain / rule`：

- `domain` 不存在
- 或用户明确勾选

## 生成后的交互流

建议流程如下：

1. 用户填写描述和 repo
2. 系统进入 `生成中`
3. 后台引擎执行：
   - 基于描述识别候选 `domain`
   - 扫描 repo
   - 命中关键词和路径
   - 生成 knowledge draft
4. UI 回到工作台并打开新草稿
5. 默认停留在 `证据` tab
6. 用户先看依据，再切到 `摘要` / `正文` 编辑
7. 用户确认后点击 `标记为已确认`

这里有一个关键设计：

- 生成完成后默认先看“证据”
- 不默认先看正文

因为我们要先解决可信度问题。

## 推荐的页面状态

### 列表项状态

建议最少支持：

- `draft`
- `approved`
- `archived`

### 生成任务状态

如果要显示后台过程，建议单独有运行态：

- `queued`
- `generating`
- `ready`
- `failed`

它和知识文件状态分开：

- 运行态描述这次生成过程
- 文件状态描述这份知识是否被确认

## 生成引擎输出契约

为了支持 UI，后台不能只返回一篇 Markdown。

建议至少返回：

- `draft_files`
  - 本次生成了哪些文件
- `metadata`
  - frontmatter 草稿
- `body`
  - 正文草稿
- `evidence`
  - repo 命中信息
- `open_questions`
  - 待确认问题
- `confidence`
  - 本次生成置信度

如果后面要调试，还可以增加：

- `retrieval_trace`
- `selected_repos`
- `selected_paths`
- `selected_keywords`

## 引擎与 UI 的分工

### 引擎负责

- 从描述中识别方向和场景
- 从 repo 中做轻量扫描
- 从知识库里做候选召回
- 生成草稿内容
- 产出证据和待确认项

### UI 负责

- 输入采集
- 证据展示
- frontmatter 编辑
- 正文编辑
- 审核状态切换
- 发布控制

## 为什么先做 UI

因为你担心的不是“能不能生成”，而是“生成过程不可控”。

这个问题只靠 skill 很难解决。

skill 只能规范：

- 怎么生成

但不能很好解决：

- 生成后怎么审
- 为什么这么生成
- 哪些内容是猜的
- 哪些知识允许进入主链路

这些事情更适合放在 UI 里做。

## 第一版最小切片

如果只做一个最小可用版本，我建议范围控制在这里：

1. 新增 `Knowledge` 页面
2. 支持输入描述 + 选择 repo
3. 默认生成 `flow + anchor` 草稿
4. 支持查看 `证据`
5. 支持编辑 frontmatter 和 Markdown
6. 支持 `draft -> approved`
7. `refine / plan` 只消费 `approved`

这已经足够验证两个问题：

- 这个引擎生成出来的知识是否像样
- UI 审核流是否足够控风险

## 页面草图

可以先粗看成这样：

```text
+---------------------------------------------------------------+
| Header: 任务推进 | 知识工作台 | 诊断 / 环境                   |
+-----------------------------+---------------------------------+
| 左栏：按 domain 聚合的知识列表 | 右栏：Knowledge Workbench      |
|                             |                                 |
| [新建知识草稿]              | Tabs: 摘要 | 正文 | 证据 | 发布 |
| 搜索                        |                                 |
| kind/status/domain 筛选     | 标题：竞拍讲解卡表达层链路      |
| 分组：按 domain / 按文件    |                                 |
|                             | 状态：draft  置信度：medium     |
| 竞拍讲解卡                  | [摘要 tab] frontmatter 编辑区    |
|   - 表达层链路              |                                 |
|     [flow] [draft]          | [正文 tab] markdown 编辑区       |
|   - 表达层代码映射          |                                 |
|     [anchor] [approved]     | [证据 tab] repo 命中、关键词、   |
|   - 默认业务规则            |            路径、待确认问题      |
|     [rule] [draft]          |                                 |
|                             |                                 |
|                             | [发布 tab] 保存草稿 / 标记确认   |
+-----------------------------+---------------------------------+
```

## 建议的后续文档

如果这个方向成立，下一步建议再补两篇：

1. `Knowledge API Draft`
2. `Knowledge File Template Draft`

前者定义接口，后者定义 `domain / flow / rule / anchor` 的文件模板。

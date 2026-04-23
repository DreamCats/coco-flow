# Chrome 插件 + Gateway MVP 方案草稿

本文记录当前关于“用 Chrome 插件替代重桌面壳，作为 `coco-flow` 轻量入口”的 MVP 结论与分阶段规划。

目标不是把 `coco-flow` 重新做成浏览器产品，而是把“入口层”做轻，把“本地执行层”收敛成一个常驻 `gateway` 服务，由插件通过 HTTP 与本地能力交互。

如本文与代码不一致，以代码为准。

---

## 背景

当前 Electron launcher 已经验证了一个方向：

1. 用户需要一个更低门槛的入口，而不是继续记 `coco-flow` 命令
2. `Local / Remote` 两条主路径都成立
3. 底层能力复用 CLI 是对的

但 Electron 形态也暴露了明显问题：

1. 包体积大
2. 冷启动和窗口切换偏重
3. 对“只是一个入口”的场景来说，工程和分发成本偏高
4. 用户日常主要停留在 Chrome，而不是桌面壳

因此更合适的形态是：

1. **Chrome 插件负责入口**
2. **本地 `gateway` 负责执行**
3. **插件与本地服务通过 HTTP 通信**

一句话说透：

> 入口应该轻，真正常驻的应该是本地控制服务，而不是一个完整桌面 App。

---

## 结论摘要

当前建议的 MVP 方案是：

1. 新增 `coco-flow gateway` 子命令
2. `gateway` 以本地 HTTP 服务形式运行，默认绑定 `127.0.0.1`
3. Chrome 插件打开后先探活 `gateway`
4. 若无响应，则提示用户在终端执行：
   - 已安装用户：`coco-flow gateway start -d`
   - 未安装用户：先执行 README 安装命令，再执行 `coco-flow gateway start -d`
5. 若有响应，则在插件内提供一个小而美的 `Local / Remote` 入口
6. local / remote 的动作全部通过 HTTP API 调用本地 `gateway`

当前不建议再继续重投入 Electron 作为长期产品形态。Electron 更适合作为方向验证版，而不是最终入口产品。

---

## MVP 目标

Chrome 插件 + gateway 的 MVP 只承担以下职责：

1. 发现本地 `gateway` 是否已启动
2. 给出明确、极简的“如何启动”引导
3. 在插件中提供 `Local` 与 `Remote` 两个入口
4. 通过 HTTP 调用本地能力：
   - local start / stop / status
   - remote list / add / remove / connect / disconnect / status
5. 在插件中展示关键状态与简短动作进度
6. 成功后直接打开本地 Web UI

---

## 非目标

MVP 明确不做：

1. 不在插件里跑完整 workflow Web UI
2. 不在插件里展示长日志控制台
3. 不做插件侧自动执行本地 shell 命令
4. 不做插件侧静默安装 `coco-flow`
5. 不做多浏览器适配，先只做 Chrome / Chromium
6. 不做复杂设置页、账号体系或云同步
7. 不在第一版解决系统登录自启动

要特别说清的一点：

> 当 `gateway` 没起来时，插件无法真正判断“没安装”还是“没启动”。

因此插件在 `gateway unreachable` 场景下，MVP 只能给出两步式引导，而不能声称自己已经准确知道用户是否已安装 CLI。

---

## 用户体验目标

### 场景 1：日常用户

1. 用户点击 Chrome 插件图标
2. 插件快速探测 `http://127.0.0.1:<port>/healthz`
3. 若 `gateway` 在线，立即展示一个很轻的入口面板
4. 用户在插件中选择 `Local` 或 `Remote`
5. 点击动作按钮
6. 插件展示简短动作进度
7. 成功后直接打开本地 Web 页

### 场景 2：首次使用 / `gateway` 未启动

1. 用户点击插件图标
2. 插件探活失败
3. 插件显示一个清晰的启动卡片：
   - Step 1: 如未安装，请先执行 `curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash`
   - Step 2: 在终端执行 `coco-flow gateway start -d`
4. 用户完成启动后，重新打开插件即可使用

### 场景 3：远程开发

1. 用户点击插件
2. 切到 `Remote`
3. 从已保存列表里选择一台开发机
4. 点击 `Connect`
5. 插件展示 3 到 5 个关键步骤：
   - Checking remote
   - Starting remote service
   - Opening tunnel
   - Ready
6. 成功后自动打开本地转发 URL

---

## 产品形态

MVP 由两个部分组成：

### 1. Chrome 插件

职责：

1. 提供入口 UI
2. 探活本地 `gateway`
3. 展示关键状态
4. 发起 HTTP 请求
5. 打开本地 Web URL

插件不负责：

1. 执行本地命令
2. 管理本地进程
3. 安装 CLI

### 2. 本地 `gateway`

职责：

1. 作为 Chrome 插件唯一的本地 HTTP 入口
2. 暴露 local / remote 相关 API
3. 复用已有 `coco-flow` 能力
4. 返回结构化状态与动作进度

`gateway` 不负责：

1. 承载完整 Web UI
2. 成为另一套产品层
3. 重新实现 SSH / 隧道 / runtime 逻辑

---

## 命令行形态

建议新增一个独立命令组：

```bash
coco-flow gateway start
coco-flow gateway start -d
coco-flow gateway status
coco-flow gateway stop
```

### 建议语义

#### `coco-flow gateway start`

- 前台运行
- 适合开发调试
- stdout 直接打印日志

#### `coco-flow gateway start -d`

- 后台运行
- 适合日常用户
- 启动后返回：
  - pid
  - bind 地址
  - log 文件路径

#### `coco-flow gateway status`

返回最小状态：

- 是否运行
- pid
- host / port
- log 文件
- 版本

#### `coco-flow gateway stop`

- 结束本地 `gateway`

### 运行时约定

建议沿用当前 `~/.config/coco-flow/` 下的约定，新增：

- `gateway.pid`
- `gateway.log`

---

## 总体结构

```text
Chrome Extension
  popup / background
        |
        | HTTP
        v
127.0.0.1:<gateway_port>
  coco-flow gateway
        |
        +-- local start/stop/status
        +-- remote list/add/remove/connect/disconnect/status
        +-- open web url
```

### 与现有代码的关系

`gateway` 不应该再用 shell 去调用一遍 `coco-flow` 自己。

建议复用顺序：

1. 优先复用现有 Python runtime / service 能力
2. 其次复用已存在的 `local` / `remote` 模块逻辑
3. 避免 `gateway -> shell -> coco-flow` 这种递归式封装

这样有两个好处：

1. 性能更稳
2. 更容易把动作进度做成结构化事件，而不是解析 CLI 文本

### 与现有 daemon 的关系

当前已有 `coco-flow daemon` 主要服务 ACP / session pool。

当前建议：

1. **不要直接把现有 daemon 暴露给插件**
2. **新增一个面向入口层的 HTTP gateway**
3. gateway 内部可以按需复用 daemon 或其他 runtime 能力

也就是说：

- `daemon` 是内部运行时复用层
- `gateway` 是对浏览器入口暴露的本地 HTTP façade

---

## 默认端口与探活

建议默认端口单独分配，例如：

- `127.0.0.1:4319`

探活接口：

```http
GET /healthz
```

返回：

```json
{
  "ok": true,
  "service": "coco-flow-gateway",
  "version": "x.y.z"
}
```

插件每次打开时先探活；若连续失败，则进入“未启动”引导状态。

---

## HTTP API 草案

MVP 只保留入口侧真正需要的薄接口。

### 环境与总状态

#### `GET /healthz`

- 服务是否在线

#### `GET /preflight`

返回：

- gateway 版本
- `coco-flow` 版本
- local web 是否健康
- 最近错误摘要

示例：

```json
{
  "ok": true,
  "gateway_version": "0.1.0",
  "cli_version": "0.1.0",
  "local": {
    "running": false,
    "healthy": false
  }
}
```

### Local

#### `GET /local/status`

返回：

- `running`
- `healthy`
- `url`
- `pid`

#### `POST /local/start`

返回：

- `operation_id`
- `url`

#### `POST /local/stop`

返回：

- `stopped`

### Remote

#### `GET /remote/list`

返回已保存 remotes。

#### `POST /remote`

新增 remote。

#### `DELETE /remote/{name}`

删除 remote。

#### `GET /remote/{name}/status`

返回：

- `local_healthy`
- `tunnel_alive`
- `remote_healthy`
- `fingerprint_match`
- `local_url`

#### `POST /remote/{name}/connect`

请求体：

```json
{
  "restart": false
}
```

返回：

- `operation_id`
- `local_url`

#### `POST /remote/{name}/disconnect`

返回：

- `disconnected`

### 动作进度

MVP 建议不要在 popup 里铺一个完整日志控制台，而是提供结构化进度接口。

#### `GET /operations/{id}`

返回：

- `state`: `pending | running | succeeded | failed`
- `steps`
- `message`
- `local_url`

示例：

```json
{
  "state": "running",
  "steps": [
    { "key": "remote_check", "label": "Checking remote", "state": "done" },
    { "key": "remote_start", "label": "Starting remote service", "state": "running" },
    { "key": "tunnel", "label": "Opening tunnel", "state": "pending" }
  ],
  "message": "remote service is starting"
}
```

这样插件只需轮询或短轮询，不必在 popup 里处理长日志流。

---

## UI 方案

MVP 的 UI 设计布局参照 [`DESIGN.md`](/Users/bytedance/Work/tools/bytedance/coco-flow/DESIGN.md)。

### 设计原则

延续 `DESIGN.md` 的方向，但不做 landing page 化表达：

1. **暖色、克制、低信息密度**
2. **一个时刻只突出一个主要动作**
3. **像工具入口，不像控制台**
4. **尽量少卡片，少层级，少解释文字**

### 视觉基调

- 背景：`#f5f4ed`
- 主卡片：`#faf9f5`
- 主文案：`#141413`
- 次文案：`#5e5d59`
- 品牌按钮：`#c96442`
- 辅助按钮：`#e8e6dc`

### 字体与层级

- 标题：沿用 `DESIGN.md` 的 serif 气质，开发态可回退 `Georgia`
- UI 文案：无衬线
- 代码 / 命令：monospace

标题只保留一个产品名，不再堆 hero 文案。

---

## 插件布局

### Popup 总体布局

建议 popup 尺寸：

- 宽度：`360-400px`
- 高度：`520-620px`

结构：

1. 顶部栏
2. 状态卡 / 引导卡
3. `Local / Remote` 分段切换
4. 当前模式主卡片
5. 底部微型状态区

### 顶部栏

内容：

- 左侧：`coco-flow`
- 右侧：gateway 状态 badge

状态 badge 分三态：

- `Gateway Ready`
- `Connecting...`
- `Gateway Missing`

### 未启动状态卡

当 `gateway` 不在线时，popup 首屏只展示一个主卡片：

1. 一句短说明
2. 两个命令块
3. `Copy` 按钮
4. `Retry` 按钮

推荐文案结构：

- `Step 1. Install coco-flow if needed`
- `Step 2. Run coco-flow gateway start -d`

这块应作为首屏唯一重点，不要再同时展示 Local / Remote 主面板。

### 模式切换

当 gateway 在线时，展示一个非常轻的 segmented control：

- `Local`
- `Remote`

不再使用大卡片 chooser。

### Local 主卡片

信息只保留：

- 状态：`Running / Stopped`
- URL：`http://127.0.0.1:4318`
- 健康态：`Healthy / Unhealthy`

按钮只保留：

- `Start`
- `Stop`
- `Open`

### Remote 主卡片

popup 内只做高频动作，不做复杂管理。

建议内容：

- remote 下拉选择器
- 当前状态 chips：
  - `Connected`
  - `Tunnel alive`
  - `Fingerprint mismatch`
- 主按钮：
  - `Connect`
  - `Disconnect`
  - `Open`
- 次链接：
  - `Manage remotes`

### Remote 管理页

remote 增删改查不建议全塞进 popup。

MVP 建议：

1. popup 只做“选中 + 连接”
2. 新增一个插件 options page 或独立扩展页做 `Manage remotes`

这样 popup 能维持“小而美”，不会重新长成一个 dashboard。

### 动作进度展示

popup 不展示长日志，只展示：

1. 当前动作名称
2. 3 到 5 个步骤
3. 成功 / 失败摘要

错误时允许展开一小块 `details`，展示最近几行诊断文本。

---

## 交互流程

### 首次使用

1. 打开插件
2. `GET /healthz` 失败
3. 展示未启动卡
4. 用户复制并执行：
   - 安装命令
   - `coco-flow gateway start -d`
5. 再次打开插件

### Local 启动

1. 打开插件
2. `GET /local/status`
3. 点击 `Start`
4. 插件轮询 `GET /operations/{id}`
5. 成功后按钮切成 `Open`
6. 自动或手动打开本地 Web

### Remote 连接

1. 打开插件
2. `GET /remote/list`
3. 选中 remote
4. 点击 `Connect`
5. 轮询操作状态
6. 成功后显示 `Connected`
7. 打开本地转发 URL

---

## 安全边界

本地 HTTP 服务如果直接裸露在 `localhost`，需要至少做最小保护。

MVP 建议：

1. 只绑定 `127.0.0.1`
2. 不监听 `0.0.0.0`
3. 要求插件请求带自定义 header，例如：
   - `X-Coco-Flow-Client: chrome-extension`
4. 对非插件来源不开放宽松 CORS

这样至少可以挡掉最普通的网页侧滥用。

更强的 token / pairing 机制可以放到后续阶段。

---

## 实现顺序

### Phase 1: Gateway 基础可用

1. 新增 `coco-flow gateway start/status/stop`
2. 跑起本地 HTTP 服务
3. 接通：
   - `/healthz`
   - `/preflight`
   - `/local/status`
   - `/local/start`
   - `/local/stop`
4. Local 路径先打通

### Phase 2: Remote MVP

1. 接通：
   - `/remote/list`
   - `/remote/{name}/status`
   - `/remote/{name}/connect`
   - `/remote/{name}/disconnect`
2. 补 `operations` 状态查询
3. 插件 popup 接好 remote 高频交互

### Phase 3: Remote 管理页

1. 增加 `Manage remotes`
2. 支持 add / remove / edit
3. 补诊断信息页

---

## 验收标准

MVP 完成后，至少应满足：

1. 用户不需要安装 Electron App
2. 用户只需在首次时手动执行一次 `coco-flow gateway start -d`
3. 插件能明确区分：
   - gateway 未启动
   - gateway 在线
4. 插件内可完成：
   - local start / stop / open
   - remote connect / disconnect / open
5. popup 仍保持轻量，不演化成复杂控制台
6. `Remote` 管理能力可通过插件配置页完成

---

## 当前建议

当前最值得推进的不是继续打磨 Electron，而是：

1. 先把 `gateway` 抽出来
2. 再做 Chrome 插件入口
3. 保持 popup 极简
4. 把复杂管理和诊断放到次级页

如果这个方向继续推进，后续可以自然扩展为：

1. Chrome 插件
2. Raycast 扩展
3. menubar 入口
4. 轻桌面壳

它们都共用同一个本地 `gateway`，而不必每个入口各自重新调 CLI。

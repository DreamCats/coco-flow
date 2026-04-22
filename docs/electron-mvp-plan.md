# Electron Launcher MVP 方案草稿

本文记录当前关于“为 `coco-flow` 提供一个最小可用的 Electron Mac App 壳”的结论与分阶段规划。

目标不是把 `coco-flow` 重写成桌面应用，而是用一个桌面壳把现有 CLI 远程连接能力包装成更低门槛的入口，让用户不必记命令。

如本文与代码不一致，以代码为准。

当前相关实现：

- CLI 入口：`src/coco_flow/cli/__init__.py`
- Remote CLI：`src/coco_flow/cli/commands/remote.py`
- Remote runtime：`src/coco_flow/cli/remote_runtime.py`
- Web UI 入口：`src/coco_flow/cli/server.py`
- Desktop 工程：`desktop/`
- 远程连接方案文档：`docs/remote-connect-ssh-plan.md`

## 当前落地状态

当前仓库已经落下第一版 launcher 骨架：

1. `desktop/` 下新增了 Electron + React 工程
2. 主进程通过受控 IPC 调用已安装的 `coco-flow` CLI
3. 已支持 launcher 首屏先选择 `Local` 或 `Remote`
4. `Local` 已接通 `start/stop/status/open`
5. `Remote` 已接通 `remote list/add/remove/connect/disconnect/status`
6. 已支持本地/远程动作的流式日志展示
7. 成功后由 Electron 打开对应的本地 Web URL

当前仍未做：

1. 安装包分发与签名
2. 内嵌 BrowserWindow 承载完整 Web UI
3. menubar、自动重连、设置页等增强能力

## 背景

当前远程开发机的主流程已经成立：

1. `coco-flow remote add/list/connect/disconnect/status`
2. 远程 `coco-flow start`
3. 本地 SSH 隧道
4. 本地浏览器打开 Web UI

技术链路已经可用，但对普通用户仍有明显门槛：

1. 需要记住 `coco-flow remote ...` 命令
2. 需要理解 `restart`、`disconnect`、`status` 等操作语义
3. 出错时只能看命令行输出，不够产品化

因此需要一个“本地桌面入口”，但应以最低成本为原则。

## 结论摘要

当前结论是：

1. **优先做 Electron 启动器壳，而不是桌面重写。**
   不重写 `remote` 逻辑，不重写 Web workflow，不重写后端。

2. **Electron 只负责入口、状态和日志。**
   真正的连接、版本检查、远程启动、SSH 隧道、健康检查，继续复用现有 CLI。

3. **MVP 不要求把完整 Web UI 内嵌进桌面壳。**
   最低成本版本允许 Electron 只负责“连接远程开发机并打开浏览器”。

4. **MVP 先解决“别记命令”，不先解决“桌面端一体化”。**
   用户体验目标是双击 App，选一台 remote，点击连接，而不是把整个 `coco-flow` Web 产品搬进 Electron。

## 为什么当前优先选 Electron

当前团队上下文下，Electron 比 Tauri 更适合做第一版：

1. **开发速度更快。**
   现有团队上下文已经有 Web UI 和 Node/npm 心智，Electron 的主进程、渲染进程、`child_process` 模型更直观。

2. **复用现有前端更顺。**
   Electron 可以直接复用现有 React / Vite 栈来做一个很薄的桌面入口页面。

3. **减少额外心智负担。**
   Tauri 虽然更轻，但会引入 Rust bridge、打包细节和更多跨栈调试成本。当前阶段不值得。

4. **目标是内部可用 MVP，不是桌面工程最优解。**
   当前主要诉求是让用户少记命令，而不是优化包体积和运行时占用。

## 产品定义

### MVP 目标

Electron App 的 MVP 只承担以下职责：

1. 展示已保存的 remote 列表
2. 支持新增 / 删除 remote
3. 支持 connect / disconnect / status
4. 实时展示 CLI 日志
5. 连接成功后自动打开本地 Web URL

### 非目标

MVP 明确不做：

1. 不重写 `remote_runtime`
2. 不重写 SSH 逻辑
3. 不在 Electron 里实现另一套任务系统
4. 不在第一版要求内嵌完整 workflow Web UI
5. 不自行实现密码输入或 SSH 认证
6. 不接管远程仓库同步 / 自动 git pull / 自动代码更新

## 用户体验目标

MVP 的理想体验是：

1. 用户打开 App
2. 看到已保存的开发机列表
3. 点击某个 remote 的 `Connect`
4. 看到实时日志：
   - `remote_start`
   - `remote_version_ok`
   - `tunnel_start`
5. 成功后自动打开 `http://127.0.0.1:4318`

如果是首次使用：

1. 用户输入名称、host、user、port
2. 点击保存
3. 后续只需再次点击 `Connect`

## MVP 功能范围

### 1. Remote 列表

展示本地已保存 remotes，字段最少包括：

- `name`
- `host`
- `user`
- `local_port`
- `remote_port`

每个 item 提供：

- `Connect`
- `Disconnect`
- `Status`
- `Delete`

### 2. 新增 Remote

最小表单字段：

- `name`
- `host`
- `user`
- `local_port`
- `remote_port`

底层映射到：

```bash
coco-flow remote add <name> --host <host> --user <user> --local-port <local_port> --remote-port <remote_port>
```

### 3. 连接 Remote

底层映射到：

```bash
coco-flow remote connect <name>
```

支持附加动作：

- `Connect`
- `Connect (Restart)`

分别映射为：

```bash
coco-flow remote connect <name>
coco-flow remote connect <name> --restart
```

### 4. 断开 Remote

底层映射到：

```bash
coco-flow remote disconnect <name>
```

### 5. 状态查看

底层映射到：

```bash
coco-flow remote status <name> --json
```

前端只展示最关键字段：

- 当前 remote
- `local_healthy`
- `tunnel_alive`
- `remote_healthy`
- `fingerprint_match`
- `local_build.fingerprint`
- `remote_build.fingerprint`

### 6. 日志面板

需要一块只读日志面板，用于展示 CLI stdout/stderr。

MVP 不需要复杂日志分类，只需要：

- 支持滚动
- 支持复制
- 在 connect 过程中持续输出

## 推荐交互形态

### 窗口布局

最小布局建议：

- 左侧：remote 列表
- 右侧上方：remote 基础信息 + 操作按钮
- 右侧下方：日志面板

### 主要按钮

- `Connect`
- `Restart & Connect`
- `Disconnect`
- `Refresh Status`
- `Open Web`

其中 `Open Web` 只在最近一次 connect 成功后可用。

### 连接成功后的行为

默认行为：

1. App 展示成功状态
2. 自动执行 `open http://127.0.0.1:<local_port>`

MVP 不强制要求把该页面嵌入 Electron `BrowserWindow` 内部。

## 技术方案

### 总体结构

建议单独建一个 Electron 工程目录，例如：

```text
desktop/
  package.json
  electron/
    main.ts
    preload.ts
  renderer/
    index.html
    src/
      app.tsx
      remotes/
      logs/
```

### 核心原则

1. Electron **main process** 负责调用 `coco-flow` CLI
2. Renderer 只做 UI
3. Renderer 不直接执行 shell 命令
4. 通过 `preload` 暴露受控 IPC

### 与现有 CLI 的集成方式

主进程通过 `child_process.spawn` 调用：

```bash
coco-flow remote list --json
coco-flow remote add ...
coco-flow remote connect ...
coco-flow remote disconnect ...
coco-flow remote status ... --json
```

建议优先直接依赖已安装的 `coco-flow` 可执行文件，而不是依赖当前仓库开发态的 `uv run coco-flow`。

这样更符合给普通用户分发的场景。

### 命令执行约束

主进程需要统一封装一个 `runCocoFlowCommand()`，负责：

1. 查找 `coco-flow` 是否在 PATH 中
2. 执行命令
3. 收集 stdout / stderr
4. 将日志流式推给 renderer
5. 在退出时返回结构化结果

### Preflight 检查

MVP 建议在启动时做一次环境检查：

1. `command -v coco-flow`
2. `coco-flow version --json`

如果失败，UI 直接给出明确提示：

- 未安装 `coco-flow`
- 或 PATH 中不可见

## 为什么 MVP 不先内嵌完整 Web UI

尽管 Electron 可以内嵌 `BrowserWindow` 加载本地 `127.0.0.1:4318`，但第一版不建议强依赖它，原因有三点：

1. 当前远程流程的真正瓶颈是“连接入口”，不是“浏览器窗口容器”
2. 先把 CLI 入口产品化，风险最小
3. 如果先做内嵌 WebView，会多一层生命周期管理和失败态处理

因此建议：

- MVP：外部浏览器打开
- Phase 2：可选内嵌 BrowserWindow

## Phase 划分

### Phase 1: Launcher MVP

目标：桌面壳可替代用户手输命令。

范围：

- remote 列表
- add / delete
- connect
- connect with restart
- disconnect
- status
- 日志面板
- 连接成功后 `open` 浏览器
- preflight 检查 `coco-flow` 是否可用

预计成本：

- `3-5` 天可出内部可用版

### Phase 2: Embedded Web

目标：连接成功后在 Electron 内打开 `coco-flow` 页面，而不是跳系统浏览器。

范围：

- 内嵌 `BrowserWindow`
- 支持重新打开当前 local URL
- 明确 local / remote 运行上下文

预计成本：

- 再加 `2-4` 天

### Phase 3: 更完整的桌面体验

目标：补产品化细节。

范围：

- menubar 入口
- 最近连接记录
- 自动重连
- 更友好的错误提示
- App 内设置页

预计成本：

- 再加 `1-2` 周

## 风险与边界

### 1. 仍然依赖本机已安装 `coco-flow`

MVP 不打算把 `coco-flow` Python/CLI/runtime 完整打进 Electron 安装包。

这意味着：

- Electron 是 launcher
- `coco-flow` 仍是底层能力依赖

优点是成本低；缺点是首次使用前仍需安装 `coco-flow`。

### 2. SSH 认证仍复用系统环境

这意味着：

- App 不接管密码管理
- 用户仍可能看到系统 SSH / SSO / GSSAPI 认证链路

这不是问题，而是刻意复用现有企业认证能力。

### 3. 错误处理以 CLI 输出为准

MVP 不建议另造一套错误码体系。优先把 CLI 输出直接展示出来，再在常见错误上做轻量文案包装。

## 推荐实施顺序

1. 先写 Electron 壳，不动 `remote_runtime`
2. 先做 `list/add/connect/disconnect/status` 五个动作
3. 先接日志流和环境检测
4. 先用外部浏览器打开 Web
5. 最后再评估是否值得做内嵌窗口

## 当前建议

当前最推荐的方向是：

1. **Electron 只做 launcher MVP**
2. **继续复用现有 `coco-flow remote ...` CLI**
3. **先帮用户“免记命令”**
4. **不要在第一版就追求桌面端一体化重构**

这是当前成本最低、落地最快、风险最可控的桌面方案。

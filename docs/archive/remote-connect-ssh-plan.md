# 本地连接远程开发机启动 coco-flow 方案草稿

本文记录当前关于“在本地电脑上连接远程开发机并启动 `coco-flow`”的讨论结论和分阶段规划。

目标不是把执行面迁回本地，而是把当前已经可行的“远程启动服务 + 本地建隧道 + 本地打开网页”流程包装成更低门槛的产品入口。

如本文与代码不一致，以代码为准。

当前相关实现：

- CLI 启动入口：`src/coco_flow/cli/__init__.py`
- Web API 入口：`src/coco_flow/api/app.py`
- 文件系统浏览：`src/coco_flow/services/runtime/fs_tools.py`
- repo 校验：`src/coco_flow/services/queries/repos.py`
- daemon：`src/coco_flow/daemon/client.py`、`src/coco_flow/daemon/server.py`
- code worktree 执行：`src/coco_flow/engines/code/execute.py`

## 背景

当前 `coco-flow` 的推荐使用方式，本质上是：

1. 登录开发机
2. 在开发机执行 `coco-flow start`
3. 再通过 IP 或 SSH 隧道从本地浏览器访问

这条链路虽然技术上已经成立，但对普通用户仍然有两个明显门槛：

1. 需要自己登录开发机并记住启动命令
2. 需要自己建立 SSH 隧道并打开网页

对于长期在远程开发机上工作的同事，这两个步骤都偏“工程师手工流程”，不够产品化。

## 结论摘要

当前结论是：

1. **保留远程执行，不把执行面搬回本地。**
   `coco-flow` 当前的 repo 视角、文件系统、task 目录、knowledge、daemon、worktree 都绑定在服务所在机器上。让服务继续跑在开发机上，改动范围最小。

2. **本地只做连接器。**
   在本地提供一个统一入口，负责：
   - 连接远程开发机
   - 在远程启动 `coco-flow`
   - 在本地建立 SSH 隧道
   - 自动打开网页

3. **认证复用系统 SSH，不自己接管密码。**
   用户侧可以输入 IP 或保存好的 host alias，但认证链路应直接复用系统 `ssh` 与本机现有配置。
   这尤其适合已有 `GSSAPIAuthentication`、跳板机、SSO 弹窗等环境。

4. **第一阶段先做 CLI 包装，不先做 Mac App。**
   Mac App 可以作为后续壳层，但应该建立在 CLI 连接能力已经稳定的前提上。

## 为什么这是最低成本路径

这条路径的核心优势是：**不改变当前服务的运行边界，只包装入口。**

当前实现已经具备以下前提：

- `coco-flow` 已支持在某台机器上启动 API + UI
- README 和 CLI 已显式给出“远程开发机 + 本地 SSH 隧道”的手工用法
- API 当前所有关键能力都默认作用于服务端本机视角
  - `/api/fs/*` 浏览的是服务端本机目录
  - repo 校验在服务端本机执行 `git`
  - daemon 使用服务端本机 Unix socket
  - code 阶段在服务端本机创建 worktree 并执行 git

因此，如果我们继续让服务跑在开发机上，只需要把手工流程自动化，不需要大改后端架构。

反过来，如果要做“本地服务直接操作远程仓库”，就会牵动：

- 文件系统抽象
- repo 校验抽象
- daemon 通信模型
- worktree 管理
- code 执行路径
- task/knowledge 存储边界

这不是入口优化，而是运行时重构，成本明显高一个量级。

## 用户体验目标

理想体验应收敛为：

1. 用户在本地执行一个命令，或点击一个入口
2. 输入或选择开发机 IP / host
3. 系统自动走 SSH 认证链路
4. 系统自动在远程启动 `coco-flow`
5. 系统自动建立本地隧道
6. 系统自动打开浏览器

用户不需要记住：

- 远程启动命令
- 隧道命令
- 本地访问地址

## 推荐产品形态

### 形态一：CLI 连接命令

建议优先新增本地入口：

```bash
coco-flow remote connect <host-or-ip>
```

可选地补充目标管理：

```bash
coco-flow remote add dev --host 10.37.122.5 --user maifeng
coco-flow remote list
coco-flow remote connect dev
coco-flow remote disconnect dev
```

这条命令的职责不是启动本机服务，而是：

1. 用系统 `ssh` 登录远程开发机
2. 在需要时于远程执行 `coco-flow start --detach --host 127.0.0.1 --port <port>`
3. 在需要时于本地执行 `ssh -fN -L <local-port>:127.0.0.1:<remote-port> ...`
4. 轮询 `http://127.0.0.1:<local-port>/healthz`
5. 执行 `open http://127.0.0.1:<local-port>`

### `remote connect` 的默认语义

`remote connect` 不应被设计成“每次都重新启动一遍”，而应被设计成：

- 连接到一个可用的远程 `coco-flow` 服务
- 尽量复用已有远程服务
- 尽量复用已有本地隧道

也就是说，`remote connect` 必须是**幂等操作**。

建议语义：

- `coco-flow remote connect <host-or-ip>`
  - 默认复用远程服务和本地隧道
- `coco-flow remote connect <host-or-ip> --restart`
  - 明确重启远程服务，并重建本地隧道
- `coco-flow remote connect <host-or-ip> --reconnect-tunnel`
  - 只重建本地隧道，不重启远程服务

默认情况下不建议盲重启，因为：

- 远程 `coco-flow` 可能已经在运行
- 盲重启可能中断已有使用中的会话
- 盲再启动可能遇到远程端口冲突
- 盲打隧道可能遇到本地端口占用或残留隧道

### `remote connect` 的幂等状态机

推荐把 `remote connect` 设计成如下状态探测流程：

1. **先检查本地隧道是否已可用**
   - 直接探测 `http://127.0.0.1:<local-port>/healthz`
   - 如果已通，直接打开网页，不再操作远程

2. **如果本地不通，再检查远程服务是否已可用**
   - 通过 `ssh` 在远程探测 `http://127.0.0.1:<remote-port>/healthz`
   - `coco-flow status` 可以作为辅助信息，但不应替代健康检查

3. **仅在远程服务不健康时才启动**
   - 远程执行 `coco-flow start --detach --host 127.0.0.1 --port <remote-port>`
   - 启动后再次探测远程 `healthz`

4. **最后再处理本地隧道**
   - 若本地隧道缺失，则建立新隧道
   - 若本地端口已被其他进程占用，则直接报错
   - 若是旧隧道残留，则清理后重建

5. **以本地健康检查作为最终成功标准**
   - 隧道建立后再次探测 `http://127.0.0.1:<local-port>/healthz`
   - 成功后才执行 `open`

这条状态机应满足以下行为：

- 本地已通：直接复用
- 本地不通 + 远程已通：只补本地隧道
- 本地不通 + 远程不通：启动远程，再补本地隧道
- 指定 `--restart`：先停远程，再启动远程，再重建本地隧道

### 服务与隧道的状态判断

这里不建议只依赖 pid 文件或单次命令输出，而应使用“状态信息 + 健康探测”双重确认。

建议原则：

1. **远程服务是否可用，以远程 `healthz` 为准**
2. **本地隧道是否可用，以本地 `healthz` 为准**
3. **`status` / pid / metadata 只用于辅助诊断，不作为唯一成功条件**

原因是：

- pid 文件可能残留
- 进程存在不代表服务可用
- 隧道进程存在不代表端口转发仍然有效

### 本地隧道元数据

为避免重复打隧道或误杀别的进程，建议在本地维护一份 tunnel metadata，例如：

- `remote_name`
- `host`
- `local_port`
- `remote_port`
- `ssh_pid`
- `created_at`

用途：

- 判断当前端口上的隧道是否由 `coco-flow` 自己创建
- 让 `disconnect` 可以精确清理自己的隧道
- 为 `status` 提供更稳定的本地可观测信息

但 metadata 仍然只是辅助信息，最终还是要以 `healthz` 探测为准。

### 形态二：Mac App / 菜单栏壳

在 CLI 稳定后，可再包一层简单 UI：

- 保存开发机列表
- 一键连接 / 断开
- 展示当前隧道状态
- 一键打开网页

这个壳层不应重新实现 SSH 逻辑，而应直接复用 CLI 或共享同一套连接模块。

## 认证与 SSH 约束

当前已知前提是，本地 SSH 配置里存在针对开发机网段的统一规则，例如：

- `Host 10.*`
- `GSSAPIAuthentication yes`
- `ServerAliveInterval 60`

这说明有较大概率已经存在统一认证机制。

因此这里的建议是：

1. **不在 `coco-flow` 内自己实现密码输入和保存。**
2. **优先依赖系统 `ssh` 拉起既有认证链路。**
3. **保存 host / user / port / alias 等连接信息即可。**
4. **如需前置认证，允许在报错时提示用户先完成 `kinit` 或组织内既有登录动作。**

这能最大程度复用现有企业环境，避免把 SSH 客户端、密码管理和统一认证一并背进产品里。

## 分阶段规划

### Phase 1: CLI MVP

目标：让用户在本地一条命令完成“远程启动 + 本地隧道 + 打开网页”。

范围：

- 新增 `coco-flow remote connect <host-or-ip>`
- 支持可选参数：
  - `--user`
  - `--port`
  - `--remote-port`
  - `--no-open`
  - `--no-build`
- 自动执行远程启动命令
- 自动建立本地隧道
- 自动探测健康检查
- 自动打开浏览器
- 默认复用已有远程服务与本地隧道
- 支持 `--restart` 与 `--reconnect-tunnel`

交付标准：

- 用户只需提供 host 或 IP，即可完成连接
- 若远程服务已在运行，不重复启动
- 若本地隧道已可用，不重复建隧道
- 若本地端口冲突，给出明确错误
- 若 SSH 认证失败，给出明确错误

预估成本：

- `2-4` 天

### Phase 2: `remote` 管理与体验补强

目标：从“一次性连接命令”升级为“可保存的远程开发机入口”。

范围：

- 新增 `remote` 子命令
- 本地保存远程配置，例如：
  - `name`
  - `host`
  - `user`
  - `port`
  - `default_local_port`
- 支持：
  - `remote add`
  - `remote list`
  - `remote remove`
  - `remote connect <remote-name>`
  - `remote disconnect`
  - `status`
- 补充隧道进程管理
- 补充更友好的错误提示与恢复提示

交付标准：

- 用户不必反复输入 IP
- 用户可以看到当前连接状态
- 用户可以显式断开已有隧道

预估成本：

- 在 Phase 1 基础上再增加 `3-5` 天

### Phase 3: Mac App 壳层

目标：把 CLI 连接能力包成更接近产品的本地入口。

范围：

- 最近连接列表
- 保存远程配置
- 一键连接 / 断开
- 状态展示
- 一键打开 `coco-flow`

边界：

- 不单独实现新的 SSH 协议栈
- 不单独实现新的认证流程
- 不重写后端

预估成本：

- 在 CLI 稳定后再增加 `1-2` 周

## 非目标

当前明确不做：

1. 不让本地 `coco-flow` 直接操作远程 repo 路径
2. 不在第一阶段支持“同一个 task 混合本地 repo 和远程 repo”
3. 不自己实现 SSH 密码框、密码保存或组织认证逻辑
4. 不在第一阶段重构 daemon 为跨机协议
5. 不在第一阶段引入 SSHFS / NFS 之类的远程挂载方案

## 风险与注意点

1. **远程环境不一致**
   需要确认远程开发机上是否稳定具备 `coco-flow`、Python、Node 以及 UI 构建依赖。

2. **端口冲突**
   本地 `4318` 或远程 `4318` 可能已被占用，需要有自动探测或明确报错。

3. **认证前置动作**
   如果某些环境仍需要先执行 `kinit` 或其他登录动作，CLI 需要能给出清晰提示，而不是只报一个 SSH 失败。

4. **连接生命周期**
   需要明确 `disconnect` 的范围：
   - 只断本地隧道
   - 还是同时停止远程 `coco-flow` 服务

5. **多目标并存**
   如果一个用户同时连接多台开发机，需要定义本地端口分配和状态展示策略。

## 建议的下一步

按性价比排序，建议这样推进：

1. 先实现 `coco-flow remote connect <host-or-ip>` 的 CLI MVP
2. 跑通一轮真实开发机环境验证
3. 再补 `remote` 保存、状态和断开能力
4. 等 CLI 连接模型稳定后，再评估是否需要 Mac App 壳层

## 一句话决策

当前最优解不是“把远程开发搬回本地”，而是“把远程启动和 SSH 隧道产品化成一个本地入口”。

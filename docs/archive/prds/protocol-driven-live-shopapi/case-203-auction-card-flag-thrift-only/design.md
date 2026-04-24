# Design

## 核心改造点

- 为竞拍讲解卡新增一个仅供服务端使用的内部判断标记
- 这是 `Thrift-only` 协议需求
- 字段需要在 `live_pack` RPC 层新增，并被 `live_shopapi` 消费，但不继续透给前端

## 系统职责

- `ttec/live_pack`
  负责在 RPC 返回中新增内部判断标记并填充

- `oec/live_shopapi`
  负责读取该标记，并用于服务端内部逻辑、埋点或分流判断

- 协议生成平台
  负责生成新的 RPC 产物

## 仓库依赖关系

依赖顺序是：

1. `live_pack` 侧 Thrift / RPC 协议先变更
2. 生成新的 `rpcv2_ttec_live_pack` 产物
3. `live_shopapi` 升级 RPC 依赖
4. `live_shopapi` 在服务层消费该字段

这里不需要新增 API Proto 字段，因此是纯服务间协议变更。

## 影响范围与边界

- 影响范围：竞拍讲解卡 RPC 返回结构、`live_shopapi` 服务层逻辑
- 不影响：前端 API 结构、客户端展示、竞拍主流程
- 风险点：
  - `blocked_by_platform`
  - 若只改 `live_pack` 不升级依赖，`live_shopapi` 无法消费
  - 若只升级依赖不补服务逻辑，字段没有实际价值

## 人力评估

- 复杂度：中
- 预估人力：1 到 2 人天
- 适合作为协议驱动型需求的 `Thrift-only` case

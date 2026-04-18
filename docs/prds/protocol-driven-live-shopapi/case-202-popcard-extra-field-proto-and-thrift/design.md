# Design

## 核心改造点

- 为竞拍讲解卡新增扩展展示字段
- 这是 `Proto + Thrift` 双协议联动需求
- 字段需要先在 `live_pack` RPC 层出现，再由 `live_shopapi` 透出给前端

## 系统职责

- `ttec/live_pack`
  负责在 RPC 返回中新增字段并填充数据

- `oec/live_shopapi`
  负责把 RPC 新字段接入 API 返回，并暴露给前端

- 协议生成平台
  负责生成新的 RPC / API 产物

## 仓库依赖关系

依赖顺序是串行的：

1. `live_pack` 侧 Thrift / RPC 协议先变更
2. 生成新的 `rpcv2_ttec_live_pack` 产物
3. `live_shopapi` 升级 RPC 依赖
4. `live_shopapi` API Proto 再新增对前端可见字段
5. 生成新的 API 产物
6. `live_shopapi` 完成最终透传

这里不是简单的多仓改代码，而是“协议生成物驱动下游演进”。

## 影响范围与边界

- 影响范围：竞拍讲解卡 RPC 返回结构、API 返回结构、转换层
- 不影响：竞拍主流程、竞价逻辑、排序逻辑
- 风险点：
  - `blocked_by_platform`
  - `blocked_by_human`
  - 若只改 API 不改 RPC，下游无数据来源
  - 若只改 RPC 不改 API，前端依然拿不到字段

## 人力评估

- 复杂度：高
- 预估人力：2 到 4 人天
- 适合作为协议驱动型需求的典型困难 case

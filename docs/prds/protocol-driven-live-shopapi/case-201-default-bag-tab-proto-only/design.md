# Design

## 核心改造点

- 新增购物袋 API 字段“默认打开 Tab”
- 复用现有服务端判定结果，不新增新的业务规则
- 这是 Proto-only 协议需求，不需要改 `live_pack` RPC 协议

## 系统职责

- `oec/live_shopapi`
  负责新增 API 字段，并把已有的默认 Tab 结果稳定透出给前端

- `ttec/live_pack`
  继续按现有逻辑提供默认 Tab 数据，不在本次改造中新增 RPC 字段

## 仓库依赖关系

- 依赖方向：`live_shopapi -> live_pack`
- 本次不涉及 `live_pack` Thrift 变更
- 主要是 `live_shopapi` 的 Proto/API 协议与格式转换层改动

## 影响范围与边界

- 影响范围：购物袋 API 返回结构
- 不影响：购物袋默认 Tab 判定规则、商品/竞拍内容、`live_pack` RPC 协议
- 风险点：若 Proto 字段加了但转换层没补，前端仍拿不到值

## 人力评估

- 复杂度：中
- 预估人力：1 到 2 人天
- 适合作为协议驱动型需求的低配版基线 case

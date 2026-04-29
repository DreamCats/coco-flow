# Design

## 核心改造点

- 这是竞拍结果态的回流入口，不是支付系统改造
- `live_common` 提供 `need_auction_retry_payment_schema` 实验字段
- `live_pack` 基于竞拍服务返回的钱包/支付 schema 和状态 retry 配置下发入口

## 系统职责

- `oec/live_common`：
  - 维护 `NeedAuctionRetryPaymentSchema` 实验字段
  - 默认关闭，避免未验证链路扩大影响
- `ttec/live_pack`：
  - auction RPC/model 层保留支付失败时间和 wallet schema
  - regular/surprise converter 拼重试支付 schema
  - bag helper 保持购物袋竞拍卡与 pop card 一致
  - DA 信息记录支付失败时间用于排查

## 依赖关系

- 主责任仓库：`ttec/live_pack`
- 公共实验仓库：`oec/live_common`
- 依赖竞拍服务返回支付失败状态、wallet schema 或可重试状态配置
- 不依赖支付页改造

## 影响范围与边界

- 影响范围：竞拍成功/完成后的失败重试表达
- 不影响：竞拍中状态、预热态、未中拍用户
- 风险点：状态判断过宽会让不该重试的用户看到支付入口

## 人力评估

- 复杂度：中
- 预估人力：1 人天
- 适合测试竞拍状态、schema 和实验开关的结合

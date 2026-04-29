# Design

## 核心改造点

- 这是购物袋竞拍准备状态提示，不是 pin 卡能力
- `AuctionInfoBanner` 的组装条件应基于竞拍 tab 是否有商品和用户签约/地址/支付状态
- schema 来源复用竞拍 TCC 配置，避免新增前端协议

## 系统职责

- `ttec/live_pack`：
  - `UserSignInfoLoader` 获取协议、地址、支付状态
  - `AuctionListConverter` 组装 `AuctionInfoBanner`
  - `converter_helpers.go` 负责按 banner type 拼协议和地址支付 schema
- `oec/live_common`：
  - 暂不需要新增字段
  - 如后续要实验化 banner，可在 `abtest` 增加独立开关

## 依赖关系

- 主责任仓库：`ttec/live_pack`
- 依赖竞拍协议 TCC：`auction_agreement`
- 依赖现有用户签约信息 RPC
- 不依赖前端新增字段

## 影响范围与边界

- 影响范围：购物袋竞拍 tab 的顶部提示
- 不影响：pop card、竞拍出价、商品排序、pin 逻辑
- 风险点：如果 banner 继续绑定 pin 商品，会导致无 pin 但有竞拍商品时缺提示

## 人力评估

- 复杂度：低
- 预估人力：0.5 人天
- 适合作为竞拍进购物袋准备链路基线 case

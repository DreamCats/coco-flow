# Design

## 核心改造点

- 这是标题表达优化，不是商品信息来源变更
- 只在 regular auction 标题组装层补一段竞拍标识
- 实验未命中或标识为空时，完整回退原标题

## 系统职责

- `live_pack`：在标题组装阶段消费实验字段并拼接前缀
- 本地化文案层：提供 `Auction` 标识文本
- 其他链路：保持不变

## 依赖关系

- 主责任仓库是 `ttec/live_pack`
- 依赖现有实验字段和文案 key
- 不需要改 BFF、前端协议或购物袋

## 影响范围与边界

- 影响范围：regular auction `AuctionTitle`
- 不影响：surprise set、temporary listing、价格、schema
- 风险点：如果前缀拼接条件过宽，可能误伤非 regular auction

## 人力评估

- 复杂度：低
- 预估人力：0.5 人天
- 适合作为标题表达类基线 case

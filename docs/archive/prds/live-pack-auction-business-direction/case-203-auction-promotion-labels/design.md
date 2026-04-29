# Design

## 核心改造点

- 这是竞拍商品权益表达补齐，不是营销计算改造
- `live_common` 提供公共 AB 字段 `use_auction_promotion_label`
- `live_pack` 在 auction placement labels loader 中读取商品模型已有 labels，并写入 auction data

## 系统职责

- `oec/live_common`：
  - 维护 `UseAuctionPromotionLabel` 实验字段
  - 保证字段默认关闭
- `ttec/live_pack`：
  - `AuctionPlacementLabelsLoader` 负责 pop card 标签提取
  - `BagAuctionPlacementLabelsLoader` 负责购物袋批量标签提取
  - `RegularAuctionConverter` 和 bag helper 写入 `PromotionLabels`
  - `SurpriseAuctionDetailConverter` 对 surprise set 奖品标签做白名单过滤

## 依赖关系

- 主责任仓库：`ttec/live_pack`
- 公共实验仓库：`oec/live_common`
- 依赖商品模型已返回 promotion labels
- 不依赖前端新增样式

## 影响范围与边界

- 影响范围：竞拍卡、购物袋竞拍卡、surprise set detail available item
- 不影响：Buy Now 商品卡、券计算、价格展示
- 风险点：surprise set 若直接透出全部标签，可能把不适合奖品维度的权益展示给用户

## 人力评估

- 复杂度：中
- 预估人力：1 人天
- 适合测试 AB 字段、loader 和 converter 跨层协作

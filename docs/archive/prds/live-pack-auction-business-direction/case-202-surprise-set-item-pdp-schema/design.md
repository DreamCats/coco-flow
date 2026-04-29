# Design

## 核心改造点

- 这是 surprise set 详情页奖品可探索性优化
- schema 应由 `live_pack` 基于商品模型和 SKU 信息拼装
- 实验开关由 `live_common/abtest` 的 `need_surprise_set_item_auction_schema` 控制

## 系统职责

- `oec/live_common`：
  - 维护公共 AB 字段 `NeedSurpriseSetItemAuctionSchema`
  - 保证字段可被 `live_pack` 的 request context 读取
- `ttec/live_pack`：
  - `SurpriseAuctionDetailConverter` 读取商品模型、SKU 和 AB 字段
  - 基于 PDP schema 追加 `checked_spec_ids`
  - schema 拼装失败时回退原展示

## 依赖关系

- 主责任仓库：`ttec/live_pack`
- 公共字段仓库：`oec/live_common`
- 依赖商品模型中的 PDP schema 和 SKU base info
- 不依赖前端新增协议字段

## 影响范围与边界

- 影响范围：surprise set detail 的 available item
- 不影响：pop card 主竞拍 schema、购物袋列表 schema、sold item
- 风险点：SKU 属性拼错会导致 PDP 默认规格不符合奖品实际 SKU

## 人力评估

- 复杂度：中
- 预估人力：1 人天
- 适合测试 surprise set 与 schema 拼装理解能力

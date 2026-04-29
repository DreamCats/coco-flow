# Design

## 核心改造点

- 这是 banner 锚定对象选择优化，不是 banner 资格体系改造
- 有 pin 时维持现有优先级
- 无 pin 时增加“列表首个竞拍商品”的回退路径

## 系统职责

- `AuctionListConverter`：负责决定 banner 绑定哪一个竞拍商品
- `UserSignInfo` 等 banner 资格判断：保持现有逻辑
- 商品列表顺序：继续由现有竞拍列表结果提供

## 依赖关系

- 主责任仓库是 `ttec/live_pack`
- 不需要联动协议或前端字段
- 不依赖购物袋默认 tab 逻辑调整

## 影响范围与边界

- 影响范围：`AuctionInfoBanner` 的锚定 config 选择
- 不影响：banner 文案、资格、默认 tab、竞拍商品排序
- 风险点：若 fallback 选错商品，banner schema 会跳到错误商品

## 人力评估

- 复杂度：低到中
- 预估人力：0.5 到 1 人天
- 适合作为“有优先级 fallback”类 case

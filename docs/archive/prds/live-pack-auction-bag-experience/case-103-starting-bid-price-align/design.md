# Design

## 核心改造点

- 这是同一业务在两个入口间的价格口径对齐
- 只修正 regular auction 的起拍价来源
- 不把问题扩大为整套价格模型重构

## 系统职责

- `live_pack` bag converter helper：负责 regular auction `start_bid_price` 的来源选择
- 讲解卡：作为对齐目标，不在本次直接改动范围
- 其他价格项：继续沿用现有逻辑

## 依赖关系

- 主责任仓库是 `ttec/live_pack`
- 依赖现有竞拍配置可读取 `StartingBidPrice`
- 不需要联动协议或前端字段

## 影响范围与边界

- 影响范围：购物袋 regular auction 的 `StartBidPrice`
- 不影响：当前最高价、下一口价、自定义出价、surprise set
- 风险点：若误把其他价格项一起切源，会造成更大范围回归

## 人力评估

- 复杂度：低
- 预估人力：0.5 人天
- 适合作为“同业务多入口口径对齐”类 case

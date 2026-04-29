# Design

## 核心改造点

- 这是竞拍 CTA 表达升级，不是出价交易链路改造
- `live_common` 提供或复用 `pincard_double_bid_btn` 实验字段
- `live_pack` 通过 product switch 控制 `PincardDisplayDoubleBtns`、bid panel 和 customize panel 下发

## 系统职责

- `oec/live_common`：
  - 维护 `PincardDoubleBidBtn` 实验字段
  - 保证字段能映射到 `ProductSwitch.GetNeedAuctionDoubleBtns`
- `ttec/live_pack`：
  - `RegularAuctionConverter` 和 `SurpriseSetAuctionConverter` 下发双按钮能力
  - `converter_helpers.go` 让购物袋竞拍卡与 pop card 对齐
  - 预热态清理不应展示的出价文案

## 依赖关系

- 主责任仓库：`ttec/live_pack`
- 公共实验仓库：`oec/live_common`
- 依赖现有 bid panel/customize panel 协议
- 不依赖交易 RPC 改造

## 影响范围与边界

- 影响范围：竞拍卡 CTA、bid panel、customize panel
- 不影响：价格计算、最低加价规则、支付链路
- 风险点：预热态如果仍展示出价按钮，会让用户误以为可以提前出价

## 人力评估

- 复杂度：中
- 预估人力：1 人天
- 适合测试实验字段到 converter 表达的链路

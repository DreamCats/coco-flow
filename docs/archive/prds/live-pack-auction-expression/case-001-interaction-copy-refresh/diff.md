# Diff

## 预期代码改动

- 在 `entities/converters/auction_converters/const.go` 增加或收敛实验文案 key 常量。
- 在 `entities/converters/auction_converters/regular_auction_converter.go` 中：
  - 读取实验字段
  - 覆盖预热态与无人出价开场态对应的 `AuctionText`
- 在 `entities/converters/auction_converters/surprise_set_auction_converter.go` 中：
  - 读取同一实验字段
  - 覆盖 surprise set 预热态与首拍态对应的 `AuctionText`

## 不应出现的改动

- 不应新增前端字段
- 不应改购物袋链路
- 不应改底层价格格式化逻辑

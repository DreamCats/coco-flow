# Diff

## 预期代码改动

- 在 `entities/converters/auction_converters/converter_helpers.go` 中：
  - 调整 regular auction `start_bid_price` helper 的取值来源
  - 从旧商品价格字段切到竞拍配置里的 `StartingBidPrice`
- 在 regular auction bag data builder 中：
  - 传入新 helper 需要的配置上下文

## 不应出现的改动

- 不应改当前最高价、下一口价、自定义出价
- 不应改 surprise set 价格逻辑
- 不应把价格来源切换扩大到整个价格体系

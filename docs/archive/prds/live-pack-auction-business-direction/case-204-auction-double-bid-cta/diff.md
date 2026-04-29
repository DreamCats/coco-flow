# Diff

## 预期代码改动

- 在 `oec/live_common/abtest/struct.go` 确认或新增 `pincard_double_bid_btn` 字段。
- 在 `ttec/live_pack/entities/converters/auction_converters/regular_auction_converter.go` 中下发 regular 双 CTA 信息。
- 在 `ttec/live_pack/entities/converters/auction_converters/surprise_set_auction_converter.go` 中下发 surprise set 双 CTA 信息。
- 在 `ttec/live_pack/entities/converters/auction_converters/converter_helpers.go` 中让购物袋竞拍卡复用相同逻辑。
- 检查预热态文案，避免命中双 CTA 后出现可提前出价的误导。

## 不应出现的改动

- 不应修改出价价格计算
- 不应修改竞拍交易 RPC
- 不应影响未命中实验的单 CTA
- 不应把双 CTA 限定在 regular auction，遗漏 surprise set

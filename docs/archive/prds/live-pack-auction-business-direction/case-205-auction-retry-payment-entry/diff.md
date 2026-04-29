# Diff

## 预期代码改动

- 在 `oec/live_common/abtest/struct.go` 确认或新增 `need_auction_retry_payment_schema` 字段。
- 在 `ttec/live_pack/entities/converters/auction_converters/regular_auction_converter.go` 中处理 regular auction 支付失败重试入口。
- 在 `ttec/live_pack/entities/converters/auction_converters/surprise_set_auction_converter.go` 中处理 surprise set 支付失败重试入口。
- 在 `ttec/live_pack/entities/converters/auction_converters/converter_helpers.go` 中让购物袋竞拍卡复用重试 schema 拼装。
- 检查 `model/format/convert_auction_resp.go` 和 `dal/rpc/oec.trade.auction.go` 是否已保留支付失败状态、失败时间和 wallet schema。

## 不应出现的改动

- 不应修改支付页或订单状态机
- 不应在非支付失败状态展示重试入口
- 不应绕过实验开关全量下发
- 不应只支持 regular auction 而遗漏 surprise set

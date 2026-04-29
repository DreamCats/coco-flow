# Diff

## 预期代码改动

- 在 `ttec/live_pack/entities/converters/auction_converters/list_converter.go` 中：
  - 将 `AuctionInfoBanner` 与 pin 竞拍商品解耦
  - 基于 `UserSignInfoLoader` 结果尝试组装 banner
- 在 `ttec/live_pack/entities/converters/auction_converters/converter_helpers.go` 中：
  - 保证协议 schema 和地址支付 schema 参数完整
  - 增加空 schema 的安全兜底

## 不应出现的改动

- 不应修改竞拍协议内容
- 不应修改前端 IDL
- 不应改变 pin 商品选取逻辑
- 不应把 banner 展示绑定到 `PopAuctionProduct`

# Diff

## 预期代码改动

- 在 `entities/converters/auction_converters/list_converter.go` 中：
  - 保留“有 pin 用 pin”的优先逻辑
  - 增加“无 pin 时用列表第一个竞拍商品”的 fallback
  - 仅在找到有效 config 后再组装 `AuctionInfoBanner`

## 不应出现的改动

- 不应改 banner 文案
- 不应改默认 tab 逻辑
- 不应改变竞拍商品列表顺序

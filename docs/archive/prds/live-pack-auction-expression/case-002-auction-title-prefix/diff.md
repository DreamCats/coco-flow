# Diff

## 预期代码改动

- 在 `entities/converters/auction_converters/const.go` 增加标题前缀文案 key 和分隔符常量。
- 在 `entities/converters/auction_converters/regular_auction_converter.go` 中：
  - 在 regular auction 标题组装完成后判断实验是否命中
  - 命中时为标题补充本地化 `Auction` 标识
  - 标识为空时回退原标题

## 不应出现的改动

- 不应改 surprise set 标题
- 不应改商品主标题来源
- 不应改购物袋或协议层

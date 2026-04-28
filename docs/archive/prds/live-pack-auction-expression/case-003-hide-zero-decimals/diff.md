# Diff

## 预期代码改动

- 在 `entities/converters/auction_converters/regular_auction_converter.go` 中：
  - 对讲解卡价格项增加实验命中后的整数金额裁剪
- 在 `entities/converters/auction_converters/surprise_set_auction_converter.go` 中：
  - 对同类价格项增加相同裁剪逻辑
- 如有需要，增加一个只服务讲解卡 converter 的轻量 helper

## 不应出现的改动

- 不应修改底层通用价格 formatter
- 不应影响购物袋 helper
- 不应改变非整数金额的展示格式

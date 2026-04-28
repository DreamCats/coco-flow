# Diff

## 预期代码改动

- 在 `handlers/get_live_bag_assemble_handler.go` 中：
  - 调整 `DefaultBagTab` 兜底逻辑
  - 仅当当前页有竞拍商品且无 Buy Now 商品时，兜底为 `AUCTION`
- 在 `handlers/get_live_bag_data_handler.go` 中：
  - 做同样的兜底调整

## 不应出现的改动

- 不应改 `BagTabs` 生成逻辑
- 不应改竞拍商品排序或分页
- 不应改 banner 逻辑

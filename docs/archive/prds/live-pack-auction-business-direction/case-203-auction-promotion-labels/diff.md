# Diff

## 预期代码改动

- 在 `oec/live_common/abtest/struct.go` 确认或新增 `use_auction_promotion_label` 字段。
- 在 `ttec/live_pack/entities/loaders/auction_loaders/auction_placement_labels_loader.go` 中提取 pop card 标签。
- 在 `ttec/live_pack/entities/loaders/auction_loaders/bag_auction_placement_labels_loader.go` 中提取购物袋竞拍商品标签。
- 在 `ttec/live_pack/entities/converters/auction_converters/regular_auction_converter.go` 和 `converter_helpers.go` 中写入 `PromotionLabels`。
- 在 `surprise_auction_detail_converter.go` 中保留 surprise set 奖品标签白名单。

## 不应出现的改动

- 不应修改商品营销标签计算逻辑
- 不应影响 Buy Now 商品卡
- 不应在未命中实验时展示新标签
- 不应把 surprise set 奖品不适用标签全部透出

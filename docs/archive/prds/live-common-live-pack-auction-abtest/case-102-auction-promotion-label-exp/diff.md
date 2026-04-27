# 预期代码改动

```diff
diff --git a/abtest/struct.go b/abtest/struct.go
@@
+	UseAuctionPromotionLabel bool `json:"use_auction_promotion_label"` // 竞拍展示营销标签
```

```diff
diff --git a/entities/loaders/auction_loaders/auction_placement_labels_loader.go b/entities/loaders/auction_loaders/auction_placement_labels_loader.go
@@
 	if rc.GetAbParam() == nil || !rc.GetAbParam().TTECContent.UseAuctionPromotionLabel {
 		return nil
 	}
```

```diff
diff --git a/entities/loaders/auction_loaders/bag_auction_placement_labels_loader.go b/entities/loaders/auction_loaders/bag_auction_placement_labels_loader.go
@@
 	if rc.GetAbParam() == nil || !rc.GetAbParam().TTECContent.UseAuctionPromotionLabel {
 		return nil
 	}
```

```diff
diff --git a/entities/converters/auction_converters/converter_helpers.go b/entities/converters/auction_converters/converter_helpers.go
@@
 	if rc.GetAbParam() == nil || !rc.GetAbParam().TTECContent.UseAuctionPromotionLabel {
 		return ""
 	}
```

```diff
diff --git a/entities/converters/auction_converters/surprise_set_auction_converter.go b/entities/converters/auction_converters/surprise_set_auction_converter.go
@@
 	if rc.GetAbParam() == nil || !rc.GetAbParam().TTECContent.UseAuctionPromotionLabel {
 		return ""
 	}
```

# 预期代码改动

```diff
diff --git a/abtest/struct.go b/abtest/struct.go
@@
+	AuctionInBagEnabled bool `json:"auction_in_bag_enabled"` // 竞拍进购物袋功能开关
```

```diff
diff --git a/handlers/get_live_bag_data_handler.go b/handlers/get_live_bag_data_handler.go
@@
+		if rCtx.GetAbParam() == nil || !rCtx.GetAbParam().TTECContent.AuctionInBagEnabled {
+			return
+		}
```

```diff
diff --git a/handlers/get_live_bag_assemble_handler.go b/handlers/get_live_bag_assemble_handler.go
@@
+		if rCtx.GetAbParam() == nil || !rCtx.GetAbParam().TTECContent.AuctionInBagEnabled {
+			return
+		}
```

```diff
diff --git a/handlers/get_live_bag_refresh_handler.go b/handlers/get_live_bag_refresh_handler.go
@@
+		if rCtx.GetAbParam() == nil || !rCtx.GetAbParam().TTECContent.AuctionInBagEnabled {
+			return
+		}
```

```diff
diff --git a/entities/dto_builders/room_lite_data_dto_builder.go b/entities/dto_builders/room_lite_data_dto_builder.go
@@
+		if rCtx.GetAbParam() != nil && rCtx.GetAbParam().TTECContent.AuctionInBagEnabled {
+			// 仅实验开启时写 bag auction 相关字段
+		}
```

```diff
diff --git a/entities/loaders/user_right/user_right_data_loader.go b/entities/loaders/user_right/user_right_data_loader.go
@@
+	auctionInBagEnabled := rc.GetAbParam() != nil && rc.GetAbParam().TTECContent.AuctionInBagEnabled
+	if auctionInBagEnabled {
+		// 合并竞拍品 ID
+	}
```

# 预期代码改动

```diff
diff --git a/entities/loaders/auction_loaders/auction_status_loader.go b/entities/loaders/auction_loaders/auction_status_loader.go
@@
-	case auction.AuctionStatus_Succeed:
-		auctionStatus = getAuctionStatusSuccess(rc.GetAbParam())
+	case auction.AuctionStatus_Succeed:
+		auctionStatus = data_pack.AuctionStatus_AuctionStatus_Success
@@
-func getAuctionStatusSuccess(abParam *abtest.AbParam) data_pack.AuctionStatus {
-	if abParam != nil && abParam.TTECContent.UseAuctionStatusSuccess {
-		return data_pack.AuctionStatus_AuctionStatus_Success
-	}
-
-	return data_pack.AuctionStatus_AuctionStatus_Complete
-}
```

```diff
diff --git a/entities/loaders/product_loaders/product_auction_data_loader.go b/entities/loaders/product_loaders/product_auction_data_loader.go
@@
-		case AuctionStatus_Succeed:
-			auctionTextType = data_pack.AuctionTextType_AuctionTextType_Success
-			auctionStatus = getAuctionStatusSuccess(rc.GetAbParam())
+		case AuctionStatus_Succeed:
+			auctionTextType = data_pack.AuctionTextType_AuctionTextType_Success
+			auctionStatus = data_pack.AuctionStatus_AuctionStatus_Success
@@
-func getAuctionStatusSuccess(abParam *abtest.AbParam) data_pack.AuctionStatus {
-	if abParam != nil && abParam.TTECContent.UseAuctionStatusSuccess {
-		return data_pack.AuctionStatus_AuctionStatus_Success
-	}
-
-	return data_pack.AuctionStatus_AuctionStatus_Complete
-}
```

## 预期结果

- 成交态统一下发 `success`
- `refine` 应该能稳定抽出“成交态口径统一”“仅讲解卡不改 bag”这两个边界
- `plan` 应该能识别出“新旧链路都要改”的一致性要求

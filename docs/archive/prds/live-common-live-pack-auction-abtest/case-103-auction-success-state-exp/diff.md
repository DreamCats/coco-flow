# 预期代码改动

```diff
diff --git a/abtest/struct.go b/abtest/struct.go
@@
+	UseAuctionStatusSuccess bool `json:"use_auction_status_success"` // 普通竞拍是否下发中拍态
```

```diff
diff --git a/entities/loaders/auction_loaders/auction_status_loader.go b/entities/loaders/auction_loaders/auction_status_loader.go
@@
 func getAuctionStatusSuccess(abParam *abtest.AbParam) data_pack.AuctionStatus {
 	if abParam != nil && abParam.TTECContent.UseAuctionStatusSuccess {
 		return data_pack.AuctionStatus_AuctionStatus_Success
 	}
 
 	return data_pack.AuctionStatus_AuctionStatus_Complete
 }
```

```diff
diff --git a/entities/loaders/auction_loaders/bag_auction_status_loader.go b/entities/loaders/auction_loaders/bag_auction_status_loader.go
@@
 	case auction.AuctionStatus_Succeed:
 		return getAuctionStatusSuccess(abParam)
```

```diff
diff --git a/entities/loaders/product_loaders/product_auction_data_loader.go b/entities/loaders/product_loaders/product_auction_data_loader.go
@@
 func getAuctionStatusSuccess(abParam *abtest.AbParam) data_pack.AuctionStatus {
 	if abParam != nil && abParam.TTECContent.UseAuctionStatusSuccess {
 		return data_pack.AuctionStatus_AuctionStatus_Success
 	}
 
 	return data_pack.AuctionStatus_AuctionStatus_Complete
 }
```

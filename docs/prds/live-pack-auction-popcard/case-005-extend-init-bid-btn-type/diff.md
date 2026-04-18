# 预期代码改动

```diff
diff --git a/entities/converters/auction_converters/regular_auction_converter.go b/entities/converters/auction_converters/regular_auction_converter.go
@@
 	default:
-		auctionTextType = data_pack.AuctionTextType_AuctionTextType_Init
+		if p.isExtendAuctionSupported {
+			auctionTextType = data_pack.AuctionTextType_ExtendAuctionTextType_Init
+		} else {
+			auctionTextType = data_pack.AuctionTextType_AuctionTextType_Init
+		}
 	}
```

```diff
diff --git a/entities/converters/auction_converters/converter_helpers.go b/entities/converters/auction_converters/converter_helpers.go
@@
-func bagGetRegularBidBtnTextType(info *modelRpc.AuctionInfoFromAuction) int32 {
+func bagGetRegularBidBtnTextType(info *modelRpc.AuctionInfoFromAuction, isExtend bool) int32 {
@@
 	default:
-		textType = data_pack.AuctionTextType_AuctionTextType_Init
+		if isExtend {
+			textType = data_pack.AuctionTextType_ExtendAuctionTextType_Init
+		} else {
+			textType = data_pack.AuctionTextType_AuctionTextType_Init
+		}
 	}
@@
-		textType := bagGetRegularBidBtnTextType(info)
+		textType := bagGetRegularBidBtnTextType(info, isExtendAuctionSupported)
```

```diff
diff --git a/entities/loaders/product_loaders/product_auction_data_loader.go b/entities/loaders/product_loaders/product_auction_data_loader.go
@@
 			default:
-				auctionTextType = data_pack.AuctionTextType_AuctionTextType_Init
+				if isExtendAuctionSupported {
+					auctionTextType = data_pack.AuctionTextType_ExtendAuctionTextType_Init
+				} else {
+					auctionTextType = data_pack.AuctionTextType_AuctionTextType_Init
+				}
 			}
```

## 预期结果

- 这个 case 能很好检验 `plan` 是否能识别“同一口径要同时改 3 条链路”
- 也能检验 `code` 是否能把 helper 签名调整、调用方同步和旧链路补齐一次做完整

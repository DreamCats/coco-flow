# 预期代码改动

```diff
diff --git a/entities/converters/auction_converters/list_converter.go b/entities/converters/auction_converters/list_converter.go
@@
-	if userSignRes != nil {
+	if userSignRes != nil && len(convertResult.AuctionProducts) > 0 {
 		auctionAgreement, _ := tcc.GetLiveAuctionAgreement(rc.GetCtx(), rc.GetUserContext().GetPriorityRegion())
 		p.intermediate.AuctionInfoBanner = bagBuildAuctionInfoBanner(rc, userSignRes.BannerType, userSignRes.HasSignedTerms, auctionAgreement)
 	}
```

```diff
diff --git a/handlers/get_live_bag_data_handler.go b/handlers/get_live_bag_data_handler.go
@@
 		if auctionListDto != nil && auctionListDto.Err == nil {
 			resp.AuctionProducts = auctionListDto.AuctionProducts
 			resp.AuctionTotal = gptr.Of(auctionListDto.AuctionTotal)
 			resp.PopAuctionProduct = auctionListDto.PopAuctionProduct
-			resp.AuctionInfoBanner = auctionListDto.AuctionInfoBanner
+			if len(auctionListDto.AuctionProducts) > 0 {
+				resp.AuctionInfoBanner = auctionListDto.AuctionInfoBanner
+			}
 			resp.DefaultBagTab = auctionListDto.DefaultBagTab
 		}
```

```diff
diff --git a/handlers/get_live_bag_assemble_handler.go b/handlers/get_live_bag_assemble_handler.go
@@
 		if auctionListDto != nil && auctionListDto.Err == nil {
 			resp.AuctionProducts = auctionListDto.AuctionProducts
 			resp.AuctionTotal = gptr.Of(auctionListDto.AuctionTotal)
 			resp.PopAuctionProduct = auctionListDto.PopAuctionProduct
-			resp.AuctionInfoBanner = auctionListDto.AuctionInfoBanner
+			if len(auctionListDto.AuctionProducts) > 0 {
+				resp.AuctionInfoBanner = auctionListDto.AuctionInfoBanner
+			}
 			resp.DefaultBagTab = auctionListDto.DefaultBagTab
 		}
```

## 预期结果

- 这是一个典型的“列表 converter + 两个 handler”三点联动 case
- 很适合检验 `plan` 是否能识别多入口同口径收敛

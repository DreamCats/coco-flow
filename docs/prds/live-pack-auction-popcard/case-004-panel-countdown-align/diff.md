# 预期代码改动

```diff
diff --git a/entities/loaders/product_loaders/product_auction_data_loader.go b/entities/loaders/product_loaders/product_auction_data_loader.go
@@
 	bidPanel := &data_pack.BidPanel{
 		PrefixBidPrice:            gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.BidPanel.PrefixBidPrice, locale)),
 		Tips:                      gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.BidPanel.Tips, locale)),
 		CustomizeBidBtnText:       gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.BidPanel.CustomizeBidBtnText, locale)),
 		NextBidBtnPricePrefixText: gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.BidPanel.NextBidBtnPricePrefixText, locale)),
 		TopTitle:                  gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.BidPanel.TopTitle, locale)),
+		TopTitleWithCountdown:     getTopTitleWithCountdown(p.auctionCardConfig.BidPanel.TopTitleWithCountdown, locale),
 		InfoList:                  formatPanelInfoList(p.auctionCardConfig.BidPanel.RegularAuctionInfoList, locale, ""),
 	}
 	customizePanel := &data_pack.CustomizePanel{
 		Title:          gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.CustomizePanel.Title, locale)),
 		Desc:           gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.CustomizePanel.Desc, locale)),
 		SubmitBtnText:  gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.CustomizePanel.SubmitBtnText, locale)),
 		SubmitTips:     gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.CustomizePanel.SubmitTips, locale)),
-		TopTitle:       gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.BidPanel.TopTitle, locale)),
+		TopTitle:       gptr.Of(starling.GetTextEcommerceWithFallBack(p.auctionCardConfig.CustomizePanel.TopTitle, locale)),
+		TopTitleWithCountdown: getTopTitleWithCountdown(p.auctionCardConfig.CustomizePanel.TopTitleWithCountdown, locale),
 		InfoList:       formatPanelInfoList(p.auctionCardConfig.CustomizePanel.RegularAuctionInfoList, locale, ""),
 		AddressPayIcon: gptr.Of(p.auctionCardConfig.CustomizePanel.AddressPayIcon),
 	}
```

## 预期结果

- 这是一个典型的“一个 PRD 三个小改点” case
- `refine` 应该能抽出“字段补齐 + 错误字段源修正”的组合需求
- `plan` 应该能识别为旧兼容链路对齐新链路，而不是全链路重构

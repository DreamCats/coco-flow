# 预期代码改动

```diff
diff --git a/entities/converters/auction_converters/regular_auction_converter.go b/entities/converters/auction_converters/regular_auction_converter.go
@@
-	// temporary list改auction标题 ,regular auction 直接用商品标题
-	if p.auctionConfigFromLiveB.GetAuctionConfigType() == live_common.AuctionConfigType_TemporaryList && len(skuBaseInfo.GetSkuName()) > 0 {
+	if skuBaseInfo != nil && len(baseInfo.GetSkuBaseInfos()) > 1 && len(skuBaseInfo.GetSkuName()) > 0 {
 		auctionTitle = "#" + skuBaseInfo.GetSkuName() + " " + baseInfo.GetTitleInfo().GetOriginalTitle()
 	} else {
 		auctionTitle = baseInfo.GetTitleInfo().GetOriginalTitle()
 	}
```

```diff
diff --git a/entities/loaders/product_loaders/product_auction_data_loader.go b/entities/loaders/product_loaders/product_auction_data_loader.go
@@
-	// 2. temporary list改auction标题
-	if auctionConfigFromLiveB.GetAuctionConfigType() == live_common.AuctionConfigType_TemporaryList && len(skuBaseInfo.GetSkuName()) > 0 {
+	if skuBaseInfo != nil && len(product.GetBaseInfo().GetSkuBaseInfos()) > 1 && len(skuBaseInfo.GetSkuName()) > 0 {
 		auctionInfoNeedChanged.Title = "#" + skuBaseInfo.GetSkuName() + " " + product.GetBaseInfo().GetTitleInfo().GetOriginalTitle()
 	}
```

## 预期结果

- `plan` 应该能识别出“新旧链路都要统一标题规则”
- `code` 的标准答案应该只改两个文件，不需要动 TCC 和 handler

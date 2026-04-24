# 预期代码改动

```diff
diff --git a/entities/loaders/product_loaders/product_auction_data_loader.go b/entities/loaders/product_loaders/product_auction_data_loader.go
@@
 	auctionData.RegularAuctionData = &data_pack.RegularAuctionData{
 		PlacementLabels: p.productPlacementLabels[pid],
 		AuctionImg:      auctionImg,
 		TargetSkuId:     gptr.Of(auctionSkuId),
 		TargetProductId: gptr.Of(baseInfo.GetId()),
 		ComponentData:   format.PackComponentData(productModel, rc.GetAbParam()),
 		Platform:        gptr.OfNotZero(data_pack.Platform(productModel.GetBaseInfo().GetPlatform())),
 		Source:          format.ConvertProductSourceVo(productModel.GetBaseInfo()),
+		AuctionLabel:    p.buildRegularAuctionLabel(rc),
 	}
```

```diff
diff --git a/entities/loaders/product_loaders/product_auction_data_loader.go b/entities/loaders/product_loaders/product_auction_data_loader.go
@@
+func (p *ProductAuctionDataLoader) buildRegularAuctionLabel(rc *engine_model.RequestContext) *data_pack.AuctionLabel {
+	if p.auctionCardConfig == nil {
+		return nil
+	}
+	cfg := p.auctionCardConfig.RegularDataInfo.AuctionLabel
+	locale := rc.GetUserContext().GetLocale()
+	return &data_pack.AuctionLabel{
+		DefaultText: starling.GetTextEcommerceWithFallBack(cfg.DefaultText, locale),
+		DefaultColor: &data_pack.Color{
+			Value:     gptr.Of(cfg.DefaultColor.Value),
+			DarkValue: gptr.Of(cfg.DefaultColor.DarkValue),
+		},
+		IconLight: convertImageWithFWH(rc.GetCtx(), cfg.IconLight),
+		IconDark:  convertImageWithFWH(rc.GetCtx(), cfg.IconDark),
+	}
+}
```

## 预期结果

- 新旧链路 regular auction 都能稳定下发 `AuctionLabel`
- 这个 case 很适合检验 `plan` 是否能识别“现状已在新链路实现，只需补旧链路”的差异化方案

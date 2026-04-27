# live_pack auction popcard 单仓对照组

目标：基于 `/Users/bytedance/go/src/code.byted.org/ttec/live_pack` 里 `popcard / auction` 相关实现，整理一批适合 `coco-flow refine -> plan -> code` 链路压测的单仓 case。

这些 case 都刻意满足下面几个条件：

- 单仓库可完成，不依赖跨 repo 联调
- 需求简单，能压中 `refine` 和 `plan` 的关键信息抽取能力
- 改动点足够具体，能形成稳定的“标准答案”
- 验证成本低，优先 `go test` 定向包，而不是全量回归

## 文档分工

- `prd.md`：产品视角，只写业务目标、范围、边界、验收
- `design.md`：评审视角，只写核心改造点、系统职责、依赖关系、影响范围、人力评估
- `plan.md`：执行视角，写实施切片、顺序、文件落点、验证动作
- `diff.md`：标准答案视角，写预期代码改动

当前 case 统一复用共享模板：[PLAN_TEMPLATE.md](/Users/bytedance/Work/tools/bytedance/coco-flow/docs/prds/PLAN_TEMPLATE.md)

## 调研结论

- 讲解卡拍卖主链路：`GetPinCardDataHandler` -> `BuildAuctionCardDataEngine` -> `PopCardProvider` / `AuctionConfigDataProvider` / `AuctionFilter` / loaders / `RegularAuctionConverter` -> `AuctionCardDataDtoBuilder`
- 用户可见字段主要由三层决定：
  1. `AuctionStatusLoader` 决定展示态
  2. `RegularAuctionConverter` 决定标题、文案、按钮、面板、标签等字段
  3. `dal/tcc/auction_config.go` 提供文案和样式配置
- 旧兼容链路仍存在于 `entities/loaders/product_loaders/product_auction_data_loader.go`，如果需求是“讲解卡实际展示字段对齐”，通常要检查这条链路是否也需要同步
- 自动化测试覆盖很薄，适合做流程对照组，但也意味着标准答案要把“最小验证命令”写清楚

## 推荐 case

1. `case-001-success-state`
   竞拍成交后，讲解卡展示独立 `success` 态，而不是继续落到 `complete`

2. `case-002-sku-title-prefix`
   多 SKU 竞拍讲解卡标题增加 `SKU 名` 前缀，帮助用户区分当前参拍规格

3. `case-003-auction-label-compat`
   旧兼容链路也下发 regular auction 的 `AuctionLabel`，避免新旧链路展示不一致

4. `case-004-panel-countdown-align`
   旧兼容链路补齐竞拍面板倒计时标题，并修正自定义出价面板标题来源

5. `case-005-extend-init-bid-btn-type`
   延时竞拍在双按钮场景下使用延时竞拍专属 `init` 按钮文案类型

6. `case-006-bag-banner-gating`
   购物袋没有竞拍商品时，不展示竞拍 banner，也不让 banner 脱离 auction tab 单独出现

## 使用建议

- 如果是验证 `refine`：优先把各 case 的 `prd.md` 直接作为输入
- 如果是验证 `design`：把 `design.md` 当作标准参考答案
- 如果是验证 `plan`：按共享 [PLAN_TEMPLATE.md](/Users/bytedance/Work/tools/bytedance/coco-flow/docs/prds/PLAN_TEMPLATE.md) 生成执行方案，再和 `diff.md` 对照
- 如果是验证 `code`：把 `diff.md` 当作预期输出对照
- 如果要统计成功率，建议先从 `case-001` 和 `case-002` 开始，这两个 case 的业务边界最清楚

# live_common + live_pack auction 实验联动对照组

目标：补一组真实风格的多仓 case，用来验证 `coco-flow` 在“一个仓库加实验字段，另一个仓库接表达层逻辑”这种场景下的 `refine -> plan -> code` 成功率。

仓库范围：

- `/Users/bytedance/go/src/code.byted.org/oec/live_common/abtest`
- `/Users/bytedance/go/src/code.byted.org/ttec/live_pack`

## 这组 case 的共同模式

这批需求都遵循同一种现实工作流：

1. 在 `live_common/abtest/struct.go` 新增或调整实验字段
2. 在 `live_pack` 里消费该实验字段
3. 改动主要落在 auction 的 loader / converter / handler / dto builder
4. 最终影响讲解卡、竞拍购物袋或相关表达层字段

## 仓库依赖关系

这组多仓 case 里，代码依赖关系是单向的，不是双向的：

- `live_pack` 依赖 `oec/live_common/abtest`
- `oec/live_common/abtest` 不依赖 `live_pack`

证据：

- `live_pack` 的 [go.mod](/Users/bytedance/go/src/code.byted.org/ttec/live_pack/go.mod) 直接依赖了 `code.byted.org/oec/live_common/abtest`
- `live_pack` 仓库里大量文件直接 import 了 `code.byted.org/oec/live_common/abtest`

因此，多仓联动里真正的技术顺序通常是：

1. 先在 `oec/live_common/abtest` 新增或调整实验字段
2. 发布或生成新的依赖版本
3. `live_pack` 更新 `go.mod / go.sum`
4. `live_pack` 再读取新字段，并把它接到 handler / loader / converter / dto builder

## 文档分工

- `prd.md`：产品视角，只描述业务意图，不暴露仓库和实现细节
- `design.md`：评审视角，强调仓库职责、依赖关系、影响范围和人力评估
- `plan.md`：执行视角，负责拆实施顺序、文件落点和验证动作
- `diff.md`：标准答案视角，给出预期代码改动

当前多仓 case 统一复用共享模板：[PLAN_TEMPLATE.md](/Users/bytedance/Work/tools/bytedance/coco-flow/docs/prds/PLAN_TEMPLATE.md)

## 依赖点要更新什么

典型要更新 3 类内容：

1. 上游结构定义
   位置通常是 `oec/live_common/abtest/struct.go`
   这里定义 `TTECContent.xxx`

2. 下游依赖版本
   位置通常是 `ttec/live_pack/go.mod` 和 `go.sum`
   如果 `live_pack` 还没拿到包含新字段的 abtest 版本，就没法安全编译和引用

3. 下游消费逻辑
   常见依赖点：
   - `req_params_builders/abparam_builder.go`
   - `engine_model/request_context.go`
   - 具体业务文件里通过 `rc.GetAbParam().TTECContent.xxx` 读取实验开关
   - 某些场景会进一步映射到 `ProductSwitch`，再由 converter / loader 消费

## 历史锚点

这组对照组参考了两个仓库里实际存在过的历史改动模式：

- `3f13bea`：`live_common/abtest` 新增 `auction double bid btn`
- `f1d5a2f`：`live_common/abtest` 新增 `竞拍无图模式优化实验字段`
- `c82be41`：`live_common/abtest` 新增 `need_live_bag_auction_filter`
- `aedcf53`：`live_common/abtest` 新增 `AuctionInBagEnabled`
- `1b942d6a`：`live_pack` 对齐 bag regular auction 状态来源
- `c14c433b`：`live_pack` 修复 auction bag 双按钮文案字段判空
- `ba172e41` / `a9ea6711` / `fc86de40`：`live_pack` 持续修正 `auction_in_bag` 开关下的 handler / user_right / banner 行为

## 推荐 case

1. `case-101-auction-in-bag-exp`
   增加 `AuctionInBagEnabled` 实验并在购物袋链路分阶段接线

2. `case-102-auction-promotion-label-exp`
   增加 `UseAuctionPromotionLabel` 实验并控制 popcard + bag 的竞拍营销标签表达

3. `case-103-auction-success-state-exp`
   增加 `UseAuctionStatusSuccess` 实验并统一讲解卡 / bag / 兼容链路的成交态表达

## 使用建议

- 这组 case 更适合压 `plan` 和 `code`
- 如果压 `refine`，需要特别观察模型能不能正确抽出“多仓联动”“实验字段先加再消费”“多个表达层落点要统一”这三件事
- 如果压 `plan`，建议先按共享 [PLAN_TEMPLATE.md](/Users/bytedance/Work/tools/bytedance/coco-flow/docs/prds/PLAN_TEMPLATE.md) 输出执行方案，再拿 `diff.md` 做对照
- 建议先从 `case-102` 和 `case-103` 开始，这两个最像“根据实验修改竞拍表达层”的真实需求

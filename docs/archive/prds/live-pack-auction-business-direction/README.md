# live_pack auction 业务方向补充组

目标：补一组围绕竞拍业务方向的 PRD，用来测试 `coco-flow` 在多仓上下文下能不能先理解竞拍业务，再回到 `ttec/live_pack` 和 `oec/live_common` 做合理拆解。

这组 case 不是 `coco-flow` 自身需求。主业务仓是 `ttec/live_pack`，公共实验与公共 schema 能力优先考虑 `oec/live_common`。

## 这组 case 的共同特点

- 业务方向集中在直播间竞拍、竞拍进购物袋、surprise set、竞拍支付链路
- `live_pack` 负责 loader/filter/converter/DTO 组装
- `live_common` 负责公共 AB 字段、公共 schema 拼装或跨服务共享配置模型
- 尽量保持用户可见目标清楚，避免把 PRD 写成代码 diff

## 文档分工

- `prd.md`：写用户目标、范围、边界和验收
- `design.md`：写仓库职责、落点、依赖和风险
- `plan.md`：写执行切片、顺序和验证动作
- `diff.md`：写预期代码修改方向

## 推荐 case

1. `case-201-auction-payment-readiness-banner`
   竞拍进购物袋后，用户在竞拍 tab 能看到地址/支付/协议准备状态提示。

2. `case-202-surprise-set-item-pdp-schema`
   surprise set 详情页里的具体奖品可以直达带 SKU 的商品详情页。

3. `case-203-auction-promotion-labels`
   竞拍卡和购物袋竞拍商品展示运费、履约或权益类营销标签。

4. `case-204-auction-double-bid-cta`
   竞拍讲解卡和购物袋竞拍卡支持快捷出价与自定义出价双 CTA。

5. `case-205-auction-retry-payment-entry`
   竞拍支付失败后，用户能从竞拍卡或购物袋快速回到重试支付链路。

## 使用建议

- 需要单仓小改动：优先 `case-201`。
- 需要跨 `live_common` AB 字段和 `live_pack` 消费链路：优先 `case-203`、`case-204`、`case-205`。
- 需要考察 surprise set 的业务理解：优先 `case-202`。

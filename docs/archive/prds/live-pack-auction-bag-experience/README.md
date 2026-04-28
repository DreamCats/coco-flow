# live_pack auction bag 体验对照组

目标：补一组更像购物袋真实业务需求的单仓 case，用来测试 `coco-flow` 能不能先理解“购物袋该怎么打开、该展示什么”，再回到 `live_pack` 做最小落地。

这组 case 同样来自 `ttec/live_pack` 里已经发生过的真实改动，但整理时优先保留业务语义，弱化代码实现口吻。

## 这组 case 的共同特点

- 单仓可完成，主责任仓库就是 `ttec/live_pack`
- 都是购物袋里用户可直接感知的行为
- 主要落在 handler 或 auction list converter
- 验证成本低，适合做 `plan` 和 `code` 稳定性测试

## 文档分工

- `prd.md`：只写用户可见目标、范围、边界和验收
- `design.md`：写职责、落点、影响范围和风险
- `plan.md`：写执行切片、顺序和验证动作
- `diff.md`：写预期代码修改方向

## 推荐 case

1. `case-101-auction-only-default-tab`
   当购物袋当前页只有竞拍商品时，默认打开竞拍 tab，而不是 Buy Now。

2. `case-102-banner-without-pin`
   即使当前没有 pin 竞拍卡，只要购物袋里有竞拍商品且 banner 应展示，也要能正常展示 banner。

3. `case-103-starting-bid-price-align`
   购物袋里 regular auction 的预热态起拍价，需要和讲解卡保持一致。

## 使用建议

- `case-101` 最适合做首个 bag 测试，因为业务判断直接、改动面小、落点明确。
- `case-102` 适合测试系统能不能抓住“有 pin 优先，无 pin fallback”的业务规则。
- `case-103` 适合测试系统会不会把“展示口径对齐”误解成大范围价格重构。

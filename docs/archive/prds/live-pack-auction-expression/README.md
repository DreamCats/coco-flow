# live_pack auction 表达体验对照组

目标：补一组更像真实业务诉求的单仓 case，用来测试 `coco-flow` 在 `refine -> design -> plan -> code` 链路里，能不能先理解“用户看到什么变化”，再回到 `live_pack` 落具体实现。

这组 case 都来自 `ttec/live_pack` 里已经发生过的真实改动，但重新整理时刻意改写成业务需求表达，而不是直接把技术实现倒写成 PRD。

## 这组 case 的共同特点

- 单仓可完成，主责任仓库就是 `ttec/live_pack`
- 都是用户可感知的卡片表达变化
- 主要落在 `regular_auction_converter` / `surprise_set_auction_converter`
- 改动范围小，验证成本低，适合作为质量基线

## 文档分工

- `prd.md`：只描述业务目标、范围、边界和验收
- `design.md`：说明方案落点、职责边界和风险
- `plan.md`：拆执行切片、顺序和验证动作
- `diff.md`：给出预期代码改动方向

## 推荐 case

1. `case-001-interaction-copy-refresh`
   实验命中时，竞拍讲解卡把预热态和首拍态文案改得更直接，更鼓励用户出第一口价。

2. `case-002-auction-title-prefix`
   实验命中时，regular auction 标题前补 `Auction` 标识，提升用户对竞拍卡的辨识度。

3. `case-003-hide-zero-decimals`
   实验命中时，讲解卡里的整数金额不再展示尾部 `.00`，让价格更干净。

## 使用建议

- 先从 `case-002` 和 `case-003` 开始。
  这两个 case 的业务目标清楚、落点集中、标准答案稳定。
- `case-001` 适合测试系统能不能把“文案体验变化”拆成状态维度和竞拍类型维度。
- 如果要验证 `code`，优先比对 converter 层改动，不要把问题扩大到 BFF 或协议层。

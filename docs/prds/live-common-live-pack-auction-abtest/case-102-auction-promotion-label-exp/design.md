# Design

## 核心改造点

- 通过实验控制竞拍促销标签表达是否开启
- 普通竞拍讲解卡、购物袋和惊喜盲盒竞拍保持统一口径
- 实验未命中时，不展示新增的竞拍促销表达

## 仓库职责

- `oec/live_common/abtest`
  负责新增竞拍促销标签实验字段

- `ttec/live_pack`
  负责把实验字段接到讲解卡 promotion label、购物袋 promotion label、惊喜盲盒 promotion text

## 仓库依赖关系

- 依赖方向：`live_pack -> oec/live_common/abtest`
- 上游只提供字段定义，下游负责表达层落地
- 依赖点除了结构定义，还包括 `live_pack` 的依赖版本升级

## 影响范围与边界

- 影响范围：竞拍营销标签、竞拍促销文案、讲解卡与购物袋的一致性
- 不影响：价格、按钮、非竞拍商品标签
- 风险点：如果只改 regular auction，不改 surprise set 或 bag，会出现表达层分叉

## 人力评估

- 复杂度：中
- 预估人力：1 到 2 人天
- 适合作为多仓“实验字段 + 多表达层落点” case

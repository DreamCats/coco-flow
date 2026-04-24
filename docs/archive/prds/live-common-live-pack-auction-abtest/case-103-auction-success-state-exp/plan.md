# Plan

## 目标

- 接通普通竞拍成交态实验
- 统一讲解卡、购物袋和其他返回路径的成交态表达

## 前置依赖

- 必须先在 `oec/live_common/abtest` 增加 `UseAuctionStatusSuccess`
- 然后升级 `ttec/live_pack` 的 abtest 依赖版本
- 不依赖 TCC、IDL 或新配置

## 执行切片

### Slice 1

- 改动范围：上游实验字段定义
- 主要文件/模块：`oec/live_common/abtest/struct.go`
- 预期产出：新增 `UseAuctionStatusSuccess`
- 风险：字段语义不清会影响下游状态口径

### Slice 2

- 改动范围：下游依赖升级
- 主要文件/模块：`ttec/live_pack/go.mod`、`go.sum`
- 预期产出：`live_pack` 可安全读取新字段
- 风险：未升级依赖时无法进行后续接线

### Slice 3

- 改动范围：讲解卡主路径状态接线
- 主要文件/模块：普通竞拍状态判定模块
- 预期产出：实验命中时成交态展示“成功”
- 风险：若只改主路径，其他入口仍保留旧口径

### Slice 4

- 改动范围：购物袋与兼容返回路径
- 主要文件/模块：bag 状态映射、兼容路径状态逻辑
- 预期产出：多入口成交态一致
- 风险：漏改任一路径都会造成用户体验分裂

## 顺序与并行关系

- Slice 1 和 Slice 2 必须串行
- Slice 3 和 Slice 4 依赖 Slice 2，可并行
- 关键路径是“字段定义 -> 依赖升级 -> 多路径状态统一”

## 验证计划

- 上游验证：`cd /Users/bytedance/go/src/code.byted.org/oec/live_common/abtest && go test ./...`
- 下游验证：`cd /Users/bytedance/go/src/code.byted.org/ttec/live_pack && go test ./entities/loaders/auction_loaders ./entities/loaders/product_loaders`
- 重点确认：实验命中时多入口都是“成交成功”；未命中时仍保持原口径

## 回滚与兜底

- 若下游状态映射异常，可先整体回滚 `live_pack` 改动
- 上游实验字段可以保留，不影响未接线逻辑
- 不建议只回滚单一路径，否则会再次产生多入口不一致

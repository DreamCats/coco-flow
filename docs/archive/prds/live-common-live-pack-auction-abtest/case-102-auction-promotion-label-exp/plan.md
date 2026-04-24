# Plan

## 目标

- 接通竞拍营销标签实验
- 统一讲解卡、购物袋和惊喜盲盒竞拍的促销表达口径

## 前置依赖

- 必须先在 `oec/live_common/abtest` 增加 `UseAuctionPromotionLabel`
- 然后升级 `ttec/live_pack` 的 abtest 依赖版本
- 不依赖新的配置结构

## 执行切片

### Slice 1

- 改动范围：上游实验字段定义
- 主要文件/模块：`oec/live_common/abtest/struct.go`
- 预期产出：新增 `UseAuctionPromotionLabel`
- 风险：字段命名和语义不清会影响多个下游消费点

### Slice 2

- 改动范围：下游依赖升级
- 主要文件/模块：`ttec/live_pack/go.mod`、`go.sum`
- 预期产出：`live_pack` 可以读取新实验字段
- 风险：依赖版本不一致会阻塞后续改动

### Slice 3

- 改动范围：popcard 与 bag 的 promotion label 接线
- 主要文件/模块：auction placement / promotion 相关 loader
- 预期产出：实验命中时正常下发 promotion label
- 风险：只接 regular auction 会漏掉 bag 或其他入口

### Slice 4

- 改动范围：surprise set promotion text 接线
- 主要文件/模块：surprise set converter
- 预期产出：惊喜盲盒竞拍也按相同实验口径展示促销文案
- 风险：若只改 label 不改 promotion text，会造成表达层分叉

## 顺序与并行关系

- Slice 1 和 Slice 2 必须串行
- Slice 3 和 Slice 4 依赖 Slice 2，可并行
- 关键路径是“上游字段定义 -> 下游依赖升级 -> 多表达层统一接线”

## 验证计划

- 上游验证：`cd /Users/bytedance/go/src/code.byted.org/oec/live_common/abtest && go test ./...`
- 下游验证：`cd /Users/bytedance/go/src/code.byted.org/ttec/live_pack && go test ./entities/loaders/auction_loaders ./entities/converters/auction_converters`
- 重点确认：实验命中时讲解卡、bag、surprise set 一致展示；未命中时都不展示

## 回滚与兜底

- 若下游表达层异常，可先回滚 `live_pack` 消费逻辑
- 上游字段可保留，不影响未接线场景
- 不建议只回滚部分表达层切片，否则会造成多入口不一致

# Plan

## 目标

- 接通“竞拍进购物袋”实验开关
- 保证实验内外流量返回口径隔离

## 前置依赖

- 必须先在 `oec/live_common/abtest` 增加实验字段
- 然后升级 `ttec/live_pack` 的 abtest 依赖版本
- 不依赖额外 IDL 变更

## 执行切片

### Slice 1

- 改动范围：上游实验字段定义
- 主要文件/模块：`oec/live_common/abtest/struct.go`
- 预期产出：新增 `AuctionInBagEnabled`
- 风险：字段命名或结构位置不对，会影响下游引用

### Slice 2

- 改动范围：下游依赖升级
- 主要文件/模块：`ttec/live_pack/go.mod`、`go.sum`
- 预期产出：`live_pack` 能安全引用新字段
- 风险：若版本未升级，下游无法编译或拿不到字段

### Slice 3

- 改动范围：购物袋主入口接线
- 主要文件/模块：`get_live_bag_data`、`assemble`、`refresh` 相关入口
- 预期产出：实验未命中时不进入竞拍购物袋链路
- 风险：若只改部分入口，会出现接口口径不一致

### Slice 4

- 改动范围：辅助返回与衍生逻辑
- 主要文件/模块：room lite、user right 等相关逻辑
- 预期产出：实验外不混入竞拍数据
- 风险：若遗漏辅助路径，会有实验外残留数据

## 顺序与并行关系

- Slice 1 必须最先完成
- Slice 2 依赖 Slice 1
- Slice 3 和 Slice 4 依赖 Slice 2，可并行
- 关键路径是“字段定义 -> 依赖升级 -> 入口接线”

## 验证计划

- 上游验证：`cd /Users/bytedance/go/src/code.byted.org/oec/live_common/abtest && go test ./...`
- 下游验证：`cd /Users/bytedance/go/src/code.byted.org/ttec/live_pack && go test ./handlers ./entities/dto_builders ./entities/loaders/user_right`
- 重点确认：实验命中与未命中两种情况下，购物袋竞拍字段是否符合预期

## 回滚与兜底

- 若下游接线异常，可先回滚 `live_pack` 业务改动
- 若字段定义本身有问题，再回滚上游实验字段
- 允许只回滚下游，不必立即回滚上游字段

# Plan

## 目标

- 在实验命中时，为 surprise set 可获得奖品下发带 SKU 的 PDP schema
- 保证缺数据时安全回退

## 前置依赖

- `oec/live_common/abtest` 已包含 `need_surprise_set_item_auction_schema`
- `live_pack` 能获取 surprise set item 的 product_id、sku_id 和商品模型
- 不涉及 IDL 变更

## 执行切片

### Slice 1

- 改动范围：AB 字段确认与消费
- 主要文件/模块：`oec/live_common/abtest/struct.go`、`ttec/live_pack/entities/converters/auction_converters/surprise_auction_detail_converter.go`
- 预期产出：命中实验时才进入 schema 拼装
- 风险：字段默认值误开会扩大影响面

### Slice 2

- 改动范围：SKU 对应规格参数提取
- 主要文件/模块：`surprise_auction_detail_converter.go`
- 预期产出：根据 surprise set item 的 sku_id 找到 `checked_spec_ids`
- 风险：商品模型缺 SKU 信息时不能 panic

### Slice 3

- 改动范围：PDP schema 拼装与回退
- 主要文件/模块：`surprise_auction_detail_converter.go`、`utils/jump_schema.go`
- 预期产出：基于原 PDP schema 追加规格参数，失败时回退原 schema 或 nil
- 风险：schema 参数编码错误会影响前端跳转

## 顺序与并行关系

- 先确认 AB 字段和默认值
- 再实现 SKU 参数提取
- 最后拼 schema 并补回退

## 验证计划

- 最小验证：定向静态检查受影响 Go 文件，不跑全量 `go test`
- 人工确认：命中实验时 available item 有 schema
- 人工确认：点击后 PDP 选中对应 SKU
- 回归确认：未命中实验时响应结构不变化
- 回归确认：缺 PDP schema 或缺 SKU 信息时不下发坏 schema

## 回滚与兜底

- 可通过 AB 关闭该能力
- 如果 schema 异常，服务端回退为不下发奖品 schema

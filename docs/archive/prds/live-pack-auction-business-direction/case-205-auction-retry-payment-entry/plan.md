# Plan

## 目标

- 命中实验且支付失败可重试时，下发竞拍重试支付入口
- regular、surprise set、购物袋竞拍卡行为一致

## 前置依赖

- `oec/live_common/abtest` 有 `need_auction_retry_payment_schema`
- 竞拍服务返回 wallet schema、支付失败时间或可重试状态
- 前端能按现有 retry/status 配置展示入口

## 执行切片

### Slice 1

- 改动范围：实验字段确认
- 主要文件/模块：`oec/live_common/abtest/struct.go`
- 预期产出：字段默认关闭，命中后 `live_pack` 可读取
- 风险：字段命名与配置不一致

### Slice 2

- 改动范围：regular auction 重试 schema
- 主要文件/模块：`regular_auction_converter.go`
- 预期产出：支付失败可重试时下发 schema 或 status retry 配置
- 风险：schema 参数缺失导致支付页无法定位订单

### Slice 3

- 改动范围：surprise set 重试 schema
- 主要文件/模块：`surprise_set_auction_converter.go`
- 预期产出：surprise set 中拍支付失败也能跳转重试
- 风险：surprise set 需要额外带 surprise_set_id 或 auction_config_id

### Slice 4

- 改动范围：购物袋竞拍卡对齐
- 主要文件/模块：`converter_helpers.go`、`refresh_converter.go`
- 预期产出：购物袋 list/refresh 下发与 pop card 一致的重试入口
- 风险：refresh 增量中缺少必要上下文

## 顺序与并行关系

- 先确认 AB 字段
- 再处理 regular
- 再处理 surprise set
- 最后对齐购物袋 list/refresh

## 验证计划

- 最小验证：定向静态检查受影响 Go 文件，不跑全量 `go test`
- 人工确认：支付失败可重试、支付成功、未中拍、竞拍中四类状态
- 人工确认：regular 与 surprise set schema 参数完整
- 回归确认：未命中实验不下发重试入口

## 回滚与兜底

- 可通过 AB 关闭重试入口
- schema 拼装失败时不展示入口，保留原完成态展示

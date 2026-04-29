# Plan

## 目标

- 命中实验时，为竞拍卡和购物袋竞拍卡下发双 CTA 信息
- 保持 regular auction 与 surprise set 行为一致

## 前置依赖

- `oec/live_common/abtest` 有 `pincard_double_bid_btn`
- `live_pack` product switch 能读取 `NeedAuctionDoubleBtns`
- 前端已支持 `PincardDisplayDoubleBtns`

## 执行切片

### Slice 1

- 改动范围：实验字段到 product switch 的映射确认
- 主要文件/模块：`oec/live_common/abtest/struct.go`、`ttec/live_pack` product switch 相关构建逻辑
- 预期产出：命中实验时 `GetNeedAuctionDoubleBtns()` 为 true
- 风险：字段只在部分请求路径生效

### Slice 2

- 改动范围：pop card 双 CTA 下发
- 主要文件/模块：`regular_auction_converter.go`、`surprise_set_auction_converter.go`
- 预期产出：regular 和 surprise set 都下发 `PincardDisplayDoubleBtns`
- 风险：两种竞拍类型文案不一致

### Slice 3

- 改动范围：购物袋竞拍卡对齐
- 主要文件/模块：`converter_helpers.go`
- 预期产出：bag regular 和 bag surprise set 也下发双 CTA 配置
- 风险：购物袋场景缺少某些面板字段时前端展示异常

### Slice 4

- 改动范围：预热态文案处理
- 主要文件/模块：`converter_helpers.go`、`regular_auction_converter.go`、`surprise_set_auction_converter.go`
- 预期产出：预热态不展示误导性出价按钮文案
- 风险：清理过度导致开拍态按钮文案缺失

## 顺序与并行关系

- 先确认实验字段映射
- 再改 pop card
- 再改购物袋
- 最后统一检查预热态文案

## 验证计划

- 最小验证：定向静态检查受影响 Go 文件，不跑全量 `go test`
- 人工确认：regular auction 命中/未命中实验
- 人工确认：surprise set 命中/未命中实验
- 人工确认：预热态、开拍无人出价、已有出价三种状态
- 回归确认：自定义出价面板字段仍完整

## 回滚与兜底

- 可通过 AB 关闭双 CTA
- 若购物袋前端承接异常，可先只关闭 bag 场景下发

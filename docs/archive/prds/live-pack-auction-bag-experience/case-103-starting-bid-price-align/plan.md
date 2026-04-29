# Plan

## 目标

- 让购物袋里 regular auction 的预热态起拍价与讲解卡一致
- 保证只改 `start_bid_price` 这一项，不扩大影响范围

## 前置依赖

- 依赖当前竞拍配置可提供 `StartingBidPrice`
- 不依赖新的协议、配置结构或发布窗口

## 执行切片

### Slice 1

- 改动范围：regular auction 起拍价 helper
- 主要文件/模块：`converter_helpers.go`
- 预期产出：`start_bid_price` 改为读取竞拍配置中的起拍价
- 风险：若 currency 或空值处理不完整，可能返回空价格

### Slice 2

- 改动范围：调用侧接线
- 主要文件/模块：bag regular auction data builder
- 预期产出：regular auction `AuctionData.StartBidPrice` 走新 helper
- 风险：若只改 helper 不改调用参数，仍拿不到配置起拍价

## 顺序与并行关系

- 先确定起拍价新来源
- 再调整 builder 调用
- 关键路径是“只改 StartBidPrice，不改其他价格字段”

## 验证计划

- 最小验证：`go test ./entities/converters/auction_converters`
- 重点确认：regular auction 预热态起拍价与讲解卡一致
- 回归确认：当前最高价、下一口价、自定义出价不变

## 回滚与兜底

- 若起拍价展示异常，可回滚 `start_bid_price` 新来源逻辑
- 保留其他价格字段现有实现
- 不需要额外降级开关

# Plan

## 目标

- 在命中实验时，让竞拍讲解卡的预热态和首拍态文案更偏行动引导
- 保证 regular auction 和 surprise set 的表达风格一致，但不混淆各自玩法语义

## 前置依赖

- 依赖现有实验字段已可读取
- 不依赖新的协议、配置结构或发布窗口

## 执行切片

### Slice 1

- 改动范围：regular auction 文案覆盖
- 主要文件/模块：`regular_auction_converter`
- 预期产出：预热态与无人出价开场态切到实验文案
- 风险：若状态映射选错，会误伤有人出价或结束态

### Slice 2

- 改动范围：surprise set 文案覆盖
- 主要文件/模块：`surprise_set_auction_converter`
- 预期产出：预热态与首拍态切到对应实验文案
- 风险：若直接复用 regular 文案，可能丢失 surprise 玩法语义

### Slice 3

- 改动范围：共享文案 key 与回退逻辑
- 主要文件/模块：`auction_converters/const.go`
- 预期产出：共享文案 key 收敛，未命中实验时仍走原逻辑
- 风险：若 key 或 fallback 处理不当，会出现空文案

## 顺序与并行关系

- 先确定实验命中后要覆盖哪些状态
- Slice 1 和 Slice 2 可并行
- Slice 3 可先完成，也可作为两边共享前置
- 关键路径是状态覆盖矩阵是否完整

## 验证计划

- 最小验证：`go test ./entities/converters/auction_converters`
- 重点确认：预热态、无人出价开场态的文案变化符合实验要求
- 回归确认：实验未命中时所有现有文案不变

## 回滚与兜底

- 若实验文案异常，可先整体回滚实验覆盖逻辑
- 保留原有状态判定和非实验链路
- 不需要额外降级开关

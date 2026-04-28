# Plan

## 目标

- 在命中实验时，让讲解卡里的整数竞拍金额展示更简洁
- 保证非整数金额和非讲解卡链路不受影响

## 前置依赖

- 依赖现有实验字段可读取
- 不依赖新的协议、配置结构或价格字段

## 执行切片

### Slice 1

- 改动范围：regular auction 价格展示裁剪
- 主要文件/模块：`regular_auction_converter`
- 预期产出：regular auction 讲解卡整数金额去掉 `.00`
- 风险：若直接改通用 formatter，会扩大影响面

### Slice 2

- 改动范围：surprise set 价格展示裁剪
- 主要文件/模块：`surprise_set_auction_converter`
- 预期产出：surprise set 讲解卡整数金额去掉 `.00`
- 风险：若只改 regular，会造成不同竞拍类型展示不一致

### Slice 3

- 改动范围：共享裁剪 helper
- 主要文件/模块：converter 内部 helper
- 预期产出：同一套实验命中判断和整数裁剪逻辑
- 风险：若 raw price 解析失败未处理，可能出现展示异常

## 顺序与并行关系

- 先确定裁剪只发生在讲解卡 converter 层
- Slice 1 和 Slice 2 可并行
- Slice 3 可先抽出，也可在任一侧稳定后复用
- 关键路径是“只改展示，不改通用格式化层”

## 验证计划

- 最小验证：`go test ./entities/converters/auction_converters`
- 重点确认：整数金额去掉 `.00`，非整数金额保持原样
- 回归确认：购物袋等其他价格链路不受影响

## 回滚与兜底

- 若价格展示异常，可整体回滚讲解卡裁剪逻辑
- 保留原有通用格式化逻辑
- 不需要额外降级开关

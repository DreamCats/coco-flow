# Plan

## 目标

- 让购物袋 banner 在无 pin 场景下仍能稳定展示
- 保持“有 pin 优先、无 pin fallback”的业务规则清晰可控

## 前置依赖

- 依赖当前竞拍列表结果能拿到顺序稳定的竞拍商品
- 不依赖新的协议、配置或发布窗口

## 执行切片

### Slice 1

- 改动范围：pin 竞拍商品优先逻辑保留
- 主要文件/模块：`list_converter`
- 预期产出：有 pin 时继续使用 pin 对应 config
- 风险：若优先级处理错误，可能破坏当前有 pin 场景

### Slice 2

- 改动范围：无 pin fallback 逻辑
- 主要文件/模块：`list_converter`
- 预期产出：无 pin 时回退到列表第一个竞拍商品
- 风险：若列表为空或 config 未找到，可能生成无效 banner

## 顺序与并行关系

- 先保住有 pin 优先逻辑
- 再补无 pin fallback 逻辑
- 关键路径是 fallback 选择和 schema 参数是否匹配同一商品

## 验证计划

- 最小验证：`go test ./entities/converters/auction_converters`
- 重点确认：无 pin 且有竞拍商品时，banner 仍能返回
- 回归确认：有 pin 场景仍优先使用 pin 商品

## 回滚与兜底

- 若 fallback banner 绑定错误，可先回滚无 pin 分支
- 保留现有有 pin 场景行为
- 不需要额外降级开关

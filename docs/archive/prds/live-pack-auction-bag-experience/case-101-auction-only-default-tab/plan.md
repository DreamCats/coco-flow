# Plan

## 目标

- 让购物袋默认 tab 与当前页真实商品内容保持一致
- 保证 assemble 和 data 两条返回路径行为统一

## 前置依赖

- 不依赖新的配置、协议或发布窗口
- 依赖当前响应层已能区分 Buy Now 商品和竞拍商品是否存在

## 执行切片

### Slice 1

- 改动范围：assemble 返回路径兜底逻辑
- 主要文件/模块：`get_live_bag_assemble_handler`
- 预期产出：只有竞拍商品时默认打开 Auction
- 风险：若遗漏 Buy Now 为空判断，会误伤混合场景

### Slice 2

- 改动范围：data 返回路径兜底逻辑
- 主要文件/模块：`get_live_bag_data_handler`
- 预期产出：data 返回路径与 assemble 行为一致
- 风险：若只改一条路径，会出现接口行为分叉

## 顺序与并行关系

- 两个切片可并行
- 关键路径是两条返回路径的兜底条件完全一致

## 验证计划

- 最小验证：`go test ./handlers`
- 重点确认：只有竞拍商品时默认打开 Auction
- 回归确认：有 Buy Now 商品时仍默认打开 Buy Now

## 回滚与兜底

- 若默认 tab 出现异常，可单独回滚对应 handler 改动
- 不涉及底层竞拍数据引擎回滚
- 不需要额外降级开关

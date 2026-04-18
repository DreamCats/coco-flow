# Plan

## 目标

- 在 `live_shopapi` API 层透出购物袋默认打开 Tab
- 不改 `live_pack` RPC 协议

## 前置依赖

- 需要确认 `live_shopapi` 当前 API Proto 定义位置和字段编号策略
- 需要人工或平台流程生成新的 API 代码
- 不依赖 `live_pack` 新版本 RPC 产物

## 执行切片

### Slice 1

- 改动范围：Proto 协议草案
- 主要文件/模块：`live_shopapi` API 协议定义
- 预期产出：新增默认 Tab 字段定义
- 风险：字段编号或命名不合规会阻塞平台生成

### Slice 2

- 改动范围：平台生成与依赖更新
- 主要文件/模块：HTTP IDL / 生成产物
- 预期产出：新的 pb 生成物可供 `live_shopapi` 编译使用
- 风险：`blocked_by_platform`

### Slice 3

- 改动范围：API 转换层接线
- 主要文件/模块：购物袋响应组装与格式转换
- 预期产出：已有默认 Tab 值被稳定写入 API 字段
- 风险：如果只加协议不补转换层，前端仍拿不到值

## 顺序与并行关系

- Slice 1 必须最先完成
- Slice 2 依赖 Slice 1
- Slice 3 依赖 Slice 2
- 关键路径是 Proto 生成物回到仓库后才能继续接线

## 验证计划

- 验证 Proto 生成产物是否可编译
- 验证购物袋 API 响应中是否新增默认 Tab 字段
- 回归确认：商品和竞拍列表内容不变

## 回滚与兜底

- 若 API 接线异常，可先回滚 `live_shopapi` 业务改动
- 若协议本身有问题，再回滚 Proto 字段
- 若前端尚未消费，可暂时保留字段不使用

## Handoff Checklist

- 协议 owner 确认字段命名、编号、兼容性
- 人工触发 API 协议生成流程
- 生成产物完成后通知业务接线
- 前端确认字段消费方式

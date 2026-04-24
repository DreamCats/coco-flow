# Plan

## 目标

- 在竞拍讲解卡链路中新增扩展展示字段
- 完成 `live_pack RPC -> live_shopapi API` 的双协议透传

## 前置依赖

- 必须明确字段最终展示对象与字段语义
- 必须确认字段先在哪一层产生
- 必须有人触发：
  - RPC 协议生成流程
  - API 协议生成流程

## 执行切片

### Slice 1

- 改动范围：Thrift / RPC 变更草案
- 主要文件/模块：`live_pack` RPC 协议定义
- 预期产出：新增 RPC 字段定义
- 风险：字段编号、optional 语义、兼容性不清会阻塞后续所有步骤

### Slice 2

- 改动范围：RPC 生成产物
- 主要文件/模块：平台生成 `rpcv2_ttec_live_pack`
- 预期产出：`live_shopapi` 可升级到带新字段的 RPC 依赖
- 风险：`blocked_by_platform`

### Slice 3

- 改动范围：`live_pack` 业务接线
- 主要文件/模块：竞拍讲解卡返回逻辑
- 预期产出：RPC 返回中真实填充新字段
- 风险：如果只改协议不填值，下游拿到空字段

### Slice 4

- 改动范围：API Proto 变更草案
- 主要文件/模块：`live_shopapi` API 协议定义
- 预期产出：新增对前端可见字段
- 风险：字段命名和 API 兼容策略需要协议 owner 确认

### Slice 5

- 改动范围：API 生成产物
- 主要文件/模块：平台生成新的 pb/http 产物
- 预期产出：`live_shopapi` 可编译引用新字段
- 风险：`blocked_by_platform`

### Slice 6

- 改动范围：`live_shopapi` 转换层接线
- 主要文件/模块：handler / service / formatter / converter
- 预期产出：RPC 新字段被稳定透传到 API
- 风险：若格式转换遗漏，前端仍拿不到值

## 顺序与并行关系

- Slice 1 -> Slice 2 -> Slice 3 必须串行
- Slice 4 最早可在 Slice 1 后并行起草，但真正接线依赖 Slice 5
- Slice 6 同时依赖 Slice 3 和 Slice 5
- 关键路径是：RPC 字段定义 -> 生成物 -> live_pack 填值 -> API 字段定义 -> 生成物 -> live_shopapi 透传

## 验证计划

- 验证 RPC 生成物是否可编译
- 验证 `live_pack` 返回是否已填充新字段
- 验证 `live_shopapi` API 是否稳定透出该字段
- 验证前端消费场景下原有字段不受影响

## 回滚与兜底

- 如果 `live_shopapi` 接线异常，可先只回滚 API 层业务逻辑
- 如果 `live_pack` 填值逻辑异常，可回滚业务接线，但保留协议字段
- 若协议已发布但未消费，可允许字段先空跑一段时间

## Handoff Checklist

- 协议 owner 确认 RPC 字段编号、兼容策略
- 人工触发 RPC 生成流程
- 生成物 ready 后，业务侧升级 `rpcv2_ttec_live_pack`
- 协议 owner 确认 API 字段命名、兼容策略
- 人工触发 API 生成流程
- 前端确认字段消费方式与灰度方案

# Plan

## 目标

- 在竞拍讲解卡 RPC 链路中新增内部判断标记
- 让 `live_shopapi` 能在服务端消费该标记
- 不新增前端 API 字段

## 前置依赖

- 必须先明确该字段只用于服务端，不透出到前端
- 必须先完成 `live_pack` RPC 协议定义
- 必须有人触发 RPC 生成流程

## 执行切片

### Slice 1

- 改动范围：Thrift / RPC 变更草案
- 主要文件/模块：`live_pack` RPC 协议定义
- 预期产出：新增内部判断标记字段
- 风险：字段命名或兼容策略不明确会阻塞后续步骤

### Slice 2

- 改动范围：RPC 生成产物
- 主要文件/模块：平台生成 `rpcv2_ttec_live_pack`
- 预期产出：`live_shopapi` 可升级新 RPC 依赖
- 风险：`blocked_by_platform`

### Slice 3

- 改动范围：`live_pack` 业务填值
- 主要文件/模块：竞拍讲解卡 RPC 返回逻辑
- 预期产出：返回中稳定带出新字段
- 风险：只改协议不填值，会导致上层永远拿空值

### Slice 4

- 改动范围：`live_shopapi` 服务端消费
- 主要文件/模块：live_pack service / formatter / handler 内部逻辑
- 预期产出：上层服务可以利用该标记做服务端判断
- 风险：若消费点选错，字段无法产生实际效果

## 顺序与并行关系

- Slice 1 -> Slice 2 -> Slice 3 -> Slice 4 基本必须串行
- 关键路径是 RPC 字段定义和生成物返回
- 本 case 不存在 API Proto 分支，因此比 `Proto + Thrift` 简单一层

## 验证计划

- 验证 RPC 生成物是否可编译
- 验证 `live_pack` RPC 返回中是否已填充新字段
- 验证 `live_shopapi` 服务端是否能读取并使用该字段
- 回归确认：前端 API 结构无变化

## 回滚与兜底

- 若上层消费逻辑异常，可先回滚 `live_shopapi` 业务逻辑
- 若字段填值有问题，可回滚 `live_pack` 业务接线
- 若协议已发布但暂未消费，可允许字段空跑

## Handoff Checklist

- 协议 owner 确认字段编号、兼容策略
- 人工触发 RPC 生成流程
- 生成物 ready 后，升级 `live_shopapi` RPC 依赖
- 确认该字段不会误透给前端 API

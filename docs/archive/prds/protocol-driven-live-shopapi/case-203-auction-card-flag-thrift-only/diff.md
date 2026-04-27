# 预期标准答案

这类 case 的标准答案由 4 部分组成：

## 1. RPC 协议变更

- `live_pack` 侧新增 Thrift / RPC 字段
- 生成新的 `rpcv2_ttec_live_pack`

## 2. RPC 业务接线

- `live_pack` 在竞拍讲解卡返回中填充该字段

## 3. 服务端消费

- `live_shopapi` 在服务层读取该字段
- 用于内部判断、埋点或兼容分流

## 4. 回归结果

- 前端 API 结构保持不变

## 说明

这是一个 `Thrift-only` case，主要用于说明：

- 即使前端 API 不变
- 只要服务间协议要新增字段
- 依然属于协议驱动型需求

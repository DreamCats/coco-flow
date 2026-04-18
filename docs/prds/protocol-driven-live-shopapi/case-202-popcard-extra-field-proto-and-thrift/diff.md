# 预期标准答案

这类 case 的标准答案由 5 部分组成，而不是单一 diff：

## 1. RPC 协议变更

- `live_pack` 侧新增 Thrift / RPC 字段
- 生成新的 `rpcv2_ttec_live_pack`

## 2. RPC 业务接线

- `live_pack` 在竞拍讲解卡返回里填充该字段

## 3. API 协议变更

- `live_shopapi` 新增对应 Proto 字段
- 完成 API 生成物更新

## 4. API 转换层接线

- `live_shopapi` handler / service / converter 完成透传

## 5. 联调验证

- 确认前端最终能稳定拿到新字段

## 说明

这是一个真正的 `Proto + Thrift` 协议驱动型 case，主要用来检验系统能否：

- 识别双协议需求
- 明确平台阻塞点
- 正确拆解人机协作步骤

# protocol-driven live_shopapi + live_pack 对照组

目标：补一组适合汇报和中后期演进的“协议驱动型需求” case，用来验证系统能否在 `refine / design / plan` 阶段正确识别：

- 这是协议变更需求，而不是普通代码需求
- 涉及哪一层协议：Proto / Thrift / both
- 哪些步骤必须人工触发平台
- 哪些仓库需要等待生成物后再接线

## 链路定位

在这组 case 里，典型链路是：

```text
Client / Frontend
  -> oec/live_shopapi (Proto / API)
      -> ttec/live_pack (Thrift / RPC)
```

其中：

- `oec/live_shopapi` 负责对前端暴露 API 协议
- `ttec/live_pack` 负责讲解卡、购物袋等 RPC 能力

## 推荐 case

1. `case-201-default-bag-tab-proto-only`
   前端需要购物袋默认 tab 字段，但 `live_pack` 已有数据，只是 `live_shopapi` API 未透出

2. `case-202-popcard-extra-field-proto-and-thrift`
   前端需要竞拍讲解卡新增字段，`live_pack` RPC 侧当前没有，需要 Thrift + Proto 双协议联动

3. `case-203-auction-card-flag-thrift-only`
   `live_shopapi` 需要一个新的竞拍卡内部判断字段，但只用于服务端逻辑，不对前端新增 API 字段

## 使用建议

- 这组 case 更适合拿来向老板汇报“为什么协议驱动型需求难”
- 也适合测试系统能否正确输出：
  - `blocked_by_human`
  - `blocked_by_platform`
  - `generated_artifacts`
  - `handoff checklist`

- 建议先从 `case-201` 开始，作为 Proto-only 基线；再用 `case-202` 展示真正困难的 `Proto + Thrift` 场景
- `case-203` 适合作为中间档：需要改协议，但不需要改前端 API

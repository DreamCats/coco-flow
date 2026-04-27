# 预期标准答案

这类 case 的标准答案不以“单个代码 diff”作为唯一结果，而是以 3 段产物组成：

## 1. 协议变更

- `live_shopapi` API Proto 新增 `default_bag_tab`
- 完成平台生成

## 2. 业务接线

- `live_shopapi` 购物袋 handler / service / converter 把已有默认 Tab 写入新字段

## 3. 验证结果

- 前端可直接消费 `default_bag_tab`
- 不再自行兜底默认打开页签

## 说明

这是一个 `Proto-only` case，主要用于说明：

- 即使 `live_pack` 已有数据
- 只要 API 协议没透出
- 也仍然属于协议驱动型需求

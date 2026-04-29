# Plan

## 目标

- 让购物袋竞拍 tab 基于用户准备状态展示 `AuctionInfoBanner`
- 保证 banner 与 pin 竞拍卡解耦

## 前置依赖

- 依赖 `UserSignInfoLoader` 已能返回签约、地址、支付状态
- 依赖 `auction_agreement` TCC 提供协议和地址支付 schema
- 不涉及 `live_common` 改动

## 执行切片

### Slice 1

- 改动范围：banner 生成条件
- 主要文件/模块：`entities/converters/auction_converters/list_converter.go`
- 预期产出：只要有竞拍商品和 user sign 结果，就尝试生成 banner
- 风险：无竞拍商品时误展示 banner

### Slice 2

- 改动范围：schema 拼装兜底
- 主要文件/模块：`entities/converters/auction_converters/converter_helpers.go`
- 预期产出：协议 schema 和地址支付 schema 都带 room_id 与必要埋点
- 风险：TCC schema 为空时需要安全降级

### Slice 3

- 改动范围：assemble/list 返回一致性
- 主要文件/模块：`handlers/get_live_bag_assemble_handler.go`、`handlers/get_live_bag_data_handler.go`
- 预期产出：两条购物袋返回路径都能透出 banner
- 风险：只改 list converter 但 handler 聚合遗漏

## 顺序与并行关系

- 先确认 `UserSignInfoLoader` 输出语义
- 再调整 converter 组装条件
- 最后检查 handler 聚合字段

## 验证计划

- 最小验证：只做受影响目录静态检查或定向编译，不跑全量 `go test`
- 人工确认：未签约、缺地址、缺支付、已完成四种用户状态
- 人工确认：有 pin 和无 pin 两种竞拍 tab 场景
- 回归确认：无竞拍商品时不展示 banner

## 回滚与兜底

- 若 banner 误展示，可回滚 converter 条件
- schema 为空时保持 banner 不跳转或不展示，避免前端跳坏链路

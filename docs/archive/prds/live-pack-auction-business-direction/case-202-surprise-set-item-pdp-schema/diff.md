# Diff

## 预期代码改动

- 在 `oec/live_common/abtest/struct.go` 确认或新增 `need_surprise_set_item_auction_schema` 字段。
- 在 `ttec/live_pack/entities/converters/auction_converters/surprise_auction_detail_converter.go` 中：
  - 命中实验时为 available item 构造 schema
  - 从商品 SKU 信息提取 `checked_spec_ids`
  - 使用统一 schema 拼装工具追加参数
  - 缺数据或拼装失败时安全回退

## 不应出现的改动

- 不应改变 surprise set 中奖逻辑
- 不应改变已售出奖品列表
- 不应强制所有流量下发 schema
- 不应新增前端协议字段

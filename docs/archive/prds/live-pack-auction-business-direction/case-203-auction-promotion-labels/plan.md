# Plan

## 目标

- 在实验命中时，为竞拍卡和购物袋竞拍卡补齐营销标签
- surprise set 奖品只展示白名单标签

## 前置依赖

- `oec/live_common/abtest` 有 `use_auction_promotion_label`
- 商品模型中已有 promotion labels
- 前端已能渲染 `PromotionLabels`

## 执行切片

### Slice 1

- 改动范围：AB 字段与默认值确认
- 主要文件/模块：`oec/live_common/abtest/struct.go`
- 预期产出：实验字段默认关闭，字段名与线上配置一致
- 风险：字段误配置会导致全量展示

### Slice 2

- 改动范围：pop card 标签提取
- 主要文件/模块：`entities/loaders/auction_loaders/auction_placement_labels_loader.go`
- 预期产出：命中实验时从商品模型提取 promotion labels
- 风险：商品模型为空时不能影响竞拍卡生成

### Slice 3

- 改动范围：购物袋标签批量提取
- 主要文件/模块：`entities/loaders/auction_loaders/bag_auction_placement_labels_loader.go`
- 预期产出：list 和 refresh 都能拿到竞拍商品标签
- 风险：批量遍历 surprise set item 时不要漏掉奖品 product_id

### Slice 4

- 改动范围：converter 写入与 surprise set 白名单
- 主要文件/模块：`regular_auction_converter.go`、`converter_helpers.go`、`surprise_auction_detail_converter.go`
- 预期产出：regular 直接透出标签，surprise set detail 只透出运费/履约类标签
- 风险：标签白名单过宽会造成误导

## 顺序与并行关系

- 先确认 AB 字段
- 再补 loader 标签提取
- 最后在 converter 写入并处理 surprise set 过滤

## 验证计划

- 最小验证：定向静态检查受影响 Go 文件，不跑全量 `go test`
- 人工确认：实验命中和未命中两组响应差异
- 人工确认：regular auction、surprise set、购物袋 list、购物袋 refresh 四个场景
- 回归确认：无标签商品不展示空结构

## 回滚与兜底

- 可通过 AB 关闭展示
- 如果标签来源异常，converter 层空数组或 nil 回退，不影响竞拍主链路

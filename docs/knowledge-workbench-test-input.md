# Knowledge Workbench Test Input

本文记录一组可直接复制到知识工作台里的测试输入，用于验证 `竞拍讲解卡（popcard auction）系统链路` 的知识生成效果。

## 完整版

```json
{
  "title": "竞拍讲解卡系统链路",
  "description": "竞拍讲解卡（popcard auction）系统链路。重点关注同步进房、异步预览/进房前链路、竞拍卡数据编排、前端/BFF 形态转换，以及各仓库在整条链路中的职责分工。",
  "selected_paths": [
    "/Users/bytedance/go/src/code.byted.org/oec/live_shop",
    "/Users/bytedance/go/src/code.byted.org/oec/live_shopapi",
    "/Users/bytedance/go/src/code.byted.org/ttec/live_pack",
    "/Users/bytedance/go/src/code.byted.org/oec/live_common",
    "/Users/bytedance/go/src/code.byted.org/ttec/content_live_bff_lib"
  ],
  "repos": [
    "/Users/bytedance/go/src/code.byted.org/oec/live_shop",
    "/Users/bytedance/go/src/code.byted.org/oec/live_shopapi",
    "/Users/bytedance/go/src/code.byted.org/ttec/live_pack",
    "/Users/bytedance/go/src/code.byted.org/oec/live_common",
    "/Users/bytedance/go/src/code.byted.org/ttec/content_live_bff_lib"
  ],
  "kinds": [
    "flow",
    "domain"
  ],
  "notes": "这是知识工作台测试样本。希望产物偏系统级认知，不要写成实现细节清单。重点回答：1）这是什么业务方向；2）主链路怎么走；3）各仓库分别承担什么职责；4）哪些信息还需要待确认。不要产出 rule。"
}
```

## 最小闭环版

```json
{
  "title": "竞拍讲解卡系统链路",
  "description": "竞拍讲解卡（popcard auction）系统链路。",
  "selected_paths": [
    "/Users/bytedance/go/src/code.byted.org/oec/live_shop",
    "/Users/bytedance/go/src/code.byted.org/oec/live_shopapi",
    "/Users/bytedance/go/src/code.byted.org/ttec/live_pack",
    "/Users/bytedance/go/src/code.byted.org/oec/live_common",
    "/Users/bytedance/go/src/code.byted.org/ttec/content_live_bff_lib"
  ],
  "repos": [
    "/Users/bytedance/go/src/code.byted.org/oec/live_shop",
    "/Users/bytedance/go/src/code.byted.org/oec/live_shopapi",
    "/Users/bytedance/go/src/code.byted.org/ttec/live_pack",
    "/Users/bytedance/go/src/code.byted.org/oec/live_common",
    "/Users/bytedance/go/src/code.byted.org/ttec/content_live_bff_lib"
  ],
  "kinds": [
    "flow"
  ],
  "notes": "先只生成 flow，观察系统是否能正确识别主链路和各仓库职责。"
}
```

## 建议

- 先跑一次 `flow`，观察系统是否能稳定识别主链路和仓库职责。
- 再跑一次 `flow + domain`，观察 `domain` 是否真的起到补充作用，而不是重复 `flow`。
- 当前不建议把 `rule` 纳入默认测试输入。

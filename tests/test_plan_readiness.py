from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from coco_flow.services.tasks.readiness import build_plan_readiness_score


class PlanReadinessScoreTest(unittest.TestCase):
    def test_build_score_rewards_executable_cross_repo_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            write_readiness_fixture(task_dir)

            payload = build_plan_readiness_score(task_dir, "task-1")

            self.assertEqual(payload["status"], "ready")
            self.assertAlmostEqual(payload["score"], 97.694, places=3)
            sections = {section["id"]: section for section in payload["sections"]}
            self.assertEqual(sections["GateCorrectness"]["score"], 1.0)
            dependency = find_child(sections["PlanExecutability"], "DependencyCorrectness")
            self.assertEqual(dependency["score"], 1.0)

    def test_plan_sync_mismatch_reduces_gate_correctness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            write_readiness_fixture(task_dir)
            write_json(task_dir / "plan-sync.json", {"synced": False, "changed_artifact": "plan.md"})

            payload = build_plan_readiness_score(task_dir, "task-1")

            sections = {section["id"]: section for section in payload["sections"]}
            self.assertLess(sections["GateCorrectness"]["score"], 1.0)
            self.assertIn("Plan 未同步但 gate 允许进入 Code", payload["recommendations"])


def write_readiness_fixture(task_dir: Path) -> None:
    (task_dir / "prd-refined.md").write_text(
        """# 需求确认书

## 验收标准
- 命中实验时，regular auction 标题前增加本地化的 `Auction` 标识。
- 标题前缀与原标题之间有稳定分隔，整体可读性不受影响。
- 如果本地化标识取值异常为空，则回退为原标题，不出现空前缀或异常连接符。
- 未命中实验时，标题保持现有线上逻辑不变。

## 边界与非目标
- 不改 surprise set 和 temporary listing
- 不改购物袋标题
- 不改价格
- 不改按钮
""",
        encoding="utf-8",
    )
    (task_dir / "design.md").write_text(
        """# Design

## live_pack
- 职责判断：需要代码改造。
- 命中实验时，regular auction 标题前增加本地化的 `Auction` 标识。
- 标题前缀与原标题之间有稳定分隔，整体可读性不受影响。
- 如果本地化标识取值异常为空，则回退为原标题，不出现空前缀或异常连接符。
- 未命中实验时，标题保持现有线上逻辑不变。
- 不改 surprise set 和 temporary listing
- 不改购物袋标题
- 不改价格
- 不改按钮

## live_common
- 职责判断：需要代码改造。
- 新增实验字段 RegularAuctionTitleAuctionLabelEnabled bool（或类似命名，最终字段名待确认）。
- 已确认：Starling key 可以暂时用字符串占位符。
""",
        encoding="utf-8",
    )
    (task_dir / "plan.md").write_text(
        """# Plan

### W1 [live_pack] 接入实验字段并更新业务逻辑
- repo: `live_pack`
- specific_steps:
  - 读取实验字段 rc.GetAbParam().TTECContent.RegularAuctionTitleAuctionLabelEnabled
  - 命中实验时，在原标题前拼接本地化的 "Auction" 标识
  - 使用稳定分隔符（如空格）分隔前缀与原标题
  - 若本地化标识取值为空，回退为原标题
  - 未命中实验时，保持现有逻辑不变
  - 参考已有实验字段的使用方式（如 needNoImgModeOptimization）实现
  - 新增或复用现有 Starling key 用于本地化的 "Auction" 标识
  - 升级 code.byted.org/oec/live_common/abtest 依赖到包含跨仓契约字段的版本

### W2 [live_common] 新增或更新实验字段契约
- repo: `live_common`
- specific_steps:
  - 在 abtest/struct.go 的 TTECContent 结构体中新增实验字段 RegularAuctionTitleAuctionLabelEnabled bool
  - 添加 json tag
  - 字段默认值 false 保持线上逻辑不变
""",
        encoding="utf-8",
    )
    write_json(task_dir / "repos.json", {"repos": [{"id": "live_pack"}, {"id": "live_common"}]})
    write_json(
        task_dir / "design-contracts.json",
        {
            "contracts": [
                {
                    "id": "C1",
                    "type": "ab_experiment_field",
                    "producer_repo": "live_common",
                    "consumer_repo": "live_pack",
                    "consumer_access": "rc.GetAbParam().TTECContent.RegularAuctionTitleAuctionLabelEnabled",
                    "compatibility": "默认值必须保持线上原逻辑",
                }
            ]
        },
    )
    write_json(
        task_dir / "plan-work-items.json",
        {
            "work_items": [
                {
                    "id": "W1",
                    "repo_id": "live_pack",
                    "change_scope": ["entities/converters/auction_converters/regular_auction_converter.go", "go.mod", "go.sum"],
                    "specific_steps": [
                        "读取实验字段 rc.GetAbParam().TTECContent.RegularAuctionTitleAuctionLabelEnabled",
                        "命中实验时，在原标题前拼接本地化的 \"Auction\" 标识",
                        "使用稳定分隔符（如空格）分隔前缀与原标题",
                        "若本地化标识取值为空，回退为原标题",
                        "未命中实验时，保持现有逻辑不变",
                        "参考已有实验字段的使用方式（如 needNoImgModeOptimization）实现",
                        "新增或复用现有 Starling key 用于本地化的 \"Auction\" 标识",
                        "升级 code.byted.org/oec/live_common/abtest 依赖到包含跨仓契约字段的版本",
                    ],
                },
                {
                    "id": "W2",
                    "repo_id": "live_common",
                    "change_scope": ["abtest/struct.go"],
                    "specific_steps": [
                        "在 abtest/struct.go 的 TTECContent 结构体中新增实验字段 RegularAuctionTitleAuctionLabelEnabled bool",
                        "添加合适的 json tag",
                        "字段含义：true 表示命中实验组，false 保持线上逻辑不变",
                    ],
                },
            ]
        },
    )
    write_json(
        task_dir / "plan-execution-graph.json",
        {
            "edges": [
                {
                    "from": "W2",
                    "to": "W1",
                    "contract": {
                        "producer_repo": "live_common",
                        "consumer_repo": "live_pack",
                    },
                }
            ]
        },
    )
    write_json(
        task_dir / "plan-validation.json",
        {
            "global_validation_focus": [
                "命中实验时，regular auction 标题前增加本地化的 `Auction` 标识。",
                "标题前缀与原标题之间有稳定分隔，整体可读性不受影响。",
                "如果本地化标识取值异常为空，则回退为原标题，不出现空前缀或异常连接符。",
                "未命中实验时，标题保持现有线上逻辑不变。",
            ]
        },
    )
    write_json(task_dir / "plan-result.json", {"code_allowed": True, "blockers": []})
    write_json(task_dir / "plan-sync.json", {"synced": True})


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_child(section: dict[str, object], child_id: str) -> dict[str, object]:
    children = section["children"]
    assert isinstance(children, list)
    for child in children:
        assert isinstance(child, dict)
        if child.get("id") == child_id:
            return child
    raise AssertionError(f"child not found: {child_id}")


if __name__ == "__main__":
    unittest.main()

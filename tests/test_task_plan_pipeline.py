from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.engines.design.assignment import build_design_change_points_payload, build_design_repo_assignment_payload
from coco_flow.engines.design.binding import build_local_repo_binding, build_repo_binding
from coco_flow.engines.design.models import DesignPreparedInput
from coco_flow.engines.design.matrix import (
    build_design_responsibility_matrix_payload,
    build_local_design_responsibility_matrix_payload,
)
from coco_flow.engines.design.pipeline import build_repo_binding_diagnosis
from coco_flow.engines.design.generate import (
    build_design_sections_payload,
    collect_design_contract_issues,
    generate_design_markdown,
    generate_local_design_markdown,
    repair_design_markdown,
)
from coco_flow.engines.design.research import _rank_candidate_file, build_design_research_payload
from coco_flow.engines.shared.models import (
    ComplexityAssessment,
    ContextSnapshot,
    DesignResearchSignals,
    GlossaryEntry,
    RefinedSections,
    RepoResearch,
    RepoScope,
    ResearchFinding,
)
from coco_flow.services.queries.skills import SkillStore
from coco_flow.services.tasks.design import design_task, start_designing_task
from coco_flow.services.tasks.plan import plan_task


def make_settings(root: Path, plan_executor: str = "local") -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
        refine_executor="local",
        plan_executor=plan_executor,
        code_executor="local",
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class PlanTaskPipelineTest(unittest.TestCase):
    def test_native_design_change_points_can_merge_duplicate_scope_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), plan_executor="native")
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-change-points",
                title="two sum",
                refined_markdown="# PRD Refined\n\n## 功能点\n- 添加 two sum 算法\n- 添加两数之和 golang 文件\n- 仅处理 two sum\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[],
                repo_researches=[],
                repo_ids=set(),
                repo_root=None,
                sections=RefinedSections(
                    change_scope=["添加 two sum 算法", "添加两数之和 golang 文件", "仅处理 two sum"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
            )

            def run_agent_stub(*args, **kwargs):
                prompt = str(args[0] if args else kwargs.get("prompt") or "")
                matched = re.search(r"(?m)^- file: (.+)$", prompt)
                self.assertIsNotNone(matched)
                template_path = Path(str(matched.group(1)).strip())
                template_path.write_text(
                    json.dumps(
                        {
                            "change_points": [
                                {
                                    "title": "添加 two sum 算法文件",
                                    "summary": "新增一个 two sum / 两数之和的 Go 算法文件，不扩展到其他算法题。",
                                    "constraints": ["仅处理 two sum"],
                                    "acceptance": [],
                                }
                            ]
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return "done"

            from unittest.mock import patch

            with patch("coco_flow.engines.design.assignment.CocoACPClient.run_agent", side_effect=run_agent_stub):
                payload = build_design_change_points_payload(prepared, settings, "", lambda _message: None)

            self.assertEqual(payload["mode"], "llm")
            self.assertEqual(len(payload["change_points"]), 1)
            self.assertEqual(payload["change_points"][0]["title"], "添加 two sum 算法文件")

    def test_design_sections_do_not_invent_repo_dependencies_without_depends_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-sections",
                title="demo",
                refined_markdown="# PRD Refined\n\n- demo\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[],
                repo_researches=[],
                repo_ids=set(),
                repo_root=None,
                sections=RefinedSections(
                    change_scope=["添加 two sum 算法文件"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
            )
            payload = build_design_sections_payload(
                prepared,
                {
                    "repo_bindings": [
                        {
                            "repo_id": "demo",
                            "decision": "in_scope",
                            "system_name": "Demo",
                            "serves_change_points": [1],
                            "responsibility": "demo repo",
                            "change_summary": ["change demo"],
                            "depends_on": [],
                        },
                        {
                            "repo_id": "test",
                            "decision": "in_scope",
                            "system_name": "Test",
                            "serves_change_points": [1],
                            "responsibility": "test repo",
                            "change_summary": ["change test"],
                            "depends_on": [],
                        },
                    ],
                    "decision_summary": "demo and test",
                },
                "",
            )

            self.assertEqual(payload["system_dependencies"], [])

    def test_design_sections_only_expand_must_change_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-sections-tiers",
                title="demo",
                refined_markdown="# PRD Refined\n\n- demo\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[],
                repo_researches=[],
                repo_ids=set(),
                repo_root=None,
                sections=RefinedSections(
                    change_scope=["统一成功态"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
            )
            repo_binding_payload = {
                "repo_bindings": [
                    {
                        "repo_id": "live_pack",
                        "decision": "in_scope",
                        "scope_tier": "must_change",
                        "system_name": "Live Pack",
                        "serves_change_points": [1],
                        "responsibility": "核心状态收敛",
                        "change_summary": ["改成功态逻辑"],
                        "candidate_files": ["entities/converters/regular_auction_converter.go"],
                        "depends_on": [],
                    },
                    {
                        "repo_id": "live_shopapi",
                        "decision": "in_scope",
                        "scope_tier": "validate_only",
                        "system_name": "Shop API",
                        "reason": "需要确认下游适配是否受影响",
                    },
                    {
                        "repo_id": "live_common",
                        "decision": "in_scope",
                        "scope_tier": "reference_only",
                        "system_name": "Common",
                        "reason": "仅提供 AB 背景",
                    },
                ],
                "decision_summary": "must_change=live_pack",
            }

            payload = build_design_sections_payload(prepared, repo_binding_payload, "")
            self.assertEqual(len(payload["system_changes"]), 1)
            self.assertEqual(payload["system_changes"][0]["system_id"], "live_pack")
            self.assertEqual(payload["repo_decisions"][0]["repo_id"], "live_pack")
            self.assertIn("联动验证", payload["repo_decisions"][1]["decision_summary"])
            self.assertEqual(payload["repo_decisions"][1]["repo_id"], "live_shopapi")
            self.assertEqual(payload["repo_decisions"][2]["repo_id"], "live_common")

            markdown = generate_local_design_markdown(prepared, repo_binding_payload, payload, "")
            self.assertIn("#### Live Pack", markdown)
            self.assertIn("选择原因", markdown)
            self.assertIn("live_shopapi", markdown)
            self.assertIn("live_common", markdown)
            self.assertIn("角色定位：联动验证仓", markdown)
            self.assertIn("角色定位：参考信息仓", markdown)

    def test_design_contract_requires_multi_repo_roles_and_candidate_files(self) -> None:
        repo_binding_payload = {
            "repo_bindings": [
                {
                    "repo_id": "demo",
                    "decision": "in_scope",
                    "scope_tier": "must_change",
                    "system_name": "Demo",
                    "candidate_files": ["main.go"],
                },
                {
                    "repo_id": "test",
                    "decision": "in_scope",
                    "scope_tier": "validate_only",
                    "system_name": "Test",
                },
            ]
        }
        sections_payload = {
            "repo_decisions": [
                {
                    "repo_id": "demo",
                    "candidate_files": ["main.go"],
                },
                {
                    "repo_id": "test",
                    "candidate_files": ["quick_sort.go"],
                },
            ]
        }

        issues = collect_design_contract_issues(
            "# Design\n\n## 分仓库方案\n\n#### Demo\n- 仓库：demo\n- 角色定位：本次主改仓\n- 职责：demo 仓负责新增 two sum。\n",
            repo_binding_payload,
            sections_payload,
        )

        self.assertTrue(any("test" in issue for issue in issues))
        self.assertTrue(any("未明确提及" in issue or "验证定位" in issue for issue in issues))
        self.assertTrue(any("main.go" in issue or "实现落点" in issue for issue in issues))

    def test_candidate_file_ranking_prefers_state_authority_over_context_paths(self) -> None:
        self.assertGreater(
            _rank_candidate_file("entities/loaders/auction_loaders/auction_status_loader.go"),
            _rank_candidate_file("entities/loaders/product_loaders/product_auction_config_data_loader.go"),
        )
        self.assertGreater(
            _rank_candidate_file("entities/loaders/product_loaders/product_auction_data_loader.go"),
            _rank_candidate_file("entities/loaders/auction_loaders/auction_product_meta_loader.go"),
        )

    def test_candidate_file_ranking_uses_context_tokens_to_downrank_generic_status_paths(self) -> None:
        context_tokens = {"auction", "regular", "card"}
        preferred_dirs = [
            "entities/loaders/auction_loaders",
            "entities/loaders/product_loaders",
            "entities/converters/auction_converters",
        ]
        self.assertGreater(
            _rank_candidate_file(
                "entities/loaders/product_loaders/product_auction_data_loader.go",
                context_tokens=context_tokens,
                preferred_dirs=preferred_dirs,
            ),
            _rank_candidate_file(
                "entities/loaders/product_loaders/product_status_loader.go",
                context_tokens=context_tokens,
                preferred_dirs=preferred_dirs,
            ),
        )
        self.assertGreater(
            _rank_candidate_file(
                "entities/converters/auction_converters/regular_auction_converter.go",
                context_tokens=context_tokens,
                preferred_dirs=preferred_dirs,
            ),
            _rank_candidate_file(
                "utils/status_code.go",
                context_tokens=context_tokens,
                preferred_dirs=preferred_dirs,
            ),
        )

    def test_build_design_sections_skips_interface_changes_without_external_boundary_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "live_pack"
            repo_root.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-no-interface-signal",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[RepoScope(repo_id="live_pack", repo_path=str(repo_root))],
                repo_researches=[],
                repo_ids={"live_pack"},
                repo_root=str(repo_root),
                sections=RefinedSections(
                    change_scope=["统一成功态"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
            )
            payload = build_design_sections_payload(
                prepared,
                {
                    "repo_bindings": [
                        {
                            "repo_id": "live_pack",
                            "decision": "in_scope",
                            "scope_tier": "must_change",
                            "system_name": "live_pack",
                            "serves_change_points": [1],
                            "responsibility": "状态收敛",
                            "change_summary": ["统一成功态"],
                            "candidate_files": [
                                "entities/loaders/auction_loaders/auction_status_loader.go",
                                "entities/loaders/product_loaders/product_auction_data_loader.go",
                            ],
                            "candidate_dirs": ["entities/loaders"],
                            "depends_on": [],
                            "reason": "负责状态收敛",
                        }
                    ],
                    "closure_mode": "single_repo",
                    "selection_basis": "strong_signal",
                    "selection_note": "单仓即可闭合实现。",
                },
                "",
            )
            self.assertEqual(payload["interface_changes"], [])

    def test_design_contract_requires_core_candidate_files_when_repo_is_mentioned(self) -> None:
        repo_binding_payload = {
            "repo_bindings": [
                {
                    "repo_id": "live_pack",
                    "decision": "in_scope",
                    "scope_tier": "must_change",
                    "system_name": "live_pack",
                    "candidate_files": [
                        "entities/loaders/auction_loaders/auction_status_loader.go",
                        "entities/loaders/product_loaders/product_auction_data_loader.go",
                        "entities/loaders/product_loaders/product_auction_config_data_loader.go",
                    ],
                }
            ]
        }
        sections_payload = {
            "repo_decisions": [
                {
                    "repo_id": "live_pack",
                    "candidate_files": [
                        "entities/loaders/auction_loaders/auction_status_loader.go",
                        "entities/loaders/product_loaders/product_auction_data_loader.go",
                        "entities/loaders/product_loaders/product_auction_config_data_loader.go",
                    ]
                }
            ]
        }
        issues = collect_design_contract_issues(
            "# Design\n\n## 改造点总览\n- 统一成功态\n\n## 总体方案\n- 只修改 live_pack。\n\n## 分仓库方案\n\n### live_pack\n- 仓库：live_pack\n- 核心改点：\n  - entities/loaders/product_loaders/product_auction_config_data_loader.go\n\n## 仓库依赖关系\n- 无\n\n## 接口协议变更\n- 本次需求不涉及对外接口协议变更。\n\n## 风险与待确认项\n- 无\n",
            repo_binding_payload,
            sections_payload,
        )
        self.assertTrue(any("第一核心实现落点" in issue for issue in issues))

    def test_design_contract_requires_primary_core_candidate_to_be_front_loaded(self) -> None:
        repo_binding_payload = {
            "repo_bindings": [
                {
                    "repo_id": "live_pack",
                    "decision": "in_scope",
                    "scope_tier": "must_change",
                    "system_name": "live_pack",
                    "candidate_files": [
                        "entities/loaders/auction_loaders/auction_status_loader.go",
                        "entities/loaders/product_loaders/product_auction_data_loader.go",
                        "entities/converters/auction_converters/regular_auction_converter.go",
                    ],
                }
            ]
        }
        sections_payload = {
            "repo_decisions": [
                {
                    "repo_id": "live_pack",
                    "candidate_files": [
                        "entities/loaders/auction_loaders/auction_status_loader.go",
                        "entities/loaders/product_loaders/product_auction_data_loader.go",
                        "entities/converters/auction_converters/regular_auction_converter.go",
                    ]
                }
            ]
        }
        issues = collect_design_contract_issues(
            "# Design\n\n## 改造点总览\n- 优先确认 entities/loaders/product_loaders/product_auction_data_loader.go。\n\n## 总体方案\n- live_pack 单仓闭合。\n\n## 分仓库方案\n\n### live_pack\n- 仓库：live_pack\n- 核心改点：\n  - entities/loaders/product_loaders/product_auction_data_loader.go\n- 联动检查：\n  - entities/converters/auction_converters/regular_auction_converter.go\n- 证据：entities/loaders/auction_loaders/auction_status_loader.go 中存在状态判定。\n\n## 仓库依赖关系\n- 无\n\n## 接口协议变更\n- 本次需求不涉及对外接口协议变更。\n\n## 风险与待确认项\n- 无\n",
            repo_binding_payload,
            sections_payload,
        )
        self.assertTrue(any("未排在候选文件前列" in issue for issue in issues))

    def test_repair_design_markdown_rewrites_repo_plan_section_only(self) -> None:
        repo_binding_payload = {
            "repo_bindings": [
                {
                    "repo_id": "demo",
                    "decision": "in_scope",
                    "scope_tier": "must_change",
                    "system_name": "Demo",
                    "responsibility": "实现 two sum 主链路",
                    "change_summary": ["新增 two sum 实现"],
                    "candidate_files": ["main.go"],
                },
                {
                    "repo_id": "test",
                    "decision": "in_scope",
                    "scope_tier": "validate_only",
                    "system_name": "Test",
                    "candidate_files": ["quick_sort.go"],
                },
            ]
        }
        sections_payload = {
            "repo_decisions": [
                {"repo_id": "demo", "candidate_files": ["main.go"]},
                {"repo_id": "test", "candidate_files": ["quick_sort.go"]},
            ]
        }
        markdown = (
            "# Design\n\n"
            "## 改造点总览\n- two sum\n\n"
            "## 总体方案\n- 保持当前输入输出。\n\n"
            "## 分仓库方案\n\n"
            "#### Demo\n- 仓库：demo\n- 职责：新增 two sum。\n\n"
            "## 仓库依赖关系\n- 当前未识别到明确的强依赖关系。\n\n"
            "## 接口协议变更\n- 本次需求不涉及对外接口协议变更。\n\n"
            "## 风险与待确认项\n- 无\n"
        )
        issues = collect_design_contract_issues(markdown, repo_binding_payload, sections_payload)

        repaired, repaired_issues = repair_design_markdown(markdown, repo_binding_payload, sections_payload, issues)
        remaining = collect_design_contract_issues(repaired, repo_binding_payload, sections_payload)

        self.assertTrue(repaired_issues)
        self.assertIn("## 总体方案\n- 保持当前输入输出。", repaired)
        self.assertIn("角色定位：本次主改仓", repaired)
        self.assertIn("main.go", repaired)
        self.assertIn("角色定位：联动验证仓", repaired)
        self.assertIn("验证定位", repaired)
        self.assertFalse(any("未落候选文件" in issue for issue in remaining))
        self.assertFalse(any("未说明仓库执行职责角色" in issue for issue in remaining))
        self.assertFalse(any("验证定位说明" in issue for issue in remaining))

    def test_generate_local_design_markdown_prioritizes_core_candidate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "live_pack"
            repo_root.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-prioritize-candidates",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[RepoScope(repo_id="live_pack", repo_path=str(repo_root))],
                repo_researches=[],
                repo_ids={"live_pack"},
                repo_root=str(repo_root),
                sections=RefinedSections(
                    change_scope=["统一成功态"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
            )
            repo_binding_payload = {
                "repo_bindings": [
                    {
                        "repo_id": "live_pack",
                        "decision": "in_scope",
                        "scope_tier": "must_change",
                        "system_name": "live_pack",
                        "serves_change_points": [1],
                        "responsibility": "状态收敛",
                        "change_summary": ["统一成功态"],
                        "candidate_files": [
                            "entities/loaders/product_loaders/product_auction_config_data_loader.go",
                            "entities/converters/auction_converters/regular_auction_converter.go",
                            "entities/loaders/auction_loaders/auction_status_loader.go",
                            "entities/loaders/product_loaders/product_auction_data_loader.go",
                        ],
                        "candidate_dirs": ["entities/loaders"],
                        "depends_on": [],
                        "reason": "负责状态收敛",
                    }
                ],
                "closure_mode": "single_repo",
                "selection_basis": "strong_signal",
                "selection_note": "单仓即可闭合实现。",
            }

            sections_payload = build_design_sections_payload(prepared, repo_binding_payload, "")
            markdown = generate_local_design_markdown(prepared, repo_binding_payload, sections_payload, "")
            self.assertLess(
                markdown.index("entities/loaders/auction_loaders/auction_status_loader.go"),
                markdown.index("entities/loaders/product_loaders/product_auction_config_data_loader.go"),
            )

    def test_generate_local_design_markdown_keeps_focus_files_ahead_of_builder_and_list_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "live_pack"
            repo_root.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-focus-order",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[RepoScope(repo_id="live_pack", repo_path=str(repo_root))],
                repo_researches=[],
                repo_ids={"live_pack"},
                repo_root=str(repo_root),
                sections=RefinedSections(
                    change_scope=["统一成功态"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
            )
            repo_binding_payload = {
                "repo_bindings": [
                    {
                        "repo_id": "live_pack",
                        "decision": "in_scope",
                        "scope_tier": "must_change",
                        "system_name": "live_pack",
                        "serves_change_points": [1],
                        "responsibility": "状态收敛",
                        "change_summary": ["统一成功态"],
                        "candidate_files": [
                            "entities/loaders/auction_loaders/auction_status_loader.go",
                            "entities/converters/auction_converters/regular_auction_converter.go",
                            "entities/dto_builders/auction_card_data_dto_builder.go",
                            "entities/loaders/product_loaders/product_auction_data_loader.go",
                            "entities/converters/auction_converters/list_converter.go",
                        ],
                        "candidate_dirs": ["entities/loaders", "entities/converters"],
                        "depends_on": [],
                        "reason": "负责状态收敛",
                    }
                ],
                "closure_mode": "single_repo",
                "selection_basis": "strong_signal",
                "selection_note": "单仓即可闭合实现。",
            }

            sections_payload = build_design_sections_payload(prepared, repo_binding_payload, "")
            markdown = generate_local_design_markdown(prepared, repo_binding_payload, sections_payload, "")
            self.assertLess(
                markdown.index("entities/converters/auction_converters/regular_auction_converter.go"),
                markdown.index("entities/converters/auction_converters/list_converter.go"),
            )
            self.assertLess(
                markdown.index("entities/loaders/product_loaders/product_auction_data_loader.go"),
                markdown.index("entities/dto_builders/auction_card_data_dto_builder.go"),
            )

    def test_local_responsibility_matrix_prefers_state_aggregation_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-matrix",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[],
                repo_researches=[],
                repo_ids=set(),
                repo_root=None,
                sections=RefinedSections(
                    change_scope=["统一成功态"],
                    non_goals=["不新增 TCC 配置"],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
                change_points_payload={"change_points": [{"id": 1, "title": "统一成功态"}]},
                research_payload={
                    "repos": [
                        {
                            "repo_id": "live_pack",
                            "summary": "负责竞拍状态收敛",
                            "candidate_dirs": ["entities/converters/auction_converters", "engines"],
                            "candidate_files": [
                                "entities/loaders/auction_loaders/auction_status_loader.go",
                                "entities/converters/auction_converters/regular_auction_converter.go",
                                "engines/auction_card_data.go",
                            ],
                            "matched_terms": ["AuctionStatus_Success", "RegularAuctionConverter"],
                            "notes": [],
                            "evidence": [],
                        },
                        {
                            "repo_id": "content_live_bff_lib",
                            "summary": "负责 Lynx 装配和数据转换",
                            "candidate_dirs": ["us/biz/pincard/pack"],
                            "candidate_files": ["us/biz/pincard/pack/pop_auction.go", "us/biz/pincard/pin_card.go"],
                            "matched_terms": ["AuctionStatus", "Lynx"],
                            "notes": [],
                            "evidence": [],
                        },
                        {
                            "repo_id": "live_common",
                            "summary": "提供 AB 配置",
                            "candidate_dirs": ["abtest"],
                            "candidate_files": ["abtest/struct.go"],
                            "matched_terms": ["UseAuctionStatusSuccess"],
                            "notes": [],
                            "evidence": [],
                        },
                    ]
                },
            )

            payload = build_local_design_responsibility_matrix_payload(prepared)
            by_repo = {item["repo_id"]: item for item in payload["repos"]}
            self.assertEqual(by_repo["live_pack"]["recommended_scope_tier"], "must_change")
            self.assertEqual(by_repo["content_live_bff_lib"]["recommended_scope_tier"], "validate_only")
            self.assertEqual(by_repo["live_common"]["recommended_scope_tier"], "reference_only")

    def test_single_bound_repo_assignment_uses_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "live_pack"
            repo_root.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-single-bound-assignment",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[RepoScope(repo_id="live_pack", repo_path=str(repo_root))],
                repo_researches=[
                    RepoResearch(
                        repo_id="live_pack",
                        repo_path=str(repo_root),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(matched_terms=[], unmatched_terms=[], candidate_files=[], candidate_dirs=[], notes=[]),
                    )
                ],
                repo_ids={"live_pack"},
                repo_root=str(repo_root),
                sections=RefinedSections(
                    change_scope=["统一成功态", "讲解卡展示 success 态"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
                repo_discovery_payload={"mode": "bound", "bound_repo_count": 1, "inferred_repo_count": 0},
            )

            payload = build_design_repo_assignment_payload(
                prepared,
                {
                    "change_points": [
                        {"id": 1, "title": "统一成功态"},
                        {"id": 2, "title": "讲解卡展示 success 态"},
                    ]
                },
            )

            self.assertEqual(payload["mode"], "single_bound_fast_path")
            self.assertEqual(payload["repo_briefs"][0]["repo_id"], "live_pack")
            self.assertEqual(payload["repo_briefs"][0]["primary_change_points"], [1, 2])

    def test_single_bound_repo_matrix_and_binding_use_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), plan_executor="native")
            repo_root = Path(tmp) / "live_pack"
            repo_root.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-single-bound-binding",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[RepoScope(repo_id="live_pack", repo_path=str(repo_root))],
                repo_researches=[
                    RepoResearch(
                        repo_id="live_pack",
                        repo_path=str(repo_root),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[GlossaryEntry(business="AuctionStatus_Success", identifier="AuctionStatusSuccess", module="loaders")],
                            unmatched_terms=[],
                            candidate_files=["entities/loaders/auction_loaders/auction_status_loader.go"],
                            candidate_dirs=["entities/loaders/auction_loaders"],
                            notes=[],
                        ),
                    )
                ],
                repo_ids={"live_pack"},
                repo_root=str(repo_root),
                sections=RefinedSections(
                    change_scope=["统一成功态"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
                repo_discovery_payload={"mode": "bound", "bound_repo_count": 1, "inferred_repo_count": 0},
                change_points_payload={"change_points": [{"id": 1, "title": "统一成功态"}]},
                research_payload={
                    "repos": [
                        {
                            "repo_id": "live_pack",
                            "summary": "负责状态收敛",
                            "candidate_dirs": ["entities/loaders/auction_loaders"],
                            "candidate_files": ["entities/loaders/auction_loaders/auction_status_loader.go"],
                            "matched_terms": ["AuctionStatus_Success"],
                            "notes": [],
                            "evidence": [],
                        }
                    ]
                },
            )

            matrix = build_design_responsibility_matrix_payload(prepared, settings, "", lambda _message: None)
            prepared.responsibility_matrix_payload = matrix
            binding = build_repo_binding(prepared, settings, "", lambda _message: None)

            self.assertEqual(matrix["mode"], "single_bound_fast_path")
            self.assertEqual(binding.mode, "single_bound_fast_path")
            self.assertEqual(binding.repo_bindings[0].scope_tier, "must_change")

    def test_single_bound_repo_native_generate_skips_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), plan_executor="native")
            repo_root = Path(tmp) / "live_pack"
            repo_root.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-single-bound-generate",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[RepoScope(repo_id="live_pack", repo_path=str(repo_root))],
                repo_researches=[],
                repo_ids={"live_pack"},
                repo_root=str(repo_root),
                sections=RefinedSections(
                    change_scope=["统一成功态"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
                repo_discovery_payload={"mode": "bound", "bound_repo_count": 1, "inferred_repo_count": 0},
            )
            repo_binding_payload = {
                "repo_bindings": [
                    {
                        "repo_id": "live_pack",
                        "decision": "in_scope",
                        "scope_tier": "must_change",
                        "system_name": "Live Pack",
                        "serves_change_points": [1],
                        "responsibility": "核心状态收敛",
                        "change_summary": ["改成功态逻辑"],
                        "candidate_files": ["entities/loaders/auction_loaders/auction_status_loader.go"],
                        "depends_on": [],
                    }
                ],
                "decision_summary": "must_change=live_pack",
            }
            sections_payload = build_design_sections_payload(prepared, repo_binding_payload, "")
            artifacts: dict[str, object] = {}

            def run_agent_stub(*args, **kwargs):
                prompt = str(args[0] if args else kwargs.get("prompt") or "")
                matched = re.search(r"(?m)^- file: (.+)$", prompt)
                self.assertIsNotNone(matched)
                template_path = Path(str(matched.group(1)).strip())
                if str(template_path).endswith(".json"):
                    template_path.write_text('{"ok": true, "issues": [], "reason": "verify ok"}\n', encoding="utf-8")
                else:
                    template_path.write_text(
                        "# Design\n\n## 改造点总览\n\n- 统一成功态\n\n## 总体方案\n\n- 只修改 live_pack。\n\n## 分仓库方案\n\n#### Live Pack\n- 仓库：live_pack\n- 角色定位：本次主改仓\n- 职责：核心状态收敛\n- 选择原因：只修改 live_pack。\n- 仓库现状：主改仓。\n- 主要改动：\n  - 改成功态逻辑\n- 核心改点：\n  - entities/loaders/auction_loaders/auction_status_loader.go\n\n## 仓库依赖关系\n\n- 当前未识别到明确的强依赖关系。\n\n## 接口协议变更\n\n- 本次需求不涉及对外接口协议变更。\n\n## 风险与待确认项\n\n- 当前未沉淀出额外技术风险或待确认项。\n",
                        encoding="utf-8",
                    )
                return "done"

            from unittest.mock import patch

            with patch("coco_flow.engines.design.generate.CocoACPClient.run_agent", side_effect=run_agent_stub) as mocked:
                markdown = generate_design_markdown(prepared, repo_binding_payload, sections_payload, "", settings, artifacts, lambda _message: None)

            self.assertIn("# Design", markdown)
            self.assertEqual(mocked.call_count, 2)

    def test_local_repo_binding_classifies_scope_tiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live_pack = Path(tmp) / "live_pack"
            live_shopapi = Path(tmp) / "live_shopapi"
            live_common = Path(tmp) / "live_common"
            live_pack.mkdir()
            live_shopapi.mkdir()
            live_common.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-local-binding",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[
                    RepoScope(repo_id="live_pack", repo_path=str(live_pack)),
                    RepoScope(repo_id="live_shopapi", repo_path=str(live_shopapi)),
                    RepoScope(repo_id="live_common", repo_path=str(live_common)),
                ],
                repo_researches=[
                    RepoResearch(
                        repo_id="live_pack",
                        repo_path=str(live_pack),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[GlossaryEntry(business="AuctionStatus_Success", identifier="AuctionStatusSuccess", module="loaders")],
                            unmatched_terms=[],
                            candidate_files=[
                                "entities/loaders/auction_loaders/auction_status_loader.go",
                                "entities/converters/auction_converters/regular_auction_converter.go",
                            ],
                            candidate_dirs=["entities/converters/auction_converters"],
                            notes=[],
                        ),
                    ),
                    RepoResearch(
                        repo_id="live_shopapi",
                        repo_path=str(live_shopapi),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[GlossaryEntry(business="AuctionStatus", identifier="AuctionStatus", module="api")],
                            unmatched_terms=[],
                            candidate_files=["biz/service/tools/live_pack_converter.go"],
                            candidate_dirs=["biz/service/tools"],
                            notes=[],
                        ),
                    ),
                    RepoResearch(
                        repo_id="live_common",
                        repo_path=str(live_common),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[GlossaryEntry(business="UseAuctionStatusSuccess", identifier="UseAuctionStatusSuccess", module="abtest")],
                            unmatched_terms=[],
                            candidate_files=["abtest/struct.go"],
                            candidate_dirs=["abtest"],
                            notes=[],
                        ),
                    ),
                ],
                repo_ids={"live_pack", "live_shopapi", "live_common"},
                repo_root=str(live_pack),
                sections=RefinedSections(
                    change_scope=["统一成功态"],
                    non_goals=["不新增 TCC 配置"],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=2, level="low", conclusion="低复杂度"),
                change_points_payload={"change_points": [{"id": 1, "title": "统一成功态"}]},
                responsibility_matrix_payload={
                    "repos": [
                        {"repo_id": "live_pack", "recommended_scope_tier": "must_change", "reasoning": "定义和收敛状态"},
                        {"repo_id": "live_shopapi", "recommended_scope_tier": "validate_only", "reasoning": "适配层"},
                        {"repo_id": "live_common", "recommended_scope_tier": "reference_only", "reasoning": "AB 配置"},
                    ]
                },
                repo_assignment_payload={
                    "repo_briefs": [
                        {"repo_id": "live_pack", "primary_change_points": [1], "secondary_change_points": []},
                        {"repo_id": "live_shopapi", "primary_change_points": [], "secondary_change_points": [1]},
                        {"repo_id": "live_common", "primary_change_points": [], "secondary_change_points": []},
                    ]
                },
            )

            binding = build_local_repo_binding(prepared).to_payload()
            by_repo = {item["repo_id"]: item for item in binding["repo_bindings"]}
            self.assertEqual(by_repo["live_pack"]["scope_tier"], "must_change")
            self.assertEqual(by_repo["live_pack"]["confidence"], "high")
            self.assertEqual(by_repo["live_shopapi"]["scope_tier"], "validate_only")
            self.assertEqual(by_repo["live_common"]["scope_tier"], "reference_only")

    def test_local_repo_binding_marks_must_change_without_candidates_as_low_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-low-confidence-binding",
                title="补充状态",
                refined_markdown="# PRD Refined\n\n- 补充状态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[RepoScope(repo_id="demo", repo_path=str(demo))],
                repo_researches=[
                    RepoResearch(
                        repo_id="demo",
                        repo_path=str(demo),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[],
                            unmatched_terms=[],
                            candidate_files=[],
                            candidate_dirs=[],
                            notes=[],
                        ),
                    )
                ],
                repo_ids={"demo"},
                repo_root=str(demo),
                sections=RefinedSections(
                    change_scope=["补充状态"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=2, level="low", conclusion="低复杂度"),
                change_points_payload={"change_points": [{"id": 1, "title": "补充状态"}]},
                responsibility_matrix_payload={
                    "repos": [
                        {"repo_id": "demo", "recommended_scope_tier": "must_change", "reasoning": "可能定义状态"},
                    ]
                },
                repo_assignment_payload={
                    "repo_briefs": [
                        {"repo_id": "demo", "primary_change_points": [1], "secondary_change_points": []},
                    ]
                },
                research_payload={"repos": [{"repo_id": "demo", "confidence": "low", "candidate_files": [], "candidate_dirs": []}]},
            )

            binding = build_local_repo_binding(prepared).to_payload()
            diagnosis = build_repo_binding_diagnosis(binding)

            self.assertEqual(binding["repo_bindings"][0]["scope_tier"], "must_change")
            self.assertEqual(binding["repo_bindings"][0]["confidence"], "low")
            self.assertIsNotNone(diagnosis)
            self.assertEqual(diagnosis["severity"], "needs_human")
            self.assertEqual(diagnosis["failure_type"], "repo_responsibility_uncertain")
            self.assertEqual(diagnosis["issues"][0]["repo_id"], "demo")

    def test_local_repo_binding_marks_single_repo_choice_as_tiebreak_when_alternatives_are_comparable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            test_repo = Path(tmp) / "test"
            demo.mkdir()
            test_repo.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-binding-selection-basis",
                title="two sum",
                refined_markdown="# PRD Refined\n\n- 添加 two sum 算法\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[
                    RepoScope(repo_id="demo", repo_path=str(demo)),
                    RepoScope(repo_id="test", repo_path=str(test_repo)),
                ],
                repo_researches=[
                    RepoResearch(
                        repo_id="demo",
                        repo_path=str(demo),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[],
                            unmatched_terms=[],
                            candidate_files=["main.go"],
                            candidate_dirs=["."],
                            notes=["已有冒泡排序"],
                        ),
                    ),
                    RepoResearch(
                        repo_id="test",
                        repo_path=str(test_repo),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[],
                            unmatched_terms=[],
                            candidate_files=["quick_sort.go"],
                            candidate_dirs=["."],
                            notes=["已有快排实现"],
                        ),
                    ),
                ],
                repo_ids={"demo", "test"},
                repo_root=str(demo),
                sections=RefinedSections(
                    change_scope=["添加 two sum 算法文件"],
                    non_goals=["不扩展到其他算法题"],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
                responsibility_matrix_payload={
                    "repos": [
                        {"repo_id": "demo", "recommended_scope_tier": "must_change", "reasoning": "demo 可直接落 two sum 实现"},
                        {"repo_id": "test", "recommended_scope_tier": "validate_only", "reasoning": "test 也可承接实现，但本轮默认不作为起始仓"},
                    ]
                },
                research_payload={
                    "repos": [
                        {"repo_id": "demo", "prefilter_score": 2, "candidate_files": ["main.go"], "summary": "demo 适合添加 two sum"},
                        {"repo_id": "test", "prefilter_score": 2, "candidate_files": ["quick_sort.go"], "summary": "test 也适合添加 two sum"},
                    ]
                },
            )

            binding = build_local_repo_binding(prepared).to_payload()

            self.assertEqual(binding["closure_mode"], "single_repo")
            self.assertEqual(binding["selection_basis"], "heuristic_tiebreak")
            self.assertIn("demo", binding["selection_note"])
            self.assertIn("test", binding["selection_note"])

    def test_local_design_markdown_separates_single_repo_closure_from_repo_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-markdown-selection-note",
                title="two sum",
                refined_markdown="# PRD Refined\n\n- 添加 two sum 算法\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[],
                repo_researches=[],
                repo_ids=set(),
                repo_root=None,
                sections=RefinedSections(
                    change_scope=["添加 two sum 算法文件"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
                research_payload={
                    "repos": [
                        {"repo_id": "demo", "summary": "已有冒泡排序", "candidate_files": ["main.go"]},
                        {"repo_id": "test", "summary": "已有快排实现", "candidate_files": ["quick_sort.go"]},
                    ]
                },
            )
            repo_binding_payload = {
                "repo_bindings": [
                    {
                        "repo_id": "demo",
                        "decision": "in_scope",
                        "scope_tier": "must_change",
                        "system_name": "Demo",
                        "responsibility": "主算法实现仓库",
                        "change_summary": ["添加 two sum 算法文件"],
                        "candidate_files": ["main.go"],
                        "reason": "demo 可作为默认起始实现仓",
                    },
                    {
                        "repo_id": "test",
                        "decision": "in_scope",
                        "scope_tier": "validate_only",
                        "system_name": "Test",
                        "reason": "test 也可承接实现，但当前不默认改动",
                    },
                ],
                "decision_summary": "选择 demo 作为默认起始实现仓",
                "closure_mode": "single_repo",
                "selection_basis": "heuristic_tiebreak",
                "selection_note": "demo 和 test 都可承接实现；当前默认选择 demo 作为起始实现仓，不代表 test 不能实现该需求。",
            }

            payload = build_design_sections_payload(prepared, repo_binding_payload, "")
            markdown = generate_local_design_markdown(prepared, repo_binding_payload, payload, "")

            self.assertIn("当前判断：需求可在单仓内闭合实现", markdown)
            self.assertIn("仓库选择：demo 和 test 都可承接实现", markdown)
            self.assertIn("仓库选择说明：demo 和 test 都可承接实现", markdown)
            self.assertEqual(markdown.count("默认选择 demo 作为起始实现仓"), 3)

    def test_native_design_research_uses_run_agent_for_multiple_candidate_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), plan_executor="native")
            task_dir = Path(tmp) / "task"
            repo_a = Path(tmp) / "repo_a"
            repo_b = Path(tmp) / "repo_b"
            task_dir.mkdir(parents=True)
            repo_a.mkdir(parents=True)
            repo_b.mkdir(parents=True)

            prepared = DesignPreparedInput(
                task_dir=task_dir,
                task_id="task-design-research",
                title="竞拍讲解卡状态提示调整",
                refined_markdown="# PRD Refined\n\n- 支持讲解卡状态提示。\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[
                    RepoScope(repo_id="repo_a", repo_path=str(repo_a)),
                    RepoScope(repo_id="repo_b", repo_path=str(repo_b)),
                ],
                repo_researches=[
                    RepoResearch(
                        repo_id="repo_a",
                        repo_path=str(repo_a),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[GlossaryEntry(business="竞拍讲解卡", identifier="ExplainCardHandler", module="app/explain_card")],
                            unmatched_terms=[],
                            candidate_files=["app/explain_card/render_handler.go"],
                            candidate_dirs=["app/explain_card"],
                            notes=["命中讲解卡入口"],
                        ),
                    ),
                    RepoResearch(
                        repo_id="repo_b",
                        repo_path=str(repo_b),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[GlossaryEntry(business="状态提示", identifier="RenderExplainCard", module="service/card_render")],
                            unmatched_terms=[],
                            candidate_files=["service/card_render/render_service.go"],
                            candidate_dirs=["service/card_render"],
                            notes=["命中状态提示渲染服务"],
                        ),
                    ),
                ],
                repo_ids={"repo_a", "repo_b"},
                repo_root=str(repo_a),
                sections=RefinedSections(
                    change_scope=["支持讲解卡状态提示"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=2, level="low", conclusion="低复杂度"),
            )

            def run_agent_stub(*args, **kwargs):
                prompt = str(args[0] if args else kwargs.get("prompt") or "")
                matched = re.search(r"(?m)^- file: (.+)$", prompt)
                self.assertIsNotNone(matched)
                template_path = Path(str(matched.group(1)).strip())
                repo_id = "repo_a" if "repo_id: repo_a" in prompt else "repo_b"
                template_path.write_text(
                    json.dumps(
                        {
                            "repo_id": repo_id,
                            "repo_path": str(repo_a if repo_id == "repo_a" else repo_b),
                            "decision": "in_scope_candidate",
                            "serves_change_points": [1],
                            "summary": f"{repo_id} 需要进入 Design。",
                            "matched_terms": ["竞拍讲解卡" if repo_id == "repo_a" else "状态提示"],
                            "candidate_dirs": ["app/explain_card" if repo_id == "repo_a" else "service/card_render"],
                            "candidate_files": ["app/explain_card/render_handler.go" if repo_id == "repo_a" else "service/card_render/render_service.go"],
                            "dependencies": [],
                            "parallelizable_with": ["repo_b" if repo_id == "repo_a" else "repo_a"],
                            "evidence": [f"{repo_id} evidence"],
                            "notes": [f"{repo_id} note"],
                            "confidence": "high",
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return "done"

            from unittest.mock import patch

            with patch("coco_flow.engines.design.research.CocoACPClient.run_agent", side_effect=run_agent_stub) as run_agent_mock:
                payload = build_design_research_payload(prepared, settings, "", lambda _message: None)

            self.assertEqual(payload["mode"], "llm_parallel")
            self.assertEqual(payload["prefilter"]["parallel"], True)
            self.assertEqual(payload["prefilter"]["candidate_repo_ids"], ["repo_a", "repo_b"])
            self.assertEqual(run_agent_mock.call_count, 2)
            self.assertCountEqual([call.kwargs["cwd"] for call in run_agent_mock.call_args_list], [str(repo_a), str(repo_b)])
            self.assertTrue(all(item["exploration_mode"] == "llm" for item in payload["repos"]))

    def test_native_design_research_normalizes_agent_repo_id_to_expected_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), plan_executor="native")
            repo_root = Path(tmp) / "live_pack"
            repo_root.mkdir()
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-research-normalize-repo-id",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_skills_selection_payload={},
                refine_skills_read_markdown="",
                repo_lines=[],
                repo_scopes=[RepoScope(repo_id="live_pack", repo_path=str(repo_root))],
                repo_researches=[
                    RepoResearch(
                        repo_id="live_pack",
                        repo_path=str(repo_root),
                        context=ContextSnapshot(available=False),
                        finding=ResearchFinding(
                            matched_terms=[],
                            unmatched_terms=[],
                            candidate_files=["entities/loaders/auction_loaders/auction_status_loader.go"],
                            candidate_dirs=["entities/loaders/auction_loaders"],
                            notes=["命中竞拍状态加载器"],
                        ),
                    )
                ],
                repo_ids={"live_pack"},
                repo_root=str(repo_root),
                sections=RefinedSections(
                    change_scope=["统一成功态"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=[],
                    open_questions=[],
                    raw="",
                ),
                research_signals=DesignResearchSignals(),
                assessment=ComplexityAssessment(dimensions=[], total=1, level="low", conclusion="低复杂度"),
                change_points_payload={"change_points": [{"id": 1, "title": "统一成功态"}]},
                repo_assignment_payload={
                    "repo_briefs": [
                        {
                            "repo_id": "live_pack",
                            "primary_change_points": [1],
                            "secondary_change_points": [],
                        }
                    ]
                },
            )

            def run_agent_stub(*args, **kwargs):
                prompt = str(args[0] if args else kwargs.get("prompt") or "")
                matched = re.search(r"(?m)^- file: (.+)$", prompt)
                self.assertIsNotNone(matched)
                template_path = Path(str(matched.group(1)).strip())
                template_path.write_text(
                    json.dumps(
                        {
                            "repo_id": "ttec/live_pack",
                            "repo_path": str(repo_root),
                            "decision": "in_scope_candidate",
                            "serves_change_points": [1],
                            "summary": "live_pack 负责成功态收敛。",
                            "matched_terms": ["AuctionStatus_Success"],
                            "candidate_dirs": ["entities/loaders/auction_loaders"],
                            "candidate_files": ["entities/loaders/auction_loaders/auction_status_loader.go"],
                            "dependencies": [],
                            "parallelizable_with": [],
                            "evidence": ["AuctionStatus_Success 已存在"],
                            "notes": ["regular auction"],
                            "confidence": "high",
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return "done"

            from unittest.mock import patch

            with patch("coco_flow.engines.design.research.CocoACPClient.run_agent", side_effect=run_agent_stub):
                payload = build_design_research_payload(prepared, settings, "", lambda _message: None)

            self.assertEqual(payload["repos"][0]["repo_id"], "live_pack")
            self.assertEqual(payload["repos"][0]["repo_path"], str(repo_root))
            self.assertIn("normalized repo_id from ttec/live_pack to live_pack", payload["repos"][0]["notes"])

    def test_design_writes_design_markdown_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_root = Path(tmp) / "demo_repo"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n\nfunc ExplainCardHandler() {}\n",
                encoding="utf-8",
            )
            context_dir = repo_root / ".livecoding" / "context"
            context_dir.mkdir(parents=True, exist_ok=True)
            (context_dir / "glossary.md").write_text(
                "| 业务术语 | 代码标识 | 说明 | 模块 |\n"
                "| --- | --- | --- | --- |\n"
                "| 竞拍讲解卡 | ExplainCardHandler | 竞拍讲解卡入口 | app/explain_card |\n",
                encoding="utf-8",
            )

            timestamp = datetime.now().astimezone()
            task_id = "task-design-native"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = timestamp.isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍讲解卡状态提示调整",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "竞拍讲解卡状态提示调整",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(
                json.dumps({"repos": [{"id": "demo_repo", "path": str(repo_root), "status": "refined"}]}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text(
                "# PRD Refined\n\n"
                "## 需求概述\n\n"
                "- 竞拍讲解卡需要支持主播侧状态提示。\n\n"
                "## 功能点\n\n"
                "- 支持竞拍讲解卡展示主播侧状态提示。\n\n"
                "## 边界条件\n\n"
                "- 非竞拍态不展示。\n\n"
                "## 交互与展示\n\n"
                "- 保持已有讲解卡样式。\n\n"
                "## 验收标准\n\n"
                "- 主播侧状态提示可正确展示。\n\n"
                "## 业务规则\n\n"
                "- 非竞拍态保持不展示。\n\n"
                "## 待确认问题\n\n"
                "- 是否需要兼容老版本样式。\n",
                encoding="utf-8",
            )

            status = design_task(task_id, settings=settings)

            self.assertEqual(status, "designed")
            self.assertEqual(json.loads((task_dir / "task.json").read_text(encoding="utf-8"))["status"], "designed")
            self.assertFalse((task_dir / "plan.md").exists())
            change_points = json.loads((task_dir / "design-change-points.json").read_text(encoding="utf-8"))
            self.assertTrue(change_points["change_points"])
            assignment = json.loads((task_dir / "design-repo-assignment.json").read_text(encoding="utf-8"))
            self.assertTrue(assignment["repo_briefs"])
            matrix = json.loads((task_dir / "design-repo-responsibility-matrix.json").read_text(encoding="utf-8"))
            self.assertTrue(matrix["repos"])
            repo_binding = json.loads((task_dir / "design-repo-binding.json").read_text(encoding="utf-8"))
            self.assertTrue(repo_binding["repo_bindings"])
            self.assertEqual(repo_binding["repo_bindings"][0]["repo_id"], "demo_repo")
            research = json.loads((task_dir / "design-research.json").read_text(encoding="utf-8"))
            self.assertIn("prefilter", research)
            self.assertEqual(research["prefilter"]["candidate_repo_ids"], ["demo_repo"])
            self.assertTrue(research["repos"][0]["selected_for_exploration"])
            sections = json.loads((task_dir / "design-sections.json").read_text(encoding="utf-8"))
            self.assertTrue(sections["system_change_points"])
            verify = json.loads((task_dir / "design-verify.json").read_text(encoding="utf-8"))
            diagnosis = json.loads((task_dir / "design-diagnosis.json").read_text(encoding="utf-8"))
            self.assertEqual(verify["ok"], True)
            self.assertEqual(verify["stage"], "design")
            self.assertEqual(verify["next_action"], "continue")
            self.assertEqual(diagnosis["stage"], "design")
            self.assertTrue(diagnosis["ok"])
            design = (task_dir / "design.md").read_text(encoding="utf-8")
            self.assertIn("## 改造点总览", design)
            self.assertIn("## 总体方案", design)
            self.assertIn("竞拍讲解卡需要支持主播侧状态提示", design)
            self.assertTrue((task_dir / "design-result.json").exists())

    def test_start_designing_task_allows_planned_and_clears_plan_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir(parents=True)
            task_id = "task-redesign-from-planned"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = datetime.now().astimezone().isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "重新设计测试",
                        "status": "planned",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "重新设计测试",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(
                json.dumps({"repos": [{"id": "demo_repo", "path": str(repo_root), "status": "planned"}]}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (task_dir / "design.md").write_text("# Design\n\n- old design\n", encoding="utf-8")
            (task_dir / "plan.md").write_text("# Plan\n\n- old plan\n", encoding="utf-8")
            (task_dir / "plan.log").write_text("old plan log\n", encoding="utf-8")
            (task_dir / "plan-result.json").write_text('{"status":"planned"}\n', encoding="utf-8")

            status = start_designing_task(task_id, settings=settings)

            self.assertEqual(status, "designing")
            self.assertEqual(json.loads((task_dir / "task.json").read_text(encoding="utf-8"))["status"], "designing")
            self.assertEqual(json.loads((task_dir / "repos.json").read_text(encoding="utf-8"))["repos"][0]["status"], "designing")
            self.assertFalse((task_dir / "plan.md").exists())
            self.assertFalse((task_dir / "plan.log").exists())
            self.assertFalse((task_dir / "plan-result.json").exists())

    def test_start_designing_task_requires_bound_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            task_id = "task-design-no-repos"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = datetime.now().astimezone().isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "无仓库设计测试",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "无仓库设计测试",
                        "repo_count": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(json.dumps({"repos": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "design requires bound repos"):
                start_designing_task(task_id, settings=settings)

    def test_design_requires_bound_repos_even_with_skill_repo_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_root = Path(tmp) / "demo_repo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
            (repo_root / "app" / "auction_card").mkdir(parents=True)
            (repo_root / "app" / "auction_card" / "render_handler.go").write_text(
                "package auction_card\n\nfunc RenderAuctionCard() {}\n",
                encoding="utf-8",
            )
            context_dir = repo_root / ".livecoding" / "context"
            context_dir.mkdir(parents=True, exist_ok=True)
            (context_dir / "glossary.md").write_text(
                "| 业务术语 | 代码标识 | 说明 | 模块 |\n"
                "| --- | --- | --- | --- |\n"
                "| 竞拍奖励卡 | RenderAuctionCard | 竞拍奖励卡入口 | app/auction_card |\n",
                encoding="utf-8",
            )

            timestamp = datetime.now().astimezone()
            create_skill_package(
                settings,
                package_id="auction-reward-card-domain",
                description="包含竞拍奖励卡相关仓库线索",
                domain="auction_reward_card",
                references={
                    "domain.md": (
                        "## Summary\n\n"
                        "- 竞拍奖励卡的主逻辑位于主播侧渲染链路。\n"
                        f"- repo: demo_repo\n"
                        f"- code path: {repo_root}\n"
                    )
                },
            )

            task_id = "task-design-reference-discovery"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = timestamp.isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍奖励卡状态提示调整",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "竞拍奖励卡状态提示调整",
                        "repo_count": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(json.dumps({"repos": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (task_dir / "refine-skills-selection.json").write_text(
                json.dumps(
                    {
                        "selected_skill_ids": ["auction-reward-card-domain"],
                        "rejected_skill_ids": [],
                        "reason": "selected for refine",
                        "candidates": [],
                        "mode": "rule",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "refine-skills-read.md").write_text(
                "# Refine Skills Read\n\n- 竞拍奖励卡主链路与 demo_repo 强相关。\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text(
                "# PRD Refined\n\n"
                "## 需求概述\n\n"
                "- 竞拍奖励卡需要补充主播侧状态提示。\n\n"
                "## 功能点\n\n"
                "- 支持竞拍奖励卡展示主播侧状态提示。\n\n"
                "## 边界条件\n\n"
                "- 非竞拍场景不展示。\n\n"
                "## 验收标准\n\n"
                "- 状态提示展示正确。\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "design requires bound repos"):
                design_task(task_id, settings=settings)

    def test_design_requires_bound_repos_even_with_selected_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
            (repo_root / "app" / "auction_card").mkdir(parents=True)
            (repo_root / "app" / "auction_card" / "render_handler.go").write_text(
                "package auction_card\n\nfunc RenderAuctionCard() {}\n",
                encoding="utf-8",
            )
            context_dir = repo_root / ".livecoding" / "context"
            context_dir.mkdir(parents=True, exist_ok=True)
            (context_dir / "glossary.md").write_text(
                "| 业务术语 | 代码标识 | 说明 | 模块 |\n"
                "| --- | --- | --- | --- |\n"
                "| 竞拍奖励卡 | RenderAuctionCard | 竞拍奖励卡入口 | app/auction_card |\n",
                encoding="utf-8",
            )

            skill_store = SkillStore(settings)
            _name, package_root, _skill_path = skill_store.create_package(
                "auction-reward-card",
                description="竞拍奖励卡相关 skill。",
                domain="auction_reward_card",
            )
            (package_root / "SKILL.md").write_text(
                (
                    "---\n"
                    "name: auction-reward-card\n"
                    "description: 竞拍奖励卡相关 skill。\n"
                    "domain: auction_reward_card\n"
                    "---\n\n"
                    "# Overview\n\n"
                    "适用于竞拍奖励卡相关需求。\n"
                ),
                encoding="utf-8",
            )
            (package_root / "references" / "main-flow.md").write_text(
                f"## Main Flow\n\n- 主链路仓库位于 {repo_root}。\n",
                encoding="utf-8",
            )

            task_id = "task-design-skill-discovery"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = datetime.now().astimezone().isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍奖励卡状态提示调整",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "竞拍奖励卡状态提示调整",
                        "repo_count": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(json.dumps({"repos": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (task_dir / "refine-skills-selection.json").write_text(
                json.dumps(
                    {
                        "selected_skill_ids": ["auction-reward-card"],
                        "rejected_skill_ids": [],
                        "reason": "selected for refine",
                        "candidates": [],
                        "mode": "rule",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "refine-skills-read.md").write_text(
                "# Refine Skills Read\n\n- 竞拍奖励卡主链路与 skill package 强相关。\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text(
                "# PRD Refined\n\n"
                "## 需求概述\n\n"
                "- 竞拍奖励卡需要补充主播侧状态提示。\n\n"
                "## 功能点\n\n"
                "- 支持竞拍奖励卡展示主播侧状态提示。\n\n"
                "## 边界条件\n\n"
                "- 非竞拍场景不展示。\n\n"
                "## 验收标准\n\n"
                "- 状态提示展示正确。\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "design requires bound repos"):
                design_task(task_id, settings=settings)

    def test_design_requires_bound_repos_even_with_candidate_file_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_root = Path(tmp) / "candidate-file-repo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
            target_file = repo_root / "service" / "reward_card" / "render_service.go"
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(
                "package reward_card\n\nfunc RenderRewardCard() {}\n",
                encoding="utf-8",
            )

            timestamp = datetime.now().astimezone()
            create_skill_package(
                settings,
                package_id="reward-card-candidate-file",
                description="仅通过 candidate file 提供仓库线索",
                domain="reward_card",
                references={
                    "domain.md": (
                        "## Summary\n\n"
                        "- 奖励卡渲染链路在服务层。\n"
                        f"- candidate file: {target_file}\n"
                    )
                },
            )

            task_id = "task-design-candidate-file-discovery"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = timestamp.isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "奖励卡展示逻辑调整",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "奖励卡展示逻辑调整",
                        "repo_count": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(json.dumps({"repos": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (task_dir / "refine-skills-selection.json").write_text(
                json.dumps(
                    {
                        "selected_skill_ids": ["reward-card-candidate-file"],
                        "rejected_skill_ids": [],
                        "reason": "selected for refine",
                        "candidates": [],
                        "mode": "rule",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text(
                "# PRD Refined\n\n"
                "## 功能点\n\n"
                "- 调整奖励卡渲染逻辑。\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "design requires bound repos"):
                design_task(task_id, settings=settings)

    def test_design_requires_bound_repos_even_with_recent_history_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_root = Path(tmp) / "auction-card-repo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
            (repo_root / "app" / "auction_card").mkdir(parents=True)
            (repo_root / "app" / "auction_card" / "handler.go").write_text(
                "package auction_card\n\nfunc HandleAuctionCard() {}\n",
                encoding="utf-8",
            )

            timestamp = datetime.now().astimezone()
            history_task_dir = settings.task_root / "history-task"
            history_task_dir.mkdir(parents=True)
            history_now = timestamp.isoformat()
            (history_task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": "history-task",
                        "title": "历史任务",
                        "status": "designed",
                        "created_at": history_now,
                        "updated_at": history_now,
                        "source_type": "text",
                        "source_value": "历史任务",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (history_task_dir / "repos.json").write_text(
                json.dumps(
                    {"repos": [{"id": "auction-card-repo", "path": str(repo_root), "status": "designed"}]},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            create_skill_package(
                settings,
                package_id="auction-card-fuzzy-hint",
                description="repo hint 与历史 repo id 存在轻微格式差异",
                domain="auction_card",
                references={
                    "domain.md": (
                        "## Summary\n\n"
                        "- 主链路仍在 auction card repo。\n"
                        "- repo: auction_card_repo\n"
                    )
                },
            )

            task_id = "task-design-fuzzy-repo-hint"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = timestamp.isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍卡交互调整",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "竞拍卡交互调整",
                        "repo_count": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(json.dumps({"repos": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (task_dir / "refine-skills-selection.json").write_text(
                json.dumps(
                    {
                        "selected_skill_ids": ["auction-card-fuzzy-hint"],
                        "rejected_skill_ids": [],
                        "reason": "selected for refine",
                        "candidates": [],
                        "mode": "rule",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text(
                "# PRD Refined\n\n"
                "## 功能点\n\n"
                "- 调整竞拍卡交互逻辑。\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "design requires bound repos"):
                design_task(task_id, settings=settings)

    def test_design_requires_bound_repos_even_with_remote_repo_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            settings = make_settings(tmp_root)
            home_root = tmp_root / "home"
            repo_root = home_root / "go" / "src" / "code.byted.org" / "oec" / "live_shop"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
            (repo_root / "service" / "auction").mkdir(parents=True)
            (repo_root / "service" / "auction" / "handler.go").write_text(
                "package auction\n\nfunc HandleAuction() {}\n",
                encoding="utf-8",
            )

            timestamp = datetime.now().astimezone()
            create_skill_package(
                settings,
                package_id="auction-remote-repo-hint",
                description="仅给出 code.byted.org 形式的 repo hint",
                domain="auction_remote",
                references={
                    "main-flow.md": (
                        "## Summary\n\n"
                        "- 竞拍主链路在 live_shop。\n"
                        "- repo: code.byted.org/oec/live_shop\n"
                    )
                },
            )

            task_id = "task-design-remote-repo-hint"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = timestamp.isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍状态调整",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "竞拍状态调整",
                        "repo_count": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(json.dumps({"repos": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (task_dir / "refine-skills-selection.json").write_text(
                json.dumps(
                    {
                        "selected_skill_ids": ["auction-remote-repo-hint"],
                        "rejected_skill_ids": [],
                        "reason": "selected for refine",
                        "candidates": [],
                        "mode": "rule",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text(
                "# PRD Refined\n\n"
                "## 功能点\n\n"
                "- 调整竞拍状态展示。\n",
                encoding="utf-8",
            )

            from unittest.mock import patch

            with patch.dict("os.environ", {"GOPATH": str(home_root / "go")}):
                with self.assertRaisesRegex(ValueError, "design requires bound repos"):
                    design_task(task_id, settings=settings)

    def test_local_plan_writes_skills_selection_and_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_root = Path(tmp) / "repo"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "service" / "card_render").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n\nfunc ExplainCardHandler() {}\n",
                encoding="utf-8",
            )
            (repo_root / "service" / "card_render" / "render_service.go").write_text(
                "package card_render\n\nfunc RenderExplainCard() {}\n",
                encoding="utf-8",
            )
            context_dir = repo_root / ".livecoding" / "context"
            context_dir.mkdir(parents=True, exist_ok=True)
            (context_dir / "glossary.md").write_text(
                "| 业务术语 | 代码标识 | 说明 | 模块 |\n"
                "| --- | --- | --- | --- |\n"
                "| 竞拍讲解卡 | ExplainCardHandler | 竞拍讲解卡入口 | app/explain_card |\n",
                encoding="utf-8",
            )

            timestamp = datetime.now().astimezone()
            create_skill_package(
                settings,
                package_id="flow-auction-card-plan",
                description="主播侧状态提示的主链路说明",
                domain="auction_card",
                references={
                    "main-flow.md": (
                        "## Main Flow\n\n"
                        "- 主链路先进入 ExplainCardHandler，再下发状态提示。\n\n"
                        "## Risks\n\n"
                        "- 需要保持非竞拍态不展示。\n\n"
                        "## Validation\n\n"
                        "- 校验主播侧状态提示与现有讲解卡兼容。\n"
                    )
                },
            )

            task_id = "task-plan"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = timestamp.isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍讲解卡状态提示调整",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "竞拍讲解卡状态提示调整",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(
                json.dumps(
                    {
                        "repos": [
                            {
                                "id": "demo_repo",
                                "path": str(repo_root),
                                "status": "refined",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text(
                "# PRD Refined\n\n"
                "## 需求概述\n\n"
                "- 竞拍讲解卡需要支持主播侧状态提示。\n\n"
                "## 功能点\n\n"
                "- 支持竞拍讲解卡展示主播侧状态提示。\n\n"
                "## 边界条件\n\n"
                "- 非竞拍态不展示。\n\n"
                "## 交互与展示\n\n"
                "- 保持已有讲解卡样式。\n\n"
                "## 验收标准\n\n"
                "- 主播侧状态提示可正确展示。\n\n"
                "## 业务规则\n\n"
                "- 非竞拍态保持不展示。\n\n"
                "## 待确认问题\n\n"
                "- 是否需要兼容老版本样式。\n",
                encoding="utf-8",
            )

            design_status = design_task(task_id, settings=settings)
            status = plan_task(task_id, settings=settings)

            self.assertEqual(design_status, "designed")
            self.assertEqual(status, "planned")
            selection = json.loads((task_dir / "plan-skills-selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["selected_skill_ids"], ["flow-auction-card-plan"])
            work_items = json.loads((task_dir / "plan-work-items.json").read_text(encoding="utf-8"))
            self.assertTrue(work_items["work_items"])
            self.assertEqual(work_items["work_items"][0]["repo_id"], "demo_repo")
            validation = json.loads((task_dir / "plan-validation.json").read_text(encoding="utf-8"))
            self.assertTrue(validation["task_validations"])
            verify = json.loads((task_dir / "plan-verify.json").read_text(encoding="utf-8"))
            diagnosis = json.loads((task_dir / "plan-diagnosis.json").read_text(encoding="utf-8"))
            self.assertEqual(verify["stage"], "plan")
            self.assertEqual(verify["next_action"], "continue")
            self.assertEqual(diagnosis["stage"], "plan")
            self.assertTrue(diagnosis["ok"])
            brief = (task_dir / "plan-skills-brief.md").read_text(encoding="utf-8")
            self.assertIn("Plan Skills Brief", brief)
            self.assertIn("flow-auction-card-plan", brief)
            self.assertIn("决策边界", brief)
            self.assertIn("稳定规则", brief)
            self.assertIn("验证要点", brief)
            design = (task_dir / "design.md").read_text(encoding="utf-8")
            plan = (task_dir / "plan.md").read_text(encoding="utf-8")
            self.assertIn("## 改造点总览", design)
            self.assertIn("## 总体方案", design)
            self.assertIn("## 分仓库方案", design)
            self.assertIn("- 仓库：demo_repo", design)
            self.assertIn("- 角色定位：本次主改仓", design)
            self.assertIn("## 任务清单", plan)
            self.assertIn("## 执行顺序", plan)
            self.assertIn("最小范围验证通过", plan)

    def test_local_plan_can_use_skill_packages_without_legacy_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_root = Path(tmp) / "repo"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "service" / "card_render").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n\nfunc ExplainCardHandler() {}\n",
                encoding="utf-8",
            )
            (repo_root / "service" / "card_render" / "render_service.go").write_text(
                "package card_render\n\nfunc RenderExplainCard() {}\n",
                encoding="utf-8",
            )
            context_dir = repo_root / ".livecoding" / "context"
            context_dir.mkdir(parents=True, exist_ok=True)
            (context_dir / "glossary.md").write_text(
                "| 业务术语 | 代码标识 | 说明 | 模块 |\n"
                "| --- | --- | --- | --- |\n"
                "| 竞拍讲解卡 | ExplainCardHandler | 竞拍讲解卡入口 | app/explain_card |\n",
                encoding="utf-8",
            )

            skill_store = SkillStore(settings)
            _name, package_root, _skill_path = skill_store.create_package(
                "auction-popcard",
                description="处理竞拍讲解卡状态提示相关需求。",
                domain="auction_card",
            )
            (package_root / "SKILL.md").write_text(
                (
                    "---\n"
                    "name: auction-popcard\n"
                    "description: 处理竞拍讲解卡状态提示相关需求。\n"
                    "domain: auction_card\n"
                    "---\n\n"
                    "# Overview\n\n"
                    "适用于竞拍讲解卡状态提示的 design/plan。\n"
                ),
                encoding="utf-8",
            )
            (package_root / "references" / "domain.md").write_text(
                "## Summary\n\n- 竞拍讲解卡属于竞拍展示链路。\n\n## Risks\n\n- 非竞拍态不展示。\n",
                encoding="utf-8",
            )
            (package_root / "references" / "main-flow.md").write_text(
                "## Main Flow\n\n- 主链路先进入 ExplainCardHandler，再下发状态提示。\n\n## Validation\n\n- 校验主播侧状态提示与现有讲解卡兼容。\n",
                encoding="utf-8",
            )

            task_id = "task-plan-skill"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = datetime.now().astimezone().isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍讲解卡状态提示调整",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "竞拍讲解卡状态提示调整",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(
                json.dumps(
                    {
                        "repos": [
                            {
                                "id": "demo_repo",
                                "path": str(repo_root),
                                "status": "refined",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text(
                "# PRD Refined\n\n"
                "## 需求概述\n\n"
                "- 竞拍讲解卡需要支持主播侧状态提示。\n\n"
                "## 功能点\n\n"
                "- 支持竞拍讲解卡展示主播侧状态提示。\n\n"
                "## 边界条件\n\n"
                "- 非竞拍态不展示。\n\n"
                "## 交互与展示\n\n"
                "- 保持已有讲解卡样式。\n\n"
                "## 验收标准\n\n"
                "- 主播侧状态提示可正确展示。\n\n"
                "## 业务规则\n\n"
                "- 非竞拍态保持不展示。\n\n"
                "## 待确认问题\n\n"
                "- 是否需要兼容老版本样式。\n",
                encoding="utf-8",
            )

            design_status = design_task(task_id, settings=settings)
            status = plan_task(task_id, settings=settings)

            self.assertEqual(design_status, "designed")
            self.assertEqual(status, "planned")
            selection = json.loads((task_dir / "plan-skills-selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["selected_skill_ids"], ["auction-popcard"])
            brief = (task_dir / "plan-skills-brief.md").read_text(encoding="utf-8")
            self.assertIn("Plan Skills Brief", brief)
            self.assertIn("auction-popcard", brief)
            self.assertIn("决策边界", brief)
            self.assertIn("稳定规则", brief)

    def test_native_plan_runs_scope_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), plan_executor="native")
            repo_root = Path(tmp) / "repo"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n\nfunc ExplainCardHandler() {}\n",
                encoding="utf-8",
            )
            context_dir = repo_root / ".livecoding" / "context"
            context_dir.mkdir(parents=True, exist_ok=True)
            (context_dir / "glossary.md").write_text(
                "| 业务术语 | 代码标识 | 说明 | 模块 |\n"
                "| --- | --- | --- | --- |\n"
                "| 竞拍讲解卡 | ExplainCardHandler | 竞拍讲解卡入口 | app/explain_card |\n",
                encoding="utf-8",
            )

            timestamp = datetime.now().astimezone()
            create_skill_package(
                settings,
                package_id="flow-auction-card-plan",
                description="主播侧状态提示的主链路说明",
                domain="auction_card",
                references={
                    "main-flow.md": (
                        "## Main Flow\n\n"
                        "- 主链路先进入 ExplainCardHandler，再下发状态提示。\n\n"
                        "## Risks\n\n"
                        "- 需要保持非竞拍态不展示。\n\n"
                        "## Validation\n\n"
                        "- 校验主播侧状态提示与现有讲解卡兼容。\n"
                    )
                },
            )

            task_id = "task-plan-native"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = timestamp.isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍讲解卡状态提示调整",
                        "status": "refined",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "竞拍讲解卡状态提示调整",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(
                json.dumps({"repos": [{"id": "demo_repo", "path": str(repo_root), "status": "refined"}]}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text(
                "# PRD Refined\n\n"
                "## 需求概述\n\n"
                "- 竞拍讲解卡需要支持主播侧状态提示。\n\n"
                "## 功能点\n\n"
                "- 支持竞拍讲解卡展示主播侧状态提示。\n\n"
                "## 边界条件\n\n"
                "- 非竞拍态不展示。\n\n"
                "## 交互与展示\n\n"
                "- 保持已有讲解卡样式。\n\n"
                "## 验收标准\n\n"
                "- 主播侧状态提示可正确展示。\n\n"
                "## 业务规则\n\n"
                "- 非竞拍态保持不展示。\n\n"
                "## 待确认问题\n\n"
                "- 是否需要兼容老版本样式。\n",
                encoding="utf-8",
            )
            (task_dir / "design.md").write_text(
                "# Design\n\n"
                "## 改造点总览\n\n"
                "- 收敛讲解卡状态提示改造范围。\n\n"
                "## 总体方案\n\n"
                "- 优先收敛讲解卡状态提示边界。\n",
                encoding="utf-8",
            )
            (task_dir / "design-repo-binding.json").write_text(
                json.dumps(
                    {
                        "repo_bindings": [
                            {
                                "repo_id": "demo_repo",
                                "repo_path": str(repo_root),
                                "decision": "in_scope",
                                "scope_tier": "must_change",
                                "serves_change_points": [1],
                                "system_name": "demo_repo",
                                "responsibility": "demo_repo 承担主改职责。",
                                "change_summary": ["收敛讲解卡状态提示改造范围。"],
                                "boundaries": ["非竞拍态不展示"],
                                "candidate_dirs": ["app/explain_card"],
                                "candidate_files": ["demo_repo/app/explain_card/render_handler.go"],
                                "depends_on": [],
                                "parallelizable_with": [],
                                "confidence": "high",
                                "reason": "主链路入口在该 repo。",
                            }
                        ],
                        "missing_repos": [],
                        "decision_summary": "必须改动仓库：demo_repo",
                        "mode": "local",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "design-sections.json").write_text(
                json.dumps(
                    {
                        "system_change_points": ["收敛讲解卡状态提示改造范围"],
                        "solution_overview": "先在现有讲解卡入口范围内收敛改动。",
                        "system_changes": [],
                        "system_dependencies": [],
                        "critical_flows": [{"name": "主链路", "trigger": "ExplainCardHandler"}],
                        "protocol_changes": [],
                        "storage_config_changes": [],
                        "experiment_changes": [],
                        "qa_inputs": ["校验主播侧状态提示与现有样式兼容。"],
                        "staffing_estimate": {"summary": "单仓收敛为主"},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            task_meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
            task_meta["status"] = "designed"
            (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            from unittest.mock import patch

            def fake_run_agent(prompt: str, *_args, **_kwargs):
                if ".plan-task-outline-" in prompt:
                    path = prompt.split("- file: ", 1)[1].split("\n", 1)[0].strip()
                    Path(path).write_text(
                        json.dumps(
                            {
                                "task_units": [
                                    {
                                        "id": "W1",
                                        "title": "[demo_repo] 推进「竞拍讲解卡需要支持主播侧状态提示。」执行",
                                        "repo_id": "demo_repo",
                                        "task_type": "implementation",
                                        "serves_change_points": [1],
                                        "goal": "在 demo_repo 完成状态提示相关执行任务。",
                                        "scope_summary": ["仅覆盖主状态定义与入口适配"],
                                        "inputs": ["design-repo-binding.json"],
                                        "outputs": ["demo_repo 执行改动完成"],
                                        "done_definition": ["主链路逻辑落地"],
                                        "validation_focus": ["最小范围验证通过"],
                                        "risk_notes": ["避免破坏现有样式"],
                                    }
                                ]
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    return "ok"
                if ".plan-template-" in prompt:
                    path = prompt.split("- file: ", 1)[1].split("\n", 1)[0].strip()
                    Path(path).write_text(
                        "# Plan\n\n"
                        "## 任务清单\n"
                        "### W1 [demo_repo] 主执行任务\n"
                        "- 目标：先收敛 demo_repo 主改范围。\n"
                        "- 具体做什么：\n"
                        "  - 收敛 demo_repo 主改范围。\n\n"
                        "## 执行顺序\n"
                        "- W1\n\n"
                        "## 验证策略\n"
                        "- 最小范围验证通过。\n\n"
                        "## 风险与阻塞项\n"
                        "- 避免破坏现有样式。\n\n",
                        encoding="utf-8",
                    )
                    return "ok"
                if ".plan-verify-" in prompt:
                    path = prompt.split("- file: ", 1)[1].split("\n", 1)[0].strip()
                    Path(path).write_text(
                        json.dumps({"ok": True, "issues": [], "reason": "plan 结构完整"}, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    return "ok"
                raise AssertionError(prompt)

            with patch("coco_flow.clients.CocoACPClient.run_agent", side_effect=fake_run_agent) as run_agent_mock:
                status = plan_task(task_id, settings=settings)

            self.assertEqual(status, "planned")
            work_items = json.loads((task_dir / "plan-work-items.json").read_text(encoding="utf-8"))
            self.assertTrue(work_items["work_items"])
            self.assertEqual(run_agent_mock.call_count, 3)
            self.assertEqual(run_agent_mock.call_args_list[0].kwargs.get("fresh_session"), True)
            design = (task_dir / "design.md").read_text(encoding="utf-8")
            plan = (task_dir / "plan.md").read_text(encoding="utf-8")
            self.assertIn("## 改造点总览", design)
            self.assertIn("收敛讲解卡状态提示改造范围", design)
            self.assertIn("## 执行顺序", plan)
            self.assertIn("## 任务清单", plan)
            self.assertIn("最小范围验证通过", plan)


def create_skill_package(
    settings: Settings,
    *,
    package_id: str,
    description: str,
    domain: str,
    references: dict[str, str],
) -> Path:
    skill_store = SkillStore(settings)
    _name, package_root, _skill_path = skill_store.create_package(
        package_id,
        description=description,
        domain=domain,
    )
    (package_root / "SKILL.md").write_text(
        (
            "---\n"
            f"name: {package_id}\n"
            f"description: {description}\n"
            f"domain: {domain}\n"
            "---\n\n"
            "# Overview\n\n"
            f"适用于 {package_id} 相关需求。\n"
        ),
        encoding="utf-8",
    )
    for name, content in references.items():
        (package_root / "references" / name).write_text(content, encoding="utf-8")
    return package_root


if __name__ == "__main__":
    unittest.main()

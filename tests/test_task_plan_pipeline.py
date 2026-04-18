from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.engines.design.assignment import build_design_change_points_payload
from coco_flow.engines.design.binding import build_local_repo_binding
from coco_flow.engines.design.models import DesignPreparedInput
from coco_flow.engines.design.matrix import build_local_design_responsibility_matrix_payload
from coco_flow.engines.design.generate import build_design_sections_payload, generate_local_design_markdown
from coco_flow.engines.design.research import build_design_research_payload
from coco_flow.engines.plan_models import (
    ComplexityAssessment,
    ContextSnapshot,
    DesignResearchSignals,
    GlossaryEntry,
    RefinedSections,
    RepoResearch,
    RepoScope,
    ResearchFinding,
)
from coco_flow.models import KnowledgeDocument, KnowledgeEvidence
from coco_flow.services.tasks.design import design_task
from coco_flow.services.tasks.plan import plan_task


def make_settings(root: Path, plan_executor: str = "local") -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    knowledge_root = config_root / "knowledge"
    task_root.mkdir(parents=True, exist_ok=True)
    knowledge_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
        knowledge_root=knowledge_root,
        knowledge_executor="local",
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
                refine_knowledge_selection_payload={},
                refine_knowledge_read_markdown="",
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
                refine_knowledge_selection_payload={},
                refine_knowledge_read_markdown="",
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
                refine_knowledge_selection_payload={},
                refine_knowledge_read_markdown="",
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
            self.assertEqual(payload["validate_repos"][0]["repo_id"], "live_shopapi")
            self.assertEqual(payload["reference_repos"][0]["repo_id"], "live_common")

            markdown = generate_local_design_markdown(prepared, repo_binding_payload, payload, "")
            self.assertIn("#### Live Pack", markdown)
            self.assertIn("### 联动验证仓库", markdown)
            self.assertIn("live_shopapi", markdown)
            self.assertIn("### 参考链路", markdown)
            self.assertIn("live_common", markdown)

    def test_local_responsibility_matrix_prefers_state_aggregation_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prepared = DesignPreparedInput(
                task_dir=Path(tmp),
                task_id="task-design-matrix",
                title="统一成功态",
                refined_markdown="# PRD Refined\n\n- 统一成功态\n",
                input_meta={},
                refine_intent_payload={},
                refine_knowledge_selection_payload={},
                refine_knowledge_read_markdown="",
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
                refine_knowledge_selection_payload={},
                refine_knowledge_read_markdown="",
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
            self.assertEqual(by_repo["live_shopapi"]["scope_tier"], "validate_only")
            self.assertEqual(by_repo["live_common"]["scope_tier"], "reference_only")

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
                refine_knowledge_selection_payload={},
                refine_knowledge_read_markdown="",
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
                            "role_hint": "primary" if repo_id == "repo_a" else "supporting",
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

    def test_design_writes_design_markdown_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
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
            self.assertEqual(verify["ok"], True)
            design = (task_dir / "design.md").read_text(encoding="utf-8")
            self.assertIn("## 系统改造点", design)
            self.assertIn("## 方案设计", design)
            self.assertIn("竞拍讲解卡需要支持主播侧状态提示", design)
            self.assertTrue((task_dir / "design-result.json").exists())

    def test_design_can_infer_repos_from_selected_knowledge_when_repos_empty(self) -> None:
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

            timestamp = datetime.now().astimezone()
            write_knowledge_document(
                settings.knowledge_root / "domains" / "auction-reward-card-domain.md",
                KnowledgeDocument(
                    id="auction-reward-card-domain",
                    kind="domain",
                    status="approved",
                    title="竞拍奖励卡领域知识",
                    desc="包含竞拍奖励卡相关仓库线索",
                    domainId="auction_reward_card",
                    domainName="竞拍奖励卡",
                    engines=["refine"],
                    repos=["demo_repo"],
                    priority="high",
                    confidence="high",
                    updatedAt=timestamp.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body=(
                        "## Summary\n\n"
                        "- 竞拍奖励卡的主逻辑位于主播侧渲染链路。\n"
                    ),
                    evidence=KnowledgeEvidence(
                        inputTitle="",
                        inputDescription="",
                        repoMatches=["demo_repo"],
                        keywordMatches=["竞拍奖励卡"],
                        pathMatches=[str(repo_root)],
                        candidateFiles=[],
                        contextHits=[],
                        retrievalNotes=[],
                        openQuestions=[],
                    ),
                ),
            )

            task_id = "task-design-knowledge-discovery"
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
            (task_dir / "refine-knowledge-selection.json").write_text(
                json.dumps(
                    {
                        "selected_ids": ["auction-reward-card-domain"],
                        "rejected_ids": [],
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
            (task_dir / "refine-knowledge-read.md").write_text(
                "# Refine Knowledge Read\n\n- 竞拍奖励卡主链路与 demo_repo 强相关。\n",
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

            status = design_task(task_id, settings=settings)

            self.assertEqual(status, "designed")
            research = json.loads((task_dir / "design-research.json").read_text(encoding="utf-8"))
            self.assertEqual(research["mode"], "local")
            self.assertEqual(research["prefilter"]["candidate_repo_ids"], ["demo_repo"])
            repo_binding = json.loads((task_dir / "design-repo-binding.json").read_text(encoding="utf-8"))
            self.assertEqual(repo_binding["repo_bindings"][0]["repo_id"], "demo_repo")
            self.assertEqual(repo_binding["repo_bindings"][0]["decision"], "in_scope")
            design_log = (task_dir / "design.log").read_text(encoding="utf-8")
            self.assertIn("design_repo_discovery_ok: mode=knowledge_selection, bound=0, inferred=1", design_log)

    def test_design_can_infer_repo_from_knowledge_candidate_file(self) -> None:
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
            write_knowledge_document(
                settings.knowledge_root / "domains" / "reward-card-candidate-file.md",
                KnowledgeDocument(
                    id="reward-card-candidate-file",
                    kind="domain",
                    status="approved",
                    title="奖励卡文件线索",
                    desc="仅通过 candidateFiles 提供仓库线索",
                    domainId="reward_card",
                    domainName="奖励卡",
                    engines=["refine"],
                    repos=[],
                    priority="high",
                    confidence="high",
                    updatedAt=timestamp.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## Summary\n\n- 奖励卡渲染链路在服务层。\n",
                    evidence=KnowledgeEvidence(
                        inputTitle="",
                        inputDescription="",
                        repoMatches=[],
                        keywordMatches=["奖励卡"],
                        pathMatches=[],
                        candidateFiles=[str(target_file)],
                        contextHits=[],
                        retrievalNotes=[],
                        openQuestions=[],
                    ),
                ),
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
            (task_dir / "refine-knowledge-selection.json").write_text(
                json.dumps(
                    {
                        "selected_ids": ["reward-card-candidate-file"],
                        "rejected_ids": [],
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

            status = design_task(task_id, settings=settings)

            self.assertEqual(status, "designed")
            research = json.loads((task_dir / "design-research.json").read_text(encoding="utf-8"))
            self.assertEqual(research["prefilter"]["candidate_repo_ids"], ["candidate-file-repo"])

    def test_design_can_fuzzy_match_repo_hint_from_recent_history(self) -> None:
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

            write_knowledge_document(
                settings.knowledge_root / "domains" / "auction-card-fuzzy-hint.md",
                KnowledgeDocument(
                    id="auction-card-fuzzy-hint",
                    kind="domain",
                    status="approved",
                    title="竞拍卡仓库线索",
                    desc="repoMatches 与历史 repo id 存在轻微格式差异",
                    domainId="auction_card",
                    domainName="竞拍卡",
                    engines=["refine"],
                    repos=[],
                    priority="high",
                    confidence="high",
                    updatedAt=timestamp.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## Summary\n\n- 主链路仍在 auction card repo。\n",
                    evidence=KnowledgeEvidence(
                        inputTitle="",
                        inputDescription="",
                        repoMatches=["auction_card_repo"],
                        keywordMatches=["竞拍卡"],
                        pathMatches=[],
                        candidateFiles=[],
                        contextHits=[],
                        retrievalNotes=[],
                        openQuestions=[],
                    ),
                ),
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
            (task_dir / "refine-knowledge-selection.json").write_text(
                json.dumps(
                    {
                        "selected_ids": ["auction-card-fuzzy-hint"],
                        "rejected_ids": [],
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

            status = design_task(task_id, settings=settings)

            self.assertEqual(status, "designed")
            research = json.loads((task_dir / "design-research.json").read_text(encoding="utf-8"))
            self.assertEqual(research["prefilter"]["candidate_repo_ids"], ["auction-card-repo"])

    def test_design_can_resolve_remote_repo_hint_via_local_go_src_mirror(self) -> None:
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
            write_knowledge_document(
                settings.knowledge_root / "flows" / "auction-remote-repo-hint.md",
                KnowledgeDocument(
                    id="auction-remote-repo-hint",
                    kind="flow",
                    status="approved",
                    title="竞拍远端 repo 线索",
                    desc="仅给出 code.byted.org 形式的 repo hint",
                    domainId="auction_remote",
                    domainName="竞拍远端仓库",
                    engines=["refine"],
                    repos=["code.byted.org/oec/live_shop"],
                    priority="high",
                    confidence="high",
                    updatedAt=timestamp.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## Summary\n\n- 竞拍主链路在 live_shop。\n",
                    evidence=KnowledgeEvidence(
                        inputTitle="",
                        inputDescription="",
                        repoMatches=["code.byted.org/oec/live_shop"],
                        keywordMatches=["竞拍"],
                        pathMatches=[],
                        candidateFiles=[],
                        contextHits=[],
                        retrievalNotes=[],
                        openQuestions=[],
                    ),
                ),
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
            (task_dir / "refine-knowledge-selection.json").write_text(
                json.dumps(
                    {
                        "selected_ids": ["auction-remote-repo-hint"],
                        "rejected_ids": [],
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
                status = design_task(task_id, settings=settings)

            self.assertEqual(status, "designed")
            research = json.loads((task_dir / "design-research.json").read_text(encoding="utf-8"))
            self.assertEqual(research["prefilter"]["candidate_repo_ids"], ["live_shop"])

    def test_local_plan_writes_knowledge_selection_and_brief(self) -> None:
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
            write_knowledge_document(
                settings.knowledge_root / "flows" / "flow-auction-card-plan.md",
                KnowledgeDocument(
                    id="flow-auction-card-plan",
                    kind="flow",
                    status="approved",
                    title="竞拍讲解卡状态提示链路",
                    desc="主播侧状态提示的主链路说明",
                    domainId="auction_card",
                    domainName="竞拍讲解卡",
                    engines=["plan"],
                    repos=["demo_repo"],
                    priority="high",
                    confidence="high",
                    updatedAt=timestamp.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body=(
                        "## Main Flow\n\n"
                        "- 主链路先进入 ExplainCardHandler，再下发状态提示。\n\n"
                        "## Risks\n\n"
                        "- 需要保持非竞拍态不展示。\n\n"
                        "## Validation\n\n"
                        "- 校验主播侧状态提示与现有讲解卡兼容。\n"
                    ),
                    evidence=KnowledgeEvidence(
                        inputTitle="",
                        inputDescription="",
                        repoMatches=["demo_repo"],
                        keywordMatches=["竞拍讲解卡"],
                        pathMatches=[str(repo_root)],
                        candidateFiles=[],
                        contextHits=[],
                        retrievalNotes=[],
                        openQuestions=[],
                    ),
                ),
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
            selection = json.loads((task_dir / "plan-knowledge-selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["selected_ids"], ["flow-auction-card-plan"])
            execution = json.loads((task_dir / "plan-execution.json").read_text(encoding="utf-8"))
            self.assertTrue(execution["tasks"])
            self.assertEqual(execution["tasks"][0]["verify_rule"], ["受影响 package 编译通过。"])
            brief = (task_dir / "plan-knowledge-brief.md").read_text(encoding="utf-8")
            self.assertIn("Plan Knowledge Brief", brief)
            self.assertIn("竞拍讲解卡状态提示链路", brief)
            self.assertIn("决策边界", brief)
            self.assertIn("稳定规则", brief)
            self.assertIn("验证要点", brief)
            design = (task_dir / "design.md").read_text(encoding="utf-8")
            plan = (task_dir / "plan.md").read_text(encoding="utf-8")
            self.assertIn("## 系统改造点", design)
            self.assertIn("## 方案设计", design)
            self.assertIn("### 分系统改造", design)
            self.assertIn("- 仓库：demo_repo", design)
            self.assertIn("- scope_tier：must_change", design)
            self.assertIn("## 实施策略", plan)
            self.assertIn("## 任务拆分", plan)
            self.assertIn("受影响 package 编译通过", plan)

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
            write_knowledge_document(
                settings.knowledge_root / "flows" / "flow-auction-card-plan.md",
                KnowledgeDocument(
                    id="flow-auction-card-plan",
                    kind="flow",
                    status="approved",
                    title="竞拍讲解卡状态提示链路",
                    desc="主播侧状态提示的主链路说明",
                    domainId="auction_card",
                    domainName="竞拍讲解卡",
                    engines=["plan"],
                    repos=["demo_repo"],
                    priority="high",
                    confidence="high",
                    updatedAt=timestamp.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body=(
                        "## Main Flow\n\n"
                        "- 主链路先进入 ExplainCardHandler，再下发状态提示。\n\n"
                        "## Risks\n\n"
                        "- 需要保持非竞拍态不展示。\n\n"
                        "## Validation\n\n"
                        "- 校验主播侧状态提示与现有讲解卡兼容。\n"
                    ),
                    evidence=KnowledgeEvidence(
                        inputTitle="",
                        inputDescription="",
                        repoMatches=["demo_repo"],
                        keywordMatches=["竞拍讲解卡"],
                        pathMatches=[str(repo_root)],
                        candidateFiles=[],
                        contextHits=[],
                        retrievalNotes=[],
                        openQuestions=[],
                    ),
                ),
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
                "## 系统改造点\n\n"
                "- 收敛讲解卡状态提示改造范围。\n\n"
                "## 方案设计\n\n"
                "### 总体方案\n\n"
                "- 优先收敛讲解卡状态提示边界。\n",
                encoding="utf-8",
            )
            task_meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
            task_meta["status"] = "designed"
            (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            from unittest.mock import patch

            with patch(
                "coco_flow.clients.CocoACPClient.run_prompt_only",
                side_effect=[
                    json.dumps(
                        {
                            "summary": "优先收敛讲解卡状态提示边界",
                            "boundaries": ["非竞拍态不展示", "保持现有样式"],
                            "priorities": ["先收敛入口文件范围"],
                            "risk_focus": ["不要破坏现有讲解卡展示"],
                            "validation_focus": ["校验主播侧状态提示与现有样式兼容"],
                        }
                    ),
                    json.dumps({"ok": True, "issues": [], "reason": "design 结构完整"}),
                    (
                        "=== EXECUTION STRATEGY ===\n"
                        "- 优先围绕现有讲解卡入口文件收敛改动。\n"
                        "=== CANDIDATE FILES ===\n"
                        "- app/explain_card/render_handler.go\n"
                        "=== TASK STEPS ===\n"
                        "- 在 app/explain_card/render_handler.go 中补齐竞拍态状态提示逻辑。\n"
                        "=== BLOCKERS AND RISKS ===\n"
                        "- 保持非竞拍态不展示。\n"
                        "=== VALIDATION PLAN ===\n"
                        "- 受影响 package 编译通过。\n"
                    ),
                    json.dumps({"ok": True, "issues": [], "reason": "execution 结构完整"}),
                ],
            ) as run_prompt_only_mock, patch(
                "coco_flow.clients.CocoACPClient.run_readonly_agent",
                return_value=(
                    "=== SYSTEM CHANGE POINTS ===\n"
                    "- 收敛讲解卡状态提示改造范围。\n"
                    "=== SOLUTION OVERVIEW ===\n"
                    "- 先在现有讲解卡入口范围内收敛改动。\n"
                    "=== SYSTEM DEPENDENCIES ===\n"
                    "- 先完成讲解卡入口逻辑，再确认上下游展示兼容性。\n"
                    "=== CRITICAL FLOWS ===\n"
                    "- 主链路从 ExplainCardHandler 进入，再下发状态提示。\n"
                    "=== PROTOCOL CHANGES ===\n"
                    "- 当前未发现明确协议变更，保持接口兼容。\n"
                    "=== STORAGE CONFIG CHANGES ===\n"
                    "- 当前未发现明确存储或配置变更。\n"
                    "=== EXPERIMENT CHANGES ===\n"
                    "- 当前未发现明确实验变更。\n"
                    "=== QA INPUTS ===\n"
                    "- 校验主播侧状态提示与现有样式兼容。\n"
                    "=== STAFFING ESTIMATE ===\n"
                    "- 预计以后端单仓收敛为主，前后协调成本较低。\n"
                ),
            ) as run_readonly_agent_mock:
                status = plan_task(task_id, settings=settings)

            self.assertEqual(status, "planned")
            execution = json.loads((task_dir / "plan-execution.json").read_text(encoding="utf-8"))
            self.assertTrue(execution["tasks"])
            self.assertEqual(run_prompt_only_mock.call_args_list[0].kwargs.get("fresh_session"), True)
            design = (task_dir / "design.md").read_text(encoding="utf-8")
            plan = (task_dir / "plan.md").read_text(encoding="utf-8")
            self.assertIn("## 系统改造点", design)
            self.assertIn("收敛讲解卡状态提示改造范围", design)
            self.assertIn("## 执行顺序", plan)
            self.assertIn("## 实施策略", plan)
            self.assertIn("受影响 package 编译通过", plan)


if __name__ == "__main__":
    unittest.main()


def write_knowledge_document(path: Path, document: KnowledgeDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "kind": document.kind,
        "id": document.id,
        "title": document.title,
        "desc": document.desc,
        "status": document.status,
        "engines": document.engines,
        "domain_id": document.domainId,
        "domain_name": document.domainName,
        "repos": document.repos,
        "priority": document.priority,
        "confidence": document.confidence,
        "updated_at": document.updatedAt,
        "owner": document.owner,
        "evidence": document.evidence.model_dump(),
    }
    frontmatter = ["---"]
    for key, value in meta.items():
        serialized = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
        frontmatter.append(f"{key}: {serialized}")
    frontmatter.append("---")
    path.write_text("\n".join(frontmatter) + "\n\n" + document.body.rstrip() + "\n", encoding="utf-8")

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.engines.design.models import DesignPreparedInput
from coco_flow.engines.design.generate import build_design_sections_payload
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
            self.assertIn("仓库 demo_repo 主要承接", design)
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

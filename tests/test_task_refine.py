from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coco_flow.config import Settings
from coco_flow.engines.refine.generate import parse_refine_verify_output
from coco_flow.models import KnowledgeDocument, KnowledgeEvidence
from coco_flow.services.queries.skills import SkillStore
from coco_flow.services.tasks.refine import refine_task, start_refining_task


def make_settings(root: Path, refine_executor: str = "local") -> Settings:
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
        refine_executor=refine_executor,
        plan_executor="local",
        code_executor="local",
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class RefineTaskTest(unittest.TestCase):
    def test_start_refining_task_resets_downstream_outputs_and_repo_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            task_dir = build_task(
                settings=settings,
                task_id="task-reset",
                title="重跑 refine",
                source_markdown="# PRD Source\n\n重跑 refine。\n",
            )

            task_meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
            task_meta["status"] = "coded"
            (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (task_dir / "repos.json").write_text(
                json.dumps(
                    {
                        "repos": [
                            {"id": "demo_repo", "path": "/tmp/demo_repo", "status": "coded"},
                            {"id": "aux_repo", "path": "/tmp/aux_repo", "status": "planned"},
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            for name in (
                "prd-refined.md",
                "design.md",
                "design-result.json",
                "plan.md",
                "plan-result.json",
                "code-result.json",
                "code.log",
            ):
                (task_dir / name).write_text("stale\n", encoding="utf-8")
            for directory in ("code-results", "code-logs", "code-verify", "diffs"):
                path = task_dir / directory
                path.mkdir(parents=True, exist_ok=True)
                (path / "demo.txt").write_text("stale\n", encoding="utf-8")

            status = start_refining_task("task-reset", settings=settings)

            self.assertEqual(status, "refining")
            next_task_meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(next_task_meta["status"], "refining")
            self.assertFalse((task_dir / "prd-refined.md").exists())
            self.assertFalse((task_dir / "design.md").exists())
            self.assertFalse((task_dir / "plan.md").exists())
            self.assertFalse((task_dir / "code-result.json").exists())
            self.assertFalse((task_dir / "code-results").exists())
            self.assertFalse((task_dir / "diffs").exists())

            repos_meta = json.loads((task_dir / "repos.json").read_text(encoding="utf-8"))
            self.assertEqual([item["status"] for item in repos_meta["repos"]], ["initialized", "initialized"])

    def test_local_refine_outputs_new_five_sections_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            now = datetime.now().astimezone()
            write_knowledge_document(
                settings.knowledge_root / "domains" / "auction-domain.md",
                KnowledgeDocument(
                    id="auction-domain",
                    kind="domain",
                    status="approved",
                    title="竞拍讲解卡术语说明",
                    desc="解释竞拍讲解卡、竞拍态和展示边界。",
                    domainId="auction_pop_card",
                    domainName="竞拍讲解卡",
                    engines=["refine"],
                    repos=[],
                    priority="high",
                    confidence="high",
                    updatedAt=now.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body=(
                        "## Summary\n\n"
                        "- 竞拍讲解卡只在竞拍态相关场景下展示。\n"
                        "- 竞拍态提示属于展示口径的一部分。\n\n"
                        "## 风险\n\n"
                        "- 非竞拍态误展示会造成业务口径错误。\n"
                    ),
                    evidence=empty_evidence(),
                ),
            )

            task_dir = build_task(
                settings=settings,
                task_id="task-local",
                title="竞拍讲解卡增加竞拍态提示",
                source_markdown=(
                    "# PRD Source\n\n"
                    "- title: 竞拍讲解卡增加竞拍态提示\n"
                    "- source_type: text\n\n"
                    "---\n\n"
                    "竞拍讲解卡需要展示竞拍态提示。\n"
                    "需要确认非竞拍态是否展示。\n\n"
                    "## 研发补充说明\n\n"
                    "- 风险是误展示影响口径。\n"
                ),
            )

            status = refine_task("task-local", settings=settings)

            self.assertEqual(status, "refined")
            refined = (task_dir / "prd-refined.md").read_text(encoding="utf-8")
            self.assertIn("# 需求确认书", refined)
            self.assertIn("## 需求概述", refined)
            self.assertIn("## 具体变更点", refined)
            self.assertIn("## 验收标准", refined)
            self.assertIn("## 边界与非目标", refined)
            self.assertIn("## 待确认项", refined)
            self.assertTrue((task_dir / "refine-query.json").exists())
            self.assertTrue((task_dir / "refine-skills-selection.json").exists())
            self.assertTrue((task_dir / "refine-skills-read.md").exists())
            result = json.loads((task_dir / "refine-result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["skills_used"], True)
            self.assertEqual(result["selected_skill_ids"], ["auction-domain"])

    def test_local_refine_can_use_skill_packages_without_knowledge_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            skill_store = SkillStore(settings)
            _name, package_root, _skill_path = skill_store.create_package(
                "auction-popcard",
                description="处理竞拍讲解卡相关需求。",
                domain="auction_pop_card",
            )
            (package_root / "SKILL.md").write_text(
                (
                    "---\n"
                    "name: auction-popcard\n"
                    "description: 处理竞拍讲解卡相关需求。\n"
                    "domain: auction_pop_card\n"
                    "---\n\n"
                    "# Overview\n\n"
                    "适用于竞拍讲解卡相关 refine。\n"
                ),
                encoding="utf-8",
            )
            (package_root / "references" / "domain.md").write_text(
                "## Summary\n\n- 竞拍讲解卡只在竞拍态相关场景下展示。\n",
                encoding="utf-8",
            )
            (package_root / "references" / "main-flow.md").write_text(
                "## Summary\n\n- 非竞拍态误展示会造成业务口径错误。\n",
                encoding="utf-8",
            )

            task_dir = build_task(
                settings=settings,
                task_id="task-skill-local",
                title="竞拍讲解卡增加竞拍态提示",
                source_markdown=(
                    "# PRD Source\n\n"
                    "- title: 竞拍讲解卡增加竞拍态提示\n"
                    "- source_type: text\n\n"
                    "---\n\n"
                    "竞拍讲解卡需要展示竞拍态提示。\n"
                ),
            )

            status = refine_task("task-skill-local", settings=settings)

            self.assertEqual(status, "refined")
            self.assertTrue((task_dir / "refine-skills-selection.json").exists())
            self.assertTrue((task_dir / "refine-skills-read.md").exists())
            result = json.loads((task_dir / "refine-result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["selected_skill_ids"], ["auction-popcard"])
            selection = json.loads((task_dir / "refine-skills-selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["selected_skill_ids"], ["auction-popcard"])

    def test_native_refine_runs_new_multi_step_prompt_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), refine_executor="native")
            now = datetime.now().astimezone()
            write_knowledge_document(
                settings.knowledge_root / "flows" / "auction-flow.md",
                KnowledgeDocument(
                    id="auction-flow",
                    kind="flow",
                    status="approved",
                    title="竞拍讲解卡主链路",
                    desc="归纳竞拍讲解卡主链路和风险。",
                    domainId="auction_pop_card",
                    domainName="竞拍讲解卡",
                    engines=["refine"],
                    repos=[],
                    priority="high",
                    confidence="high",
                    updatedAt=now.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## Summary\n\n- 竞拍讲解卡属于竞拍展示链路。\n",
                    evidence=empty_evidence(),
                ),
            )
            task_dir = build_task(
                settings=settings,
                task_id="task-native",
                title="竞拍讲解卡需求",
                source_markdown=(
                    "# PRD Source\n\n"
                    "- title: 竞拍讲解卡需求\n"
                    "- source_type: text\n\n"
                    "---\n\n"
                    "竞拍讲解卡需要展示竞拍态提示。\n"
                ),
            )

            def run_agent_stub(*args, **kwargs):
                cwd = Path(kwargs["cwd"])
                if list(cwd.glob(".refine-intent-*.json")):
                    next(cwd.glob(".refine-intent-*.json")).write_text(
                        json.dumps(
                            {
                                "goal": "提炼竞拍讲解卡的竞拍态提示诉求",
                                "change_points": ["新增竞拍态提示"],
                                "terms": ["竞拍讲解卡", "竞拍态提示"],
                                "risks_seed": ["误展示导致口径错误"],
                                "discussion_seed": ["是否只在竞拍态展示"],
                                "boundary_seed": ["不默认扩展其他卡片"],
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-shortlist-*.json")):
                    next(cwd.glob(".refine-shortlist-*.json")).write_text(
                        json.dumps(
                            {"selected_skill_ids": ["auction-flow"], "rejected_skill_ids": [], "reason": "术语和风险最相关"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-skills-read-*.md")):
                    next(cwd.glob(".refine-skills-read-*.md")).write_text(
                        "## 术语解释\n- 竞拍讲解卡属于竞拍展示链路。\n\n## 稳定规则\n- 非竞拍态误展示会影响口径。\n\n## 冲突提醒\n- 当前未识别到明确冲突。\n\n## 边界提示\n- 仅围绕竞拍讲解卡。\n",
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-template-*.md")):
                    next(cwd.glob(".refine-template-*.md")).write_text(
                        "# 需求确认书\n\n"
                        "## 需求概述\n"
                        "- 提炼竞拍讲解卡的竞拍态提示诉求。\n\n"
                        "## 具体变更点\n"
                        "- 场景：竞拍讲解卡；当前行为：暂无竞拍态提示；期望行为：新增竞拍态提示。\n\n"
                        "## 验收标准\n"
                        "- 当进入竞拍态时，应该正确展示竞拍态提示。\n\n"
                        "## 边界与非目标\n"
                        "- 不默认扩展其他卡片。\n\n"
                        "## 待确认项\n"
                        "- 问题：是否只在竞拍态展示；当前假设：仅竞拍态展示；影响范围：竞拍讲解卡提示口径。\n",
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-verify-*.json")):
                    next(cwd.glob(".refine-verify-*.json")).write_text(
                        json.dumps(
                            {"ok": True, "issues": [], "missing_sections": [], "reason": "结构完整"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                return "done"

            with patch(
                "coco_flow.clients.CocoACPClient.run_agent",
                side_effect=run_agent_stub,
            ) as run_agent_mock:
                status = refine_task("task-native", settings=settings)

            self.assertEqual(status, "refined")
            self.assertEqual(run_agent_mock.call_count, 5)
            verify = json.loads((task_dir / "refine-verify.json").read_text(encoding="utf-8"))
            self.assertEqual(verify["ok"], True)
            selection = json.loads((task_dir / "refine-skills-selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["mode"], "llm_batch")
            self.assertEqual(selection["selected_skill_ids"], ["auction-flow"])

    def test_native_refine_shortlist_guard_rejects_low_relevance_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), refine_executor="native")
            now = datetime.now().astimezone()
            write_knowledge_document(
                settings.knowledge_root / "flows" / "auction-flow.md",
                KnowledgeDocument(
                    id="auction-flow",
                    kind="flow",
                    status="approved",
                    title="竞拍讲解卡主链路",
                    desc="归纳竞拍讲解卡主链路和风险。",
                    domainId="auction_pop_card",
                    domainName="竞拍讲解卡",
                    engines=["refine"],
                    repos=[],
                    priority="high",
                    confidence="high",
                    updatedAt=now.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## Summary\n\n- 竞拍讲解卡属于竞拍展示链路。\n",
                    evidence=empty_evidence(),
                ),
            )
            task_dir = build_task(
                settings=settings,
                task_id="task-low-relevance",
                title="两数之和 leetcode golang",
                source_markdown=(
                    "# PRD Source\n\n"
                    "- title: 两数之和 leetcode golang\n"
                    "- source_type: text\n\n"
                    "---\n\n"
                    "给仓库添加两数之和的leetcode算法实现。\n"
                ),
            )

            def run_agent_stub(*args, **kwargs):
                cwd = Path(kwargs["cwd"])
                if list(cwd.glob(".refine-intent-*.json")):
                    next(cwd.glob(".refine-intent-*.json")).write_text(
                        json.dumps(
                            {
                                "goal": "给仓库添加两数之和的leetcode算法实现",
                                "change_points": ["新增两数之和算法实现"],
                                "terms": ["两数之和", "leetcode", "golang"],
                                "risks_seed": [],
                                "discussion_seed": [],
                                "boundary_seed": [],
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-shortlist-*.json")):
                    next(cwd.glob(".refine-shortlist-*.json")).write_text(
                        json.dumps(
                            {"selected_skill_ids": ["auction-flow"], "rejected_skill_ids": [], "reason": "只有这一篇候选"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-template-*.md")):
                    next(cwd.glob(".refine-template-*.md")).write_text(
                        "# 需求确认书\n\n"
                        "## 需求概述\n"
                        "- 给仓库添加两数之和的算法实现。\n\n"
                        "## 具体变更点\n"
                        "- 场景：算法题实现；当前行为：仓库内暂无对应实现；期望行为：补齐两数之和算法。\n\n"
                        "## 验收标准\n"
                        "- 当输入合法测试样例时，应该返回正确结果。\n\n"
                        "## 边界与非目标\n"
                        "- 仅围绕当前输入明确提到的需求范围推进，不默认扩展到相邻能力。\n\n"
                        "## 待确认项\n"
                        "- 问题：是否需要补测试；当前假设：当前阶段先不补；影响范围：算法实现验证深度。\n",
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-verify-*.json")):
                    next(cwd.glob(".refine-verify-*.json")).write_text(
                        json.dumps(
                            {"ok": True, "issues": [], "missing_sections": [], "reason": "结构完整"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                return "done"

            with patch("coco_flow.clients.CocoACPClient.run_agent", side_effect=run_agent_stub) as run_agent_mock:
                status = refine_task("task-low-relevance", settings=settings)

            self.assertEqual(status, "refined")
            self.assertEqual(run_agent_mock.call_count, 4)
            selection = json.loads((task_dir / "refine-skills-selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["mode"], "llm_empty")
            self.assertEqual(selection["selected_skill_ids"], [])
            self.assertFalse((task_dir / "refine-skills-read.md").exists())

    def test_native_refine_falls_back_when_verify_rejects_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), refine_executor="native")
            now = datetime.now().astimezone()
            write_knowledge_document(
                settings.knowledge_root / "flows" / "auction-flow.md",
                KnowledgeDocument(
                    id="auction-flow",
                    kind="flow",
                    status="approved",
                    title="竞拍讲解卡主链路",
                    desc="归纳竞拍讲解卡主链路和风险。",
                    domainId="auction_pop_card",
                    domainName="竞拍讲解卡",
                    engines=["refine"],
                    repos=[],
                    priority="high",
                    confidence="high",
                    updatedAt=now.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## Summary\n\n- 竞拍讲解卡属于竞拍展示链路。\n",
                    evidence=empty_evidence(),
                ),
            )
            task_dir = build_task(
                settings=settings,
                task_id="task-rewrite",
                title="竞拍讲解卡需求",
                source_markdown=(
                    "# PRD Source\n\n"
                    "- title: 竞拍讲解卡需求\n"
                    "- source_type: text\n\n"
                    "---\n\n"
                    "竞拍讲解卡需要展示竞拍态提示。\n"
                ),
            )

            def run_agent_stub(*args, **kwargs):
                cwd = Path(kwargs["cwd"])
                if list(cwd.glob(".refine-intent-*.json")):
                    next(cwd.glob(".refine-intent-*.json")).write_text(
                        json.dumps(
                            {
                                "goal": "提炼竞拍讲解卡的竞拍态提示诉求",
                                "change_points": ["新增竞拍态提示"],
                                "terms": ["竞拍讲解卡", "竞拍态提示"],
                                "risks_seed": ["误展示导致口径错误"],
                                "discussion_seed": ["是否只在竞拍态展示"],
                                "boundary_seed": ["不默认扩展其他卡片"],
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-shortlist-*.json")):
                    next(cwd.glob(".refine-shortlist-*.json")).write_text(
                        json.dumps(
                            {"selected_skill_ids": ["auction-flow"], "rejected_skill_ids": [], "reason": "术语和风险最相关"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-skills-read-*.md")):
                    next(cwd.glob(".refine-skills-read-*.md")).write_text(
                        "## 术语解释\n- 竞拍讲解卡属于竞拍展示链路。\n\n## 稳定规则\n- 仅围绕竞拍讲解卡。\n\n## 冲突提醒\n- 当前未识别到明确冲突。\n\n## 边界提示\n- 不默认扩展其他卡片。\n",
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-template-*.md")):
                    next(cwd.glob(".refine-template-*.md")).write_text(
                        "# 需求确认书\n\n"
                        "## 需求概述\n"
                        "- 提炼竞拍讲解卡的竞拍态提示诉求。\n\n"
                        "## 具体变更点\n"
                        "- 场景：竞拍讲解卡；当前行为：暂无竞拍态提示；期望行为：新增竞拍态提示。\n\n"
                        "## 验收标准\n"
                        "- 当进入竞拍态时，应该正确展示竞拍态提示。\n\n"
                        "## 边界与非目标\n"
                        "- 不默认扩展其他卡片。\n\n"
                        "## 待确认项\n"
                        "- 问题：是否只在竞拍态展示；当前假设：仅竞拍态展示；影响范围：竞拍讲解卡提示口径。\n",
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-verify-*.json")):
                    next(cwd.glob(".refine-verify-*.json")).write_text(
                        json.dumps(
                            {"ok": False, "issues": ["风险提示越界"], "missing_sections": [], "reason": "风险项不收敛"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                return "done"

            with patch(
                "coco_flow.clients.CocoACPClient.run_agent",
                side_effect=run_agent_stub,
            ) as run_agent_mock:
                status = refine_task("task-rewrite", settings=settings)

            self.assertEqual(status, "refined")
            self.assertEqual(run_agent_mock.call_count, 5)
            verify = json.loads((task_dir / "refine-verify.json").read_text(encoding="utf-8"))
            self.assertEqual(verify["ok"], False)
            self.assertEqual(verify["issues"], ["风险提示越界"])

    def test_verify_failure_before_fallback_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), refine_executor="native")
            now = datetime.now().astimezone()
            write_knowledge_document(
                settings.knowledge_root / "flows" / "auction-flow.md",
                KnowledgeDocument(
                    id="auction-flow",
                    kind="flow",
                    status="approved",
                    title="竞拍讲解卡主链路",
                    desc="归纳竞拍讲解卡主链路和风险。",
                    domainId="auction_pop_card",
                    domainName="竞拍讲解卡",
                    engines=["refine"],
                    repos=[],
                    priority="high",
                    confidence="high",
                    updatedAt=now.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## Summary\n\n- 竞拍讲解卡属于竞拍展示链路。\n",
                    evidence=empty_evidence(),
                ),
            )
            task_dir = build_task(
                settings=settings,
                task_id="task-verify-fallback",
                title="竞拍讲解卡需求",
                source_markdown=(
                    "# PRD Source\n\n"
                    "- title: 竞拍讲解卡需求\n"
                    "- source_type: text\n\n"
                    "---\n\n"
                    "竞拍讲解卡需要展示竞拍态提示。\n"
                ),
            )

            def run_agent_stub(*args, **kwargs):
                cwd = Path(kwargs["cwd"])
                if list(cwd.glob(".refine-intent-*.json")):
                    next(cwd.glob(".refine-intent-*.json")).write_text(
                        json.dumps(
                            {
                                "goal": "提炼竞拍讲解卡的竞拍态提示诉求",
                                "change_points": ["新增竞拍态提示"],
                                "terms": ["竞拍讲解卡", "竞拍态提示"],
                                "risks_seed": ["误展示导致口径错误"],
                                "discussion_seed": ["是否只在竞拍态展示"],
                                "boundary_seed": ["不默认扩展其他卡片"],
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-shortlist-*.json")):
                    next(cwd.glob(".refine-shortlist-*.json")).write_text(
                        json.dumps(
                            {"selected_skill_ids": ["auction-flow"], "rejected_skill_ids": [], "reason": "术语和风险最相关"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-skills-read-*.md")):
                    next(cwd.glob(".refine-skills-read-*.md")).write_text(
                        "## 术语解释\n- 竞拍讲解卡属于竞拍展示链路。\n\n## 稳定规则\n- 仅围绕竞拍讲解卡。\n\n## 冲突提醒\n- 当前未识别到明确冲突。\n\n## 边界提示\n- 不默认扩展其他卡片。\n",
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-template-*.md")):
                    next(cwd.glob(".refine-template-*.md")).write_text(
                        "# 需求确认书\n\n"
                        "## 需求概述\n"
                        "- 初稿概述。\n\n"
                        "## 具体变更点\n"
                        "- 场景：初稿场景；当前行为：初稿当前行为；期望行为：初稿期望行为。\n\n"
                        "## 验收标准\n"
                        "- 当验证初稿时，应该满足基本结构要求。\n\n"
                        "## 边界与非目标\n"
                        "- 初稿边界。\n\n"
                        "## 待确认项\n"
                        "- 问题：初稿讨论点；当前假设：待继续完善；影响范围：初稿质量。\n",
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-verify-*.json")):
                    next(cwd.glob(".refine-verify-*.json")).write_text(
                        json.dumps(
                            {"ok": False, "issues": ["需要重写"], "missing_sections": [], "reason": "初稿不理想"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                return "done"

            with patch(
                "coco_flow.clients.CocoACPClient.run_agent",
                side_effect=run_agent_stub,
            ):
                status = refine_task("task-verify-fallback", settings=settings)

            self.assertEqual(status, "refined")
            verify = json.loads((task_dir / "refine-verify.json").read_text(encoding="utf-8"))
            self.assertEqual(verify["ok"], False)
            self.assertEqual(verify["issues"], ["需要重写"])

    def test_plan_research_can_parse_new_refined_sections(self) -> None:
        from coco_flow.engines.shared.research import parse_refined_sections

        sections = parse_refined_sections(
            "# 需求确认书\n\n"
            "## 需求概述\n- 统一规则口径\n\n"
            "## 具体变更点\n- 场景：竞拍讲解卡；当前行为：旧提示口径不一致；期望行为：统一规则口径。\n\n"
            "## 验收标准\n- 当进入竞拍态时，应该展示统一提示。\n\n"
            "## 边界与非目标\n- 不处理非竞拍卡\n"
        )

        self.assertIn("统一规则口径", sections.change_scope)
        self.assertIn("不处理非竞拍卡", sections.non_goals)
        self.assertIn("当进入竞拍态时，应该展示统一提示。", sections.acceptance_criteria)

    def test_parse_refine_verify_output_accepts_fenced_json(self) -> None:
        payload = parse_refine_verify_output(
            '```json\n{"ok": true, "issues": [], "missing_sections": [], "reason": "结构完整"}\n```'
        )
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["reason"], "结构完整")

    def test_native_refine_accepts_valid_verify_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), refine_executor="native")
            now = datetime.now().astimezone()
            write_knowledge_document(
                settings.knowledge_root / "flows" / "auction-flow.md",
                KnowledgeDocument(
                    id="auction-flow",
                    kind="flow",
                    status="approved",
                    title="竞拍讲解卡主链路",
                    desc="归纳竞拍讲解卡主链路和风险。",
                    domainId="auction_pop_card",
                    domainName="竞拍讲解卡",
                    engines=["refine"],
                    repos=[],
                    priority="high",
                    confidence="high",
                    updatedAt=now.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## Summary\n\n- 竞拍讲解卡属于竞拍展示链路。\n",
                    evidence=empty_evidence(),
                ),
            )
            build_task(
                settings=settings,
                task_id="task-repair",
                title="竞拍讲解卡需求",
                source_markdown=(
                    "# PRD Source\n\n"
                    "- title: 竞拍讲解卡需求\n"
                    "- source_type: text\n\n"
                    "---\n\n"
                    "竞拍讲解卡需要展示竞拍态提示。\n"
                ),
            )

            def run_agent_stub(*args, **kwargs):
                cwd = Path(kwargs["cwd"])
                if list(cwd.glob(".refine-intent-*.json")):
                    next(cwd.glob(".refine-intent-*.json")).write_text(
                        json.dumps(
                            {
                                "goal": "提炼竞拍讲解卡的竞拍态提示诉求",
                                "change_points": ["新增竞拍态提示"],
                                "terms": ["竞拍讲解卡", "竞拍态提示"],
                                "risks_seed": ["误展示导致口径错误"],
                                "discussion_seed": ["是否只在竞拍态展示"],
                                "boundary_seed": ["不默认扩展其他卡片"],
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-shortlist-*.json")):
                    next(cwd.glob(".refine-shortlist-*.json")).write_text(
                        json.dumps(
                            {"selected_skill_ids": ["auction-flow"], "rejected_skill_ids": [], "reason": "术语和风险最相关"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-skills-read-*.md")):
                    next(cwd.glob(".refine-skills-read-*.md")).write_text(
                        "## 术语解释\n- 竞拍讲解卡属于竞拍展示链路。\n\n## 稳定规则\n- 非竞拍态误展示会影响口径。\n\n## 冲突提醒\n- 当前未识别到明确冲突。\n\n## 边界提示\n- 不默认扩展其他卡片。\n",
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-template-*.md")):
                    next(cwd.glob(".refine-template-*.md")).write_text(
                        "# 需求确认书\n\n"
                        "## 需求概述\n"
                        "- 提炼竞拍讲解卡的竞拍态提示诉求。\n\n"
                        "## 具体变更点\n"
                        "- 场景：竞拍讲解卡；当前行为：暂无竞拍态提示；期望行为：新增竞拍态提示。\n\n"
                        "## 验收标准\n"
                        "- 当进入竞拍态时，应该正确展示竞拍态提示。\n\n"
                        "## 边界与非目标\n"
                        "- 不默认扩展其他卡片。\n\n"
                        "## 待确认项\n"
                        "- 问题：是否只在竞拍态展示；当前假设：仅竞拍态展示；影响范围：竞拍讲解卡提示口径。\n",
                        encoding="utf-8",
                    )
                elif list(cwd.glob(".refine-verify-*.json")):
                    next(cwd.glob(".refine-verify-*.json")).write_text(
                        json.dumps(
                            {"ok": True, "issues": [], "missing_sections": [], "reason": "结构完整"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                return "done"

            with patch(
                "coco_flow.clients.CocoACPClient.run_agent",
                side_effect=run_agent_stub,
            ) as run_agent_mock:
                status = refine_task("task-repair", settings=settings)

            self.assertEqual(status, "refined")
            self.assertEqual(run_agent_mock.call_count, 5)


def build_task(*, settings: Settings, task_id: str, title: str, source_markdown: str) -> Path:
    task_dir = settings.task_root / task_id
    task_dir.mkdir(parents=True)
    now = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "title": title,
                "status": "input_ready",
                "created_at": now,
                "updated_at": now,
                "source_type": "text",
                "source_value": title,
                "repo_count": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "repos.json").write_text(json.dumps({"repos": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (task_dir / "input.json").write_text(
        json.dumps(
            {
                "title": title,
                "title_explicit": True,
                "source_input": title,
                "supplement": "- 风险是误展示影响口径。",
                "source_type": "text",
                "status": "input_ready",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "source.json").write_text(
        json.dumps({"type": "text", "title": title}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_dir / "prd.source.md").write_text(source_markdown, encoding="utf-8")
    return task_dir


def empty_evidence() -> KnowledgeEvidence:
    return KnowledgeEvidence(
        inputTitle="",
        inputDescription="",
        repoMatches=[],
        keywordMatches=[],
        pathMatches=[],
        candidateFiles=[],
        contextHits=[],
        retrievalNotes=[],
        openQuestions=[],
    )


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


if __name__ == "__main__":
    unittest.main()

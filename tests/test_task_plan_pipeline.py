from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.models import KnowledgeDocument, KnowledgeEvidence
from coco_flow.services.tasks.plan import plan_task


def make_settings(root: Path) -> Settings:
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
        plan_executor="local",
        code_executor="local",
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class PlanTaskPipelineTest(unittest.TestCase):
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
                    traceId="trace-plan-1",
                    kind="flow",
                    status="approved",
                    title="竞拍讲解卡状态提示链路",
                    desc="主播侧状态提示的主链路说明",
                    domainId="auction_card",
                    domainName="竞拍讲解卡",
                    engines=["plan"],
                    repos=["demo_repo"],
                    paths=[str(repo_root)],
                    keywords=["竞拍讲解卡", "状态提示", "ExplainCardHandler"],
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

            status = plan_task(task_id, settings=settings)

            self.assertEqual(status, "planned")
            selection = json.loads((task_dir / "plan-knowledge-selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["selected_ids"], ["flow-auction-card-plan"])
            brief = (task_dir / "plan-knowledge-brief.md").read_text(encoding="utf-8")
            self.assertIn("Plan Knowledge Brief", brief)
            self.assertIn("竞拍讲解卡状态提示链路", brief)
            self.assertIn("决策边界", brief)
            self.assertIn("稳定规则", brief)
            self.assertIn("验证要点", brief)
            design = (task_dir / "design.md").read_text(encoding="utf-8")
            plan = (task_dir / "plan.md").read_text(encoding="utf-8")
            self.assertIn("竞拍讲解卡状态提示链路", design)
            self.assertIn("竞拍讲解卡状态提示链路", plan)


if __name__ == "__main__":
    unittest.main()


def write_knowledge_document(path: Path, document: KnowledgeDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "kind": document.kind,
        "id": document.id,
        "trace_id": document.traceId,
        "title": document.title,
        "desc": document.desc,
        "status": document.status,
        "engines": document.engines,
        "domain_id": document.domainId,
        "domain_name": document.domainName,
        "repos": document.repos,
        "paths": document.paths,
        "keywords": document.keywords,
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

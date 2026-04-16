from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.models import KnowledgeDocument, KnowledgeEvidence
from coco_flow.services.tasks.refine import refine_task


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
    def test_pending_lark_source_keeps_initialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            task_id = "task-pending"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = datetime.now().astimezone().isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "飞书需求",
                        "status": "initialized",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "lark_doc",
                        "source_value": "https://example.feishu.cn/wiki/abc123",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            (task_dir / "source.json").write_text(
                json.dumps(
                    {
                        "type": "lark_doc",
                        "title": "飞书需求",
                        "url": "https://example.feishu.cn/wiki/abc123",
                        "doc_token": "abc123",
                        "fetch_error": "lark-cli 不可用",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            (task_dir / "prd.source.md").write_text(
                "# PRD Source\n\n"
                "- source_type: lark_doc\n"
                "- url: https://example.feishu.cn/wiki/abc123\n"
                "- doc_token: abc123\n"
                "- fetched_at: 2026-04-14T00:00:00+08:00\n\n"
                "---\n\n"
                "尚未自动拉取该来源的正文内容，请稍后补充。\n"
            )

            status = refine_task(task_id, settings=settings)

            self.assertEqual(status, "initialized")
            refined = (task_dir / "prd-refined.md").read_text()
            self.assertIn("状态：待补充源内容", refined)
            self.assertIn("lark-cli 不可用", refined)
            self.assertIn("npm install -g @larksuite/cli", refined)
            self.assertIn("lark-cli auth login --recommend", refined)
            task_meta = json.loads((task_dir / "task.json").read_text())
            self.assertEqual(task_meta["status"], "initialized")
            result = json.loads((task_dir / "refine-result.json").read_text())
            self.assertIn("refine-intent.json", result["intermediate_artifacts"])

    def test_local_refine_writes_intent_and_knowledge_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_root = Path(tmp) / "repo"
            timestamp = datetime.now().astimezone()
            now_iso = timestamp.isoformat()
            now_display = timestamp.strftime("%Y-%m-%d %H:%M")
            context_dir = repo_root / ".livecoding" / "context"
            context_dir.mkdir(parents=True, exist_ok=True)
            (context_dir / "glossary.md").write_text(
                "# Glossary\n\n- 竞拍讲解卡：直播间竞拍讲解卡片组件。\n",
                encoding="utf-8",
            )
            (context_dir / "business-rules.md").write_text(
                "# Rules\n\n- 默认只在竞拍中展示，非竞拍态不可见。\n",
                encoding="utf-8",
            )
            write_knowledge_document(
                settings.knowledge_root / "domains" / "domain-auction-card.md",
                KnowledgeDocument(
                    id="domain-auction-card",
                    traceId="trace-1",
                    kind="domain",
                    status="approved",
                    title="竞拍讲解卡领域说明",
                    desc="竞拍讲解卡在竞拍态的业务定义",
                    domainId="auction_card",
                    domainName="竞拍讲解卡",
                    engines=["refine"],
                    repos=["demo_repo"],
                    paths=[str(repo_root)],
                    keywords=["竞拍讲解卡", "竞拍"],
                    priority="high",
                    confidence="high",
                    updatedAt=now_display,
                    owner="tester",
                    body="## 术语定义\n\n- 竞拍讲解卡仅在竞拍态展示。\n\n## 边界\n\n- 非竞拍态默认不展示。\n",
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

            task_id = "task-local"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍讲解卡表达层调整",
                        "status": "initialized",
                        "created_at": now_iso,
                        "updated_at": now_iso,
                        "source_type": "text",
                        "source_value": "竞拍讲解卡在竞拍中展示，需要支持主播侧状态提示。",
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
                                "status": "initialized",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "source.json").write_text(
                json.dumps(
                    {
                        "type": "text",
                        "title": "竞拍讲解卡表达层调整",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd.source.md").write_text(
                "# PRD Source\n\n---\n\n"
                "竞拍讲解卡在竞拍中展示，需要支持主播侧状态提示，并兼容已有讲解卡样式。\n"
                "需要确认非竞拍态是否展示。\n",
                encoding="utf-8",
            )

            status = refine_task(task_id, settings=settings)

            self.assertEqual(status, "refined")
            intent = json.loads((task_dir / "refine-intent.json").read_text(encoding="utf-8"))
            self.assertEqual(intent["title"], "竞拍讲解卡表达层调整")
            self.assertTrue(intent["goal"])
            brief = (task_dir / "refine-knowledge-brief.md").read_text(encoding="utf-8")
            self.assertIn("Refine Knowledge Brief", brief)
            self.assertIn("glossary.md", brief)
            self.assertIn("竞拍讲解卡领域说明", brief)
            selection = json.loads((task_dir / "refine-knowledge-selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["selected_ids"], ["domain-auction-card"])
            result = json.loads((task_dir / "refine-result.json").read_text(encoding="utf-8"))
            self.assertIn("refine-intent.json", result["intermediate_artifacts"])
            self.assertIn("refine-knowledge-selection.json", result["intermediate_artifacts"])
            self.assertIn("refine-knowledge-brief.md", result["intermediate_artifacts"])

    def test_native_refine_adjudicates_selected_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), refine_executor="native")
            repo_root = Path(tmp) / "repo"
            timestamp = datetime.now().astimezone()
            context_dir = repo_root / ".livecoding" / "context"
            context_dir.mkdir(parents=True, exist_ok=True)
            (context_dir / "glossary.md").write_text("# Glossary\n\n- 竞拍讲解卡：直播间讲解卡。\n", encoding="utf-8")

            write_knowledge_document(
                settings.knowledge_root / "domains" / "domain-auction-card.md",
                KnowledgeDocument(
                    id="domain-auction-card",
                    traceId="trace-1",
                    kind="domain",
                    status="approved",
                    title="竞拍讲解卡领域说明",
                    desc="竞拍态定义",
                    domainId="auction_card",
                    domainName="竞拍讲解卡",
                    engines=["refine"],
                    repos=["demo_repo"],
                    paths=[str(repo_root)],
                    keywords=["竞拍讲解卡", "竞拍"],
                    priority="high",
                    confidence="high",
                    updatedAt=timestamp.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## 术语定义\n\n- 竞拍讲解卡仅在竞拍态展示。\n",
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
            write_knowledge_document(
                settings.knowledge_root / "flows" / "flow-weak.md",
                KnowledgeDocument(
                    id="flow-weak",
                    traceId="trace-2",
                    kind="flow",
                    status="approved",
                    title="弱相关链路",
                    desc="实现链路细节",
                    domainId="auction_card",
                    domainName="竞拍讲解卡",
                    engines=["refine"],
                    repos=["demo_repo"],
                    paths=[str(repo_root)],
                    keywords=["handler", "render"],
                    priority="medium",
                    confidence="medium",
                    updatedAt=timestamp.strftime("%Y-%m-%d %H:%M"),
                    owner="tester",
                    body="## Main Flow\n\n- ExplainCardHandler 调用 render 细节。\n",
                    evidence=KnowledgeEvidence(
                        inputTitle="",
                        inputDescription="",
                        repoMatches=["demo_repo"],
                        keywordMatches=["handler"],
                        pathMatches=[str(repo_root)],
                        candidateFiles=[],
                        contextHits=[],
                        retrievalNotes=[],
                        openQuestions=[],
                    ),
                ),
            )

            task_id = "task-native"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = timestamp.isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "竞拍讲解卡需求",
                        "status": "initialized",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "竞拍讲解卡需求",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(
                json.dumps({"repos": [{"id": "demo_repo", "path": str(repo_root), "status": "initialized"}]}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "source.json").write_text(json.dumps({"type": "text"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (task_dir / "prd.source.md").write_text("# PRD Source\n\n---\n\n竞拍讲解卡需要展示竞拍态提示。\n", encoding="utf-8")

            from unittest.mock import patch

            with patch(
                "coco_flow.clients.CocoACPClient.run_prompt_only",
                side_effect=[
                    json.dumps({"selected_ids": ["domain-auction-card"], "rejected_ids": ["flow-weak"], "reason": "flow 更偏实现细节"}),
                    "# PRD Refined\n\n## 需求概述\n\n- 竞拍讲解卡需求。\n\n## 功能点\n\n- 展示竞拍态提示。\n\n## 边界条件\n\n- 非竞拍态不展示。\n\n## 交互与展示\n\n- 保持当前样式。\n\n## 验收标准\n\n- 竞拍态可见。\n\n## 业务规则\n\n- 仅竞拍态展示。\n\n## 待确认问题\n\n- 无。\n",
                ],
            ):
                status = refine_task(task_id, settings=settings)

            self.assertEqual(status, "refined")
            selection = json.loads((task_dir / "refine-knowledge-selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["selected_ids"], ["domain-auction-card"])
            self.assertEqual(selection["adjudication"]["mode"], "llm_adjudicated")
            self.assertEqual(selection["adjudication"]["rejected_ids"], ["flow-weak"])


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

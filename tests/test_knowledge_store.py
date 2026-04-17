from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.services.queries.knowledge import KnowledgeStore


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


class KnowledgeStoreTest(unittest.TestCase):
    def test_create_document_supports_plain_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = KnowledgeStore(settings)

            document = store.create_document(
                "竞拍讲解卡参考",
                "## Summary\n\n手工维护的知识文档。\n",
            )

            self.assertEqual(document.title, "竞拍讲解卡参考")
            self.assertEqual(document.kind, "flow")
            self.assertEqual(document.status, "draft")
            self.assertEqual(document.engines, [])
            self.assertIn("手工维护的知识文档", document.body)

            saved_path = settings.knowledge_root / "flows" / f"{document.id}.md"
            self.assertTrue(saved_path.is_file())
            saved_content = saved_path.read_text(encoding="utf-8")
            self.assertIn("title: 竞拍讲解卡参考", saved_content)
            self.assertIn("kind: flow", saved_content)
            self.assertIn("## Summary", saved_content)

    def test_update_document_content_rewrites_frontmatter_and_kind_location(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = KnowledgeStore(settings)
            created = store.create_document("竞拍讲解卡参考", "## Summary\n\n初始内容。\n")

            updated = store.update_document_content(
                created.id,
                (
                    "---\n"
                    "kind: domain\n"
                    "status: approved\n"
                    "engines: [\"plan\"]\n"
                    "domain_name: 竞拍讲解卡\n"
                    "---\n\n"
                    "## Summary\n\n改成领域知识。\n"
                ),
            )

            self.assertEqual(updated.id, created.id)
            self.assertEqual(updated.kind, "domain")
            self.assertEqual(updated.status, "approved")
            self.assertEqual(updated.engines, ["plan"])
            self.assertEqual(updated.domainName, "竞拍讲解卡")
            self.assertIn("改成领域知识", updated.body)

            old_path = settings.knowledge_root / "flows" / f"{created.id}.md"
            new_path = settings.knowledge_root / "domains" / f"{created.id}.md"
            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())

    def test_update_document_content_preserves_raw_frontmatter_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = KnowledgeStore(settings)
            created = store.create_document("竞拍讲解卡参考", "## Summary\n\n初始内容。\n")

            source = (
                "---\n"
                "kind: flow\n"
                "status: approved\n"
                "custom_tags:\n"
                "  - auction\n"
                "  - popcard\n"
                "review_note: |\n"
                "  第一行\n"
                "  第二行\n"
                "---\n\n"
                "## Summary\n\n保留原始 YAML。\n"
            )
            updated = store.update_document_content(created.id, source)

            self.assertIn("custom_tags:", updated.rawFrontmatter)
            self.assertIn("review_note: |", updated.rawFrontmatter)
            self.assertIn("第一行", updated.rawFrontmatter)
            self.assertEqual(updated.rawContent, source)

            saved_path = settings.knowledge_root / "flows" / f"{created.id}.md"
            saved_content = saved_path.read_text(encoding="utf-8")
            self.assertEqual(saved_content, source)

    def test_update_document_content_normalizes_multiple_frontmatter_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = KnowledgeStore(settings)
            created = store.create_document("竞拍讲解卡参考", "## Summary\n\n初始内容。\n")

            source = (
                "---\n"
                f"id: {created.id}\n"
                "title: 临时标题\n"
                "status: draft\n"
                "---\n\n"
                "---\n"
                "id: imported-reference-id\n"
                "title: 系统链路\n"
                "status: approved\n"
                "---\n\n"
                "## Summary\n\n规范化后只保留一段 frontmatter。\n"
            )
            updated = store.update_document_content(created.id, source)

            self.assertEqual(updated.id, created.id)
            self.assertEqual(updated.title, "系统链路")
            self.assertEqual(updated.status, "approved")
            self.assertIn(f"id: {created.id}", updated.rawFrontmatter)
            self.assertNotIn("imported-reference-id", updated.rawFrontmatter)

            saved_path = settings.knowledge_root / "flows" / f"{created.id}.md"
            saved_content = saved_path.read_text(encoding="utf-8")
            self.assertEqual(saved_content.count("---\n"), 2)
            self.assertIn("title: 系统链路", saved_content)
            self.assertIn("## Summary", saved_content)


if __name__ == "__main__":
    unittest.main()

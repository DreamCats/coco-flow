from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.services.queries.skills import SkillStore


def make_settings(root: Path) -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
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


class SkillStoreTest(unittest.TestCase):
    def test_create_package_writes_skill_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = SkillStore(settings)

            name, package_root, skill_path = store.create_package(
                "Auction Popcard",
                description="处理竞拍讲解卡相关需求。",
                domain="auction_pop_card",
            )

            self.assertEqual(name, "auction-popcard")
            self.assertEqual(skill_path, "auction-popcard/SKILL.md")
            self.assertTrue((package_root / "SKILL.md").is_file())
            self.assertTrue((package_root / "references" / "domain.md").is_file())
            self.assertTrue((package_root / "references" / "main-flow.md").is_file())
            self.assertTrue((package_root / "references" / "change-workflows.md").is_file())

            content = (package_root / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: auction-popcard", content)
            self.assertIn("description: 处理竞拍讲解卡相关需求。", content)
            self.assertIn("domain: auction_pop_card", content)

    def test_list_tree_returns_directory_and_skill_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = SkillStore(settings)
            store.create_package("auction-popcard")

            _root, nodes = store.list_tree()

            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0].name, "auction-popcard")
            self.assertEqual(nodes[0].nodeType, "directory")
            self.assertEqual(nodes[0].children[0].name, "references")
            self.assertEqual(nodes[0].children[1].name, "SKILL.md")

    def test_write_file_updates_skill_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = SkillStore(settings)
            store.create_package("auction-popcard")

            updated_path, content = store.write_file(
                "auction-popcard/SKILL.md",
                "---\nname: auction-popcard\ndescription: updated\ndomain: auction_pop_card\n---\n",
            )

            self.assertEqual(updated_path, "auction-popcard/SKILL.md")
            self.assertIn("description: updated", content)
            _source_id, _path, saved = store.read_file("auction-popcard/SKILL.md")
            self.assertIn("description: updated", saved)

    def test_list_packages_uses_namespaced_skill_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = SkillStore(settings)
            store.create_package("auction-popcard")

            packages = store.list_packages()

            self.assertEqual([package.id for package in packages], ["local/auction-popcard"])
            self.assertEqual(packages[0].source_id, "local")
            self.assertEqual(packages[0].package_id, "auction-popcard")

    def test_add_git_source_persists_not_cloned_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = SkillStore(settings)

            source = store.add_git_source(
                name="Live Team Skills",
                url="git@gitlab.example.com:team/coco-flow-skills.git",
                branch="main",
            )

            self.assertEqual(source["id"], "live-team-skills")
            self.assertEqual(source["status"], "not_cloned")
            sources = store.list_sources()
            self.assertEqual([item["id"] for item in sources], ["local", "live-team-skills"])
            self.assertEqual(sources[1]["localPath"], str(settings.config_root / "skills-sources" / "live-team-skills"))

    def test_remove_sources_hides_git_and_local_without_deleting_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = SkillStore(settings)
            store.create_package("auction-popcard")
            store.add_git_source(name="Live Team Skills", url="git@gitlab.example.com:team/coco-flow-skills.git")

            git_local_path = settings.config_root / "skills-sources" / "live-team-skills"
            git_local_path.mkdir(parents=True)
            removed_git = store.remove_source("live-team-skills")
            removed_local = store.remove_source("local")

            self.assertFalse(removed_git["enabled"])
            self.assertFalse(removed_local["enabled"])
            self.assertTrue(git_local_path.is_dir())
            self.assertEqual(store.list_sources(), [])
            self.assertEqual(store.list_packages(), [])


if __name__ == "__main__":
    unittest.main()

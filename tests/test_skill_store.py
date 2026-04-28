from __future__ import annotations

import json
from pathlib import Path
import subprocess
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


def write_sources_config(settings: Settings, *source_ids: str) -> None:
    payload = {
        "sources": [
            {
                "id": source_id,
                "name": source_id,
                "type": "git",
                "url": f"git@gitlab.example.com:team/{source_id}.git",
                "branch": "main",
                "local_path": str(settings.config_root / "skills-sources" / source_id),
                "enabled": True,
            }
            for source_id in source_ids
        ]
    }
    settings.config_root.mkdir(parents=True, exist_ok=True)
    (settings.config_root / "skills-sources.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_skill(settings: Settings, source_id: str, package_id: str, *, description: str = "demo") -> Path:
    package_root = settings.config_root / "skills-sources" / source_id / package_id
    references = package_root / "references"
    references.mkdir(parents=True, exist_ok=True)
    (package_root / "SKILL.md").write_text(
        f"---\nname: {package_id}\ndescription: {description}\ndomain: auction_pop_card\n---\n\n# Overview\n\n{description}\n",
        encoding="utf-8",
    )
    (references / "main-flow.md").write_text("# Main Flow\n\n- live_pack consumes live_common.\n", encoding="utf-8")
    return package_root


def run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def write_git_source_config(settings: Settings, source_id: str, *, url: str, branch: str, local_path: Path) -> None:
    payload = {
        "sources": [
            {
                "id": source_id,
                "name": source_id,
                "type": "git",
                "url": url,
                "branch": branch,
                "local_path": str(local_path),
                "enabled": True,
            }
        ]
    }
    settings.config_root.mkdir(parents=True, exist_ok=True)
    (settings.config_root / "skills-sources.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def create_skill_origin(root: Path) -> tuple[Path, Path]:
    origin = root / "origin.git"
    seed = root / "seed"
    local_path = root / "config" / "skills-sources" / "live-ai-skills"
    run_git(["init", "--bare", str(origin)], cwd=root)
    seed.mkdir()
    run_git(["init"], cwd=seed)
    run_git(["config", "user.email", "test@example.com"], cwd=seed)
    run_git(["config", "user.name", "Test User"], cwd=seed)
    package_root = seed / "auction-popcard"
    package_root.mkdir()
    (package_root / "SKILL.md").write_text("---\nname: auction-popcard\ndescription: main\n---\n\nmain\n", encoding="utf-8")
    run_git(["add", "."], cwd=seed)
    run_git(["commit", "-m", "main skill"], cwd=seed)
    run_git(["branch", "-M", "main"], cwd=seed)
    run_git(["remote", "add", "origin", str(origin)], cwd=seed)
    run_git(["push", "-u", "origin", "main"], cwd=seed)
    run_git(["symbolic-ref", "HEAD", "refs/heads/main"], cwd=origin)
    run_git(["switch", "-c", "dev"], cwd=seed)
    (package_root / "SKILL.md").write_text("---\nname: auction-popcard\ndescription: dev\n---\n\ndev\n", encoding="utf-8")
    run_git(["add", "."], cwd=seed)
    run_git(["commit", "-m", "dev skill"], cwd=seed)
    run_git(["push", "-u", "origin", "dev"], cwd=seed)
    local_path.parent.mkdir(parents=True)
    run_git(["clone", "--branch", "main", str(origin), str(local_path)], cwd=root)
    return origin, local_path


class SkillStoreTest(unittest.TestCase):
    def test_no_sources_config_means_no_default_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            store = SkillStore(settings)

            self.assertEqual(store.list_sources(), [])
            self.assertEqual(store.list_packages(), [])

    def test_legacy_local_source_config_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            payload = {
                "sources": [
                    {
                        "id": "local",
                        "name": "Local Skills",
                        "type": "local",
                        "local_path": str(settings.config_root / "skills"),
                        "enabled": True,
                    }
                ]
            }
            settings.config_root.mkdir(parents=True, exist_ok=True)
            (settings.config_root / "skills-sources.json").write_text(json.dumps(payload), encoding="utf-8")
            write_skill(settings, "local", "auction-popcard")
            store = SkillStore(settings)

            self.assertEqual(store.list_sources(), [])
            self.assertEqual(store.list_packages(), [])
            self.assertIsNone(store.get_package("local/auction-popcard"))

    def test_list_tree_returns_source_directory_and_skill_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            write_sources_config(settings, "live-ai-skills")
            write_skill(settings, "live-ai-skills", "auction-popcard")
            store = SkillStore(settings)

            source, nodes = store.list_tree_for_source("live-ai-skills")

            self.assertEqual(source.id, "live-ai-skills")
            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0].name, "auction-popcard")
            self.assertEqual(nodes[0].nodeType, "directory")
            self.assertEqual(nodes[0].path, "auction-popcard")
            self.assertEqual(nodes[0].children[0].name, "references")
            self.assertEqual(nodes[0].children[1].name, "SKILL.md")

    def test_read_file_requires_explicit_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            write_sources_config(settings, "live-ai-skills")
            write_skill(settings, "live-ai-skills", "auction-popcard", description="updated")
            store = SkillStore(settings)

            source_id, path, content = store.read_file("auction-popcard/SKILL.md", source_id="live-ai-skills")

            self.assertEqual(source_id, "live-ai-skills")
            self.assertEqual(path, "auction-popcard/SKILL.md")
            self.assertIn("description: updated", content)

    def test_list_packages_uses_namespaced_skill_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            write_sources_config(settings, "live-ai-skills")
            write_skill(settings, "live-ai-skills", "auction-popcard")
            store = SkillStore(settings)

            packages = store.list_packages()

            self.assertEqual([package.id for package in packages], ["live-ai-skills/auction-popcard"])
            self.assertEqual(packages[0].source_id, "live-ai-skills")
            self.assertEqual(packages[0].package_id, "auction-popcard")

    def test_get_package_rejects_non_namespaced_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            write_sources_config(settings, "live-ai-skills")
            write_skill(settings, "live-ai-skills", "auction-popcard")
            store = SkillStore(settings)

            self.assertIsNone(store.get_package("auction-popcard"))
            self.assertIsNotNone(store.get_package("live-ai-skills/auction-popcard"))

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
            self.assertEqual([item["id"] for item in sources], ["live-team-skills"])
            self.assertEqual(sources[0]["localPath"], str(settings.config_root / "skills-sources" / "live-team-skills"))

    def test_remove_source_hides_git_source_without_deleting_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(Path(temp_dir))
            write_sources_config(settings, "live-team-skills")
            git_local_path = write_skill(settings, "live-team-skills", "auction-popcard")
            store = SkillStore(settings)

            removed = store.remove_source("live-team-skills")

            self.assertFalse(removed["enabled"])
            self.assertTrue(git_local_path.is_dir())
            self.assertEqual(store.list_sources(), [])
            self.assertEqual(store.list_packages(), [])

    def test_checkout_source_branch_switches_remote_branch_and_updates_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = make_settings(root)
            origin, local_path = create_skill_origin(root)
            write_git_source_config(settings, "live-ai-skills", url=str(origin), branch="main", local_path=local_path)
            store = SkillStore(settings)

            source, output = store.checkout_source_branch("live-ai-skills", "dev")

            self.assertEqual(source["currentBranch"], "dev")
            self.assertEqual(source["branch"], "dev")
            self.assertIn("dev", output)
            self.assertIn("description: dev", (local_path / "auction-popcard" / "SKILL.md").read_text(encoding="utf-8"))
            config = json.loads((settings.config_root / "skills-sources.json").read_text(encoding="utf-8"))
            self.assertEqual(config["sources"][0]["branch"], "dev")

    def test_checkout_source_branch_rejects_dirty_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = make_settings(root)
            origin, local_path = create_skill_origin(root)
            write_git_source_config(settings, "live-ai-skills", url=str(origin), branch="main", local_path=local_path)
            (local_path / "dirty.md").write_text("dirty\n", encoding="utf-8")
            store = SkillStore(settings)

            with self.assertRaisesRegex(ValueError, "本地改动"):
                store.checkout_source_branch("live-ai-skills", "dev")


if __name__ == "__main__":
    unittest.main()

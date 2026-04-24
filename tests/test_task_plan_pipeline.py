from __future__ import annotations

from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.engines.design.models import DesignInputBundle
from coco_flow.engines.design.gate import local_gate_payload
from coco_flow.engines.design.pipeline import apply_review_issues_to_decision, normalize_decision_for_gate
from coco_flow.engines.design.adjudication import normalize_adjudication, review_payload_after_revision
from coco_flow.engines.design.research import build_research_plan, research_single_repo
from coco_flow.engines.design.skills import build_design_skills_bundle
from coco_flow.engines.shared.models import RefinedSections, RepoScope
from coco_flow.services.tasks.design import design_task
from coco_flow.services.tasks.plan import start_planning_task


def make_settings(root: Path, *, plan_executor: str = "local") -> Settings:
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


class DesignV3PipelineTest(unittest.TestCase):
    def test_revision_removes_blocked_candidate_file(self) -> None:
        decision = {
            "repo_decisions": [
                {
                    "repo_id": "demo",
                    "work_type": "must_change",
                    "candidate_files": ["src/right.py", "src/wrong.py"],
                    "candidate_dirs": ["src"],
                }
            ]
        }
        review = {
            "issues": [
                {
                    "severity": "blocking",
                    "failure_type": "candidate_file_not_proven",
                    "target": "src/wrong.py",
                    "suggested_action": "remove wrong candidate",
                }
            ]
        }

        revised, resolutions = apply_review_issues_to_decision(decision, review)

        repo = revised["repo_decisions"][0]
        self.assertEqual(repo["candidate_files"], ["src/right.py"])
        self.assertEqual(resolutions[0]["resolution"], "accepted")

    def test_validate_only_decision_does_not_expose_candidate_files(self) -> None:
        decision = {
            "repo_decisions": [
                {
                    "repo_id": "demo",
                    "work_type": "validate_only",
                    "candidate_files": ["src/noisy.py"],
                    "candidate_dirs": ["src"],
                }
            ]
        }

        normalized = normalize_decision_for_gate(decision, {"issues": []})

        repo = normalized["repo_decisions"][0]
        self.assertEqual(repo["candidate_files"], [])
        self.assertEqual(repo["candidate_dirs"], [])

    def test_repo_research_includes_git_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            self._run(repo_dir, "git", "init")
            self._run(repo_dir, "git", "config", "user.email", "test@example.com")
            self._run(repo_dir, "git", "config", "user.name", "Test User")
            (repo_dir / "auction_config.go").write_text(
                "package demo\n\nfunc AuctionTextConfig() string { return \"Starting bid\" }\n",
                encoding="utf-8",
            )
            self._run(repo_dir, "git", "add", ".")
            self._run(repo_dir, "git", "commit", "-m", "update auction text config")

            payload = research_single_repo(
                "demo",
                str(repo_dir),
                {
                    "search_terms": ["auction", "Starting", "bid"],
                    "budget": {"max_files_read": 4, "max_search_commands": 3},
                },
            )

            git_evidence = payload["git_evidence"]
            self.assertTrue(git_evidence)
            self.assertTrue(any(item["path"] == "auction_config.go" for item in git_evidence))
            self.assertGreaterEqual(payload["budget_used"]["git_commands"], 1)

    def test_research_plan_consumes_search_hints(self) -> None:
        prepared = DesignInputBundle(
            task_dir=Path("/tmp/task"),
            task_id="task",
            title="更新出价成功态",
            refined_markdown="需要更新 BidSuccessToast。",
            input_meta={},
            refine_brief_payload={},
            refine_intent_payload={},
            refine_skills_selection_payload={},
            refine_skills_read_markdown="",
            repos_meta={},
            repo_scopes=[RepoScope(repo_id="demo", repo_path="/tmp/repo")],
            sections=RefinedSections(
                change_scope=["更新出价成功态"],
                non_goals=[],
                key_constraints=[],
                acceptance_criteria=["BidSuccessToast 展示正确"],
                open_questions=[],
                raw="",
            ),
        )

        payload = build_research_plan(
            prepared,
            {
                "source": "native",
                "search_terms": ["bid success"],
                "likely_symbols": ["BidSuccessToast"],
                "likely_file_patterns": ["bid_success"],
                "negative_terms": ["legacy"],
                "confidence": "high",
            },
        )

        repo_plan = payload["repos"][0]
        self.assertIn("BidSuccessToast", repo_plan["search_terms"])
        self.assertEqual(repo_plan["likely_file_patterns"], ["bid_success"])
        self.assertEqual(repo_plan["negative_terms"], ["legacy"])
        self.assertEqual(repo_plan["search_hints_source"], "native")

    def test_design_skills_selects_auction_pop_card_and_builds_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            self._write_skill(
                settings.config_root / "skills" / "auction-pop-card",
                skill_body=(
                    "适用于竞拍讲解卡需求。\n"
                    "公共配置 / 实验开关 通常关注 live_common，再看业务仓如何消费。\n"
                ),
                references={
                    "references/change-workflows.md": (
                        "## Stable Repo Roles\n"
                        "- `live_pack` 更偏竞拍卡数据编排、状态收敛。\n"
                        "- `live_common` 更偏 AB/TCC/schema 开关。\n"
                        "## Stable Multi-Repo Patterns\n"
                        "- `live_common + 业务仓` AB 参数、实验开关、共享配置。\n"
                        "### 数据编排 / 状态口径对齐\n"
                        "- 常见模块: entities/converters/auction_converters/*\n"
                        "### 公共配置 / 实验开关\n"
                        "- 常见模块: live_common/abtest/*\n"
                    )
                },
            )
            prepared = self._design_bundle(
                repo_scopes=[
                    RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                    RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
                ],
                title="竞拍讲解卡文案实验",
                refined_markdown="命中实验时，普通竞拍和 surprise set 展示 Starting bid。",
            )

            brief, selection, selected_ids = build_design_skills_bundle(prepared, settings)

            self.assertEqual(selected_ids, ["auction-pop-card"])
            self.assertEqual(selection["selected_skill_ids"], ["auction-pop-card"])
            self.assertIn("Stable Repo Roles", brief)
            self.assertIn("live_common + 业务仓", brief)
            self.assertIn("Design 必须说明实验字段来源", brief)

    def test_repo_research_uses_file_pattern_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            (repo_dir / "bid_success_view.go").write_text(
                "package demo\n\nfunc Render() string { return \"ok\" }\n",
                encoding="utf-8",
            )

            payload = research_single_repo(
                "demo",
                str(repo_dir),
                {
                    "search_terms": ["missing-content-term"],
                    "likely_file_patterns": ["bid_success"],
                    "budget": {"max_files_read": 4, "max_search_commands": 1, "max_path_pattern_scans": 2},
                },
            )

            candidate_paths = [item["path"] for item in payload["candidate_files"]]
            self.assertIn("bid_success_view.go", candidate_paths)
            self.assertEqual(payload["budget_used"]["path_pattern_scans"], 1)

    def test_repo_research_demotes_broad_file_pattern_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            for index in range(16):
                (repo_dir / f"card_{index}.go").write_text(
                    "package demo\n\nfunc Render() string { return \"ok\" }\n",
                    encoding="utf-8",
                )

            payload = research_single_repo(
                "demo",
                str(repo_dir),
                {
                    "search_terms": [],
                    "likely_file_patterns": ["card"],
                    "budget": {"max_files_read": 4, "max_search_commands": 0, "max_path_pattern_scans": 1},
                },
            )

            self.assertEqual(payload["candidate_files"], [])
            self.assertTrue(payload["related_files"])

    def test_revision_can_promote_related_file_to_candidate(self) -> None:
        prepared = self._design_bundle(repo_scopes=[RepoScope(repo_id="demo", repo_path="/tmp/repo")])
        payload = {
            "decision_summary": "demo",
            "core_change_points": ["update regular auction"],
            "repo_decisions": [
                {
                    "repo_id": "demo",
                    "work_type": "must_change",
                    "candidate_files": ["core.go", "related.go"],
                    "responsibility": "demo",
                }
            ],
        }
        research_summary = {
            "repos": [
                {
                    "repo_id": "demo",
                    "candidate_files": [{"path": "core.go"}],
                    "related_files": [{"path": "related.go"}],
                }
            ]
        }

        normalized = normalize_adjudication(prepared, payload, research_summary)

        self.assertEqual(normalized["repo_decisions"][0]["candidate_files"], ["core.go", "related.go"])

    def test_accepted_revision_must_be_reflected_in_decision(self) -> None:
        review = {
            "issues": [
                {
                    "severity": "blocking",
                    "failure_type": "missing_candidate_file",
                    "target": "demo candidate_files",
                    "expected": "应包含 related.go",
                    "suggested_action": "添加 related.go",
                }
            ]
        }
        debate = {
            "revision": {
                "issue_resolutions": [
                    {
                        "failure_type": "missing_candidate_file",
                        "target": "demo candidate_files",
                        "resolution": "accepted",
                        "decision_change": "添加 related.go",
                    }
                ]
            }
        }

        still_blocked = review_payload_after_revision(review, debate, {"repo_decisions": [{"repo_id": "demo", "candidate_files": []}]})
        fixed = review_payload_after_revision(review, debate, {"repo_decisions": [{"repo_id": "demo", "candidate_files": ["related.go"]}]})

        self.assertFalse(still_blocked["ok"])
        self.assertEqual(still_blocked["issues"][0]["severity"], "blocking")
        self.assertTrue(fixed["ok"])
        self.assertEqual(fixed["issues"][0]["severity"], "info")

    def test_gate_blocks_markdown_plan_status_conflict(self) -> None:
        prepared = self._design_bundle(repo_scopes=[RepoScope(repo_id="demo", repo_path="/tmp/repo")])

        payload = local_gate_payload(
            prepared,
            {"repo_decisions": [{"repo_id": "demo"}]},
            "# Demo\n\n当前不能进入 Plan，阻断原因：缺文件。\n",
            {"issues": []},
            degraded=False,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["gate_status"], "needs_human")

    def test_local_design_v3_writes_agentic_artifacts_and_blocks_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, plan_executor="local")
            task_dir, _repo_dir = self._create_refined_task(settings.task_root, "task-design-v3")

            status = design_task("task-design-v3", settings=settings)

            self.assertEqual(status, "failed")
            self.assertTrue((task_dir / "design-input.json").exists())
            self.assertTrue((task_dir / "design-research-plan.json").exists())
            self.assertTrue((task_dir / "design-skills-selection.json").exists())
            self.assertTrue((task_dir / "design-search-hints.json").exists())
            self.assertTrue((task_dir / "design-research" / "demo.json").exists())
            self.assertTrue((task_dir / "design-research-summary.json").exists())
            self.assertTrue((task_dir / "design-adjudication.json").exists())
            self.assertTrue((task_dir / "design-review.json").exists())
            self.assertTrue((task_dir / "design-debate.json").exists())
            self.assertTrue((task_dir / "design-decision.json").exists())
            self.assertTrue((task_dir / "design-repo-binding.json").exists())
            self.assertTrue((task_dir / "design-sections.json").exists())
            self.assertTrue((task_dir / "design.md").exists())
            self.assertTrue((task_dir / "design-verify.json").exists())
            self.assertTrue((task_dir / "design-diagnosis.json").exists())

            result = self._read_json(task_dir / "design-result.json")
            self.assertEqual(result["gate_status"], "degraded")
            self.assertEqual(result["plan_allowed"], False)
            with self.assertRaisesRegex(ValueError, "does not allow plan"):
                start_planning_task("task-design-v3", settings=settings)

    def test_design_v3_requires_bound_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, plan_executor="local")
            task_dir = settings.task_root / "task-no-repo"
            task_dir.mkdir(parents=True)
            self._write_json(task_dir / "task.json", {"task_id": "task-no-repo", "title": "No repo", "status": "refined"})
            self._write_json(task_dir / "input.json", {})
            self._write_json(task_dir / "repos.json", {"repos": []})
            (task_dir / "prd-refined.md").write_text("# PRD\n\n## 本次范围\n- 更新成功态。\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "design requires bound repos"):
                design_task("task-no-repo", settings=settings)

    def _create_refined_task(self, task_root: Path, task_id: str) -> tuple[Path, Path]:
        repo_dir = task_root.parent / "demo-repo"
        repo_dir.mkdir(parents=True)
        (repo_dir / "status.py").write_text(
            "def success_status():\n    return 'success'\n",
            encoding="utf-8",
        )
        task_dir = task_root / task_id
        task_dir.mkdir(parents=True)
        self._write_json(task_dir / "task.json", {"task_id": task_id, "title": "成功态状态提示", "status": "refined"})
        self._write_json(task_dir / "input.json", {"title": "成功态状态提示"})
        self._write_json(task_dir / "refine-brief.json", {"change_points": ["成功态状态提示"]})
        self._write_json(task_dir / "refine-intent.json", {})
        self._write_json(task_dir / "repos.json", {"repos": [{"id": "demo", "path": str(repo_dir), "status": "refined"}]})
        (task_dir / "prd-refined.md").write_text(
            "# PRD\n\n## 本次范围\n- 成功态状态提示需要落到 success_status。\n\n## 验收标准\n- success 状态展示正确。\n",
            encoding="utf-8",
        )
        return task_dir, repo_dir

    def _design_bundle(
        self,
        *,
        repo_scopes: list[RepoScope],
        title: str = "Demo",
        refined_markdown: str = "demo",
    ) -> DesignInputBundle:
        return DesignInputBundle(
            task_dir=Path("/tmp/task"),
            task_id="task",
            title=title,
            refined_markdown=refined_markdown,
            input_meta={},
            refine_brief_payload={},
            refine_intent_payload={},
            refine_skills_selection_payload={},
            refine_skills_read_markdown="",
            repos_meta={},
            repo_scopes=repo_scopes,
            sections=RefinedSections(
                change_scope=["demo"],
                non_goals=[],
                key_constraints=[],
                acceptance_criteria=[],
                open_questions=[],
                raw="",
            ),
        )

    def _write_skill(self, root: Path, *, skill_body: str, references: dict[str, str]) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "SKILL.md").write_text(
            "---\n"
            "name: auction-pop-card\n"
            "description: 竞拍讲解卡获取数据及打包链路\n"
            "domain: auction-pop-card\n"
            "---\n\n"
            f"{skill_body}\n",
            encoding="utf-8",
        )
        for rel, content in references.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _run(self, cwd: Path, *cmd: str) -> None:
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()

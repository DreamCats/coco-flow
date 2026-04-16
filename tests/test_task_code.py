from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coco_flow.services.tasks.code import (
    FAILURE_BLOCKED,
    FAILURE_AGENT,
    FAILURE_BUILD,
    FAILURE_GIT,
    FAILURE_VERIFY,
    build_native_code_prompt,
    build_blocked_report,
    classify_exception_failure_type,
    classify_failure_type,
    collect_repo_dependency_repos,
    discover_go_test_packages,
    find_unmet_repo_dependencies,
    package_has_go_tests,
    reorder_target_repos_by_plan,
    select_retry_target_files,
    select_verification_target_files,
    split_ready_and_blocked_target_repos,
    verify_go_build,
)


class TaskCodeVerificationTest(unittest.TestCase):
    def test_build_native_code_prompt_includes_structured_plan_tasks(self) -> None:
        prompt = build_native_code_prompt(
            "task-1",
            "demo_repo",
            {
                "tasks": [
                    {
                        "id": "T1",
                        "title": "收敛后端主链路",
                        "target_system_or_repo": "demo_repo",
                        "goal": "补齐主链路状态提示逻辑",
                        "depends_on": ["T0"],
                        "change_scope": ["service/status/service.go"],
                        "actions": ["补齐状态提示逻辑。"],
                        "verify_rule": ["受影响 package 编译通过。"],
                    }
                ]
            },
        )

        self.assertIn("plan-execution.json", prompt)
        self.assertIn("当前 repo 对应的结构化任务", prompt)
        self.assertIn("T1 收敛后端主链路", prompt)
        self.assertIn("service/status/service.go", prompt)
        self.assertIn("当前 repo 本轮优先范围与验证规则", prompt)
        self.assertIn("verify_rule", prompt)
        self.assertIn("当前 repo 任务顺序与依赖", prompt)
        self.assertIn("task_order: T1", prompt)
        self.assertIn("T1 depends_on: T0", prompt)

    def test_reorder_target_repos_by_plan_prefers_task_order(self) -> None:
        targets = [
            {"id": "repo-b", "status": "planned"},
            {"id": "repo-a", "status": "planned"},
        ]
        reordered = reorder_target_repos_by_plan(
            targets,
            {
                "tasks": [
                    {"id": "T1", "target_system_or_repo": "repo-a"},
                    {"id": "T2", "target_system_or_repo": "repo-b"},
                ]
            },
        )
        self.assertEqual([repo["id"] for repo in reordered], ["repo-a", "repo-b"])

    def test_collect_repo_dependency_repos_reads_cross_repo_depends_on(self) -> None:
        dependency_repos = collect_repo_dependency_repos(
            {
                "tasks": [
                    {"id": "T1", "target_system_or_repo": "repo-a", "depends_on": []},
                    {"id": "T2", "target_system_or_repo": "repo-b", "depends_on": ["T1"]},
                ]
            },
            "repo-b",
        )
        self.assertEqual(dependency_repos, ["repo-a"])

    def test_find_unmet_repo_dependencies_requires_upstream_coded(self) -> None:
        unmet = find_unmet_repo_dependencies(
            [
                {"id": "repo-a", "status": "planned"},
                {"id": "repo-b", "status": "planned"},
            ],
            {
                "tasks": [
                    {"id": "T1", "target_system_or_repo": "repo-a", "depends_on": []},
                    {"id": "T2", "target_system_or_repo": "repo-b", "depends_on": ["T1"]},
                ]
            },
            "repo-b",
        )
        self.assertEqual(unmet, ["repo-a"])

    def test_split_ready_and_blocked_target_repos_blocks_single_repo_when_dependency_unmet(self) -> None:
        ready, blocked = split_ready_and_blocked_target_repos(
            [{"id": "repo-b", "status": "planned"}],
            [
                {"id": "repo-a", "status": "planned"},
                {"id": "repo-b", "status": "planned"},
            ],
            {
                "tasks": [
                    {"id": "T1", "target_system_or_repo": "repo-a", "depends_on": []},
                    {"id": "T2", "target_system_or_repo": "repo-b", "depends_on": ["T1"]},
                ]
            },
            all_repos=False,
        )
        self.assertEqual(ready, [])
        self.assertEqual(blocked, [("repo-b", ["repo-a"])])

    def test_split_ready_and_blocked_target_repos_keeps_ready_prefix_for_all_repos(self) -> None:
        ready, blocked = split_ready_and_blocked_target_repos(
            [
                {"id": "repo-a", "status": "planned"},
                {"id": "repo-b", "status": "planned"},
            ],
            [
                {"id": "repo-a", "status": "planned"},
                {"id": "repo-b", "status": "planned"},
            ],
            {
                "tasks": [
                    {"id": "T1", "target_system_or_repo": "repo-a", "depends_on": []},
                    {"id": "T2", "target_system_or_repo": "repo-b", "depends_on": ["T1"]},
                ]
            },
            all_repos=True,
        )
        self.assertEqual([repo["id"] for repo in ready], ["repo-a"])
        self.assertEqual(blocked, [("repo-b", ["repo-a"])])

    def test_build_blocked_report_marks_repo_as_blocked_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_blocked_report(Path(tmp), "repo-b", ["repo-a"])
        self.assertEqual(report["status"], "planned")
        self.assertEqual(report["failure_type"], FAILURE_BLOCKED)
        self.assertIn("repo-a", report["failure_action"])

    def test_select_verification_target_files_prefers_task_scope_overlap(self) -> None:
        targets = select_verification_target_files(
            ["service/status/service.go", "service/other/ignore.go"],
            ["service/status/service.go"],
        )
        self.assertEqual(targets, ["service/status/service.go"])

    def test_select_retry_target_files_falls_back_to_task_scope(self) -> None:
        targets = select_retry_target_files([], ["service/status/service.go"])
        self.assertEqual(targets, ["service/status/service.go"])

    def test_classify_failure_type_prefers_build_failure(self) -> None:
        self.assertEqual(
            classify_failure_type("failed", "go build ./internal/service/... 失败:\nundefined symbol", True),
            FAILURE_BUILD,
        )

    def test_classify_failure_type_detects_verify_failure(self) -> None:
        self.assertEqual(
            classify_failure_type("failed", "go test ./internal/service 失败:\nassert failed", True),
            FAILURE_VERIFY,
        )

    def test_classify_failure_type_detects_agent_failure_without_changes(self) -> None:
        self.assertEqual(
            classify_failure_type("failed", "", False),
            FAILURE_AGENT,
        )

    def test_classify_exception_failure_type_detects_git_error(self) -> None:
        self.assertEqual(
            classify_exception_failure_type(RuntimeError("git index.lock already exists")),
            FAILURE_GIT,
        )

    def test_package_has_go_tests_detects_test_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "internal" / "service"
            pkg.mkdir(parents=True)
            (pkg / "service.go").write_text("package service\n")
            (pkg / "service_test.go").write_text("package service\n")

            self.assertTrue(package_has_go_tests(str(root), "./internal/service"))

    def test_discover_go_test_packages_skips_packages_without_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = root / "internal" / "service"
            handler = root / "internal" / "handler"
            service.mkdir(parents=True)
            handler.mkdir(parents=True)
            (service / "service.go").write_text("package service\n")
            (service / "service_test.go").write_text("package service\n")
            (handler / "handler.go").write_text("package handler\n")

            packages = discover_go_test_packages(
                str(root),
                [
                    "internal/service/service.go",
                    "internal/handler/handler.go",
                ],
            )

            self.assertEqual(packages, ["./internal/service"])

    def test_verify_go_build_default_does_not_run_go_test(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, capture_output: bool, text: bool, check: bool):
            calls.append(cmd)

            class Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return Result()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "internal" / "service"
            pkg.mkdir(parents=True)
            (pkg / "service.go").write_text("package service\n")

            with patch("coco_flow.services.tasks.code.subprocess.run", side_effect=fake_run):
                ok, output = verify_go_build(str(root), ["internal/service/service.go"])

        self.assertTrue(ok)
        self.assertNotIn("go test", output)
        self.assertEqual(calls, [["go", "build", "./internal/service/..."]])

    def test_verify_go_build_runs_go_test_when_explicitly_enabled(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], cwd: str, capture_output: bool, text: bool, check: bool):
            calls.append(cmd)

            class Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return Result()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "internal" / "service"
            pkg.mkdir(parents=True)
            (pkg / "service.go").write_text("package service\n")
            (pkg / "service_test.go").write_text("package service\n")

            with patch("coco_flow.services.tasks.code.subprocess.run", side_effect=fake_run):
                ok, output = verify_go_build(
                    str(root),
                    ["internal/service/service.go"],
                    enable_go_test=True,
                )

        self.assertTrue(ok)
        self.assertIn(["go", "build", "./internal/service/..."], calls)
        self.assertIn(["go", "test", "./internal/service"], calls)
        self.assertNotIn("go test skipped", output)


if __name__ == "__main__":
    unittest.main()

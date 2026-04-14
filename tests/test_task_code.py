from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coco_flow.services.task_code import (
    FAILURE_AGENT,
    FAILURE_BUILD,
    FAILURE_GIT,
    FAILURE_VERIFY,
    classify_exception_failure_type,
    classify_failure_type,
    discover_go_test_packages,
    package_has_go_tests,
    verify_go_build,
)


class TaskCodeVerificationTest(unittest.TestCase):
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

            with patch("coco_flow.services.task_code.subprocess.run", side_effect=fake_run):
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

            with patch("coco_flow.services.task_code.subprocess.run", side_effect=fake_run):
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

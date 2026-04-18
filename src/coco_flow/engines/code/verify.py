from __future__ import annotations

from pathlib import Path
import subprocess

from .models import MAX_GO_TEST_DISCOVERY_PACKAGES, MAX_GO_TEST_PACKAGES


def verify_repo_changes(
    repo_root: str,
    files: list[str],
    *,
    verify_rules: list[str] | None = None,
    enable_go_test: bool = False,
) -> tuple[bool, str]:
    target_files = dedupe_relative_files(files)
    if not target_files:
        output = "no changed files"
        if verify_rules:
            output += "\n\nverify rules:\n" + "\n".join(f"- {item}" for item in verify_rules)
        return True, output

    go_files = [item for item in target_files if item.endswith(".go")]
    if go_files:
        ok, output = verify_go_build(repo_root, go_files, enable_go_test=enable_go_test)
        if verify_rules:
            output = (output + "\n\nverify rules:\n" + "\n".join(f"- {item}" for item in verify_rules)).strip()
        return ok, output

    py_files = [item for item in target_files if item.endswith(".py")]
    if py_files:
        ok, output = verify_python_files(repo_root, py_files)
        if verify_rules:
            output = (output + "\n\nverify rules:\n" + "\n".join(f"- {item}" for item in verify_rules)).strip()
        return ok, output

    output = "no language-specific verification for current changed files"
    if verify_rules:
        output += "\n\nverify rules:\n" + "\n".join(f"- {item}" for item in verify_rules)
    return True, output


def verify_go_build(repo_root: str, files: list[str], enable_go_test: bool = False) -> tuple[bool, str]:
    packages = sorted({go_package_pattern(file_path) for file_path in files if file_path.endswith(".go")})
    if not packages:
        return True, "no go packages to build"

    outputs: list[str] = []
    all_ok = True
    test_candidates = discover_go_test_packages(repo_root, files) if enable_go_test else []
    for package in packages:
        result = subprocess.run(
            ["go", "build", package],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            all_ok = False
            outputs.append(f"go build {package} 失败:\n{result.stdout}{result.stderr}".strip())
        elif result.stdout.strip() or result.stderr.strip():
            outputs.append(f"go build {package} 成功:\n{result.stdout}{result.stderr}".strip())
    if all_ok and test_candidates:
        for package in test_candidates[:MAX_GO_TEST_PACKAGES]:
            result = subprocess.run(
                ["go", "test", package],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                all_ok = False
                outputs.append(f"go test {package} 失败:\n{result.stdout}{result.stderr}".strip())
            elif result.stdout.strip() or result.stderr.strip():
                outputs.append(f"go test {package} 成功:\n{result.stdout}{result.stderr}".strip())
    elif all_ok and enable_go_test:
        outputs.append("go test skipped: no *_test.go files in affected packages")
    if all_ok and not outputs:
        outputs.append("go build passed")
    return all_ok, "\n\n".join(outputs).strip()


def verify_python_files(repo_root: str, files: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        ["python3", "-m", "py_compile", *files],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}{result.stderr}".strip()
    if result.returncode == 0:
        return True, output or "python py_compile passed"
    return False, output or "python py_compile failed"


def dedupe_relative_files(files: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in files:
        current = str(item).strip().lstrip("./")
        lowered = current.lower()
        if not current or lowered in seen:
            continue
        seen.add(lowered)
        result.append(current)
    return result


def go_package_pattern(file_path: str) -> str:
    directory = str(Path(file_path).parent)
    if directory in {"", "."}:
        return "./..."
    return f"./{directory}/..."


def go_test_package_pattern(file_path: str) -> str:
    directory = str(Path(file_path).parent)
    if directory in {"", "."}:
        return "."
    return f"./{directory}"


def discover_go_test_packages(repo_root: str, files: list[str]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for file_path in files:
        if not file_path.endswith(".go"):
            continue
        package = go_test_package_pattern(file_path)
        if package in seen:
            continue
        seen.add(package)
        candidates.append(package)
        if len(candidates) >= MAX_GO_TEST_DISCOVERY_PACKAGES:
            break
    return [package for package in candidates if package_has_go_tests(repo_root, package)]


def package_has_go_tests(repo_root: str, package_pattern: str) -> bool:
    directory = package_pattern.removeprefix("./")
    package_dir = Path(repo_root) / directory
    if directory in {"", "."}:
        package_dir = Path(repo_root)
    if not package_dir.is_dir():
        return False
    return any(path.is_file() for path in package_dir.glob("*_test.go"))

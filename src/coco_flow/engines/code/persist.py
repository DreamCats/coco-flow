from __future__ import annotations

from pathlib import Path
import json

from coco_flow.services.runtime.repo_state import (
    write_repo_code_log,
    write_repo_code_result,
    write_repo_code_verify,
    write_repo_diff_artifacts,
)

from .models import CodeRepoBatch, CodeRepoRunResult


def write_json_artifact(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_code_runtime_artifacts(task_dir: Path, dispatch_payload: dict[str, object], progress_payload: dict[str, object]) -> None:
    write_json_artifact(task_dir / "code-dispatch.json", dispatch_payload)
    write_json_artifact(task_dir / "code-progress.json", progress_payload)


def write_repo_runtime_artifacts(task_dir: Path, result: CodeRepoRunResult) -> None:
    write_repo_code_result(task_dir, result.repo_id, result.report)
    write_repo_code_log(task_dir, result.repo_id, result.repo_log)
    write_repo_code_verify(task_dir, result.repo_id, result.verify_payload)
    if result.diff_patch and str(result.report.get("commit") or "").strip():
        write_repo_diff_artifacts(
            task_dir,
            result.repo_id,
            str(result.report.get("branch") or ""),
            str(result.report.get("commit") or ""),
            [str(item) for item in (result.report.get("files_written") or []) if isinstance(item, str)],
            result.diff_patch,
        )


def build_task_result_payload(task_id: str, batches: list[CodeRepoBatch], repo_results: list[CodeRepoRunResult]) -> dict[str, object]:
    completed_batches = [batch.id for batch in batches if batch.status == "completed"]
    failed_batches = [batch.id for batch in batches if batch.status == "failed"]
    blocked_batches = [batch.id for batch in batches if batch.status == "blocked"]
    status = "failed" if failed_batches else "coded" if completed_batches and len(completed_batches) == len(batches) else "partially_coded"
    if not batches:
        status = "failed"
    return {
        "task_id": task_id,
        "status": status,
        "batch_count": len(batches),
        "completed_batch_count": len(completed_batches),
        "failed_batch_count": len(failed_batches),
        "blocked_batch_count": len(blocked_batches),
        "repo_results": [
            {
                "repo_id": item.repo_id,
                "batch_id": item.batch_id,
                "execution_mode": item.execution_mode,
                "repo_status": item.repo_status,
                "summary": str(item.report.get("summary") or ""),
                "commit": str(item.report.get("commit") or ""),
                "build_ok": bool(item.report.get("build_ok")),
                "failure_type": str(item.report.get("failure_type") or ""),
            }
            for item in repo_results
        ],
        "next_actions": _build_next_actions(batches, failed_batches, blocked_batches),
    }


def _build_next_actions(batches: list[CodeRepoBatch], failed_batches: list[str], blocked_batches: list[str]) -> list[str]:
    if failed_batches:
        return ["先查看失败 repo 的 code.log / code-result.json / code-verify.json，再决定重试还是回退。"]
    if blocked_batches:
        return ["依赖尚未满足，先推进上游 repo，再继续 blocked repo。"]
    if batches:
        return ["结果已产出，可查看 diff / verify 结论并决定是否归档。"]
    return ["当前未生成 runnable batch，请回到 Plan 检查输入契约。"]

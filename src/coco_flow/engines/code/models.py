from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

STATUS_CODING = "coding"
STATUS_PLANNED = "planned"
STATUS_CODED = "coded"
STATUS_FAILED = "failed"
STATUS_ARCHIVED = "archived"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"
MAX_CODE_ATTEMPTS = 3
MAX_GO_TEST_PACKAGES = 3
MAX_GO_TEST_DISCOVERY_PACKAGES = 8
FAILURE_AGENT = "agent_failed"
FAILURE_BUILD = "build_failed"
FAILURE_VERIFY = "verify_failed"
FAILURE_GIT = "git_failed"
FAILURE_RUNTIME = "runtime_failed"
FAILURE_BLOCKED = "blocked_by_dependency"

LogHandler = Callable[[str], None]


@dataclass
class CodePreparedInput:
    task_dir: Path
    task_id: str
    title: str
    task_meta: dict[str, object]
    repos_meta: dict[str, object]
    design_repo_binding_payload: dict[str, object]
    plan_work_items_payload: dict[str, object]
    plan_execution_graph_payload: dict[str, object]
    plan_validation_payload: dict[str, object]
    plan_result_payload: dict[str, object]
    refined_markdown: str
    design_markdown: str
    plan_markdown: str


@dataclass
class CodeWorkItem:
    id: str
    repo_id: str
    title: str
    goal: str
    change_scope: list[str]
    done_definition: list[str]
    verification_steps: list[str]
    depends_on: list[str]


@dataclass
class CodeRepoBatch:
    id: str
    repo_id: str
    repo_path: str
    scope_tier: str
    execution_mode: str
    work_item_ids: list[str]
    depends_on_batch_ids: list[str]
    blocked_by_batch_ids: list[str]
    change_scope: list[str]
    verify_rules: list[str]
    done_definition: list[str]
    status: str
    summary: str

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "repo_path": self.repo_path,
            "scope_tier": self.scope_tier,
            "execution_mode": self.execution_mode,
            "work_item_ids": self.work_item_ids,
            "depends_on_batch_ids": self.depends_on_batch_ids,
            "blocked_by_batch_ids": self.blocked_by_batch_ids,
            "change_scope": self.change_scope,
            "verify_rules": self.verify_rules,
            "done_definition": self.done_definition,
            "status": self.status,
            "summary": self.summary,
        }


@dataclass
class CodeRunState:
    dispatch_payload: dict[str, object]
    progress_payload: dict[str, object]
    batches: list[CodeRepoBatch] = field(default_factory=list)


@dataclass
class CodeRepoRunResult:
    repo_id: str
    batch_id: str
    execution_mode: str
    repo_status: str
    report: dict[str, object]
    repo_log: str
    verify_payload: dict[str, object]
    diff_patch: str = ""

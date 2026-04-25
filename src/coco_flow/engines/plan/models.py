"""Plan 引擎数据模型。

这里只保留 doc-only Plan 需要的输入 bundle 和结果模型；
旧 work item、执行图、验证矩阵和 gate 相关模型已经移除。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from coco_flow.engines.shared.models import RefinedSections, RepoScope

STATUS_PLANNING = "planning"
STATUS_PLANNED = "planned"
STATUS_FAILED = "failed"
EXECUTOR_NATIVE = "native"

LogHandler = Callable[[str], None]


@dataclass
class PlanPreparedInput:
    task_dir: Path
    task_id: str
    title: str
    design_markdown: str
    refined_markdown: str
    input_meta: dict[str, object]
    task_meta: dict[str, object]
    repos_meta: dict[str, object]
    repo_scopes: list[RepoScope]
    repo_ids: set[str]
    refined_sections: RefinedSections
    skills_brief_markdown: str = ""
    skills_selection_payload: dict[str, object] = field(default_factory=dict)
    selected_skill_ids: list[str] = field(default_factory=list)


@dataclass
class PlanEngineResult:
    status: str
    plan_markdown: str

"""Design 引擎数据模型。

这里只保留 doc-only Design 需要的输入 bundle 和结果模型；
旧 schema gate、repo binding、sections 等结构化结果已经移除。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from coco_flow.engines.shared.models import RefinedSections, RepoScope

STATUS_DESIGNING = "designing"
STATUS_DESIGNED = "designed"
STATUS_FAILED = "failed"

EXECUTOR_NATIVE = "native"

LogHandler = Callable[[str], None]


@dataclass
class DesignInputBundle:
    task_dir: Path
    task_id: str
    title: str
    refined_markdown: str
    input_meta: dict[str, object]
    refine_brief_payload: dict[str, object]
    refine_intent_payload: dict[str, object]
    refine_skills_selection_payload: dict[str, object]
    refine_skills_read_markdown: str
    repos_meta: dict[str, object]
    repo_scopes: list[RepoScope]
    sections: RefinedSections
    selected_skill_ids: list[str] = field(default_factory=list)
    design_skills_selection_payload: dict[str, object] = field(default_factory=dict)
    design_skills_index_markdown: str = ""
    design_skills_brief_markdown: str = ""
    design_selected_skill_ids: list[str] = field(default_factory=list)


@dataclass
class DesignEngineResult:
    status: str
    design_markdown: str

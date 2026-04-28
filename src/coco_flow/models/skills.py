from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SkillTreeNode(BaseModel):
    name: str
    path: str
    nodeType: Literal["directory", "file"]
    children: list["SkillTreeNode"] = Field(default_factory=list)


SkillTreeNode.model_rebuild()


class SkillTreeResponse(BaseModel):
    rootPath: str
    sourceId: str
    nodes: list[SkillTreeNode]


class SkillFileResponse(BaseModel):
    path: str
    sourceId: str
    content: str


class SkillSourceStatus(BaseModel):
    id: str
    name: str
    sourceType: Literal["git"]
    enabled: bool = True
    url: str = ""
    branch: str = ""
    localPath: str
    status: str
    message: str = ""
    isGitRepo: bool = False
    currentBranch: str = ""
    commit: str = ""
    remoteUrl: str = ""
    dirty: bool = False
    ahead: int = 0
    behind: int = 0
    packageCount: int = 0


class SkillSourcesResponse(BaseModel):
    sources: list[SkillSourceStatus]


class CreateSkillSourceRequest(BaseModel):
    name: str = ""
    url: str
    branch: str = ""


class SkillSourceActionResponse(BaseModel):
    source: SkillSourceStatus
    output: str = ""

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
    nodes: list[SkillTreeNode]


class SkillFileResponse(BaseModel):
    path: str
    content: str


class UpdateSkillFileRequest(BaseModel):
    content: str


class CreateSkillPackageRequest(BaseModel):
    name: str
    description: str = ""
    domain: str = ""


class SkillPackageResponse(BaseModel):
    name: str
    rootPath: str
    skillPath: str

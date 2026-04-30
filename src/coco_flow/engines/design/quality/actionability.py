"""Deterministic actionability checks for design.md."""

from __future__ import annotations

from .models import DesignActionabilityResult, DesignQualityIssue


def evaluate_design_actionability(markdown: str) -> DesignActionabilityResult:
    normalized = markdown.strip()
    issues: list[DesignQualityIssue] = []
    if not normalized:
        return DesignActionabilityResult(
            passed=False,
            issues=[
                DesignQualityIssue(
                    issue_type="empty_design_markdown",
                    severity="blocking",
                    summary="design.md 为空，无法进入后续阶段。",
                    repair_suggestion="重新生成 design.md，至少包含方案设计、分仓库职责、验收与验证。",
                )
            ],
        )

    if not any(keyword in normalized for keyword in ("改造方案", "技术方案", "方案落点", "实现方案", "方案设计")):
        issues.append(
            DesignQualityIssue(
                issue_type="missing_solution_section",
                severity="blocking",
                summary="design.md 缺少可执行的方案设计表达。",
                evidence=["未命中“改造方案 / 技术方案 / 方案落点 / 实现方案 / 方案设计”等关键结构。"],
                repair_suggestion="补齐业务层方案设计和每个仓库的改造方案，不要只复述需求。",
            )
        )
    if not any(keyword in normalized for keyword in ("验收与验证", "验证方案", "验证关注", "验收标准")):
        issues.append(
            DesignQualityIssue(
                issue_type="missing_validation_section",
                severity="blocking",
                summary="design.md 缺少验收或验证方案。",
                evidence=["未命中“验收与验证 / 验证方案 / 验证关注 / 验收标准”等关键结构。"],
                repair_suggestion="补齐覆盖 refined PRD 验收标准的验证方案。",
            )
        )
    if not any(section in normalized for section in ("## 分仓库职责", "## 分仓库方案", "## 仓库方案")):
        issues.append(
            DesignQualityIssue(
                issue_type="missing_repo_responsibility_section",
                severity="blocking",
                summary="design.md 缺少分仓库职责说明。",
                evidence=["未命中“## 分仓库职责 / ## 分仓库方案 / ## 仓库方案”。"],
                repair_suggestion="逐个绑定仓库说明职责、是否改造、边界和待确认项。",
            )
        )
    return DesignActionabilityResult(passed=not issues, issues=issues)


def design_markdown_is_actionable(markdown: str) -> bool:
    return evaluate_design_actionability(markdown).passed

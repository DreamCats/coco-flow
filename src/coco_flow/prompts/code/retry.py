from __future__ import annotations


def build_code_retry_prompt(
    *,
    task_id: str,
    repo_id: str,
    execution_mode: str,
    work_item_brief: str,
    change_scope_brief: str,
    verify_brief: str,
    dependency_brief: str,
    changed_file_brief: str,
    verification_output: str,
) -> str:
    return f"""刚才的实现未通过最小验证，请继续在当前 worktree 中直接修复，不要重置已有改动。

任务要求：
1. 继续围绕 `.coco-flow/tasks/{task_id}/prd-refined.md`、`design.md`、`plan.md`、`plan-work-items.json`、`plan-execution-graph.json`、`plan-validation.json`、`plan-result.json` 修复问题。
2. 仅修改当前 worktree 内与本次 repo batch 相关的代码，不要改 `.coco-flow/` 和 `.livecoding/`。
3. 优先修复下面这些已经变更过的文件：
{changed_file_brief}
4. 修复后请再次做最小范围验证。
5. 最后仍然必须输出：

=== CODE RESULT ===
status: success|no_change|failed
build: passed|failed|unknown
summary: 一句话总结
files:
- relative/path

最近一次验证失败输出：
{verification_output.strip() or '无'}

当前 repo_id: {repo_id}
当前 task_id: {task_id}
当前 batch mode: {execution_mode}

当前 repo 对应的 work items：
{work_item_brief}

当前 repo 本轮 change scope：
{change_scope_brief}

当前 repo 本轮验证要求：
{verify_brief}

当前 repo 依赖关系：
{dependency_brief}
"""

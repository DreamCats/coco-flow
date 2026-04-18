from __future__ import annotations


def build_code_execute_prompt(
    *,
    task_id: str,
    repo_id: str,
    execution_mode: str,
    work_item_brief: str,
    change_scope_brief: str,
    verify_brief: str,
    dependency_brief: str,
) -> str:
    return f"""你正在一个代码仓库的隔离 worktree 中执行实现任务。

任务要求：
1. 优先读取 `.coco-flow/tasks/{task_id}/code-batch.json` 和 `.coco-flow/tasks/{task_id}/code-batch.md`。
2. 只有在确有必要时，才参考 `.coco-flow/tasks/{task_id}/prd-refined.md`、`design.md`、`plan.md`。
3. 只实现 `code-batch` 中列出的 work items，不要实现其他 repo 或其他 batch 的任务，不要顺手扩改无关功能。
4. 只在当前 worktree 内修改与本次 repo batch 相关的代码，不要修改 `.coco-flow/` 和 `.livecoding/`。
5. 如果当前 repo batch 是 verify_only，则不要改代码，只总结验证结论。
6. 优先做最小范围实现和最小范围验证。
7. 如果不需要改动，请明确说明 `no_change`。
8. 最后必须输出如下结构，且不要省略字段：

=== CODE RESULT ===
status: success|no_change|failed
build: passed|failed|unknown
summary: 一句话总结
files:
- relative/path

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

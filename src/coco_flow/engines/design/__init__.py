"""Design 引擎对外入口。

Design 阶段按架构层拆分：

- ``input/``：读取 task 输入，生成 ``DesignInputBundle``。
- ``knowledge/``：选择 Skills/SOP，生成完整文件路径索引和 local fallback excerpt。
- ``discovery/``：生成 repo research 的搜索线索。
- ``evidence/``：在本地仓库收集代码证据、候选文件和 git evidence。
- ``writer/``：生成最终 ``design.md``。
- ``runtime/``：ACP session 与 ``design.log`` 适配。

这里只暴露服务层需要的状态常量、日志函数、任务目录定位和主编排入口。
内部已经收敛为 doc-only Design，不再导出旧 schema / gate 相关能力。
"""

from .input import locate_task_dir
from .pipeline import run_design_engine
from .runtime import append_design_log
from .types import (
    EXECUTOR_NATIVE,
    STATUS_DESIGNED,
    STATUS_DESIGNING,
    STATUS_FAILED,
    LogHandler,
)

__all__ = [
    "EXECUTOR_NATIVE",
    "LogHandler",
    "STATUS_DESIGNED",
    "STATUS_DESIGNING",
    "STATUS_FAILED",
    "append_design_log",
    "locate_task_dir",
    "run_design_engine",
]

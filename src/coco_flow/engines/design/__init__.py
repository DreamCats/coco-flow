"""Design 引擎对外入口。

这里只暴露服务层需要的状态常量、日志函数、任务目录定位和主编排入口。
内部已经收敛为 doc-only Design，不再导出旧 schema / gate 相关能力。
"""

from .logging import append_design_log
from .models import (
    EXECUTOR_NATIVE,
    STATUS_DESIGNED,
    STATUS_DESIGNING,
    STATUS_FAILED,
    LogHandler,
)
from .pipeline import run_design_engine
from .source import locate_task_dir

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

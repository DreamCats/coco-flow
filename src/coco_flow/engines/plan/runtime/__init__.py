"""Plan runtime adapters.

This package contains external runtime integration such as ACP sessions and
log appenders. Core planning logic should not depend on ACP details directly.
"""

from .agent import (
    close_plan_agent_session,
    new_plan_agent_session,
    run_plan_agent_markdown_with_new_session,
)
from .logging import append_plan_log

__all__ = [
    "append_plan_log",
    "close_plan_agent_session",
    "new_plan_agent_session",
    "run_plan_agent_markdown_with_new_session",
]

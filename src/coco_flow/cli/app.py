from __future__ import annotations

import typer

app = typer.Typer(
    help="coco-flow: workflow product layer for PRD, task, worktree, and local API.",
    no_args_is_help=True,
)
api_app = typer.Typer(help="Run the local FastAPI service.")
tasks_app = typer.Typer(help="Inspect task roots and task summaries.")
ui_app = typer.Typer(help="Serve the built web UI together with the local API.")
daemon_app = typer.Typer(help="Manage the local coco-flow ACP daemon.")
knowledge_app = typer.Typer(help="Manage knowledge documents.")

app.add_typer(api_app, name="api")
app.add_typer(tasks_app, name="tasks")
app.add_typer(ui_app, name="ui")
app.add_typer(daemon_app, name="daemon")
app.add_typer(knowledge_app, name="knowledge")

from .commands import core as _core  # noqa: E402,F401
from .commands import daemon as _daemon  # noqa: E402,F401
from .commands import knowledge as _knowledge  # noqa: E402,F401
from .commands import tasks as _tasks  # noqa: E402,F401

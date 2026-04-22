from __future__ import annotations

import json

import typer

from coco_flow.config import load_settings
from coco_flow.services.queries.knowledge import KnowledgeStore

from ..app import knowledge_app


@knowledge_app.command("list")
def knowledge_list_cmd(
    limit: int = typer.Option(50, min=1, max=500, help="Max number of documents to show."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
    status: str = typer.Option("", help="Filter by knowledge status."),
    kind: str = typer.Option("", help="Filter by knowledge kind."),
) -> None:
    store = KnowledgeStore(load_settings())
    documents = store.list_documents()
    if status.strip():
        documents = [document for document in documents if document.status == status.strip()]
    if kind.strip():
        documents = [document for document in documents if document.kind == kind.strip()]
    documents = documents[:limit]
    if as_json:
        typer.echo(json.dumps({"documents": [document.model_dump() for document in documents]}, ensure_ascii=False, indent=2))
        return
    if not documents:
        typer.echo("No knowledge documents found.")
        return
    for document in documents:
        typer.echo(f"{document.id} [{document.status}] {document.domainName} / {document.kind} / {document.title}")

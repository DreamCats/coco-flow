from __future__ import annotations

from dataclasses import dataclass

from coco_flow.engines.shared.manual_extract import MANUAL_EXTRACT_HEADING

STATUS_INITIALIZED = "initialized"
STATUS_INPUT_PROCESSING = "input_processing"
STATUS_INPUT_READY = "input_ready"
STATUS_INPUT_FAILED = "input_failed"

SOURCE_TYPE_TEXT = "text"
SOURCE_TYPE_FILE = "file"
SOURCE_TYPE_LARK_DOC = "lark_doc"

SUPPLEMENT_HEADING = MANUAL_EXTRACT_HEADING


@dataclass
class ResolvedSource:
    source_type: str
    title: str
    source_value: str
    content: str
    path: str = ""
    url: str = ""
    doc_token: str = ""
    fetch_error: str = ""
    fetch_error_code: str = ""
    needs_async_processing: bool = False


@dataclass
class InputTaskResult:
    task_id: str
    status: str


@dataclass
class InputSections:
    source_input: str
    supplement: str

from __future__ import annotations

from pathlib import Path
import json
import re
import shutil
import subprocess
from urllib.parse import urlparse

from .models import InputSections, ResolvedSource, SOURCE_TYPE_FILE, SOURCE_TYPE_LARK_DOC, SOURCE_TYPE_TEXT, SUPPLEMENT_HEADING

_spacing = re.compile(r"[ \t]+")
_markdown_title = re.compile(r"(?m)^#\s+(.+?)\s*$")
_wiki_token = re.compile(r"/wiki/([A-Za-z0-9]+)")
_doc_token = re.compile(r"/docx?/([A-Za-z0-9]+)")


def split_input_sections(raw_input: str, supplement: str | None = None) -> InputSections:
    normalized_supplement = (supplement or "").strip()
    normalized_input = raw_input.strip()
    if normalized_supplement:
        return InputSections(source_input=normalized_input, supplement=normalized_supplement)
    source_part, parsed_supplement = normalized_input.split(SUPPLEMENT_HEADING, 1) if SUPPLEMENT_HEADING in normalized_input else (normalized_input, "")
    return InputSections(source_input=source_part.strip(), supplement=parsed_supplement.strip())


def normalize_repo_paths(repos: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for repo in repos:
        path = str(Path(repo).expanduser()).strip()
        if not path or path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def resolve_source(raw_input: str, explicit_title: str | None, defer_lark_resolution: bool = False) -> ResolvedSource:
    file_path = maybe_local_file(raw_input)
    if file_path is not None:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        title = normalize_title(explicit_title, extract_file_title(content, file_path))
        return ResolvedSource(
            source_type=SOURCE_TYPE_FILE,
            title=title,
            source_value=str(file_path),
            content=content.strip(),
            path=str(file_path),
        )

    if is_likely_url(raw_input):
        parsed = urlparse(raw_input)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"无效的 URL: {raw_input}")
        if is_lark_doc_url(raw_input):
            inferred_title = ""
            doc_token = extract_raw_lark_token(raw_input)
            if defer_lark_resolution:
                title = normalize_title(explicit_title, infer_title_from_url(raw_input) or "未命名需求")
                return ResolvedSource(
                    source_type=SOURCE_TYPE_LARK_DOC,
                    title=title,
                    source_value=raw_input,
                    content="",
                    url=raw_input,
                    doc_token=doc_token,
                    needs_async_processing=True,
                )
            content = ""
            fetch_error = ""
            fetch_error_code = ""
            try:
                doc_token, inferred_title = resolve_lark_doc_token(raw_input)
                content, fetched_title = fetch_lark_doc_markdown(doc_token)
                if fetched_title:
                    inferred_title = fetched_title
            except ValueError as error:
                fetch_error = str(error)
                fetch_error_code = classify_source_fetch_error(fetch_error)
            title = normalize_title(explicit_title, inferred_title or infer_title_from_url(raw_input) or "未命名需求")
            return ResolvedSource(
                source_type=SOURCE_TYPE_LARK_DOC,
                title=title,
                source_value=raw_input,
                content=content.strip(),
                url=raw_input,
                doc_token=doc_token,
                fetch_error=fetch_error,
                fetch_error_code=fetch_error_code,
            )

    title = normalize_title(explicit_title, raw_input)
    return ResolvedSource(
        source_type=SOURCE_TYPE_TEXT,
        title=title,
        source_value=raw_input,
        content=raw_input.strip(),
    )


def maybe_local_file(raw_input: str) -> Path | None:
    candidate = Path(raw_input).expanduser()
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate.resolve()


def is_likely_url(raw_input: str) -> bool:
    return raw_input.startswith("http://") or raw_input.startswith("https://")


def is_lark_doc_url(raw_input: str) -> bool:
    return bool(_wiki_token.search(raw_input) or _doc_token.search(raw_input))


def extract_file_title(content: str, path: Path) -> str:
    match = _markdown_title.search(content)
    if match:
        return match.group(1).strip()
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    if first_line:
        return first_line[:80]
    return path.stem


def normalize_title(title: str | None, raw_input: str) -> str:
    if title and title.strip():
        return collapse_spacing(title.strip())
    first_line = raw_input.strip().splitlines()[0].strip() if raw_input.strip() else ""
    if first_line:
        return collapse_spacing(first_line[:80])
    return "未命名任务"


def infer_title_from_url(raw_input: str) -> str:
    parsed = urlparse(raw_input)
    host = parsed.netloc or ""
    path = parsed.path.strip("/")
    if host or path:
        return f"{host}/{path}".strip("/")[:80]
    return "未命名需求"


def classify_source_fetch_error(message: str) -> str:
    normalized = message.strip().lower()
    if "lark-cli" in normalized and "不可用" in message:
        return "missing_lark_cli"
    return ""


def resolve_lark_doc_token(raw_url: str) -> tuple[str, str]:
    wiki_match = _wiki_token.search(raw_url)
    if wiki_match:
        return resolve_wiki_node(wiki_match.group(1))
    doc_match = _doc_token.search(raw_url)
    if doc_match:
        return doc_match.group(1), ""
    raise ValueError(f"无法从链接中提取文档 token: {raw_url}")


def extract_raw_lark_token(raw_url: str) -> str:
    wiki_match = _wiki_token.search(raw_url)
    if wiki_match:
        return wiki_match.group(1)
    doc_match = _doc_token.search(raw_url)
    if doc_match:
        return doc_match.group(1)
    return ""


def ensure_lark_cli() -> None:
    if shutil.which("lark-cli") is None:
        raise ValueError("lark-cli 不可用，请先安装并完成登录")


def resolve_wiki_node(wiki_token: str) -> tuple[str, str]:
    params = json.dumps({"token": wiki_token}, ensure_ascii=False)
    result = subprocess.run(
        ["lark-cli", "wiki", "spaces", "get_node", "--params", params],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"解析 wiki 节点失败: {result.stderr.strip() or result.stdout.strip()}")
    payload = json.loads(result.stdout or "{}")
    if int(payload.get("code") or 0) != 0:
        raise ValueError(f"wiki get_node 返回错误: code={payload.get('code')}, msg={payload.get('msg') or ''}")
    node = ((payload.get("data") or {}).get("node") or {})
    doc_token = str(node.get("obj_token") or "").strip()
    if not doc_token:
        raise ValueError(f"wiki 节点未返回 obj_token，wiki_token={wiki_token}")
    return doc_token, str(node.get("title") or "").strip()


def fetch_lark_doc_markdown(doc_token: str) -> tuple[str, str]:
    ensure_lark_cli()
    result = subprocess.run(
        ["lark-cli", "docs", "+fetch", "--doc", doc_token],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"拉取文档内容失败: {result.stderr.strip() or result.stdout.strip()}")
    payload = json.loads(result.stdout or "{}")
    if not bool(payload.get("ok")):
        raise ValueError(f"docs +fetch 返回失败，doc_token={doc_token}")
    data = payload.get("data") or {}
    return str(data.get("markdown") or ""), str(data.get("title") or "").strip()


def collapse_spacing(value: str) -> str:
    return _spacing.sub(" ", value).strip()

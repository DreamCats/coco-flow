from __future__ import annotations

from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
import json
import re
import shutil
import subprocess
from urllib.parse import urlparse

from coco_flow.config import Settings, load_settings

STATUS_INITIALIZED = "initialized"
SOURCE_TYPE_TEXT = "text"
SOURCE_TYPE_FILE = "file"
SOURCE_TYPE_LARK_DOC = "lark_doc"

_ascii_word = re.compile(r"[a-zA-Z0-9]+")
_spacing = re.compile(r"[ \t]+")
_slug_dash = re.compile(r"-+")
_markdown_title = re.compile(r"(?m)^#\s+(.+?)\s*$")
_wiki_token = re.compile(r"/wiki/([A-Za-z0-9]+)")
_doc_token = re.compile(r"/docx?/([A-Za-z0-9]+)")


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


def create_task(
    raw_input: str,
    title: str | None,
    repos: list[str],
    settings: Settings | None = None,
) -> tuple[str, str]:
    cfg = settings or load_settings()
    normalized_input = raw_input.strip()
    normalized_repos = normalize_repo_paths(repos)
    if not normalized_input:
        raise ValueError("input 不能为空")
    if not normalized_repos:
        raise ValueError("repos 不能为空")

    resolved_source = resolve_source(normalized_input, title)
    resolved_title = resolved_source.title
    task_id = build_task_id(resolved_title)
    task_dir = cfg.task_root / task_id
    task_dir.mkdir(parents=True, exist_ok=False)

    now = datetime.now().astimezone()

    write_json(
        task_dir / "task.json",
        {
            "task_id": task_id,
            "title": resolved_title,
            "status": STATUS_INITIALIZED,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "source_type": resolved_source.source_type,
            "source_value": resolved_source.source_value,
            "repo_count": len(normalized_repos),
        },
    )
    source_payload: dict[str, object] = {
        "type": resolved_source.source_type,
        "title": resolved_title,
        "captured_at": now.isoformat(),
    }
    if resolved_source.path:
        source_payload["path"] = resolved_source.path
    if resolved_source.url:
        source_payload["url"] = resolved_source.url
    if resolved_source.doc_token:
        source_payload["doc_token"] = resolved_source.doc_token
    if resolved_source.fetch_error:
        source_payload["fetch_error"] = resolved_source.fetch_error
    if resolved_source.fetch_error_code:
        source_payload["fetch_error_code"] = resolved_source.fetch_error_code
    write_json(task_dir / "source.json", source_payload)
    write_json(
        task_dir / "repos.json",
        {
            "repos": [
                {
                    "id": derive_repo_id(path),
                    "path": path,
                    "status": STATUS_INITIALIZED,
                }
                for path in normalized_repos
            ]
        },
    )
    (task_dir / "prd.source.md").write_text(build_source_markdown(resolved_source, now))
    return task_id, STATUS_INITIALIZED


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


def normalize_title(title: str | None, raw_input: str) -> str:
    if title and title.strip():
        return collapse_spacing(title.strip())
    first_line = raw_input.strip().splitlines()[0].strip()
    if first_line:
        return collapse_spacing(first_line[:80])
    return "未命名任务"


def resolve_source(raw_input: str, explicit_title: str | None) -> ResolvedSource:
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


def infer_title_from_url(raw_input: str) -> str:
    parsed = urlparse(raw_input)
    host = parsed.netloc or ""
    path = parsed.path.strip("/")
    if host or path:
        return f"{host}/{path}".strip("/")[:80]
    return "未命名需求"


def ensure_lark_cli() -> None:
    if shutil.which("lark-cli") is None:
        raise ValueError("lark-cli 不可用，请先安装并完成登录")


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


def build_task_id(title: str) -> str:
    now = datetime.now().astimezone()
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{build_task_slug(title)}"


def build_task_slug(title: str) -> str:
    tokens = [token.lower() for token in _ascii_word.findall(title) if len(token) >= 2]
    if tokens:
        return trim_slug("-".join(tokens[:4]))
    compact = re.sub(r"\s+", "", title)
    if compact:
        return "task"
    return "task"


def trim_slug(value: str) -> str:
    return _slug_dash.sub("-", value.strip("-"))[:48] or "task"


def derive_repo_id(path: str) -> str:
    name = Path(path).name.strip()
    return name or "repo"


def build_source_markdown(source: ResolvedSource, now: datetime) -> str:
    lines = [
        "# PRD Source",
        "",
        f"- title: {source.title}",
        f"- source_type: {source.source_type}",
    ]
    if source.path:
        lines.append(f"- path: {source.path}")
    if source.url:
        lines.append(f"- url: {source.url}")
    if source.doc_token:
        lines.append(f"- doc_token: {source.doc_token}")
    if source.fetch_error:
        lines.append(f"- fetch_error: {source.fetch_error}")
    if source.fetch_error_code:
        lines.append(f"- fetch_error_code: {source.fetch_error_code}")
    lines.extend(
        [
            f"- captured_at: {now.isoformat()}",
            "",
            "---",
            "",
            source.content
            or (
                "当前版本尚未自动拉取该来源的正文内容。\n"
                "请将 PRD 正文粘贴到本文件后，再重新执行 refine。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def collapse_spacing(value: str) -> str:
    return _spacing.sub(" ", value).strip()

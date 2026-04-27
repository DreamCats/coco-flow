"""Cross-repo contract extraction shared by Design and Plan."""

from __future__ import annotations

import re

from coco_flow.engines.shared.models import RepoScope

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def build_design_contracts_payload(design_markdown: str, repo_scopes: list[RepoScope]) -> dict[str, object]:
    repo_ids = [scope.repo_id for scope in repo_scopes if scope.repo_id]
    repo_sections = extract_repo_sections(design_markdown, repo_ids)
    contracts = build_cross_repo_contracts(design_markdown, repo_sections, repo_ids)
    return {
        "contracts": contracts,
        "contract_count": len(contracts),
        "source": "design.md",
    }


def build_cross_repo_contracts(
    design_markdown: str,
    repo_sections: dict[str, str],
    repo_ids: list[str],
) -> list[dict[str, object]]:
    contracts: list[dict[str, object]] = []
    for producer_repo in repo_ids:
        producer_text = repo_sections.get(producer_repo, "")
        if not is_producer_section(producer_repo, producer_text, design_markdown):
            continue
        for consumer_repo in repo_ids:
            if consumer_repo == producer_repo:
                continue
            consumer_text = repo_sections.get(consumer_repo, "")
            if not (is_consumer_section(consumer_text, design_markdown) or shared_dependency_signal(producer_text, consumer_text)):
                continue
            contract = extract_dependency_contract(design_markdown, producer_repo, consumer_repo, producer_text, consumer_text)
            if contract:
                contract["id"] = f"C{len(contracts) + 1}"
                contracts.append(contract)
    return contracts


def extract_repo_sections(markdown: str, repo_ids: list[str]) -> dict[str, str]:
    lines = markdown.splitlines()
    headings: list[tuple[int, int, str]] = []
    starts: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line.strip())
        if not match:
            continue
        title = match.group(2).strip().strip("`")
        level = len(match.group(1))
        headings.append((index, level, title))
        repo_id = match_repo_heading(title, repo_ids)
        if repo_id:
            starts.append((index, level, repo_id))
    sections: dict[str, str] = {}
    for start, level, repo_id in starts:
        end = len(lines)
        for next_start, next_level, _next_title in headings:
            if next_start > start and next_level <= level:
                end = next_start
                break
        sections[repo_id] = "\n".join(lines[start:end]).strip()
    return sections


def match_repo_heading(title: str, repo_ids: list[str]) -> str:
    normalized = title.strip().strip("`")
    for repo_id in repo_ids:
        if normalized == repo_id:
            return repo_id
        if re.match(rf"^{re.escape(repo_id)}(?:$|[\s\-:：\(（\[])", normalized):
            return repo_id
        if normalized.startswith(f"{repo_id} ") or normalized.startswith(f"{repo_id}-") or normalized.startswith(f"{repo_id} -"):
            return repo_id
        if normalized.startswith(f"{repo_id}：") or normalized.startswith(f"{repo_id}:"):
            return repo_id
    return ""


def extract_dependency_contract(
    design_markdown: str,
    producer_repo: str,
    consumer_repo: str,
    producer_text: str,
    consumer_text: str,
) -> dict[str, object]:
    text = "\n".join([producer_text, consumer_text, design_markdown])
    field_name = extract_contract_field_name(text)
    json_tag = extract_json_tag(text, field_name)
    consumer_access = extract_consumer_access(text, field_name)
    if field_name and not consumer_access:
        consumer_access = f"待确认：{consumer_repo} 读取 {field_name}"
    default_value = extract_contract_default_value(text)
    value_semantics = extract_contract_value_semantics(text)
    contract_type = "ab_experiment_field" if any(token in text for token in ("实验", "AB", "abtest")) else "cross_repo_contract"
    if not any([field_name, json_tag, consumer_access, default_value, value_semantics]):
        return {}
    return {
        "type": contract_type,
        "producer_repo": producer_repo,
        "consumer_repo": consumer_repo,
        **({"field_name": field_name} if field_name else {}),
        **({"json_tag": json_tag} if json_tag else {}),
        **({"default_value": default_value} if default_value else {}),
        **({"value_semantics": value_semantics} if value_semantics else {}),
        **({"consumer_access": consumer_access} if consumer_access else {}),
        "compatibility": "默认值必须保持线上原逻辑；consumer 不得在字段缺失或默认值下改变旧链路行为。",
    }


def is_producer_section(repo_id: str, text: str, design_text: str = "") -> bool:
    if looks_like_shared_repo(repo_id):
        return True
    if repo_has_role(repo_id, design_text, "Producer"):
        return True
    if is_consumer_section(text, design_text):
        return False
    return any(token in text for token in ("新增", "定义", "产出", "提供")) and any(
        token in text for token in ("字段", "接口", "模型", "配置", "key", "契约", "AB")
    )


def is_consumer_section(text: str, design_text: str = "") -> bool:
    if any(role in design_text for role in ("Consumer 仓库", "consumer")) and any(token in text for token in ("消费", "接入", "读取")):
        return True
    return any(token in text for token in ("读取", "消费", "依赖", "接入", "使用")) and any(
        token in text for token in ("字段", "接口", "模型", "配置", "key", "契约", "AB")
    )


def repo_has_role(repo_id: str, design_text: str, role: str) -> bool:
    if not design_text:
        return False
    role_patterns = [
        rf"{re.escape(role)}\s*仓库\*\*[:：]\s*{re.escape(repo_id)}",
        rf"{re.escape(role)}\s*仓库[:：]\s*{re.escape(repo_id)}",
        rf"{re.escape(repo_id)}[^\n]*{re.escape(role)}",
    ]
    return any(re.search(pattern, design_text, flags=re.IGNORECASE) for pattern in role_patterns)


def shared_dependency_signal(producer_text: str, consumer_text: str) -> bool:
    shared_terms = {"AB", "实验字段", "字段", "接口", "配置"}
    return any(term in producer_text and term in consumer_text for term in shared_terms)


def looks_like_shared_repo(repo_id: str) -> bool:
    lowered = repo_id.lower()
    return any(token in lowered for token in ("common", "proto", "idl", "model", "schema", "shared"))


def extract_contract_field_name(text: str) -> str:
    patterns = [
        r"(?:字段名|field_name|field)\s*[:：]\s*`?([A-Z][A-Za-z0-9_]{2,})`?",
        r"`?([A-Z][A-Za-z0-9_]*(?:Exp|Experiment|Type|Flag)[A-Za-z0-9_]*)\s+(?:int64|int32|int|bool|string)`?",
        r"([A-Z][A-Za-z0-9_]*(?:Exp|Experiment|Type|Flag)[A-Za-z0-9_]*)\s+(?:int64|int32|int|bool|string)\s+`json:",
        r"`?([A-Z][A-Za-z0-9_]*(?:Exp|Experiment|Type|Flag)[A-Za-z0-9_]*)`?\s*字段",
        r"新增\s+`?([A-Z][A-Za-z0-9_]*(?:Exp|Experiment|Type|Flag)[A-Za-z0-9_]*)`?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def extract_json_tag(text: str, field_name: str) -> str:
    patterns = [
        r"(?:json tag|json_tag|JSON tag)\s*(?:为|=|[:：])\s*`?([a-z][a-z0-9_]+)`?",
        r"`json:\"([a-z][a-z0-9_]+)\"`",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    if field_name:
        return camel_to_snake(field_name)
    return ""


def extract_consumer_access(text: str, field_name: str) -> str:
    if field_name:
        pattern = rf"`?([A-Za-z_][A-Za-z0-9_().]*\.{re.escape(field_name)})`?"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    match = re.search(r"(?:读取|消费|access path|consumer_access)[^`\n]*`([^`]+)`", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def extract_contract_default_value(text: str) -> str:
    patterns = [
        r"(?:默认值|default(?:_value)?)\s*(?:为|=|[:：])\s*`?([A-Za-z0-9_\"'-]+)`?",
        r"([0-9]+)\s*[（(]\s*默认[^）)]*[）)]",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip('"')
    if "默认" in text and "0" in text:
        return "0"
    return ""


def extract_contract_value_semantics(text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"([0-9]+)\s*[（(]([^）)]+)[）)]", text):
        values.append(f"{match.group(1)}: {match.group(2).strip()}")
    slash_values = re.search(r"\b([0-9]+(?:/[0-9]+)+)\b", text)
    if slash_values and not values:
        values.append(f"{slash_values.group(1)}: 待确认")
    if not slash_values:
        for match in re.finditer(r"([0-9]+)\s*(?:对应|代表)\s*([^；;，,\n]+)", text):
            values.append(f"{match.group(1)}: {match.group(2).strip()}")
    return dedupe(values)[:6]


def camel_to_snake(value: str) -> str:
    first = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", first).lower()


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result

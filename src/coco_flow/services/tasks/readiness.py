from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from coco_flow.config import Settings, load_settings
from coco_flow.engines.plan.input import locate_task_dir
from coco_flow.services.queries.task_detail import read_json_file


READINESS_ARTIFACT = "plan-readiness-score.json"

_SECTION_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_UNCERTAINTY_RE = re.compile(r"(待确认|或类似命名|暂时|占位)")


def evaluate_plan_readiness_task(task_id: str, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    if not (task_dir / "design.md").exists() or not (task_dir / "plan.md").exists():
        raise ValueError("需要先生成 design.md 和 plan.md 后才能评测")

    payload = build_plan_readiness_score(task_dir, task_id)
    (task_dir / READINESS_ARTIFACT).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def build_plan_readiness_score(task_dir: Path, task_id: str | None = None) -> dict[str, Any]:
    refined = _read_text(task_dir / "prd-refined.md")
    design = _read_text(task_dir / "design.md")
    plan = _read_text(task_dir / "plan.md")
    combined = "\n".join([design, plan])
    work_items_payload = read_json_file(task_dir / "plan-work-items.json")
    graph_payload = read_json_file(task_dir / "plan-execution-graph.json")
    validation_payload = read_json_file(task_dir / "plan-validation.json")
    result_payload = read_json_file(task_dir / "plan-result.json")
    contracts_payload = read_json_file(task_dir / "design-contracts.json")
    sync_payload = read_json_file(task_dir / "plan-sync.json")
    repos_payload = read_json_file(task_dir / "repos.json")

    acceptance = _section_bullets(refined, "验收标准")
    boundaries = _section_bullets(refined, "边界与非目标") + _section_bullets(refined, "明确不做")
    work_items = _list_of_records(work_items_payload.get("work_items"))
    contracts = _list_of_records(contracts_payload.get("contracts"))
    edges = _list_of_records(graph_payload.get("edges"))
    repo_ids = _repo_ids(repos_payload, work_items)

    requirement = _coverage_score(acceptance, combined)
    boundary = _coverage_score(boundaries, combined)
    repo_clarity = _repo_responsibility_score(repo_ids, work_items, design)
    contract = _contract_score(contracts, combined)
    risk = _risk_resolution_score(combined, result_payload)
    design_quality = _weighted(
        [
            (0.25, requirement),
            (0.20, boundary),
            (0.20, repo_clarity),
            (0.20, contract),
            (0.15, risk),
        ]
    )

    task_coverage = _task_coverage_score(repo_ids, work_items)
    file_specificity = _file_specificity_score(work_items)
    step_actionability, noisy_steps, total_steps = _step_actionability_score(work_items)
    dependency = _dependency_correctness_score(contracts, edges)
    validation = _validation_mapping_score(acceptance, validation_payload)
    code_gate = 1.0 if result_payload.get("code_allowed") is True else 0.0
    plan_executability = _weighted(
        [
            (0.25, task_coverage),
            (0.20, file_specificity),
            (0.20, step_actionability),
            (0.15, dependency),
            (0.10, validation),
            (0.10, code_gate),
        ]
    )

    gate_correctness, gate_issues = _gate_correctness_score(result_payload, sync_payload, contracts, edges)
    noise_control, noise_issues = _noise_control_score(work_items, result_payload, noisy_steps, total_steps)
    pcrs = _weighted(
        [
            (0.35, design_quality),
            (0.45, plan_executability),
            (0.10, gate_correctness),
            (0.10, noise_control),
        ]
    )

    recommendations = _recommendations(
        [
            ("ContractCompleteness", contract),
            ("RiskResolution", risk),
            ("StepActionability", step_actionability),
            ("GateCorrectness", gate_correctness),
            ("NoiseControl", noise_control),
        ],
        gate_issues + noise_issues,
    )
    generated_at = datetime.now().astimezone().isoformat()
    return {
        "task_id": task_id or task_dir.name,
        "generated_at": generated_at,
        "score": _round_score(pcrs * 100),
        "status": _status_label(pcrs * 100),
        "formula": "PCRS = 100 * (0.35*DesignQuality + 0.45*PlanExecutability + 0.10*GateCorrectness + 0.10*NoiseControl)",
        "inputs": {
            "acceptance_count": len(acceptance),
            "boundary_count": len(boundaries),
            "repo_count": len(repo_ids),
            "work_item_count": len(work_items),
            "contract_count": len(contracts),
            "edge_count": len(edges),
            "step_count": total_steps,
        },
        "sections": [
            _section(
                "DesignQuality",
                "Design Quality",
                0.35,
                design_quality,
                "Design 是否讲清需求覆盖、边界、仓库职责、跨仓契约和风险结论。",
                [
                    _metric("RequirementCoverage", "Requirement Coverage", 0.25, requirement, f"{_covered_count(acceptance, combined)}/{len(acceptance)} 条验收标准已映射"),
                    _metric("BoundaryCoverage", "Boundary Coverage", 0.20, boundary, f"{_covered_count(boundaries, combined)}/{len(boundaries)} 条边界已保留"),
                    _metric("RepoResponsibilityClarity", "Repo Responsibility Clarity", 0.20, repo_clarity, _repo_reason(repo_ids, work_items)),
                    _metric("ContractCompleteness", "Contract Completeness", 0.20, contract, _contract_reason(contracts, combined)),
                    _metric("RiskResolution", "Risk Resolution", 0.15, risk, _risk_reason(combined, result_payload)),
                ],
            ),
            _section(
                "PlanExecutability",
                "Plan Executability",
                0.45,
                plan_executability,
                "Plan 是否能直接交给 Code 阶段执行。",
                [
                    _metric("TaskCoverage", "Task Coverage", 0.25, task_coverage, _task_coverage_reason(repo_ids, work_items)),
                    _metric("FileSpecificity", "File Specificity", 0.20, file_specificity, _file_specificity_reason(work_items)),
                    _metric("StepActionability", "Step Actionability", 0.20, step_actionability, f"{max(total_steps - len(noisy_steps), 0)}/{total_steps} 个 step 是可执行动作"),
                    _metric("DependencyCorrectness", "Dependency Correctness", 0.15, dependency, _dependency_reason(contracts, edges)),
                    _metric("ValidationMapping", "Validation Mapping", 0.10, validation, _validation_reason(acceptance, validation_payload)),
                    _metric("CodeGatePass", "Code Gate Pass", 0.10, code_gate, "plan-result.json 已允许进入 Code" if code_gate else "plan-result.json 未允许进入 Code"),
                ],
            ),
            _section(
                "GateCorrectness",
                "Gate Correctness",
                0.10,
                gate_correctness,
                "系统是否正确判断能否进入 Code。",
                [_metric("GateErrorRate", "Gate Error Rate", 1.0, 1.0 - gate_correctness, "; ".join(gate_issues) or "未发现 gate 误判")],
            ),
            _section(
                "NoiseControl",
                "Noise Control",
                0.10,
                noise_control,
                "Plan 中是否混入会干扰 Code agent 的噪音。",
                [_metric("NoiseCount", "Noise Count", 1.0, 1.0 - noise_control, "; ".join(noise_issues) or "未发现证据句、重复文件或已确认 blocker 等噪音")],
            ),
        ],
        "recommendations": recommendations,
        "notes": [
            "评分是进入 Code 前的启发式质量评估，不替代编译、测试和 diff review。",
            "所有子项按 0~1 归一化后带入 PCRS 公式。",
        ],
    }


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _section_bullets(markdown: str, section_name: str) -> list[str]:
    section = _extract_section(markdown, section_name)
    result: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            result.append(stripped[2:].strip())
        elif re.match(r"^\d+\.\s+", stripped):
            result.append(re.sub(r"^\d+\.\s+", "", stripped).strip())
    return [item for item in result if item]


def _extract_section(markdown: str, section_name: str) -> str:
    matches = list(_SECTION_HEADING.finditer(markdown))
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        if title != section_name:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        return markdown[start:end]
    return ""


def _coverage_score(items: list[str], text: str) -> float:
    if not items:
        return 1.0
    return _covered_count(items, text) / len(items)


def _covered_count(items: list[str], text: str) -> int:
    normalized_text = _normalize(text)
    return sum(1 for item in items if _normalize(item) in normalized_text)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).strip("。.;；")


def _list_of_records(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _repo_ids(repos_payload: dict[str, object], work_items: list[dict[str, Any]]) -> list[str]:
    raw_repos = repos_payload.get("repos")
    result: list[str] = []
    if isinstance(raw_repos, list):
        for item in raw_repos:
            if isinstance(item, dict):
                repo_id = str(item.get("id") or "").strip()
                if repo_id:
                    result.append(repo_id)
    if result:
        return _unique(result)
    return _unique(str(item.get("repo_id") or item.get("repoId") or "").strip() for item in work_items)


def _repo_responsibility_score(repo_ids: list[str], work_items: list[dict[str, Any]], design: str) -> float:
    if not repo_ids:
        return 1.0
    item_repos = {str(item.get("repo_id") or item.get("repoId") or "") for item in work_items}
    total = 0.0
    for repo_id in repo_ids:
        if repo_id in design and ("职责判断" in design or "职责" in design):
            total += 1.0
        elif repo_id in item_repos:
            total += 0.75
        elif repo_id in design:
            total += 0.5
    return total / len(repo_ids)


def _contract_score(contracts: list[dict[str, Any]], text: str) -> float:
    if not contracts:
        return 1.0
    scores: list[float] = []
    for contract in contracts:
        filled = sum(
            1
            for key in ("type", "producer_repo", "consumer_repo", "consumer_access", "compatibility")
            if str(contract.get(key) or "").strip()
        )
        score = filled / 5
        scores.append(max(0.0, score - _uncertainty_penalty(text, limit=0.1)))
    return sum(scores) / len(scores)


def _risk_resolution_score(text: str, result_payload: dict[str, object]) -> float:
    blockers = _string_list(result_payload.get("blockers"))
    unresolved_blockers = [item for item in blockers if not item.startswith("已确认")]
    if unresolved_blockers:
        return 0.4
    return max(0.0, 1.0 - _uncertainty_penalty(text, limit=0.15))


def _uncertainty_penalty(text: str, limit: float) -> float:
    return min(limit, len(_UNCERTAINTY_RE.findall(text)) * 0.05)


def _task_coverage_score(repo_ids: list[str], work_items: list[dict[str, Any]]) -> float:
    if not repo_ids:
        return 1.0 if work_items else 0.0
    item_repos = {str(item.get("repo_id") or item.get("repoId") or "") for item in work_items}
    return sum(1 for repo_id in repo_ids if repo_id in item_repos) / len(repo_ids)


def _file_specificity_score(work_items: list[dict[str, Any]]) -> float:
    if not work_items:
        return 0.0
    scoped = 0
    for item in work_items:
        if _string_list(item.get("change_scope") or item.get("changeScope")):
            scoped += 1
    return scoped / len(work_items)


def _step_actionability_score(work_items: list[dict[str, Any]]) -> tuple[float, list[str], int]:
    steps: list[str] = []
    for item in work_items:
        steps.extend(_string_list(item.get("specific_steps") or item.get("specificSteps")))
    if not steps:
        return 0.0, [], 0
    noisy = [step for step in steps if _is_non_action_step(step)]
    return (len(steps) - len(noisy)) / len(steps), noisy, len(steps)


def _is_non_action_step(step: str) -> bool:
    stripped = step.strip()
    if not stripped:
        return True
    if stripped.startswith(("代码证据", "证据", "参考")):
        return True
    if stripped in {"完成相关改动", "按 Design 实现", "实现相关逻辑"}:
        return True
    if re.match(r"^在\s+.+[：:]$", stripped):
        return True
    return False


def _dependency_correctness_score(contracts: list[dict[str, Any]], edges: list[dict[str, Any]]) -> float:
    if not contracts:
        return 1.0
    expected = {
        (str(contract.get("producer_repo") or ""), str(contract.get("consumer_repo") or ""))
        for contract in contracts
    }
    expected.discard(("", ""))
    if not expected:
        return 1.0
    actual = {(str(edge.get("from") or ""), str(edge.get("to") or "")) for edge in edges}
    for edge in edges:
        contract = edge.get("contract")
        if isinstance(contract, dict):
            actual.add((str(contract.get("producer_repo") or ""), str(contract.get("consumer_repo") or "")))
    return sum(1 for edge in expected if edge in actual) / len(expected)


def _validation_mapping_score(acceptance: list[str], validation_payload: dict[str, object]) -> float:
    if not acceptance:
        return 1.0
    text = json.dumps(validation_payload, ensure_ascii=False)
    return _coverage_score(acceptance, text)


def _gate_correctness_score(
    result_payload: dict[str, object],
    sync_payload: dict[str, object],
    contracts: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    issues: list[str] = []
    blockers = _string_list(result_payload.get("blockers"))
    code_allowed = result_payload.get("code_allowed") is True
    if blockers and code_allowed:
        issues.append("存在 blockers 但 code_allowed=true")
    if blockers and all(item.startswith("已确认") for item in blockers) and result_payload.get("code_allowed") is False:
        issues.append("已确认项仍阻断 Code")
    if sync_payload.get("synced") is False and code_allowed:
        issues.append("Plan 未同步但 gate 允许进入 Code")
    if contracts and _dependency_correctness_score(contracts, edges) < 1:
        issues.append("跨仓契约缺少正确依赖边")
    return max(0.0, 1.0 - min(1.0, len(issues) * 0.25)), issues


def _noise_control_score(
    work_items: list[dict[str, Any]],
    result_payload: dict[str, object],
    noisy_steps: list[str],
    total_steps: int,
) -> tuple[float, list[str]]:
    noise: list[str] = []
    evidence_noise = [step for step in noisy_steps if step.startswith(("代码证据", "证据")) or re.match(r"^在\s+.+[：:]$", step)]
    if evidence_noise:
        noise.append(f"{len(evidence_noise)} 个证据句或悬空标题进入 steps")
    duplicate_files = _duplicate_file_noise(work_items)
    if duplicate_files:
        noise.append(f"{len(duplicate_files)} 个 change_scope 同时出现完整路径和 basename")
    confirmed_blockers = [item for item in _string_list(result_payload.get("blockers")) if item.startswith("已确认")]
    if confirmed_blockers:
        noise.append(f"{len(confirmed_blockers)} 个已确认项仍作为 blocker")
    total_items = max(1, total_steps + len(work_items))
    score = 1.0 - min(1.0, (len(evidence_noise) + len(duplicate_files) + len(confirmed_blockers)) / total_items)
    return score, noise


def _duplicate_file_noise(work_items: list[dict[str, Any]]) -> list[str]:
    duplicates: list[str] = []
    for item in work_items:
        scopes = _string_list(item.get("change_scope") or item.get("changeScope"))
        scope_set = set(scopes)
        for scope in scopes:
            basename = Path(scope).name
            if "/" in scope and basename in scope_set:
                duplicates.append(scope)
    return duplicates


def _weighted(items: list[tuple[float, float]]) -> float:
    return sum(weight * score for weight, score in items)


def _metric(metric_id: str, label: str, weight: float, score: float, reason: str) -> dict[str, Any]:
    return {
        "id": metric_id,
        "label": label,
        "weight": weight,
        "score": _round_score(score),
        "reason": reason,
    }


def _section(section_id: str, label: str, weight: float, score: float, reason: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": section_id,
        "label": label,
        "weight": weight,
        "score": _round_score(score),
        "reason": reason,
        "children": children,
    }


def _round_score(value: float) -> float:
    return round(value + 1e-9, 3)


def _status_label(score: float) -> str:
    if score >= 85:
        return "ready"
    if score >= 70:
        return "review"
    return "revise"


def _recommendations(metrics: list[tuple[str, float]], issues: list[str]) -> list[str]:
    result = list(issues)
    for metric_id, score in metrics:
        if score >= 0.95:
            continue
        if metric_id == "ContractCompleteness":
            result.append("收敛实验字段、接口或配置契约，避免字段名和默认值仍保留待确认表述。")
        elif metric_id == "RiskResolution":
            result.append("把待确认项改写成明确结论，无法确认的内容应保留为真实 blocker。")
        elif metric_id == "StepActionability":
            result.append("把参考句、证据句改成可执行动作，确保每个 step 都有对象和结果。")
        elif metric_id == "GateCorrectness":
            result.append("检查 Plan gate、同步状态和 blocker，避免错误放行或错误阻断。")
        elif metric_id == "NoiseControl":
            result.append("清理证据句、重复文件路径和已确认 blocker，降低 Code 阶段干扰。")
    return _unique(result)


def _repo_reason(repo_ids: list[str], work_items: list[dict[str, Any]]) -> str:
    return f"{len(repo_ids)} 个绑定仓库，{len(work_items)} 个 work item；Design/Plan 已描述仓库职责"


def _contract_reason(contracts: list[dict[str, Any]], text: str) -> str:
    if not contracts:
        return "未发现跨仓契约，按单仓或无契约场景处理"
    if _UNCERTAINTY_RE.search(text):
        return "跨仓契约字段完整，但文档仍存在待确认或占位表述"
    return f"{len(contracts)} 条跨仓契约包含 producer、consumer、访问方式和兼容策略"


def _risk_reason(text: str, result_payload: dict[str, object]) -> str:
    blockers = _string_list(result_payload.get("blockers"))
    if blockers:
        return f"plan-result.json 中仍有 {len(blockers)} 个 blocker"
    if _UNCERTAINTY_RE.search(text):
        return "无 gate blocker，但文档仍存在轻微待确认或占位表述"
    return "待确认项已处理，且没有 gate blocker"


def _task_coverage_reason(repo_ids: list[str], work_items: list[dict[str, Any]]) -> str:
    item_repos = {str(item.get("repo_id") or item.get("repoId") or "") for item in work_items}
    covered = sum(1 for repo_id in repo_ids if repo_id in item_repos)
    return f"{covered}/{len(repo_ids)} 个 must-change repo 已生成 work item"


def _file_specificity_reason(work_items: list[dict[str, Any]]) -> str:
    scoped = sum(1 for item in work_items if _string_list(item.get("change_scope") or item.get("changeScope")))
    return f"{scoped}/{len(work_items)} 个 work item 有明确 change_scope"


def _dependency_reason(contracts: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    if not contracts:
        return "没有跨仓契约依赖需要建图"
    correct = _dependency_correctness_score(contracts, edges)
    return f"{round(correct * len(contracts))}/{len(contracts)} 条跨仓依赖边正确"


def _validation_reason(acceptance: list[str], validation_payload: dict[str, object]) -> str:
    text = json.dumps(validation_payload, ensure_ascii=False)
    return f"{_covered_count(acceptance, text)}/{len(acceptance)} 条验收标准已映射到验证"


def _string_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _unique(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result

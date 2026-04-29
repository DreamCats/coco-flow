from __future__ import annotations

from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from coco_flow.clients import AgentSessionHandle
from coco_flow.config import Settings
from coco_flow.engines.design.evidence import build_research_plan, normalize_agent_research_payload, research_single_repo, run_agent_repo_research
from coco_flow.engines.design.evidence.repo_index import build_repo_context_package, load_or_build_repo_index
from coco_flow.engines.design.evidence.agent_research import (
    _apply_experiment_gate_repo_policy,
    _merge_repo_research_payload,
    _normalize_research_review,
    _normalize_research_instructions,
    _research_instructions_by_repo,
    _retry_instructions_for_repo,
)
from coco_flow.engines.design.knowledge import build_design_skills_bundle
from coco_flow.engines.design.pipeline import _build_degraded_design_markdown
from coco_flow.engines.design.runtime.agent import _repair_common_agent_json, run_agent_json
from coco_flow.engines.design.types import DesignInputBundle
from coco_flow.engines.design.writer.markdown import (
    build_local_doc_only_design_markdown,
    render_research_summary_markdown,
    sanitize_design_markdown_paths,
    write_doc_only_design_markdown,
)
from coco_flow.engines.plan.compiler import build_structured_plan_artifacts, render_plan_markdown
from coco_flow.engines.plan.knowledge import build_plan_skills_bundle
from coco_flow.engines.plan.knowledge.selection import build_plan_skills_context
from coco_flow.engines.plan.types import PlanPreparedInput
from coco_flow.engines.shared.models import RefinedSections, RepoScope
from coco_flow.services.tasks.design import design_task
from coco_flow.services.tasks.plan import start_planning_task
from coco_flow.services.tasks.design_sync import sync_design_task


def make_settings(root: Path, *, plan_executor: str = "local") -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
        refine_executor="local",
        plan_executor=plan_executor,
        code_executor="local",
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class DesignPipelineTest(unittest.TestCase):
    def test_design_research_summary_markdown_hides_internal_payload_shape(self) -> None:
        rendered = render_research_summary_markdown(
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "work_hypothesis": "required",
                        "candidate_files": [
                            {
                                "path": "entities/converters/auction_converters/regular_auction_converter.go",
                                "kind": "core_change",
                                "confidence": "high",
                                "matched_behavior": "预热态、竞拍中",
                                "core_evidence": True,
                            }
                        ],
                    }
                ]
            }
        )

        self.assertIn("### live_pack", rendered)
        self.assertIn("必改", rendered)
        self.assertIn("regular_auction_converter.go", rendered)
        self.assertIn("命中 预热态、竞拍中 相关代码证据", rendered)
        self.assertNotIn("requires_code_change", rendered)
        self.assertNotIn("{'path'", rendered)
        self.assertNotIn("core_evidence", rendered)

    def test_design_research_summary_markdown_renders_repo_relative_paths(self) -> None:
        rendered = render_research_summary_markdown(
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "repo_path": "/repo/live_pack",
                        "work_hypothesis": "required",
                        "claims": [
                            {
                                "claim": "标题在 getAuctionTitle 生成",
                                "status": "supported",
                                "files": [
                                    {
                                        "path": "/repo/live_pack/entities/converters/auction_converters/regular_auction_converter.go",
                                        "line": 594,
                                        "symbol": "getAuctionTitle",
                                    }
                                ],
                            }
                        ],
                        "candidate_files": [
                            {
                                "path": "/repo/live_pack/entities/converters/auction_converters/regular_auction_converter.go",
                                "reason": "核心落点。",
                            }
                        ],
                    }
                ]
            }
        )

        self.assertIn("entities/converters/auction_converters/regular_auction_converter.go", rendered)
        self.assertNotIn("/repo/live_pack", rendered)

    def test_agent_research_payload_normalizes_to_design_research_summary(self) -> None:
        payload = normalize_agent_research_payload(
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "repo_path": "/repo/live_pack",
                        "work_hypothesis": "required",
                        "confidence": "high",
                        "skill_usage": {
                            "read_files": ["/skills/auction/SKILL.md"],
                            "applied_rules": ["讲解卡标题只改 converter 层"],
                            "derived_search_hints": ["AuctionTitle", "bagGetRegularTitle"],
                        },
                        "claims": [{"claim": "标题在 converter 组装", "status": "supported", "files": []}],
                        "candidate_files": [
                            {
                                "path": "entities/converters/auction_converters/converter_helpers.go",
                                "symbol": "bagGetRegularTitle",
                                "reason": "直接给 AuctionTitle 赋值。",
                                "confidence": "high",
                            }
                        ],
                        "rejected_candidates": [{"path": "pin_card.go", "reason": "PRD 明确不改讲解卡。"}],
                    }
                ],
                "summary": "Research Agent completed.",
            }
        )

        self.assertEqual(payload["source"], "agent")
        self.assertEqual(payload["candidate_file_count"], 1)
        self.assertEqual(payload["research_status"], "ok")
        self.assertEqual(payload["repos"][0]["work_hypothesis"], "required")
        self.assertEqual(payload["repos"][0]["skill_usage"]["read_files"], ["/skills/auction/SKILL.md"])
        self.assertEqual(payload["repos"][0]["candidate_files"][0]["symbol"], "bagGetRegularTitle")
        self.assertEqual(payload["repos"][0]["rejected_candidates"][0]["path"], "pin_card.go")

    def test_agent_research_payload_accepts_common_agent_field_aliases(self) -> None:
        payload = normalize_agent_research_payload(
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "repo_path": "/repo/live_pack",
                        "work_hypothesis": "required",
                        "confidence": "high",
                        "candidate_files": [
                            {
                                "file_path": "/repo/live_pack/entities/converters/auction_converters/regular_auction_converter.go",
                                "line_start": 594,
                                "reason": "getAuctionTitle 组装标题。",
                                "confidence": "high",
                            }
                        ],
                        "related_files": ["/repo/live_pack/engines/live_bag_auction_list.go"],
                        "boundaries": [{"description": "不修改 temporary listing。"}],
                        "unknowns": [{"question": "AB key 未确认", "next_steps": "确认实验参数名"}],
                    }
                ]
            }
        )

        repo = payload["repos"][0]
        self.assertEqual(repo["candidate_files"][0]["path"], "/repo/live_pack/entities/converters/auction_converters/regular_auction_converter.go")
        self.assertEqual(repo["candidate_files"][0]["line"], 594)
        self.assertEqual(repo["related_files"][0]["path"], "/repo/live_pack/engines/live_bag_auction_list.go")
        self.assertEqual(repo["boundaries"], ["不修改 temporary listing。"])
        self.assertEqual(repo["unknowns"], ["AB key 未确认；下一步：确认实验参数名"])
        self.assertIn("live_pack: AB key 未确认", payload["unknowns"][0])

    def test_agent_research_payload_accepts_string_candidate_files(self) -> None:
        payload = normalize_agent_research_payload(
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "repo_path": "/repo/live_pack",
                        "candidate_files": [
                            "/repo/live_pack/entities/converters/auction_converters/regular_auction_converter.go",
                            "constdef/component.go",
                        ],
                    }
                ]
            }
        )

        repo = payload["repos"][0]
        self.assertEqual(payload["candidate_file_count"], 2)
        self.assertEqual(repo["candidate_files"][0]["path"], "/repo/live_pack/entities/converters/auction_converters/regular_auction_converter.go")
        self.assertEqual(repo["candidate_files"][1]["path"], "constdef/component.go")

    def test_agent_json_preserves_failed_raw_template_for_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            prepared = self._design_bundle(repo_scopes=[RepoScope(repo_id="demo", repo_path=str(root / "repo"))])
            prepared.task_dir = root / "task"
            prepared.task_dir.mkdir()
            with patch(
                "coco_flow.engines.design.runtime.agent._run_agent_template",
                return_value='{"repo_id": "__FILL__"}',
            ):
                with self.assertRaisesRegex(ValueError, "failed_output="):
                    run_agent_json(prepared, settings, "{}", lambda path: path, ".design-research-agent-demo-")

            failed_files = list(prepared.task_dir.glob(".design-research-agent-demo-*-failed.json"))
            self.assertEqual(len(failed_files), 1)
            self.assertIn("__FILL__", failed_files[0].read_text(encoding="utf-8"))

    def test_agent_json_writes_transcript_with_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            prepared = self._design_bundle(repo_scopes=[RepoScope(repo_id="demo", repo_path=str(root / "repo"))])
            prepared.task_dir = root / "task"
            prepared.task_dir.mkdir()

            def fake_run_agent(prompt: str, *_args, **_kwargs) -> str:
                Path(prompt).write_text('{"ok": true}\n', encoding="utf-8")
                return "done"

            logs: list[str] = []
            with patch("coco_flow.engines.design.runtime.agent.CocoACPClient.run_agent", side_effect=fake_run_agent):
                payload = run_agent_json(
                    prepared,
                    settings,
                    "{}",
                    lambda path: path,
                    ".design-research-agent-demo-",
                    role="design_research:demo",
                    stage="repo_research",
                    on_log=logs.append,
                )

            self.assertEqual(payload, {"ok": True})
            transcript = (prepared.task_dir / "design-agent-transcript.jsonl").read_text(encoding="utf-8")
            row = json.loads(transcript)
            self.assertEqual(row["role"], "design_research:demo")
            self.assertEqual(row["stage"], "repo_research")
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["response"], '{"ok": true}\n')
            self.assertIsInstance(row["duration_ms"], int)
            self.assertTrue(any("duration_ms=" in item for item in logs))

    def test_agent_json_repair_quotes_line_number_ranges(self) -> None:
        repaired = _repair_common_agent_json('{"file": "abtest/struct.go", "line": 983-1017, "claim": "ok"}')

        self.assertEqual(json.loads(repaired)["line"], "983-1017")

    def test_agent_json_repair_escapes_control_chars_inside_strings(self) -> None:
        repaired = _repair_common_agent_json('{"evidence": "line 1:\tvalue\nline 2"}')

        self.assertEqual(json.loads(repaired)["evidence"], "line 1:\tvalue\nline 2")

    def test_agent_research_payload_marks_failed_repo_as_failed_summary(self) -> None:
        payload = normalize_agent_research_payload(
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "repo_path": "/repo/live_pack",
                        "research_status": "failed",
                        "research_error": "Internal error",
                        "unknowns": ["Research Agent failed for repo live_pack: Internal error"],
                    }
                ],
                "summary": "Research Agent failed.",
            }
        )

        self.assertEqual(payload["research_status"], "failed")
        self.assertEqual(payload["candidate_file_count"], 0)
        self.assertIn("live_pack: Research Agent failed", payload["unknowns"][0])

    def test_research_review_pass_is_overridden_when_repo_failed(self) -> None:
        review = _normalize_research_review(
            {
                "passed": True,
                "decision": "pass",
                "confidence": "high",
                "blocking_issues": [],
                "research_instructions": [],
                "reason": "core repo evidence is enough",
            },
            {
                "repos": [
                    {"repo_id": "live_pack", "research_status": "ok"},
                    {"repo_id": "live_common", "research_status": "failed"},
                ]
            },
        )

        self.assertFalse(review["passed"])
        self.assertEqual(review["decision"], "redo_research")
        self.assertIn("live_common", review["research_instructions"][0])
        self.assertIn("failed", review["blocking_issues"][0]["summary"])

    def test_research_review_redo_becomes_pass_when_design_starting_point_exists(self) -> None:
        review = _normalize_research_review(
            {
                "passed": False,
                "decision": "redo_research",
                "confidence": "medium",
                "blocking_issues": ["缺少配置 key 细节"],
                "research_instructions": [{"repo_id": "live_pack", "instructions": ["继续补查配置 key"]}],
                "reason": "还缺实现细节。",
            },
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "research_status": "ok",
                        "work_hypothesis": "required",
                        "confidence": "high",
                        "skill_usage": {"read_files": ["/repo/live_pack/entities/converters/auction_converters/converter_helpers.go"]},
                        "claims": [{"claim": "核心函数已定位"}],
                        "candidate_files": [{"path": "entities/converters/auction_converters/converter_helpers.go"}],
                    },
                    {
                        "repo_id": "live_common",
                        "research_status": "ok",
                        "work_hypothesis": "conditional",
                        "confidence": "high",
                        "claims": [{"claim": "配置结构已定位"}],
                        "candidate_files": [{"path": "abtest/struct.go"}],
                    },
                ]
            },
        )

        self.assertTrue(review["passed"])
        self.assertEqual(review["decision"], "pass")
        self.assertEqual(review["research_instructions"], [])
        self.assertIn("remaining gaps", review["reason"])

    def test_research_review_redo_is_not_overridden_when_candidate_file_was_not_read(self) -> None:
        review = _normalize_research_review(
            {
                "passed": False,
                "decision": "redo_research",
                "confidence": "medium",
                "blocking_issues": [],
                "research_instructions": ["读取候选文件"],
                "reason": "候选文件未读。",
            },
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "research_status": "ok",
                        "work_hypothesis": "required",
                        "confidence": "high",
                        "skill_usage": {"read_files": ["/skills/auction/SKILL.md"]},
                        "claims": [{"claim": "核心函数已定位"}],
                        "candidate_files": [{"path": "entities/converters/auction_converters/regular_auction_converter.go"}],
                    }
                ]
            },
        )

        self.assertFalse(review["passed"])
        self.assertEqual(review["decision"], "redo_research")
        self.assertEqual(review["research_instructions"], ["读取候选文件"])

    def test_experiment_gate_keeps_shared_config_repo_conditional_without_explicit_key(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[
                RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
            ],
            title="实验组竞拍购物袋标题增加 Auction 标识",
            refined_markdown="命中实验时，regular auction 标题前增加 Auction 标识。未命中实验时保持不变。",
        )
        payload = {
            "repos": [
                {
                    "repo_id": "live_common",
                    "repo_path": "/repo/live_common",
                    "research_status": "ok",
                    "work_hypothesis": "not_needed",
                    "confidence": "high",
                    "skill_usage": {
                        "read_files": ["/repo/live_common/abtest/struct.go"],
                        "applied_rules": ["live_common 提供公共 AB 实验配置"],
                        "derived_search_hints": ["确认是否需要新增 AB 参数"],
                    },
                    "claims": [{"claim": "live_common 是公共实验配置仓"}],
                    "candidate_files": [],
                }
            ],
            "summary": "Research Agent completed.",
        }

        adjusted = _apply_experiment_gate_repo_policy(prepared, payload)
        repo = adjusted["repos"][0]

        self.assertEqual(repo["work_hypothesis"], "conditional")
        self.assertEqual(repo["confidence"], "medium")
        self.assertIn("未指定实验 key", repo["unknowns"][0])

    def test_experiment_gate_allows_not_needed_when_refined_names_experiment_key(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[RepoScope(repo_id="live_common", repo_path="/repo/live_common")],
            title="实验组竞拍购物袋标题增加 Auction 标识",
            refined_markdown="命中实验 key `RegularAuctionTitleAuctionLabelEnabled` 时，标题前增加 Auction 标识。",
        )
        payload = {
            "repos": [
                {
                    "repo_id": "live_common",
                    "repo_path": "/repo/live_common",
                    "research_status": "ok",
                    "work_hypothesis": "not_needed",
                    "confidence": "high",
                    "skill_usage": {"applied_rules": ["live_common 提供公共 AB 实验配置"]},
                    "claims": [],
                    "candidate_files": [],
                }
            ],
            "summary": "Research Agent completed.",
        }

        adjusted = _apply_experiment_gate_repo_policy(prepared, payload)

        self.assertEqual(adjusted["repos"][0]["work_hypothesis"], "not_needed")

    def test_research_review_instruction_objects_keep_repo_scope(self) -> None:
        instructions = _normalize_research_instructions(
            [
                {
                    "repo_id": "live_pack",
                    "instructions": ["查看 converter_helpers.go", "确认 AB 参数"],
                },
                {
                    "repo_id": "live_common",
                    "instructions": ["查看 abtest/struct.go"],
                },
            ]
        )

        self.assertEqual(
            instructions,
            [
                "live_pack: 查看 converter_helpers.go",
                "live_pack: 确认 AB 参数",
                "live_common: 查看 abtest/struct.go",
            ],
        )

    def test_agent_research_preserves_repo_evidence_when_research_supervisor_fails(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[RepoScope(repo_id="live_pack", repo_path="/repo/live_pack")],
            title="竞拍标题增加 Auction 标识",
            refined_markdown="regular auction 标题需要增加 Auction 前缀。",
        )
        repo_payload = {
            "repo_id": "live_pack",
            "repo_path": "/repo/live_pack",
            "research_status": "ok",
            "work_hypothesis": "required",
            "confidence": "high",
            "skill_usage": {
                "read_files": ["/skills/auction/SKILL.md"],
                "applied_rules": ["regular auction title workflow"],
                "derived_search_hints": ["getAuctionTitle"],
            },
            "claims": [{"claim": "标题在 getAuctionTitle 生成", "evidence": ["regular_auction_converter.go:594"]}],
            "candidate_files": [
                {
                    "path": "entities/converters/auction_converters/regular_auction_converter.go",
                    "symbol": "getAuctionTitle",
                    "evidence": ["函数返回 regular auction 标题"],
                }
            ],
        }
        logs: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            with (
                patch("coco_flow.engines.design.evidence.agent_research._run_repo_research_agents", return_value=[repo_payload]),
                patch(
                    "coco_flow.engines.design.evidence.agent_research._review_research_payload",
                    side_effect=RuntimeError("design_agent_template_unfilled"),
                ),
            ):
                payload = run_agent_repo_research(prepared, settings, on_log=logs.append)

        self.assertEqual(payload["candidate_file_count"], 1)
        self.assertEqual(payload["repos"][0]["research_status"], "ok")
        self.assertEqual(payload["repos"][0]["candidate_files"][0]["path"], "entities/converters/auction_converters/regular_auction_converter.go")
        self.assertEqual(payload["research_review"]["decision"], "needs_human")
        self.assertEqual(payload["research_review"]["blocking_issues"][0]["type"], "research_supervisor_failed")
        self.assertTrue(any("design_research_supervisor_failed" in item for item in logs))

    def test_agent_research_retry_failure_does_not_overwrite_previous_repo_evidence(self) -> None:
        previous = {
            "repo_id": "live_pack",
            "repo_path": "/repo/live_pack",
            "research_status": "ok",
            "work_hypothesis": "required",
            "confidence": "high",
            "candidate_files": ["entities/converters/auction_converters/converter_helpers.go"],
            "unknowns": ["AB key 待确认"],
        }
        failed_retry = {
            "repo_id": "live_pack",
            "repo_path": "/repo/live_pack",
            "research_status": "failed",
            "research_error": "acp session/prompt failed: Internal error",
            "candidate_files": [],
            "unknowns": ["Research Agent failed for repo live_pack"],
        }

        merged = _merge_repo_research_payload(previous, failed_retry)

        self.assertEqual(merged["research_status"], "ok")
        self.assertEqual(merged["candidate_files"], ["entities/converters/auction_converters/converter_helpers.go"])
        self.assertIn("AB key 待确认", merged["unknowns"])
        self.assertIn("Supplemental Research Agent retry failed", merged["unknowns"][-1])
        self.assertEqual(merged["retry_errors"], ["acp session/prompt failed: Internal error"])

    def test_agent_research_retry_instructions_merge_global_and_repo_specific_items(self) -> None:
        retry = _retry_instructions_for_repo(
            {
                "*": ["搜索 Starling key", "查看 git history"],
                "live_pack": ["检查 bagGetRegularTitle 调用点", "搜索 Starling key"],
            },
            "live_pack",
        )

        self.assertEqual(retry, ["搜索 Starling key", "查看 git history", "检查 bagGetRegularTitle 调用点"])

    def test_agent_research_retry_freezes_high_confidence_not_needed_repo(self) -> None:
        retry_by_repo = _research_instructions_by_repo(
            [
                RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
            ],
            {"research_instructions": ["补充 Starling key 获取方式", "live_common: 确认是否需要新增 AB 参数"]},
            {
                "repos": [
                    {"repo_id": "live_pack", "research_status": "ok", "work_hypothesis": "required", "confidence": "high"},
                    {"repo_id": "live_common", "research_status": "ok", "work_hypothesis": "not_needed", "confidence": "high"},
                ]
            },
        )

        self.assertEqual(retry_by_repo["live_pack"], ["补充 Starling key 获取方式"])
        self.assertEqual(retry_by_repo["live_common"], ["live_common: 确认是否需要新增 AB 参数"])

    def test_research_summary_markdown_renders_agent_claims_and_review(self) -> None:
        rendered = render_research_summary_markdown(
            {
                "research_review": {
                    "passed": False,
                    "decision": "redo_research",
                    "reason": "缺少标题赋值链路。",
                    "blocking_issues": [{"summary": "candidate 未证明能改标题。"}],
                },
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "work_hypothesis": "required",
                        "skill_usage": {
                            "read_files": ["/skills/auction/SKILL.md"],
                            "applied_rules": ["讲解卡标题只改 converter 层"],
                            "derived_search_hints": ["AuctionTitle"],
                        },
                        "claims": [
                            {
                                "claim": "标题在 converter 组装",
                                "status": "supported",
                                "files": [
                                    {
                                        "path": "entities/converters/auction_converters/converter_helpers.go",
                                        "line": 241,
                                        "symbol": "AuctionTitle",
                                    }
                                ],
                            }
                        ],
                        "candidate_files": [
                            {
                                "path": "entities/converters/auction_converters/converter_helpers.go",
                                "reason": "直接给 AuctionTitle 赋值。",
                            }
                        ],
                        "rejected_candidates": [{"path": "pin_card.go", "reason": "PRD 明确不改讲解卡。"}],
                    }
                ],
            }
        )

        self.assertIn("Research Supervisor", rendered)
        self.assertIn("redo_research", rendered)
        self.assertIn("标题在 converter 组装", rendered)
        self.assertIn("Skill/SOP 使用", rendered)
        self.assertIn("/skills/auction/SKILL.md", rendered)
        self.assertIn("讲解卡标题只改 converter 层", rendered)
        self.assertIn("converter_helpers.go:241", rendered)
        self.assertIn("已拒绝候选", rendered)
        self.assertIn("pin_card.go", rendered)

    def test_degraded_design_markdown_surfaces_research_blockers_and_next_steps(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[RepoScope(repo_id="live_pack", repo_path="/repo/live_pack")],
            title="实验组竞拍购物袋标题增加 Auction 标识",
            refined_markdown="命中实验时标题加 Auction。",
        )

        markdown = _build_degraded_design_markdown(
            prepared,
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "work_hypothesis": "required",
                        "claims": [{"claim": "标题在 getAuctionTitle 生成", "status": "supported"}],
                        "candidate_files": [{"path": "/repo/live_pack/entities/converters/auction_converters/regular_auction_converter.go", "symbol": "getAuctionTitle"}],
                    }
                ],
                "research_review": {
                    "blocking_issues": [{"summary": "缺少实验开关名称。"}],
                    "research_instructions": ["确认 live_common AB 参数命名。"],
                },
            },
            {"blocking_issues": [{"summary": "Research Gate 未通过。"}]},
        )

        self.assertIn("## 设计状态", markdown)
        self.assertIn("人工确认版设计草稿", markdown)
        self.assertIn("## 已确认设计基础", markdown)
        self.assertIn("标题在 getAuctionTitle 生成", markdown)
        self.assertIn("regular_auction_converter.go / getAuctionTitle", markdown)
        self.assertIn("## 待确认设计决策", markdown)
        self.assertIn("待确认：缺少实验开关名称", markdown)
        self.assertIn("## 补齐建议", markdown)
        self.assertIn("确认 live_common AB 参数命名", markdown)
        self.assertNotIn("/repo/live_pack", markdown)

    def test_design_markdown_sanitizer_renders_repo_relative_paths(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[RepoScope(repo_id="live_pack", repo_path="/repo/live_pack")],
            title="实验组竞拍购物袋标题增加 Auction 标识",
            refined_markdown="命中实验时 regular auction 标题拼接 Auction 标识。",
        )
        markdown = sanitize_design_markdown_paths(
            prepared,
            "- 仓库路径：/repo/live_pack\n"
            "- 文件：`/repo/live_pack/entities/converters/auction_converters/regular_auction_converter.go`\n",
        )

        self.assertIn("仓库：live_pack", markdown)
        self.assertIn("`entities/converters/auction_converters/regular_auction_converter.go`", markdown)
        self.assertNotIn("/repo/live_pack", markdown)

    def test_local_design_markdown_includes_actionable_solution_and_validation(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[RepoScope(repo_id="live_pack", repo_path="/repo/live_pack")],
            title="实验组竞拍讲解卡标题增加 Auction 标识",
            refined_markdown="命中实验时 regular auction 标题拼接 Auction 标识。",
        )
        prepared.sections = RefinedSections(
            change_scope=["命中实验， regular auction 讲解卡标题拼接 `Auction` 标识"],
            non_goals=["不改 surprise set 和 temporary listing", "不改购物袋标题"],
            key_constraints=[],
            acceptance_criteria=[
                "命中实验时，regular auction 标题前增加本地化的 `Auction` 标识。",
                "如果本地化标识取值异常为空，则回退为原标题，不出现空前缀或异常连接符。",
                "未命中实验时，标题保持现有线上逻辑不变。",
            ],
            open_questions=[],
            raw="",
        )

        markdown = build_local_doc_only_design_markdown(
            prepared,
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "repo_path": "/repo/live_pack",
                        "work_hypothesis": "required",
                        "candidate_files": [
                            {
                                "path": "entities/converters/auction_converters/regular_auction_converter.go",
                                "matched_behavior": "regular auction、标题",
                            }
                        ],
                    }
                ]
            },
        )

        self.assertIn("## 方案设计", markdown)
        self.assertIn("## 分仓库职责", markdown)
        self.assertIn("- 改造方案：", markdown)
        self.assertIn("尚不足以确定精准文件落点", markdown)
        self.assertNotIn("代码线索", markdown)
        self.assertNotIn("core_evidence", markdown)
        self.assertIn("用户可见变化", markdown)
        self.assertIn("服务端策略", markdown)
        self.assertIn("实验控制", markdown)
        self.assertIn("实验命中、异常回退、未命中不变", markdown)
        self.assertIn("## 验收与验证", markdown)
        self.assertIn("回退为原标题", markdown)
        self.assertIn("用户可见表达所需资源", markdown)
        self.assertIn("不改购物袋标题", markdown)

    def test_local_design_markdown_renders_conditional_repo_responsibility(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[
                RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
            ],
            title="实验组竞拍讲解卡整数金额隐藏尾部 `.00`",
            refined_markdown="仅竞拍讲解卡价格展示变化。",
        )
        prepared.sections = RefinedSections(
            change_scope=["仅竞拍讲解卡价格展示变化"],
            non_goals=["不改购物袋价格展示"],
            key_constraints=[],
            acceptance_criteria=["未命中实验时保持现有线上逻辑不变。"],
            open_questions=[],
            raw="",
        )

        markdown = build_local_doc_only_design_markdown(
            prepared,
            {
                "repos": [
                    {"repo_id": "live_pack", "repo_path": "/repo/live_pack", "work_hypothesis": "required"},
                    {"repo_id": "live_common", "repo_path": "/repo/live_common", "work_hypothesis": "conditional"},
                ]
            },
        )

        self.assertIn("### live_pack", markdown)
        self.assertIn("职责判断：必改", markdown)
        self.assertIn("### live_common", markdown)
        self.assertIn("职责判断：条件改", markdown)
        self.assertIn("仅当缺少公共字段、配置或协议能力时才需要改动", markdown)

    def test_repo_research_includes_git_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            self._run(repo_dir, "git", "init")
            self._run(repo_dir, "git", "config", "user.email", "test@example.com")
            self._run(repo_dir, "git", "config", "user.name", "Test User")
            (repo_dir / "auction_config.go").write_text(
                "package demo\n\nfunc AuctionTextConfig() string { return \"Starting bid\" }\n",
                encoding="utf-8",
            )
            self._run(repo_dir, "git", "add", ".")
            self._run(repo_dir, "git", "commit", "-m", "update auction text config")

            payload = research_single_repo(
                "demo",
                str(repo_dir),
                {
                    "search_terms": ["auction", "Starting", "bid"],
                    "budget": {"max_files_read": 4, "max_search_commands": 3},
                },
            )

            git_evidence = payload["git_evidence"]
            self.assertTrue(git_evidence)
            self.assertTrue(any(item["path"] == "auction_config.go" for item in git_evidence))
            self.assertGreaterEqual(payload["budget_used"]["git_commands"], 1)

    def test_repo_index_persists_files_symbols_and_git_without_livecoding_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo_dir = root / "repo"
            repo_dir.mkdir()
            self._run(repo_dir, "git", "init")
            self._run(repo_dir, "git", "config", "user.email", "test@example.com")
            self._run(repo_dir, "git", "config", "user.name", "Test User")
            (repo_dir / "regular_auction_converter.go").write_text(
                "package demo\n\nfunc getAuctionTitle() string { return \"Auction title\" }\n",
                encoding="utf-8",
            )
            (repo_dir / ".livecoding" / "context").mkdir(parents=True)
            (repo_dir / ".livecoding" / "context" / "auction_context.go").write_text(
                "package hidden\n\nfunc HiddenAuctionContext() {}\n",
                encoding="utf-8",
            )
            self._run(repo_dir, "git", "add", "regular_auction_converter.go")
            self._run(repo_dir, "git", "commit", "-m", "add auction title converter")

            repo = RepoScope(repo_id="demo", repo_path=str(repo_dir))
            first = load_or_build_repo_index(repo, settings)
            second = load_or_build_repo_index(repo, settings)

            self.assertEqual(first["index_status"], "rebuilt")
            self.assertEqual(second["index_status"], "cache_hit")
            paths = [item["path"] for item in second["files"]]
            symbols = [item["name"] for item in second["symbols"]]
            self.assertIn("regular_auction_converter.go", paths)
            self.assertIn("getAuctionTitle", symbols)
            self.assertNotIn(".livecoding/context/auction_context.go", paths)
            self.assertTrue((settings.config_root / "repo-index").is_dir())

            (repo_dir / "regular_auction_converter.go").write_text(
                "package demo\n\nfunc getAuctionTitle() string { return \"Auction title v2\" }\n",
                encoding="utf-8",
            )
            dirty = load_or_build_repo_index(repo, settings)
            self.assertEqual(dirty["index_status"], "rebuilt")

    def test_repo_context_package_ranks_index_clues_for_research_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo_dir = root / "repo"
            repo_dir.mkdir()
            self._run(repo_dir, "git", "init")
            self._run(repo_dir, "git", "config", "user.email", "test@example.com")
            self._run(repo_dir, "git", "config", "user.name", "Test User")
            (repo_dir / "regular_auction_converter.go").write_text(
                "package demo\n\nfunc getAuctionTitle() string { return \"Auction title\" }\n",
                encoding="utf-8",
            )
            self._run(repo_dir, "git", "add", ".")
            self._run(repo_dir, "git", "commit", "-m", "add auction title converter")
            prepared = self._design_bundle(
                repo_scopes=[RepoScope(repo_id="demo", repo_path=str(repo_dir))],
                title="竞拍标题增加 Auction 标识",
                refined_markdown="regular auction title 需要改 getAuctionTitle。",
            )

            logs: list[str] = []
            package = build_repo_context_package(prepared, settings, prepared.repo_scopes[0], on_log=logs.append)

            self.assertEqual(package["source"], "local_repo_index")
            self.assertTrue(any(item["path"] == "regular_auction_converter.go" for item in package["top_files"]))
            self.assertTrue(any(item["name"] == "getAuctionTitle" for item in package["top_symbols"]))
            self.assertTrue(any("design_repo_index_ok" in item for item in logs))

    def test_research_plan_consumes_search_hints(self) -> None:
        prepared = DesignInputBundle(
            task_dir=Path("/tmp/task"),
            task_id="task",
            title="更新出价成功态",
            refined_markdown="需要更新 BidSuccessToast。",
            input_meta={},
            refine_brief_payload={},
            refine_intent_payload={},
            refine_skills_selection_payload={},
            refine_skills_read_markdown="",
            repos_meta={},
            repo_scopes=[RepoScope(repo_id="demo", repo_path="/tmp/repo")],
            sections=RefinedSections(
                change_scope=["更新出价成功态"],
                non_goals=[],
                key_constraints=[],
                acceptance_criteria=["BidSuccessToast 展示正确"],
                open_questions=[],
                raw="",
            ),
        )

        payload = build_research_plan(
            prepared,
            {
                "source": "native",
                "search_terms": ["bid success"],
                "likely_symbols": ["BidSuccessToast"],
                "likely_file_patterns": ["bid_success"],
                "negative_terms": ["legacy"],
                "confidence": "high",
            },
        )

        repo_plan = payload["repos"][0]
        self.assertIn("BidSuccessToast", repo_plan["search_terms"])
        self.assertEqual(repo_plan["likely_file_patterns"], ["bid_success"])
        self.assertEqual(repo_plan["negative_terms"], ["legacy"])
        self.assertEqual(repo_plan["search_hints_source"], "native")

    def test_research_plan_derives_negative_terms_from_non_goals(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[RepoScope(repo_id="live_pack", repo_path="/tmp/repo")],
            title="竞拍讲解卡价格展示",
            refined_markdown="只改竞拍讲解卡，不改购物袋价格。",
        )
        prepared.sections = RefinedSections(
            change_scope=["竞拍讲解卡整数金额隐藏尾部 `.00`"],
            non_goals=["不改购物袋价格展示"],
            key_constraints=[],
            acceptance_criteria=[],
            open_questions=[],
            raw="",
        )

        payload = build_research_plan(prepared, {})

        negative_terms = payload["repos"][0]["negative_terms"]
        self.assertIn("购物袋", negative_terms)

    def test_repo_research_excludes_non_goal_bag_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "live_pack"
            (repo_dir / "entities" / "converters" / "auction_converters").mkdir(parents=True)
            (repo_dir / "entities" / "converters" / "auction_converters" / "regular_auction_converter.go").write_text(
                "package demo\n\nfunc RegularAuctionPrice() string { return \"auction decimal price\" }\n",
                encoding="utf-8",
            )
            (repo_dir / "entities" / "converters" / "auction_converters" / "converter_helpers.go").write_text(
                "package demo\n\nfunc BagAuctionPrice() string { return \"shopping bag auction decimal price\" }\n",
                encoding="utf-8",
            )

            payload = research_single_repo(
                "live_pack",
                str(repo_dir),
                {
                    "search_terms": ["auction", "decimal", "price"],
                    "negative_terms": ["购物袋", "bag", "shopping bag", "converter_helpers"],
                    "budget": {"max_files_read": 4, "max_search_commands": 3},
                },
            )

            candidate_paths = [item["path"] for item in payload["candidate_files"]]
            excluded_paths = [item["path"] for item in payload["excluded_files"]]
            self.assertIn("entities/converters/auction_converters/regular_auction_converter.go", candidate_paths)
            self.assertNotIn("entities/converters/auction_converters/converter_helpers.go", candidate_paths)
            self.assertIn("entities/converters/auction_converters/converter_helpers.go", excluded_paths)

    def test_repo_research_marks_shared_abtest_repo_as_conditional(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "live_common"
            (repo_dir / "abtest").mkdir(parents=True)
            (repo_dir / "abtest" / "struct.go").write_text(
                "package abtest\n\ntype TTECContent struct { UseAuctionPromotionLabel bool `json:\"use_auction_promotion_label\"` }\n",
                encoding="utf-8",
            )

            payload = research_single_repo(
                "live_common",
                str(repo_dir),
                {
                    "search_terms": ["auction", "UseAuctionPromotionLabel"],
                    "budget": {"max_files_read": 4, "max_search_commands": 2},
                },
            )

            self.assertEqual(payload["work_hypothesis"], "conditional")
            self.assertTrue(payload["candidate_files"])
            self.assertTrue(payload["unknowns"])

    def test_local_design_markdown_infers_trailing_zero_question(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[RepoScope(repo_id="live_pack", repo_path="/repo/live_pack")],
            title="实验组竞拍讲解卡整数金额隐藏尾部 `.00`",
            refined_markdown=(
                "## 本次范围\n"
                "- 12.50 保持原有格式不变。\n"
                "## 验收标准\n"
                "- 小数点后面的 0 都去掉。\n"
            ),
        )
        prepared.sections = RefinedSections(
            change_scope=["竞拍讲解卡整数金额隐藏尾部 `.00`"],
            non_goals=[],
            key_constraints=["12.50 保持原有格式不变"],
            acceptance_criteria=["小数点后面的 0 都去掉"],
            open_questions=[],
            raw=prepared.refined_markdown,
        )

        markdown = build_local_doc_only_design_markdown(
            prepared,
            {"repos": [{"repo_id": "live_pack", "repo_path": "/repo/live_pack", "work_hypothesis": "required"}]},
        )

        self.assertIn("## 风险与待确认", markdown)
        self.assertIn("12.50", markdown)
        self.assertIn("12.5", markdown)
        self.assertNotIn("当前无待确认项", markdown)

    def test_design_writer_repairs_missing_inferred_open_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), plan_executor="native")
            prepared = self._design_bundle(
                repo_scopes=[RepoScope(repo_id="demo", repo_path="/repo/demo")],
                title="格式展示调整",
                refined_markdown=(
                    "## 本次范围\n"
                    "- 12.50 保持原有格式不变。\n"
                    "## 验收标准\n"
                    "- 小数点后面的 0 都去掉。\n"
                ),
            )
            prepared.sections = RefinedSections(
                change_scope=["格式展示调整"],
                non_goals=[],
                key_constraints=["12.50 保持原有格式不变"],
                acceptance_criteria=["小数点后面的 0 都去掉"],
                open_questions=[],
                raw=prepared.refined_markdown,
            )
            logs: list[str] = []
            generated = (
                "# 格式展示调整 Design\n\n"
                "## 方案设计\n"
                "- 更新展示格式。\n\n"
                "## 分仓库职责\n"
                "### demo\n"
                "- 改造方案：在展示层处理。\n\n"
                "## 验收与验证\n"
                "- 覆盖格式展示。\n\n"
                "## 风险与待确认\n"
                "- 当前无额外待确认项。\n\n"
                "## 明确不做\n"
                "- 无\n"
            )

            with patch("coco_flow.engines.design.writer.markdown.run_agent_markdown_with_new_session", return_value=generated):
                markdown = write_doc_only_design_markdown(
                    prepared,
                    {"repos": [{"repo_id": "demo", "repo_path": "/repo/demo", "work_hypothesis": "required"}]},
                    settings,
                    native_ok=True,
                    on_log=logs.append,
                )

            self.assertIn("格式规则存在冲突", markdown)
            self.assertIn("12.50", markdown)
            self.assertIn("12.5", markdown)
            self.assertTrue(any("design_quality_repair: inferred_open_questions_added=1" in item for item in logs))

    def test_local_design_markdown_adds_fallback_implementation_hints(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[
                RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
            ],
            title="实验组购物袋标题增加本地化标识",
            refined_markdown="命中实验时，标题前增加本地化标识，未命中实验保持现状。",
        )
        prepared.sections = RefinedSections(
            change_scope=["命中实验时，标题前增加本地化标识"],
            non_goals=["不改讲解卡标题"],
            key_constraints=[],
            acceptance_criteria=[
                "命中实验时，标题前增加本地化标识。",
                "本地化标识为空时回退原标题。",
                "未命中实验时保持现状。",
            ],
            open_questions=[],
            raw=prepared.refined_markdown,
        )

        markdown = build_local_doc_only_design_markdown(
            prepared,
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "repo_path": "/repo/live_pack",
                        "work_hypothesis": "required",
                        "candidate_files": [
                            {
                                "path": "entities/converters/live_bag/title_converter.go",
                                "matched_behavior": "标题、本地化标识",
                                "confidence": "high",
                                "core_evidence": True,
                            }
                        ],
                    },
                    {
                        "repo_id": "live_common",
                        "repo_path": "/repo/live_common",
                        "work_hypothesis": "conditional",
                    },
                ]
            },
        )

        self.assertIn("实验控制", markdown)
        self.assertIn("尚不足以确定精准文件落点", markdown)
        self.assertIn("实验或配置字段是否已有可复用能力", markdown)
        self.assertIn("用户可见表达所需资源", markdown)
        self.assertNotIn("confidence", markdown)
        self.assertNotIn("core_evidence", markdown)
        self.assertNotIn("搜索命中", markdown)

    def test_local_design_markdown_does_not_promote_weak_candidates_to_focus_files(self) -> None:
        prepared = self._design_bundle(
            repo_scopes=[
                RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
            ],
            title="实验组购物袋标题增加本地化标识",
            refined_markdown="命中实验时，标题前增加本地化标识，未命中实验保持现状。",
        )
        prepared.sections = RefinedSections(
            change_scope=["命中实验时，标题前增加本地化标识"],
            non_goals=["不改讲解卡标题"],
            key_constraints=[],
            acceptance_criteria=["命中实验时，标题前增加本地化标识。"],
            open_questions=[],
            raw=prepared.refined_markdown,
        )

        markdown = build_local_doc_only_design_markdown(
            prepared,
            {
                "repos": [
                    {
                        "repo_id": "live_pack",
                        "repo_path": "/repo/live_pack",
                        "work_hypothesis": "required",
                        "candidate_files": [
                            {
                                "path": "handlers/get_live_bag_data_handler.go",
                                "matched_behavior": "Auction、实验、购物袋",
                            }
                        ],
                    },
                    {
                        "repo_id": "live_common",
                        "repo_path": "/repo/live_common",
                        "work_hypothesis": "conditional",
                        "candidate_files": [
                            {
                                "path": "abtest/test_sdk.go",
                                "matched_behavior": "experiment、ab",
                            }
                        ],
                    },
                ]
            },
        )

        self.assertNotIn("get_live_bag_data_handler.go`：", markdown)
        self.assertNotIn("abtest/test_sdk.go`：", markdown)
        self.assertIn("尚不足以确定精准文件落点", markdown)

    def test_design_skills_selects_auction_pop_card_and_builds_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            self._write_skill(
                settings.config_root / "skills-sources" / "test-skills" / "auction-pop-card",
                skill_body=(
                    "适用于竞拍讲解卡需求。\n"
                    "公共配置 / 实验开关 通常关注 live_common，再看业务仓如何消费。\n"
                ),
                references={
                    "references/change-workflows.md": (
                        "## Stable Repo Roles\n"
                        "- `live_pack` 更偏竞拍卡数据编排、状态收敛。\n"
                        "- `live_common` 更偏 AB/TCC/schema 开关。\n"
                        "## Stable Multi-Repo Patterns\n"
                        "- `live_common + 业务仓` AB 参数、实验开关、共享配置。\n"
                        "### 数据编排 / 状态口径对齐\n"
                        "- 常见模块: entities/converters/auction_converters/*\n"
                        "### 公共配置 / 实验开关\n"
                        "- 常见模块: live_common/abtest/*\n"
                    )
                },
            )
            prepared = self._design_bundle(
                repo_scopes=[
                    RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                    RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
                ],
                title="竞拍讲解卡文案实验",
                refined_markdown="命中实验时，普通竞拍和 surprise set 展示 Starting bid。",
            )

            index, fallback, selection, selected_ids = build_design_skills_bundle(prepared, settings)

            self.assertEqual(selected_ids, ["test-skills/auction-pop-card"])
            self.assertEqual(selection["selected_skill_ids"], ["test-skills/auction-pop-card"])
            self.assertEqual(selection["selected_skill_sources"][0]["source_id"], "test-skills")
            self.assertEqual(selection["selected_skill_sources"][0]["package_id"], "auction-pop-card")
            self.assertIn("Design Skills Index", index)
            self.assertIn("SKILL.md", index)
            self.assertIn("references/change-workflows.md", index)
            self.assertIn("Matched Excerpts", fallback)
            self.assertIn("live_common + 业务仓", fallback)
            self.assertIn("Reference Files", fallback)

    def test_design_skills_prunes_adjacent_auction_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            self._write_skill(
                settings.config_root / "skills-sources" / "test-skills" / "auction-pop-card",
                skill_body=(
                    "适用于竞拍讲解卡 / auction popcard 的需求分析。\n"
                    "Use this skill when the task changes pop card copy, price expression, or AuctionCardData."
                ),
                references={},
            )
            self._write_skill(
                settings.config_root / "skills-sources" / "test-skills" / "auction-live-bag",
                skill_body=(
                    "适用于竞拍购物袋 / auction live bag 的需求分析。\n"
                    "Use this skill when the task changes live bag list, shopping bag refresh, or bag item display."
                ),
                references={},
            )
            prepared = self._design_bundle(
                repo_scopes=[
                    RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                    RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
                ],
                title="竞拍讲解卡文案实验",
                refined_markdown="命中实验时，普通竞拍和 surprise set 展示 Starting bid。",
            )

            _index, _fallback, selection, selected_ids = build_design_skills_bundle(prepared, settings)

            self.assertEqual(selected_ids, ["test-skills/auction-pop-card"])
            self.assertEqual(selection["selector"]["source"], "program")
            self.assertIn("test-skills/auction-live-bag", [item["id"] for item in selection["candidates"]])

    def test_design_skills_skips_native_selector_when_program_score_is_decisive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            self._write_skill(
                settings.config_root / "skills-sources" / "test-skills" / "auction-live-bag",
                skill_body="Auction 竞拍 购物 购物袋 live_pack live_common 实验 标题 标识 拍购 " * 3,
                references={},
            )
            self._write_skill(
                settings.config_root / "skills-sources" / "test-skills" / "auction-pop-card",
                skill_body="竞拍讲解卡 pop card。",
                references={},
            )
            prepared = self._design_bundle(
                repo_scopes=[
                    RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                    RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
                ],
                title="实验组竞拍购物袋标题增加 Auction 标识",
                refined_markdown="命中实验时，regular auction 竞拍购物袋标题前增加 Auction 标识。",
            )
            logs: list[str] = []

            with patch("coco_flow.engines.design.knowledge.skills._select_design_skills_with_agent") as selector:
                _index, _fallback, selection, selected_ids = build_design_skills_bundle(prepared, settings, native_ok=True, on_log=logs.append)

            selector.assert_not_called()
            self.assertEqual(selected_ids, ["test-skills/auction-live-bag"])
            self.assertEqual(selection["selector"]["source"], "program")
            self.assertTrue(any("design_skills_selector_skipped" in item for item in logs))

    def test_plan_skills_builds_index_with_full_file_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            self._write_skill(
                settings.config_root / "skills-sources" / "test-skills" / "auction-pop-card",
                skill_body="适用于竞拍讲解卡需求，Plan 需要关注 live_pack 和 live_common 的执行顺序。",
                references={"references/main-flow.md": "## Main Flow\n- live_pack 消费 live_common 实验字段。"},
            )

            index, fallback, selection, selected_ids = build_plan_skills_context(
                settings,
                title="竞拍讲解卡文案实验",
                sections=RefinedSections(
                    change_scope=["live_pack 消费 live_common 实验字段"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=["实验字段命中时展示 Starting bid"],
                    open_questions=[],
                    raw="",
                ),
                repo_scopes=[RepoScope(repo_id="live_pack", repo_path="/repo/live_pack")],
            )

            self.assertEqual(selected_ids, ["test-skills/auction-pop-card"])
            self.assertIn("Plan Skills Index", index)
            self.assertIn("SKILL.md", index)
            self.assertIn("references/main-flow.md", index)
            self.assertIn("selected_skill_sources", selection)
            self.assertIn("Plan Skills Local Fallback", fallback)

    def test_plan_skills_inherit_design_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            self._write_skill(
                settings.config_root / "skills-sources" / "test-skills" / "auction-pop-card",
                skill_body="适用于竞拍讲解卡需求。Plan 需要关注 live_pack 消费 live_common 实验字段的顺序。",
                references={"references/main-flow.md": "## Main Flow\n- live_pack 消费 live_common 实验字段。"},
            )
            self._write_skill(
                settings.config_root / "skills-sources" / "test-skills" / "auction-live-bag",
                skill_body="适用于竞拍购物袋需求。Plan 需要关注购物袋列表刷新。",
                references={},
            )
            prepared = PlanPreparedInput(
                task_dir=Path("/tmp/task"),
                task_id="task",
                title="竞拍购物袋与讲解卡都出现在标题里",
                design_markdown="# Design\n\n只做竞拍讲解卡。",
                refined_markdown="# PRD\n\n## 本次范围\n- 竞拍讲解卡文案实验。",
                input_meta={},
                task_meta={},
                repos_meta={},
                repo_scopes=[RepoScope(repo_id="live_pack", repo_path="/repo/live_pack")],
                repo_ids={"live_pack"},
                refined_sections=RefinedSections(
                    change_scope=["竞拍讲解卡文案实验"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=["命中实验时展示 Starting bid"],
                    open_questions=[],
                    raw="",
                ),
                inherited_design_skills_payload={
                    "selected_skill_ids": ["test-skills/auction-pop-card"],
                    "selected_skill_sources": [{"id": "test-skills/auction-pop-card", "keyword_hits": ["竞拍讲解卡"]}],
                    "selector": {"source": "native"},
                },
            )

            index, fallback, selection, selected_ids = build_plan_skills_bundle(prepared, settings)

            self.assertEqual(selected_ids, ["test-skills/auction-pop-card"])
            self.assertEqual(selection["source"], "design")
            self.assertEqual(selection["inherited_from"], "design-skills.json")
            self.assertEqual(selection["selected_skill_sources"][0]["source_id"], "test-skills")
            self.assertEqual(selection["selected_skill_sources"][0]["package_id"], "auction-pop-card")
            self.assertNotIn("test-skills/auction-live-bag", selected_ids)
            self.assertIn("inherited_from_design=true", index)
            self.assertIn("不能扩大 design.md", fallback)

    def test_plan_compiler_uses_repo_prefixed_design_sections(self) -> None:
        prepared = PlanPreparedInput(
            task_dir=Path("/tmp/task"),
            task_id="task",
            title="竞拍讲解卡文案实验",
            design_markdown=(
                "# Design\n\n"
                "## 工作流分类与仓库职责\n"
                "- **Producer 仓库**：live_common（新增实验字段）\n"
                "- **Consumer 仓库**：live_pack（消费实验字段）\n\n"
                "## 分仓库方案\n"
                "### live_pack（必须改动）\n"
                "- **待修改文件**：\n"
                "  - `entities/converters/auction_converters/regular_auction_converter.go`：处理普通竞拍文案\n"
                "  - `entities/converters/auction_converters/surprise_set_auction_converter.go`：处理 Surprise set 文案\n"
                "- 读取实验字段 `rc.GetAbParam().TTECContent.AuctionInteractionExpType`\n"
                "- **关键证据**：\n"
                "  - 普通竞拍文案逻辑在 RegularAuctionConverter.getAuctionText 中\n\n"
                "### live_common（必须改动）\n"
                "- **待修改文件**：\n"
                "  - `abtest/struct.go`：新增 `AuctionInteractionExpType int64` 字段\n"
                "- json tag 为 auction_interaction_exp_type，默认值 0 保持线上逻辑\n\n"
                "## 风险与待确认\n"
                "- **待确认项 1**：实验字段枚举值\n"
            ),
            refined_markdown="# PRD",
            input_meta={},
            task_meta={},
            repos_meta={},
            repo_scopes=[
                RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
            ],
            repo_ids={"live_pack", "live_common"},
            refined_sections=RefinedSections(
                change_scope=["竞拍讲解卡文案实验"],
                non_goals=[],
                key_constraints=[],
                acceptance_criteria=["命中实验时展示 Starting bid"],
                open_questions=[],
                raw="",
            ),
        )

        work_items_payload, graph_payload, validation_payload, result_payload, repo_markdowns = build_structured_plan_artifacts(prepared)

        items = {item["repo_id"]: item for item in work_items_payload["work_items"]}
        self.assertEqual(items["live_pack"]["depends_on"], ["W2"])
        self.assertEqual(items["live_common"]["blocks"], ["W1"])
        self.assertIn("regular_auction_converter.go", items["live_pack"]["change_scope"][0])
        self.assertNotIn("RegularAuctionConverter.getAuctionText", "\n".join(items["live_pack"]["specific_steps"]))
        self.assertEqual(graph_payload["execution_order"], ["W2", "W1"])
        self.assertEqual(graph_payload["parallel_groups"], [])
        contract = graph_payload["edges"][0]["contract"]
        self.assertEqual(contract["field_name"], "AuctionInteractionExpType")
        self.assertEqual(contract["json_tag"], "auction_interaction_exp_type")
        self.assertEqual(contract["default_value"], "0")
        self.assertEqual(contract["consumer_access"], "rc.GetAbParam().TTECContent.AuctionInteractionExpType")
        rendered = render_plan_markdown(prepared, work_items_payload, graph_payload, validation_payload, result_payload)
        self.assertIn("## 跨仓契约", rendered)
        self.assertIn("field: AuctionInteractionExpType", rendered)
        self.assertIn("## 输出契约", repo_markdowns["live_common"])
        self.assertIn("## 输入契约", repo_markdowns["live_pack"])
        self.assertEqual(result_payload["blockers"], ["待确认项 1：实验字段枚举值"])

    def test_plan_compiler_filters_evidence_sentences_from_tasks(self) -> None:
        prepared = PlanPreparedInput(
            task_dir=Path("/tmp/task"),
            task_id="task",
            title="竞拍讲解卡标题实验",
            design_markdown=(
                "# Design\n\n"
                "## 分仓库方案\n"
                "### live_pack\n"
                "- 代码证据：\n"
                "  - `entities/converters/auction_converters/regular_auction_converter.go`：明确包含 `getAuctionTitle` 方法，当前直接返回商品标题，是本次改造的核心落点\n"
                "- 改造方案：\n"
                "  - 在 `regular_auction_converter.go` 中：\n"
                "    - 读取实验字段 `rc.GetAbParam().TTECContent.RegularAuctionTitleAuctionLabelEnabled`\n"
                "    - 命中实验时，在原标题前拼接本地化 Auction 标识\n"
                "    - 若本地化标识取值为空，回退为原标题\n\n"
                "### live_common\n"
                "- 改造方案：\n"
                "  - 在 `abtest/struct.go` 中新增 `RegularAuctionTitleAuctionLabelEnabled bool` 字段\n"
            ),
            refined_markdown="# PRD",
            input_meta={},
            task_meta={},
            repos_meta={},
            repo_scopes=[
                RepoScope(repo_id="live_pack", repo_path="/repo/live_pack"),
                RepoScope(repo_id="live_common", repo_path="/repo/live_common"),
            ],
            repo_ids={"live_pack", "live_common"},
            refined_sections=RefinedSections(
                change_scope=["regular auction 标题拼接 Auction 标识"],
                non_goals=[],
                key_constraints=[],
                acceptance_criteria=["命中实验时标题前增加 Auction 标识"],
                open_questions=[],
                raw="",
            ),
        )

        work_items_payload, _graph_payload, _validation_payload, _result_payload, _repo_markdowns = build_structured_plan_artifacts(prepared)

        live_pack_item = next(item for item in work_items_payload["work_items"] if item["repo_id"] == "live_pack")
        steps_text = "\n".join(live_pack_item["specific_steps"])
        self.assertEqual(live_pack_item["change_scope"], ["entities/converters/auction_converters/regular_auction_converter.go"])
        self.assertNotIn("明确包含", steps_text)
        self.assertNotIn("当前直接返回商品标题", steps_text)
        self.assertNotIn("在 regular_auction_converter.go 中", steps_text)
        self.assertIn("读取实验字段 rc.GetAbParam().TTECContent.RegularAuctionTitleAuctionLabelEnabled", steps_text)
        self.assertIn("命中实验时，在原标题前拼接本地化 Auction 标识", steps_text)

    def test_plan_compiler_adds_go_module_upgrade_for_cross_repo_ab_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live_pack = root / "live_pack"
            live_pack.mkdir()
            (live_pack / "go.mod").write_text(
                "module code.byted.org/ttec/live_pack\n\n"
                "require code.byted.org/oec/live_common/abtest v0.0.0-20260408082303-984c086f6a89\n",
                encoding="utf-8",
            )
            (live_pack / "go.sum").write_text("", encoding="utf-8")
            prepared = PlanPreparedInput(
                task_dir=Path("/tmp/task"),
                task_id="task",
                title="竞拍讲解卡文案实验",
                design_markdown=(
                    "# Design\n\n"
                    "## 工作流分类与仓库职责\n"
                    "- **Producer 仓库**：live_common（新增实验字段）\n"
                    "- **Consumer 仓库**：live_pack（消费实验字段）\n\n"
                    "## 分仓库方案\n"
                    "### live_common（必须改动）\n"
                    "- `abtest/struct.go`：新增 `AuctionInteractionExpType int64` 字段\n"
                    "- json tag 为 auction_interaction_exp_type，默认值 0 保持线上逻辑\n\n"
                    "### live_pack（必须改动）\n"
                    "- 读取实验字段 `rc.GetAbParam().TTECContent.AuctionInteractionExpType`\n"
                    "- `entities/converters/auction_converters/regular_auction_converter.go`：消费实验字段\n"
                ),
                refined_markdown="# PRD",
                input_meta={},
                task_meta={},
                repos_meta={},
                repo_scopes=[
                    RepoScope(repo_id="live_pack", repo_path=str(live_pack)),
                    RepoScope(repo_id="live_common", repo_path=str(root / "live_common")),
                ],
                repo_ids={"live_pack", "live_common"},
                refined_sections=RefinedSections(
                    change_scope=["竞拍讲解卡文案实验"],
                    non_goals=[],
                    key_constraints=[],
                    acceptance_criteria=["命中实验时展示 Starting bid"],
                    open_questions=[],
                    raw="",
                ),
            )

            work_items_payload, _graph_payload, _validation_payload, _result_payload, repo_markdowns = build_structured_plan_artifacts(prepared)

            live_pack_item = next(item for item in work_items_payload["work_items"] if item["repo_id"] == "live_pack")
            self.assertIn("go.mod", live_pack_item["change_scope"])
            self.assertIn("go.sum", live_pack_item["change_scope"])
            self.assertIn(
                "升级 code.byted.org/oec/live_common/abtest 依赖到包含 AuctionInteractionExpType 的版本",
                live_pack_item["specific_steps"],
            )
            self.assertIn("go.mod", repo_markdowns["live_pack"])
            self.assertIn("升级 code.byted.org/oec/live_common/abtest", repo_markdowns["live_pack"])

    def test_repo_research_uses_file_pattern_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            (repo_dir / "bid_success_view.go").write_text(
                "package demo\n\nfunc Render() string { return \"ok\" }\n",
                encoding="utf-8",
            )

            payload = research_single_repo(
                "demo",
                str(repo_dir),
                {
                    "search_terms": ["missing-content-term"],
                    "likely_file_patterns": ["bid_success"],
                    "budget": {"max_files_read": 4, "max_search_commands": 1, "max_path_pattern_scans": 2},
                },
            )

            candidate_paths = [item["path"] for item in payload["candidate_files"]]
            self.assertIn("bid_success_view.go", candidate_paths)
            self.assertEqual(payload["budget_used"]["path_pattern_scans"], 1)

    def test_repo_research_demotes_broad_file_pattern_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            for index in range(16):
                (repo_dir / f"card_{index}.go").write_text(
                    "package demo\n\nfunc Render() string { return \"ok\" }\n",
                    encoding="utf-8",
                )

            payload = research_single_repo(
                "demo",
                str(repo_dir),
                {
                    "search_terms": [],
                    "likely_file_patterns": ["card"],
                    "budget": {"max_files_read": 4, "max_search_commands": 0, "max_path_pattern_scans": 1},
                },
            )

            self.assertEqual(payload["candidate_files"], [])
            self.assertTrue(payload["related_files"])

    def test_local_design_doc_only_writes_markdown_and_skill_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, plan_executor="local")
            task_dir, _repo_dir = self._create_refined_task(settings.task_root, "task-design-v3")

            status = design_task("task-design-v3", settings=settings)

            self.assertEqual(status, "designed")
            self.assertTrue((task_dir / "design.md").exists())
            self.assertTrue((task_dir / "design-skills.json").exists())
            self.assertTrue((task_dir / "design-contracts.json").exists())
            self.assertTrue((task_dir / "design-research-summary.json").exists())
            self.assertTrue((task_dir / "design-quality.json").exists())
            self.assertTrue((task_dir / "design-supervisor-review.json").exists())
            self.assertTrue((task_dir / "design-sync.json").exists())
            self.assertTrue(self._read_json(task_dir / "design-sync.json")["synced"])
            self.assertEqual(self._read_json(task_dir / "design-quality.json")["quality_status"], "passed")
            self.assertEqual(self._read_json(task_dir / "design-supervisor-review.json")["decision"], "pass")
            self.assertFalse((task_dir / "design-decision.json").exists())
            self.assertFalse((task_dir / "design-repo-binding.json").exists())
            self.assertFalse((task_dir / "design-sections.json").exists())
            self.assertEqual(start_planning_task("task-design-v3", settings=settings), "planning")

    def test_native_design_doc_only_uses_writer_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, plan_executor="native")
            task_dir, _repo_dir = self._create_refined_task(settings.task_root, "task-design-native")
            session_roles: list[str] = []
            prompt_events: list[tuple[str, str]] = []
            closed_roles: list[str] = []

            with (
                patch(
                    "coco_flow.engines.design.runtime.agent.CocoACPClient.run_agent",
                    side_effect=ValueError("search hints native unavailable"),
                ),
                patch(
                    "coco_flow.engines.design.runtime.agent.CocoACPClient.new_agent_session",
                    side_effect=lambda *, query_timeout, cwd, role: make_design_agent_session_handle(
                        query_timeout=query_timeout,
                        cwd=cwd,
                        role=role,
                        roles=session_roles,
                    ),
                ),
                patch(
                    "coco_flow.engines.design.runtime.agent.CocoACPClient.prompt_agent_session",
                    side_effect=lambda handle, prompt: write_native_design_artifacts(handle, prompt, prompt_events),
                ),
                patch(
                    "coco_flow.engines.design.runtime.agent.CocoACPClient.close_agent_session",
                    side_effect=lambda handle: closed_roles.append(handle.role),
                ),
            ):
                status = design_task("task-design-native", settings=settings)

            design_log = (task_dir / "design.log").read_text(encoding="utf-8")
            self.assertEqual(status, "designed")
            self.assertEqual(session_roles, ["design_writer"])
            self.assertEqual(prompt_events, [("design_writer", "writer")])
            self.assertEqual(closed_roles, ["design_writer"])
            self.assertIn("session_role: design_writer", design_log)
            self.assertIn("bootstrap_prompt: inline role=design_writer", design_log)
            self.assertFalse((task_dir / "design-decision.json").exists())
            self.assertFalse((task_dir / "design-verify.json").exists())

    def test_design_v3_requires_bound_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, plan_executor="local")
            task_dir = settings.task_root / "task-no-repo"
            task_dir.mkdir(parents=True)
            self._write_json(task_dir / "task.json", {"task_id": "task-no-repo", "title": "No repo", "status": "refined"})
            self._write_json(task_dir / "input.json", {})
            self._write_json(task_dir / "repos.json", {"repos": []})
            (task_dir / "prd-refined.md").write_text("# PRD\n\n## 本次范围\n- 更新成功态。\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "design requires bound repos"):
                design_task("task-no-repo", settings=settings)

    def test_plan_blocks_when_design_contracts_unsynced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            task_dir, _repo_dir = self._create_refined_task(settings.task_root, "task-design-unsynced")
            self._write_json(task_dir / "task.json", {"task_id": "task-design-unsynced", "title": "Demo", "status": "designed"})
            (task_dir / "design.md").write_text("# Design\n\n更新 demo。\n", encoding="utf-8")
            self._write_json(task_dir / "design-sync.json", {"synced": False, "status": "markdown_changed"})

            with self.assertRaisesRegex(ValueError, "结构化设计契约未同步"):
                start_planning_task("task-design-unsynced", settings=settings)

    def test_sync_design_task_refreshes_contract_sidecar_without_overwriting_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            task_dir, _repo_dir = self._create_refined_task(settings.task_root, "task-design-sync")
            original_markdown = (
                "# Design\n\n"
                "## 工作流分类与仓库职责\n"
                "- **Producer 仓库**：live_common（新增实验字段）\n"
                "- **Consumer 仓库**：live_pack（消费实验字段）\n\n"
                "## 分仓库方案\n"
                "### live_common（必须改动）\n"
                "- `abtest/struct.go`：新增 `AuctionInteractionExpType int64` 字段\n"
                "- json tag 为 auction_interaction_exp_type，默认值 0 保持线上逻辑\n\n"
                "### live_pack（必须改动）\n"
                "- 读取实验字段 `rc.GetAbParam().TTECContent.AuctionInteractionExpType`\n"
            )
            self._write_json(task_dir / "task.json", {"task_id": "task-design-sync", "title": "Demo", "status": "designed"})
            self._write_json(
                task_dir / "repos.json",
                {
                    "repos": [
                        {"id": "live_pack", "path": "/repo/live_pack", "status": "designed"},
                        {"id": "live_common", "path": "/repo/live_common", "status": "designed"},
                    ]
                },
            )
            (task_dir / "design.md").write_text(original_markdown, encoding="utf-8")
            self._write_json(task_dir / "design-sync.json", {"synced": False, "status": "markdown_changed"})

            self.assertEqual(sync_design_task("task-design-sync", settings=settings), "designed")

            self.assertEqual((task_dir / "design.md").read_text(encoding="utf-8"), original_markdown)
            contracts = self._read_json(task_dir / "design-contracts.json")
            sync_payload = self._read_json(task_dir / "design-sync.json")
            self.assertEqual(contracts["contract_count"], 1)
            self.assertEqual(contracts["contracts"][0]["field_name"], "AuctionInteractionExpType")
            self.assertTrue(sync_payload["synced"])
            self.assertEqual(sync_payload["status"], "synced_from_markdown")

    def _create_refined_task(self, task_root: Path, task_id: str) -> tuple[Path, Path]:
        repo_dir = task_root.parent / "demo-repo"
        repo_dir.mkdir(parents=True)
        (repo_dir / "status.py").write_text(
            "def success_status():\n    return 'success'\n",
            encoding="utf-8",
        )
        task_dir = task_root / task_id
        task_dir.mkdir(parents=True)
        self._write_json(task_dir / "task.json", {"task_id": task_id, "title": "成功态状态提示", "status": "refined"})
        self._write_json(task_dir / "input.json", {"title": "成功态状态提示"})
        self._write_json(task_dir / "refine-brief.json", {"change_points": ["成功态状态提示"]})
        self._write_json(task_dir / "refine-intent.json", {})
        self._write_json(task_dir / "repos.json", {"repos": [{"id": "demo", "path": str(repo_dir), "status": "refined"}]})
        (task_dir / "prd-refined.md").write_text(
            "# PRD\n\n## 本次范围\n- 成功态状态提示需要落到 success_status。\n\n## 验收标准\n- success 状态展示正确。\n",
            encoding="utf-8",
        )
        return task_dir, repo_dir

    def _design_bundle(
        self,
        *,
        repo_scopes: list[RepoScope],
        title: str = "Demo",
        refined_markdown: str = "demo",
    ) -> DesignInputBundle:
        return DesignInputBundle(
            task_dir=Path("/tmp/task"),
            task_id="task",
            title=title,
            refined_markdown=refined_markdown,
            input_meta={},
            refine_brief_payload={},
            refine_intent_payload={},
            refine_skills_selection_payload={},
            refine_skills_read_markdown="",
            repos_meta={},
            repo_scopes=repo_scopes,
            sections=RefinedSections(
                change_scope=["demo"],
                non_goals=[],
                key_constraints=[],
                acceptance_criteria=[],
                open_questions=[],
                raw="",
            ),
        )

    def _write_skill(self, root: Path, *, skill_body: str, references: dict[str, str]) -> None:
        root.mkdir(parents=True, exist_ok=True)
        parts = root.parts
        if "skills-sources" in parts:
            source_id = parts[parts.index("skills-sources") + 1]
            config_root = Path(*parts[: parts.index("skills-sources")])
            config_path = config_root / "skills-sources.json"
            payload = {"sources": []}
            if config_path.is_file():
                payload = json.loads(config_path.read_text(encoding="utf-8"))
            sources = [item for item in payload.get("sources", []) if item.get("id") != source_id]
            sources.append(
                {
                    "id": source_id,
                    "name": source_id,
                    "type": "git",
                    "url": f"git@gitlab.example.com:team/{source_id}.git",
                    "branch": "main",
                    "local_path": str(config_root / "skills-sources" / source_id),
                    "enabled": True,
                }
            )
            config_path.write_text(json.dumps({"sources": sources}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        name = root.name
        (root / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            f"description: {name} 业务知识库\n"
            f"domain: {name}\n"
            "---\n\n"
            f"{skill_body}\n",
            encoding="utf-8",
        )
        for rel, content in references.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _run(self, cwd: Path, *cmd: str) -> None:
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def make_design_agent_session_handle(*, query_timeout: str, cwd: str, role: str, roles: list[str]) -> AgentSessionHandle:
    roles.append(role)
    return AgentSessionHandle(
        handle_id=f"{role}-handle",
        cwd=cwd,
        mode="agent",
        query_timeout=query_timeout,
        role=role,
    )


def write_native_design_artifacts(handle: AgentSessionHandle, prompt: str, prompt_events: list[tuple[str, str]]) -> str:
    task_dir = Path(handle.cwd)
    if handle.role == "design_writer" and list(task_dir.glob(".design-writer-*.md")):
        prompt_events.append((handle.role, "writer"))
        next(task_dir.glob(".design-writer-*.md")).write_text(
            "# 成功态状态提示 Design\n\n## 结论\n更新 demo 的 status.py。\n",
            encoding="utf-8",
        )
        return "done"
    raise AssertionError(f"unexpected design agent prompt: role={handle.role} prompt={prompt[:120]}")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import json
import re
import tempfile
import time
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from coco_flow.cli import app
from coco_flow.config import Settings
from coco_flow.models.knowledge import CreateKnowledgeDraftsRequest, KnowledgeDocument, KnowledgeEvidence
from coco_flow.services.knowledge.background import get_generation_job, retry_background_generation, start_background_generation
from coco_flow.services.knowledge import KnowledgeDraftInput
from coco_flow.services.knowledge.generation import (
    apply_flow_final_editor,
    apply_flow_final_polisher,
    apply_flow_judge_notes,
    build_role_driven_summary,
    build_dependency_lines_local,
    build_storyline_steps_local,
    build_flow_judge_local,
    build_topic_adjudication_local,
    enforce_role_specific_responsibilities,
    filter_publishable_open_questions,
    sanitize_storyline_summary_lines,
    soften_repo_responsibility,
    sanitize_flow_slot_payload,
    soften_weak_claims,
    unique_questions,
)
from coco_flow.services.knowledge.prompting import extract_flow_judge_output
from coco_flow.services.queries.knowledge import KnowledgeStore


def make_settings(root: Path, knowledge_executor: str = "local") -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    knowledge_root = config_root / "knowledge"
    task_root.mkdir(parents=True, exist_ok=True)
    knowledge_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
        knowledge_root=knowledge_root,
        knowledge_executor=knowledge_executor,
        refine_executor="local",
        plan_executor="local",
        code_executor="local",
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class KnowledgeGenerationTest(unittest.TestCase):
    def test_topic_adjudication_demotes_technical_and_config_terms(self) -> None:
        intent_payload = {
            "title": "竞拍讲解卡",
            "description": "竞拍讲解卡系统链路",
            "normalized_intent": "竞拍讲解卡系统链路",
        }
        focus_boundary_payload = {
            "canonical_subject": "竞拍讲解卡",
            "in_scope_terms": ["竞拍讲解卡", "popcard auction"],
            "supporting_terms": ["AuctionInBagEnabled", "auction_lynx_schema_param", "preview"],
            "out_of_scope_terms": ["live_bag"],
            "open_questions": [],
        }
        repo_research_payloads = [
            {
                "repo_id": "auction-live",
                "likely_modules": ["biz/handler", "config", "schema", "live_bag"],
                "route_hits": ["router.go#/auction", "router.go#/bag"],
            }
        ]
        payload = build_topic_adjudication_local(intent_payload, focus_boundary_payload, repo_research_payloads)
        self.assertIn("竞拍讲解卡", payload["related_subjects"])
        self.assertNotIn("AuctionInBagEnabled", payload["related_subjects"])
        self.assertIn("AuctionInBagEnabled", payload["suppressed_terms"])
        self.assertIn("live_bag", payload["suppressed_terms"])

    def test_flow_judge_flags_adjacent_topic_in_mainline(self) -> None:
        document = KnowledgeDocument(
            id="flow-1",
            traceId="trace-1",
            kind="flow",
            status="draft",
            title="系统链路",
            desc="desc",
            domainId="domain-1",
            domainName="竞拍讲解卡",
            engines=["plan"],
            repos=["live-shopapi"],
            paths=[],
            keywords=[],
            priority="high",
            confidence="medium",
            updatedAt="2026-04-17 22:00",
            owner="Maifeng",
            body=(
                "## Summary\n\n"
                "系统围绕 live_bag 展开。\n\n"
                "## Main Flow\n\n"
                "1. live_bag 预览链路。\n"
                "2. 配置支撑。\n\n"
                "## Dependencies\n\n"
                "- live-shopapi 依赖 live-pack\n\n"
                "## Repo Hints\n\n"
                "### `live-shopapi`\n\n"
                "- repo: `live-shopapi`\n- role: `HTTP/API 入口`\n\n"
                "#### Key Modules\n- biz/handler\n\n"
                "#### Responsibilities\n- 提供 API\n\n"
                "## Open Questions\n\n"
                "- live_bag 是否为主线\n"
            ),
            evidence=KnowledgeEvidence(
                inputTitle="竞拍讲解卡",
                inputDescription="竞拍讲解卡系统链路",
                repoMatches=["live-shopapi"],
                keywordMatches=[],
                pathMatches=[],
                candidateFiles=[],
                contextHits=[],
                retrievalNotes=[],
                openQuestions=["live_bag 是否为主线"],
            ),
        )
        topic_adjudication_payload = {
            "adjacent_subjects": ["live_bag"],
            "suppressed_terms": ["AuctionInBagEnabled"],
        }
        repo_role_signal_payloads = [{"repo_id": "live-common", "resolved_role_label": "公共能力底座"}]
        flow_slot_payload = {"sync_entry_or_init": {"repos": ["live-shop"], "summary": "同步入口", "evidence": []}}
        judge = build_flow_judge_local([document], topic_adjudication_payload, repo_role_signal_payloads, flow_slot_payload)
        self.assertFalse(judge["passed"])
        self.assertTrue(any(item["code"] == "suppressed_topic_in_mainline" for item in judge["findings"]))
        self.assertTrue(judge["must_rewrite_summary"])
        self.assertTrue(judge["must_prune_open_questions"])

    def test_apply_flow_judge_notes_rewrites_flow_body(self) -> None:
        document = KnowledgeDocument(
            id="flow-1",
            traceId="trace-1",
            kind="flow",
            status="draft",
            title="系统链路",
            desc="desc",
            domainId="domain-1",
            domainName="竞拍讲解卡",
            engines=["plan"],
            repos=["live-shop", "live-shopapi", "live-pack"],
            paths=[],
            keywords=[],
            priority="high",
            confidence="medium",
            updatedAt="2026-04-17 22:00",
            owner="Maifeng",
            body=(
                "## Summary\n\n系统围绕 live_bag 展开。\n\n"
                "## Main Flow\n\n1. live_bag 预览链路。\n\n"
                "## Dependencies\n\n- live-shopapi 依赖 live-pack\n\n"
                "## Repo Hints\n\n### `live-shopapi`\n\n- repo: `live-shopapi`\n- role: `HTTP/API 入口`\n\n"
                "#### Key Modules\n- biz/handler\n\n#### Responsibilities\n- 提供 API\n\n"
                "## Open Questions\n\n- live_bag 是否为主线\n- API 路由是什么\n"
            ),
            evidence=KnowledgeEvidence(
                inputTitle="竞拍讲解卡",
                inputDescription="竞拍讲解卡系统链路",
                repoMatches=["live-shop", "live-shopapi", "live-pack"],
                keywordMatches=[],
                pathMatches=[],
                candidateFiles=[],
                contextHits=[],
                retrievalNotes=[],
                openQuestions=["live_bag 是否为主线", "API 路由是什么"],
            ),
        )
        rewritten = apply_flow_judge_notes(
            [document],
            {
                "findings": [{"document_id": "flow-1", "message": "blocked"}],
                "must_rewrite_summary": True,
                "must_rewrite_flow_steps": True,
                "must_prune_open_questions": True,
            },
            intent_payload={
                "title": "竞拍讲解卡",
                "description": "竞拍讲解卡系统链路",
                "normalized_intent": "竞拍讲解卡系统链路",
                "domain_name": "竞拍讲解卡",
            },
            storyline_outline_payload={
                "system_summary": ["竞拍讲解卡系统链路由 live-shopapi 作为 HTTP/API 入口。"],
                "main_flow_steps": ["live_bag 预览链路", "竞拍卡数据编排"],
                "dependencies": ["live-shopapi 依赖 live-pack"],
                "repo_hints": [
                    {
                        "repo_id": "live-shopapi",
                        "role_label": "HTTP/API 入口",
                        "key_modules": ["biz/handler"],
                        "responsibilities": ["负责 live_bag 相关业务逻辑"],
                        "upstream": [],
                        "downstream": [],
                        "notes": [],
                    }
                ],
                "open_questions": ["live_bag 是否为主线", "API 路由是什么"],
            },
            flow_slot_payload={
                "sync_entry_or_init": {"repos": ["live-shop"], "summary": "同步进房初始化，获取房间基础信息和竞拍讲解卡初始化数据", "evidence": []},
                "async_preview_or_pre_enter": {"repos": ["live-shopapi"], "summary": "异步预览/进房前，获取竞拍讲解卡预览数据", "evidence": []},
                "data_orchestration": {"repos": ["live-pack"], "summary": "竞拍卡数据编排，处理竞拍配置、竞拍信息等数据的组装", "evidence": []},
                "frontend_bff_transform": {},
                "runtime_update_or_notification": {},
                "config_or_experiment_support": {},
            },
            repo_research_payloads=[
                {"repo_id": "live-shopapi", "likely_modules": ["biz/handler"], "facts": [], "inferences": [], "open_questions": []}
            ],
            topic_adjudication_payload={"adjacent_subjects": ["live_bag"], "suppressed_terms": []},
        )[0]
        self.assertNotIn("live_bag", rewritten.body)
        self.assertIn("异步预览/进房前，获取竞拍讲解卡预览数据", rewritten.body)
        self.assertNotIn("live_bag 是否为主线", rewritten.body)
        self.assertTrue(any("flow judge findings:" in note for note in rewritten.evidence.retrievalNotes))

    def test_apply_flow_final_editor_overrides_sections(self) -> None:
        document = KnowledgeDocument(
            id="flow-1",
            traceId="trace-1",
            kind="flow",
            status="draft",
            title="系统链路",
            desc="desc",
            domainId="domain-1",
            domainName="竞拍讲解卡",
            engines=["plan"],
            repos=["live-shopapi"],
            paths=[],
            keywords=[],
            priority="high",
            confidence="medium",
            updatedAt="2026-04-17 22:00",
            owner="Maifeng",
            body=(
                "## Summary\n\n旧 summary\n\n"
                "## Main Flow\n\n1. 旧步骤\n\n"
                "## Dependencies\n\n- x\n\n"
                "## Repo Hints\n\n### `live-shopapi`\n\n- repo: `live-shopapi`\n- role: `HTTP/API 入口`\n\n"
                "#### Key Modules\n- biz/handler\n\n#### Responsibilities\n- 提供 API\n\n"
                "## Open Questions\n\n- 旧问题\n"
            ),
            evidence=KnowledgeEvidence(
                inputTitle="竞拍讲解卡",
                inputDescription="desc",
                repoMatches=["live-shopapi"],
                keywordMatches=[],
                pathMatches=[],
                candidateFiles=[],
                contextHits=[],
                retrievalNotes=[],
                openQuestions=["旧问题"],
            ),
        )
        rewritten = apply_flow_final_editor(
            [document],
            {
                "documents": [
                    {
                        "document_id": "flow-1",
                        "summary_lines": ["新 summary"],
                        "main_flow_steps": ["新步骤一", "新步骤二"],
                        "dependency_lines": ["系统依赖一", "系统依赖二"],
                        "open_questions": ["系统边界问题"],
                    }
                ]
            },
        )[0]
        self.assertIn("新 summary", rewritten.body)
        self.assertIn("1. 新步骤一", rewritten.body)
        self.assertIn("2. 新步骤二", rewritten.body)
        self.assertIn("- 系统依赖一", rewritten.body)
        self.assertIn("- 系统依赖二", rewritten.body)
        self.assertIn("- 系统边界问题", rewritten.body)
        self.assertEqual(rewritten.evidence.openQuestions, ["系统边界问题"])

    def test_apply_flow_final_polisher_overrides_dependencies(self) -> None:
        document = KnowledgeDocument(
            id="flow-1",
            traceId="trace-1",
            kind="flow",
            status="draft",
            title="系统链路",
            desc="desc",
            domainId="domain-1",
            domainName="竞拍讲解卡",
            engines=["plan"],
            repos=["live-shopapi"],
            paths=[],
            keywords=[],
            priority="high",
            confidence="medium",
            updatedAt="2026-04-17 22:00",
            owner="Maifeng",
            body=(
                "## Summary\n\n旧 summary\n\n"
                "## Main Flow\n\n1. 旧步骤\n\n"
                "## Dependencies\n\n- 旧依赖\n\n"
                "## Repo Hints\n\n### `live-shopapi`\n\n- repo: `live-shopapi`\n- role: `HTTP/API 入口`\n\n"
                "#### Key Modules\n- biz/handler\n\n#### Responsibilities\n- 提供 API\n\n"
                "## Open Questions\n\n- 旧问题\n"
            ),
            evidence=KnowledgeEvidence(
                inputTitle="竞拍讲解卡",
                inputDescription="desc",
                repoMatches=["live-shopapi"],
                keywordMatches=[],
                pathMatches=[],
                candidateFiles=[],
                contextHits=[],
                retrievalNotes=[],
                openQuestions=["旧问题"],
            ),
        )
        rewritten = apply_flow_final_polisher(
            [document],
            {
                "documents": [
                    {
                        "document_id": "flow-1",
                        "summary_lines": ["更克制的 summary"],
                        "main_flow_steps": ["更克制的步骤"],
                        "dependency_lines": ["系统依赖面表达"],
                        "open_questions": ["边界问题"],
                    }
                ]
            },
        )[0]
        self.assertIn("更克制的 summary", rewritten.body)
        self.assertIn("1. 更克制的步骤", rewritten.body)
        self.assertIn("- 系统依赖面表达", rewritten.body)
        self.assertIn("- 边界问题", rewritten.body)

    def test_extract_flow_judge_output_normalizes_native_codes(self) -> None:
        payload = extract_flow_judge_output(
            '{"passed":false,"findings":['
            '{"severity":"high","code":"SUPPRESSED_TOPIC_IN_SUMMARY","document_id":"flow-1","message":"x"},'
            '{"severity":"medium","code":"OPEN_QUESTIONS_ON_SUPPRESSED_TOPICS","document_id":"flow-1","message":"y"}'
            ']}'
        )
        self.assertEqual(payload["findings"][0]["code"], "suppressed_topic_in_mainline")
        self.assertEqual(payload["findings"][1]["code"], "suppressed_topic_in_questions")
        self.assertTrue(payload["must_rewrite_summary"])
        self.assertTrue(payload["must_rewrite_flow_steps"])
        self.assertTrue(payload["must_prune_open_questions"])

    def test_flow_slot_sanitizer_demotes_implementation_symbol_summary(self) -> None:
        payload = sanitize_flow_slot_payload(
            {
                "sync_entry_or_init": {
                    "repos": ["live-shopapi"],
                    "summary": "通过 ApiHandler_GetLiveRoomCommonInfo 发起同步进房请求",
                    "evidence": [],
                }
            },
            {"adjacent_subjects": [], "suppressed_terms": []},
        )
        self.assertEqual(
            payload["sync_entry_or_init"]["summary"],
            "同步进房初始化链路由 `live-shopapi` 承接，负责基础信息和初始化数据聚合。",
        )

    def test_filters_self_reflective_open_questions(self) -> None:
        questions = filter_publishable_open_questions(
            [
                "当前相邻主题是否只应保留为背景，而不进入主链路正文。",
                "当前主链路场景槽位是否已经覆盖同步、异步、编排和展示四类关键阶段。",
                "live-pack 和 live-shop 在数据编排上的具体分工是什么",
                "竞拍核心业务逻辑是否在该 repo 实现，还是依赖外部 RPC 服务",
            ],
            limit=8,
        )
        self.assertEqual(
            questions,
            [
                "live-pack 和 live-shop 在数据编排上的具体分工是什么",
                "竞拍核心业务逻辑是否在该 repo 实现，还是依赖外部 RPC 服务",
            ],
        )

    def test_soften_repo_responsibility_reduces_overclaim(self) -> None:
        self.assertEqual(
            soften_repo_responsibility("该repo是竞拍讲解卡系统的核心服务，负责数据组装和业务逻辑处理"),
            "该 repo 负责竞拍讲解卡相关的数据组装与状态收敛",
        )

    def test_build_storyline_steps_local_prefers_stage_skeleton(self) -> None:
        steps = build_storyline_steps_local(
            {},
            [
                {"repo_id": "live-shopapi", "role_label": "HTTP/API 入口"},
                {"repo_id": "live-pack", "role_label": "数据编排层"},
                {"repo_id": "content-live-bff-lib", "role_label": "前端/BFF 装配层"},
                {"repo_id": "live-common", "role_label": "公共能力底座"},
            ],
        )
        self.assertEqual(
            steps[:4],
            [
                "同步进房初始化通常由 `live-shopapi` 承接入口与基础信息聚合。",
                "异步预览或进房前链路通常由 `live-shopapi` 提供 preview/pop 等预览态数据。",
                "主数据随后由 `live-pack` 编排竞拍配置、状态和商品模型。",
                "前端展示前，会由 `content-live-bff-lib` 转成前端/BFF 可消费结构。",
            ],
        )

    def test_sanitize_storyline_summary_lines_prefers_role_summary(self) -> None:
        lines = sanitize_storyline_summary_lines(
            ["竞拍讲解卡链路由 live-shopapi 承接 HTTP/API 入口，由 live-pack 负责数据编排，由 content-live-bff-lib 负责前端/BFF 装配，由 live-common 提供公共能力底座。"],
            {"normalized_intent": "竞拍讲解卡系统链路"},
        )
        self.assertEqual(
            lines,
            ["竞拍讲解卡系统链路 由 HTTP/API 入口、数据编排层、前端/BFF 装配层和公共能力底座共同组成。"],
        )

    def test_build_role_driven_summary_prefers_repo_role_statement(self) -> None:
        lines = build_role_driven_summary(
            [
                {"repo_id": "live-shopapi", "repo_display_name": "live_shopapi", "role_label": "HTTP/API 入口"},
                {"repo_id": "live-shop", "repo_display_name": "live_shop", "role_label": "数据编排层"},
                {"repo_id": "live-pack", "repo_display_name": "live_pack", "role_label": "数据编排层"},
                {"repo_id": "content-live-bff-lib", "repo_display_name": "content_live_bff_lib", "role_label": "前端/BFF 装配层"},
                {"repo_id": "live-common", "repo_display_name": "live_common", "role_label": "公共能力底座"},
            ],
            {"normalized_intent": "竞拍讲解卡系统链路"},
        )
        self.assertEqual(
            lines,
            ["竞拍讲解卡系统链路 中，`live_shopapi` 是 HTTP/API 入口，`live_shop`、`live_pack` 负责编排，`content_live_bff_lib` 负责前端/BFF 装配，`live_common` 提供公共能力。"],
        )

    def test_enforce_role_specific_responsibilities_limits_overclaim(self) -> None:
        self.assertEqual(
            enforce_role_specific_responsibilities(
                "HTTP/API 入口",
                ["该 repo 是竞拍讲解卡系统的 BFF 层主入口", "承接 preview/pop 等异步或 API 场景请求，并决定是否走新架构或 BFF 路径。"],
            ),
            ["承接 preview/pop 等异步或 API 场景请求，并决定是否走新架构或 BFF 路径。"],
        )
        self.assertEqual(
            enforce_role_specific_responsibilities(
                "公共能力底座",
                ["提供闪购商品、直播商品关系、AB实验等公共能力。"],
            ),
            ["提供 AB、schema、配置或共享工具能力，不直接承接主链路。"],
        )

    def test_filters_discovery_style_open_questions(self) -> None:
        questions = filter_publishable_open_questions(
            [
                "auction 关键词具体对应哪个 API 入口或 handler 文件？",
                "竞拍讲解卡具体对应的 engine 和 converter 文件是什么？",
                "live-shop 与 live-pack 在数据编排上的具体分工是什么",
                "该 repo 与其他服务（如 live_core）的具体交互方式是什么",
            ],
            limit=8,
        )
        self.assertEqual(
            questions,
            [
                "live-shop 与 live-pack 在数据编排上的具体分工是什么",
                "该 repo 与其他服务（如 live_core）的具体交互方式是什么",
            ],
        )

    def test_filter_publishable_open_questions_prefers_boundary_authority_compat(self) -> None:
        questions = filter_publishable_open_questions(
            [
                "竞拍 session 的权威源是否已经稳定",
                "live_shop 与 live_shopapi 的生产边界是否还有兼容层",
                "除 US 外其他 region 是否仍有有效主链路",
                "当前还需要继续调研什么",
            ],
            limit=3,
        )
        self.assertEqual(
            questions,
            [
                "live_shop 与 live_shopapi 的生产边界是否还有兼容层",
                "竞拍 session 的权威源是否已经稳定",
                "除 US 外其他 region 是否仍有有效主链路",
            ],
        )

    def test_build_dependency_lines_local_prefers_system_dependency_surface(self) -> None:
        lines = build_dependency_lines_local(
            [
                {"repo_id": "live-shop", "repo_display_name": "live_shop", "role_label": "服务聚合入口"},
                {"repo_id": "live-pack", "repo_display_name": "live_pack", "role_label": "数据编排层"},
                {"repo_id": "content-live-bff-lib", "repo_display_name": "content_live_bff_lib", "role_label": "前端/BFF 装配层"},
                {"repo_id": "live-common", "repo_display_name": "live_common", "role_label": "公共能力底座"},
            ],
            [
                {"repo_id": "live-shop", "facts": ["notify evidence"], "likely_modules": ["service", "notify"]},
                {"repo_id": "live-pack", "facts": [], "likely_modules": ["engine", "provider"]},
                {"repo_id": "content-live-bff-lib", "facts": [], "likely_modules": ["pincard", "lynx"]},
                {"repo_id": "live-common", "facts": [], "likely_modules": ["schema", "abtest"]},
            ],
        )
        self.assertEqual(
            lines,
            [
                "`live_shop` 通过通知或刷新出口把运行时状态变化下发到客户端。",
                "`live_pack` 消费配置、session 和商品 relation 等依赖，收敛成主链路所需数据结构。",
                "`content_live_bff_lib` 依赖上游入口或编排层提供的数据，装配前端/BFF 可消费结构。",
                "`live_common` 提供配置、AB、schema 或共享工具能力，不直接承接业务主链。",
            ],
        )

    def test_question_dedupe_and_soften_helpers(self) -> None:
        questions = unique_questions(
            [
                "Launch/Deactivate 动作对应的具体 API 子路径是什么？",
                "Launch/Deactivate 动作对应的具体 API 子路径是什么?",
                "是否以 `biz/service/flash_sale` 为第一跳入口目录。",
                "是否以 biz/service/flash_sale 为第一跳入口目录。",
            ]
        )
        self.assertEqual(
            questions,
            [
                "Launch/Deactivate 动作对应的具体 API 子路径是什么？",
                "是否以 `biz/service/flash_sale` 为第一跳入口目录。",
            ],
        )
        softened = soften_weak_claims("涉及分布式事务场景时，`live-promotion-api` 的 `infra/tcc` 模块可能参与处理。")
        self.assertIn("当前线索显示", softened)
        self.assertIn("仍需进一步确认", softened)

    def test_create_drafts_writes_documents_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo_root = root / "auction-live"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / ".livecoding" / "context").mkdir(parents=True)
            (repo_root / ".livecoding" / "context" / "glossary.md").write_text(
                "竞拍讲解卡 explain_card render\n",
                encoding="utf-8",
            )
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "service" / "card_render").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n",
                encoding="utf-8",
            )
            (repo_root / "service" / "card_render" / "render_service.go").write_text(
                "package card_render\n",
                encoding="utf-8",
            )

            store = KnowledgeStore(settings)
            result = store.create_drafts(
                KnowledgeDraftInput(
                    title="竞拍讲解卡表达层",
                    description="竞拍讲解卡表达层",
                    selected_paths=[str(repo_root)],
                    kinds=["flow"],
                    notes="先关注表达层入口和渲染链路",
                )
            )

            self.assertEqual(len(result.documents), 1)
            self.assertEqual(result.documents[0].kind, "flow")
            self.assertTrue(result.trace_id.startswith("knowledge-"))
            self.assertEqual(result.documents[0].traceId, result.trace_id)
            self.assertEqual(result.documents[0].evidence.inputTitle, "竞拍讲解卡表达层")

            flow_path = settings.knowledge_root / "flows" / f"{result.documents[0].id}.md"
            self.assertTrue(flow_path.is_file())
            content = flow_path.read_text(encoding="utf-8")
            self.assertIn("## Repo Hints", content)
            self.assertIn("render_handler.go", content)
            self.assertIn("## Open Questions", content)
            self.assertIn(f"trace_id: {result.trace_id}", content)

            trace_root = settings.knowledge_root / "trace" / result.trace_id
            self.assertTrue((trace_root / "intent.json").is_file())
            self.assertTrue((trace_root / "repo-discovery.json").is_file())
            self.assertTrue((trace_root / "knowledge-draft.json").is_file())
            self.assertTrue((trace_root / "validation-result.json").is_file())
            research_dir = trace_root / "repo-research"
            research_files = sorted(research_dir.glob("*.json"))
            self.assertEqual(len(research_files), 1)

            discovery = json.loads((trace_root / "repo-discovery.json").read_text(encoding="utf-8"))
            self.assertEqual(discovery["repos"][0]["repo_id"], "auction-live")
            self.assertIn("app/explain_card/render_handler.go", discovery["repos"][0]["candidate_files"])

            trace = store.get_trace(result.trace_id)
            self.assertEqual(trace.trace_id, result.trace_id)
            self.assertIn("intent.json", trace.files)
            self.assertIn("term-mapping.json", trace.files)
            self.assertIn("candidate-ranking.json", trace.files)
            self.assertIn("term-family.json", trace.files)
            self.assertIn("anchor-selection.json", trace.files)
            self.assertIn("repo-discovery.json", trace.files)
            self.assertIn("auction-live", trace.repo_research)
            self.assertIn("repos", trace.anchor_selection)
            self.assertEqual(trace.validation["ok"], True)
            self.assertEqual(trace.repo_research["auction-live"]["executor"], "local")
            self.assertEqual(result.documents[0].title, "系统链路")
            self.assertEqual(result.documents[0].evidence.pathMatches, [str(repo_root)])
            self.assertIn("### `auction-live`", result.documents[0].body)
            self.assertIn("#### Key Modules", result.documents[0].body)
            self.assertFalse(any(str(term).startswith("knowledge-") for term in trace.repo_discovery["search_terms"]))
            self.assertFalse(any(re.fullmatch(r"[a-f0-9]{8,}", str(term)) for term in trace.repo_discovery["search_terms"]))

    def test_native_repo_research_uses_llm_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, knowledge_executor="native")
            repo_root = root / "auction-live"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n",
                encoding="utf-8",
            )

            store = KnowledgeStore(settings)
            with patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_readonly_agent",
                return_value=(
                    '{"role":"primary","likely_modules":["llm/app","llm/service"],'
                    '"risks":["llm risk"],"facts":["llm fact"],'
                    '"inferences":["llm inference"],"open_questions":["llm question"]}'
                ),
            ), patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_prompt_only",
                side_effect=[
                    (
                        '{"mapped_terms":[{"user_term":"竞拍讲解卡","repo_terms":["ExplainCard","render_handler"],'
                        '"repo_ids":["auction-live"],"confidence":"high","reason":"命中 repo 符号"}],'
                        '"search_terms":["ExplainCard","render_handler","knowledge","pipeline","talent"],"open_questions":["LLM term question"]}'
                    ),
                    (
                        '{"primary_files":["app/explain_card/render_handler.go"],'
                        '"secondary_files":[],"primary_dirs":["app/explain_card"],'
                        '"preferred_symbols":["ExplainCardHandler"],'
                        '"preferred_routes":[],"discarded_noise":["README.md"],'
                        '"reason":"render_handler.go 是最直接的表达层入口。","open_questions":[]}'
                    ),
                    (
                        '{"strongest_terms":["ExplainCard","render_handler"],'
                        '"entry_files":["app/explain_card/render_handler.go"],'
                        '"business_symbols":["ExplainCardHandler"],'
                        '"route_signals":[],"discarded_noise":["README.md"],'
                        '"reason":"render_handler.go 直接承接讲解卡表达层动作。","open_questions":[]}'
                    ),
                    (
                        '{"primary_family":["ExplainCard","render_handler"],'
                        '"secondary_families":[["card","render"]],"noise_terms":["README.md"],'
                        '"reason":"ExplainCard/render_handler 在 term mapping、候选裁剪和锚点中共现。","open_questions":[]}'
                    ),
                    (
                        '{"primary_subject":"竞拍讲解卡表达层系统链路","related_subjects":["ExplainCard","render_handler"],'
                        '"adjacent_subjects":["README"],"suppressed_terms":["README"],'
                        '"suppressed_modules":[],"suppressed_routes":[],"reason":"主主题清晰。","open_questions":[]}'
                    ),
                    (
                        '{"repos":[{"repo_id":"auction-live","has_external_entry_signal":true,"has_http_api_signal":false,'
                        '"has_orchestration_signal":false,"has_frontend_assembly_signal":false,"has_shared_capability_signal":false,'
                        '"has_runtime_update_signal":false,"signal_notes":["存在对外入口信号"],"resolved_role_label":"服务聚合入口","open_questions":[]}]}'
                    ),
                    (
                        '{"sync_entry_or_init":{"repos":["auction-live"],"summary":"LLM sync step","evidence":["llm fact"]},'
                        '"async_preview_or_pre_enter":{},"data_orchestration":{},"runtime_update_or_notification":{},'
                        '"frontend_bff_transform":{},"config_or_experiment_support":{},"open_questions":[]}'
                    ),
                    (
                        '{"system_summary":["LLM summary"],"main_flow_steps":["LLM step"],'
                        '"dependencies":["`auction-live`：负责入口聚合。"],'
                        '"repo_hints":[{"repo_id":"auction-live","role_label":"服务聚合入口","key_modules":["llm/app"],'
                        '"responsibilities":["承接入口请求并聚合场景参数"],"upstream":[],"downstream":[],"notes":[]}],'
                        '"domain_summary":["LLM domain summary"],"open_questions":["LLM open question"]}'
                    ),
                    (
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                        '## Dependencies\\n\\n- `auction-live`：负责入口聚合。\\n\\n'
                        '## Repo Hints\\n\\n### `auction-live`\\n\\n- repo: `auction-live`\\n- role: `服务聚合入口`\\n\\n#### Key Modules\\n- llm/app\\n\\n## Open Questions\\n\\n- LLM open question",'
                        '"open_questions":["LLM open question"]}]}'  # noqa: E501
                    ),
                    (
                        '{"passed":true,"findings":[]}'
                    ),
                ],
            ):
                result = store.create_drafts(
                    KnowledgeDraftInput(
                        title="竞拍讲解卡表达层",
                        description="竞拍讲解卡表达层",
                        selected_paths=[str(repo_root)],
                        kinds=["flow"],
                        notes="",
                    )
                )

            trace = store.get_trace(result.trace_id)
            research = trace.repo_research["auction-live"]
            self.assertEqual(research["executor"], "native")
            self.assertEqual(research["requested_executor"], "native")
            self.assertEqual(research["likely_modules"], ["llm/app", "llm/service"])
            self.assertEqual(research["facts"], ["llm fact"])
            self.assertEqual(research["inferences"], ["llm inference"])
            self.assertEqual(trace.topic_adjudication["executor"], "native")
            self.assertEqual(trace.topic_adjudication["requested_executor"], "native")
            self.assertEqual(trace.repo_role_signals["repos"][0]["executor"], "native")
            self.assertEqual(trace.repo_role_signals["repos"][0]["requested_executor"], "native")
            self.assertEqual(trace.flow_slots["executor"], "native")
            self.assertEqual(trace.flow_slots["requested_executor"], "native")
            self.assertEqual(trace.storyline_outline["executor"], "native")
            self.assertEqual(trace.storyline_outline["requested_executor"], "native")
            self.assertEqual(trace.flow_judge["executor"], "native")
            self.assertEqual(trace.flow_judge["requested_executor"], "native")
            self.assertEqual(result.documents[0].title, "系统链路")
            self.assertIn("LLM summary", result.documents[0].body)
            self.assertIn("- repo: `auction-live`", result.documents[0].body)
            self.assertNotIn(str(repo_root), result.documents[0].body)
            self.assertEqual(trace.intent["title"], "竞拍讲解卡表达层")
            self.assertIn("render_handler", trace.repo_discovery["search_terms"])
            self.assertNotIn("knowledge", trace.repo_discovery["search_terms"])
            self.assertNotIn("pipeline", trace.repo_discovery["search_terms"])
            self.assertIn("knowledge synthesis executor: native", result.documents[0].evidence.retrievalNotes[3])

    def test_native_repo_research_falls_back_to_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, knowledge_executor="native")
            repo_root = root / "auction-live"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n",
                encoding="utf-8",
            )

            store = KnowledgeStore(settings)
            with patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_readonly_agent",
                side_effect=ValueError("native repo research exploded"),
            ), patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_prompt_only",
                side_effect=[
                    (
                        '{"mapped_terms":[{"user_term":"竞拍讲解卡","repo_terms":["ExplainCard"],'
                        '"repo_ids":["auction-live"],"confidence":"high","reason":"命中 repo 符号"}],'
                        '"search_terms":["ExplainCard"],"open_questions":[]}'
                    ),
                    (
                        '{"primary_files":["app/explain_card/render_handler.go"],'
                        '"secondary_files":[],"primary_dirs":["app/explain_card"],'
                        '"preferred_symbols":["ExplainCardHandler"],'
                        '"preferred_routes":[],"discarded_noise":[],"reason":"命中入口文件。","open_questions":[]}'
                    ),
                    (
                        '{"strongest_terms":["ExplainCard"],'
                        '"entry_files":["app/explain_card/render_handler.go"],'
                        '"business_symbols":["ExplainCardHandler"],'
                        '"route_signals":[],"discarded_noise":[],"reason":"命中入口文件。","open_questions":[]}'
                    ),
                    (
                        '{"primary_family":["ExplainCard","render_handler"],'
                        '"secondary_families":[],"noise_terms":[],"reason":"主术语族群清晰。","open_questions":[]}'
                    ),
                    (
                        '{"primary_subject":"竞拍讲解卡表达层系统链路","related_subjects":["ExplainCard"],'
                        '"adjacent_subjects":[],"suppressed_terms":[],"suppressed_modules":[],"suppressed_routes":[],"reason":"主主题清晰。","open_questions":[]}'
                    ),
                    (
                        '{"repos":[{"repo_id":"auction-live","has_external_entry_signal":true,"has_http_api_signal":false,'
                        '"has_orchestration_signal":false,"has_frontend_assembly_signal":false,"has_shared_capability_signal":false,'
                        '"has_runtime_update_signal":false,"signal_notes":["存在对外入口信号"],"resolved_role_label":"服务聚合入口","open_questions":[]}]}'
                    ),
                    (
                        '{"sync_entry_or_init":{"repos":["auction-live"],"summary":"LLM sync step","evidence":["llm fact"]},'
                        '"async_preview_or_pre_enter":{},"data_orchestration":{},"runtime_update_or_notification":{},'
                        '"frontend_bff_transform":{},"config_or_experiment_support":{},"open_questions":[]}'
                    ),
                    (
                        '{"system_summary":["LLM summary"],"main_flow_steps":["LLM step"],'
                        '"dependencies":["`auction-live`：负责入口聚合。"],'
                        '"repo_hints":[{"repo_id":"auction-live","role_label":"服务聚合入口","key_modules":["llm/app"],'
                        '"responsibilities":["承接入口请求并聚合场景参数"],"upstream":[],"downstream":[],"notes":[]}],'
                        '"domain_summary":["LLM domain summary"],"open_questions":["LLM open question"]}'
                    ),
                    (
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                        '## Dependencies\\n\\n- `auction-live`：负责入口聚合。\\n\\n'
                        '## Repo Hints\\n\\n### `auction-live`\\n\\n- repo: `auction-live`\\n- role: `服务聚合入口`\\n\\n#### Key Modules\\n- llm/app\\n\\n## Open Questions\\n\\n- LLM open question",'
                        '"open_questions":["LLM open question"]}]}'  # noqa: E501
                    ),
                ],
            ):
                result = store.create_drafts(
                    KnowledgeDraftInput(
                        title="竞拍讲解卡表达层",
                        description="竞拍讲解卡表达层",
                        selected_paths=[str(repo_root)],
                        kinds=["flow"],
                        notes="",
                    )
                )

            trace = store.get_trace(result.trace_id)
            research = trace.repo_research["auction-live"]
            self.assertEqual(research["executor"], "local")
            self.assertEqual(research["requested_executor"], "native")
            self.assertEqual(research["fallback_reason"], "native repo research exploded")

    def test_native_synthesis_falls_back_to_local_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, knowledge_executor="native")
            repo_root = root / "auction-live"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n",
                encoding="utf-8",
            )

            store = KnowledgeStore(settings)
            with patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_readonly_agent",
                return_value=(
                    '{"role":"primary","likely_modules":["llm/app"],'
                    '"risks":["llm risk"],"facts":["llm fact"],'
                    '"inferences":["llm inference"],"open_questions":["llm question"]}'
                ),
            ), patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_prompt_only",
                side_effect=[
                    (
                        '{"mapped_terms":[{"user_term":"竞拍讲解卡","repo_terms":["ExplainCard"],'
                        '"repo_ids":["auction-live"],"confidence":"high","reason":"命中 repo 符号"}],'
                        '"search_terms":["ExplainCard"],"open_questions":[]}'
                    ),
                    (
                        '{"primary_files":["app/explain_card/render_handler.go"],'
                        '"secondary_files":[],"primary_dirs":["app/explain_card"],'
                        '"preferred_symbols":["ExplainCardHandler"],'
                        '"preferred_routes":[],"discarded_noise":[],"reason":"命中入口文件。","open_questions":[]}'
                    ),
                    (
                        '{"strongest_terms":["ExplainCard"],'
                        '"entry_files":["app/explain_card/render_handler.go"],'
                        '"business_symbols":["ExplainCardHandler"],'
                        '"route_signals":[],"discarded_noise":[],"reason":"命中入口文件。","open_questions":[]}'
                    ),
                    (
                        '{"primary_family":["ExplainCard","render_handler"],'
                        '"secondary_families":[],"noise_terms":[],"reason":"主术语族群清晰。","open_questions":[]}'
                    ),
                    (
                        '{"primary_subject":"竞拍讲解卡表达层系统链路","related_subjects":["ExplainCard"],'
                        '"adjacent_subjects":[],"suppressed_terms":[],"suppressed_modules":[],"suppressed_routes":[],"reason":"主主题清晰。","open_questions":[]}'
                    ),
                    (
                        '{"repos":[{"repo_id":"auction-live","has_external_entry_signal":true,"has_http_api_signal":false,'
                        '"has_orchestration_signal":false,"has_frontend_assembly_signal":false,"has_shared_capability_signal":false,'
                        '"has_runtime_update_signal":false,"signal_notes":["存在对外入口信号"],"resolved_role_label":"服务聚合入口","open_questions":[]}]}'
                    ),
                    (
                        '{"sync_entry_or_init":{"repos":["auction-live"],"summary":"LLM sync step","evidence":["llm fact"]},'
                        '"async_preview_or_pre_enter":{},"data_orchestration":{},"runtime_update_or_notification":{},'
                        '"frontend_bff_transform":{},"config_or_experiment_support":{},"open_questions":[]}'
                    ),
                    (
                        '{"system_summary":["LLM summary"],"main_flow_steps":["LLM step"],'
                        '"dependencies":["`auction-live`：负责入口聚合。"],'
                        '"repo_hints":[{"repo_id":"auction-live","role_label":"服务聚合入口","key_modules":["llm/app"],'
                        '"responsibilities":["承接入口请求并聚合场景参数"],"upstream":[],"downstream":[],"notes":[]}],'
                        '"domain_summary":["LLM domain summary"],"open_questions":["LLM open question"]}'
                    ),
                    ValueError("native synthesis exploded"),
                ],
            ):
                result = store.create_drafts(
                    KnowledgeDraftInput(
                        title="竞拍讲解卡表达层",
                        description="竞拍讲解卡表达层",
                        selected_paths=[str(repo_root)],
                        kinds=["flow"],
                        notes="",
                    )
                )

            self.assertIn("## Repo Hints", result.documents[0].body)
            self.assertIn("LLM step", result.documents[0].body)
            self.assertIn("## Summary", result.documents[0].body)
            self.assertTrue(
                any("knowledge synthesis fallback: native synthesis exploded" in item for item in result.documents[0].evidence.retrievalNotes)
            )

    def test_native_term_mapping_falls_back_to_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, knowledge_executor="native")
            repo_root = root / "auction-live"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "biz" / "service").mkdir(parents=True)
            (repo_root / "biz" / "service" / "create_promotion.go").write_text(
                "package service\nconst PromotionTypeExclusiveFlashSale = 1\n",
                encoding="utf-8",
            )

            store = KnowledgeStore(settings)
            with patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_prompt_only",
                side_effect=[
                    ValueError("native term mapping exploded"),
                    (
                        '{"primary_files":["biz/service/create_promotion.go"],'
                        '"secondary_files":[],"primary_dirs":["biz/service"],'
                        '"preferred_symbols":["PromotionTypeExclusiveFlashSale"],'
                        '"preferred_routes":[],"discarded_noise":[],"reason":"命中业务常量。","open_questions":[]}'
                    ),
                    (
                        '{"strongest_terms":["PromotionTypeExclusiveFlashSale"],'
                        '"entry_files":["biz/service/create_promotion.go"],'
                        '"business_symbols":["PromotionTypeExclusiveFlashSale"],'
                        '"route_signals":[],"discarded_noise":[],"reason":"命中业务常量。","open_questions":[]}'
                    ),
                    (
                        '{"primary_family":["PromotionTypeExclusiveFlashSale"],'
                        '"secondary_families":[["create_promotion"]],"noise_terms":[],"reason":"主术语族群来自业务常量。","open_questions":[]}'
                    ),
                    (
                        '{"primary_subject":"达人秒杀链路","related_subjects":["PromotionTypeExclusiveFlashSale"],'
                        '"adjacent_subjects":[],"suppressed_terms":[],"suppressed_modules":[],"suppressed_routes":[],"reason":"主主题清晰。","open_questions":[]}'
                    ),
                    (
                        '{"repos":[{"repo_id":"auction-live","has_external_entry_signal":true,"has_http_api_signal":false,'
                        '"has_orchestration_signal":false,"has_frontend_assembly_signal":false,"has_shared_capability_signal":false,'
                        '"has_runtime_update_signal":false,"signal_notes":["存在对外入口信号"],"resolved_role_label":"服务聚合入口","open_questions":[]}]}'
                    ),
                    (
                        '{"sync_entry_or_init":{"repos":["auction-live"],"summary":"LLM sync step","evidence":["llm fact"]},'
                        '"async_preview_or_pre_enter":{},"data_orchestration":{},"runtime_update_or_notification":{},'
                        '"frontend_bff_transform":{},"config_or_experiment_support":{},"open_questions":[]}'
                    ),
                    (
                        '{"system_summary":["LLM summary"],"main_flow_steps":["LLM step"],'
                        '"dependencies":["`auction-live`：负责入口聚合。"],'
                        '"repo_hints":[{"repo_id":"auction-live","role_label":"服务聚合入口","key_modules":["llm/app"],'
                        '"responsibilities":["承接入口请求并聚合场景参数"],"upstream":[],"downstream":[],"notes":[]}],'
                        '"domain_summary":["LLM domain summary"],"open_questions":["LLM open question"]}'
                    ),
                    (
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                        '## Dependencies\\n\\n- `auction-live`：负责入口聚合。\\n\\n'
                        '## Repo Hints\\n\\n### `auction-live`\\n\\n- repo: `auction-live`\\n- role: `服务聚合入口`\\n\\n#### Key Modules\\n- llm/app\\n\\n## Open Questions\\n\\n- LLM open question",'
                        '"open_questions":["LLM open question"]}]}'  # noqa: E501
                    ),
                ],
            ), patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_readonly_agent",
                return_value=(
                    '{"role":"primary","likely_modules":["biz/service"],'
                    '"risks":["llm risk"],"facts":["llm fact"],'
                    '"inferences":["llm inference"],"open_questions":["llm question"]}'
                ),
            ):
                result = store.create_drafts(
                    KnowledgeDraftInput(
                        title="达人秒杀链路",
                        description="达人秒杀相关链路",
                        selected_paths=[str(repo_root)],
                        kinds=["flow"],
                        notes="",
                    )
                )

            trace = store.get_trace(result.trace_id)
            self.assertTrue(any("达人秒杀" in item for item in trace.repo_discovery["search_terms"]))
            term_mapping = json.loads((settings.knowledge_root / "trace" / result.trace_id / "term-mapping.json").read_text(encoding="utf-8"))
            self.assertEqual(term_mapping["executor"], "local")
            self.assertEqual(term_mapping["requested_executor"], "native")
            self.assertEqual(term_mapping["fallback_reason"], "native term mapping exploded")
            self.assertTrue(
                any("term mapping fallback: native term mapping exploded" in item for item in result.documents[0].evidence.retrievalNotes)
            )

    def test_discovery_uses_mapped_symbol_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, knowledge_executor="native")
            repo_root = root / "promotion-core"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "biz" / "service").mkdir(parents=True)
            (repo_root / "biz" / "router").mkdir(parents=True)
            (repo_root / "biz" / "service" / "entry.go").write_text(
                "package service\nconst PromotionTypeExclusiveFlashSale = 1\nfunc CreateCreatorPromotion() {}\n",
                encoding="utf-8",
            )
            (repo_root / "biz" / "router" / "live_promotion.go").write_text(
                'package router\nvar route = "/api/v1/live_promotion/flash_sale/create"\n',
                encoding="utf-8",
            )

            store = KnowledgeStore(settings)
            with patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_prompt_only",
                side_effect=[
                    (
                        '{"mapped_terms":[{"user_term":"达人秒杀","repo_terms":["ExclusiveFlashSale","CreatorPromotion"],'
                        '"repo_ids":["promotion-core"],"confidence":"high","reason":"命中业务枚举和服务名"}],'
                        '"search_terms":["ExclusiveFlashSale","CreatorPromotion"],"open_questions":[]}'
                    ),
                    (
                        '{"primary_files":["biz/router/live_promotion.go","biz/service/entry.go"],'
                        '"secondary_files":[],"primary_dirs":["biz/router","biz/service"],'
                        '"preferred_symbols":["PromotionTypeExclusiveFlashSale","CreateCreatorPromotion"],'
                        '"preferred_routes":["biz/router/live_promotion.go#/api/v1/live_promotion/flash_sale/create"],'
                        '"discarded_noise":["biz/router/live_promotion.go#/save_template"],'
                        '"reason":"route 和业务常量共同构成主候选。","open_questions":[]}'
                    ),
                    (
                        '{"strongest_terms":["ExclusiveFlashSale","CreatorPromotion"],'
                        '"entry_files":["biz/router/live_promotion.go","biz/service/entry.go"],'
                        '"business_symbols":["PromotionTypeExclusiveFlashSale","CreateCreatorPromotion"],'
                        '"route_signals":["biz/router/live_promotion.go#/api/v1/live_promotion/flash_sale/create","biz/router/live_promotion.go#/save_template"],'
                        '"discarded_noise":[],"reason":"route 和业务常量共同构成主锚点。","open_questions":[]}'
                    ),
                    (
                        '{"primary_family":["ExclusiveFlashSale","CreatorPromotion","flash_sale"],'
                        '"secondary_families":[["create"]],"noise_terms":["save_template"],'
                        '"reason":"这些词跨 route、symbol、entry file 共现。","open_questions":[]}'
                    ),
                    (
                        '{"primary_subject":"达人秒杀链路","related_subjects":["ExclusiveFlashSale","CreatorPromotion"],'
                        '"adjacent_subjects":["save_template"],"suppressed_terms":["save_template"],'
                        '"suppressed_modules":[],"suppressed_routes":["biz/router/live_promotion.go#/save_template"],'
                        '"reason":"save_template 不应主导主主题。","open_questions":[]}'
                    ),
                    (
                        '{"repos":[{"repo_id":"promotion-core","has_external_entry_signal":true,"has_http_api_signal":true,'
                        '"has_orchestration_signal":false,"has_frontend_assembly_signal":false,"has_shared_capability_signal":false,'
                        '"has_runtime_update_signal":false,"signal_notes":["存在对外入口信号","存在 HTTP/API 信号"],"resolved_role_label":"HTTP/API 入口","open_questions":[]}]}'
                    ),
                    (
                        '{"sync_entry_or_init":{},"async_preview_or_pre_enter":{"repos":["promotion-core"],"summary":"LLM async step","evidence":["llm fact"]},'
                        '"data_orchestration":{},"runtime_update_or_notification":{},"frontend_bff_transform":{},"config_or_experiment_support":{},"open_questions":[]}'
                    ),
                    (
                        '{"system_summary":["LLM summary"],"main_flow_steps":["LLM step"],'
                        '"dependencies":["`promotion-core`：负责入口聚合。"],'
                        '"repo_hints":[{"repo_id":"promotion-core","role_label":"HTTP/API 入口","key_modules":["biz/service"],'
                        '"responsibilities":["承接异步/API 场景请求，并决定是否走新架构或 BFF 路径。"],"upstream":[],"downstream":[],"notes":[]}],'
                        '"domain_summary":["LLM domain summary"],"open_questions":["LLM open question"]}'
                    ),
                    (
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                        '## Dependencies\\n\\n- `promotion-core`：负责入口聚合。\\n\\n'
                        '## Repo Hints\\n\\n### `promotion-core`\\n\\n- repo: `promotion-core`\\n- role: `服务聚合入口`\\n\\n#### Key Modules\\n- biz/service\\n\\n## Open Questions\\n\\n- LLM open question",'
                        '"open_questions":["LLM open question"]}]}'  # noqa: E501
                    ),
                ],
            ), patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_readonly_agent",
                return_value=(
                    '{"role":"primary","likely_modules":["biz/service"],'
                    '"risks":["llm risk"],"facts":["llm fact"],'
                    '"inferences":["llm inference"],"open_questions":["llm question"]}'
                ),
            ):
                result = store.create_drafts(
                    KnowledgeDraftInput(
                        title="达人秒杀链路",
                        description="我想要一份达人秒杀系统链路知识",
                        selected_paths=[str(repo_root)],
                        kinds=["flow"],
                        notes="",
                    )
                )

            trace = store.get_trace(result.trace_id)
            repo_discovery = trace.repo_discovery["repos"][0]
            self.assertIn("ExclusiveFlashSale", trace.repo_discovery["search_terms"])
            self.assertTrue(repo_discovery["symbol_hits"], msg=json.dumps(repo_discovery, ensure_ascii=False))
            self.assertTrue(any("ExclusiveFlashSale" in item for item in repo_discovery["symbol_hits"]))
            self.assertTrue(repo_discovery["route_hits"], msg=json.dumps(repo_discovery, ensure_ascii=False))
            repo_research = trace.repo_research["promotion-core"]
            self.assertTrue(repo_research["anchors"]["entry_files"], msg=json.dumps(repo_research, ensure_ascii=False))
            self.assertTrue(all("/save_template" not in item for item in repo_research["anchors"]["route_signals"]))

    def test_discovery_prioritizes_requested_subpath(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo_root = root / "promotion-core"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "000_noise").mkdir(parents=True)
            for index in range(1705):
                (repo_root / "000_noise" / f"noise_{index:04d}.go").write_text(
                    "package noise\n",
                    encoding="utf-8",
                )
            target_dir = repo_root / "zzz_target" / "service"
            target_dir.mkdir(parents=True)
            (target_dir / "create_promotion.go").write_text(
                "package service\nfunc CreatePromotion() {}\n",
                encoding="utf-8",
            )

            store = KnowledgeStore(settings)
            result = store.create_drafts(
                KnowledgeDraftInput(
                    title="create promotion",
                    description="create promotion flow",
                    selected_paths=[str(target_dir)],
                    kinds=["flow"],
                    notes="",
                )
            )

            trace = store.get_trace(result.trace_id)
            candidate_files = trace.repo_discovery["repos"][0]["candidate_files"]
            self.assertIn("zzz_target/service/create_promotion.go", candidate_files)

    def test_local_research_prefers_primary_entry_over_noise_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo_root = root / "promotion-core"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "README.md").write_text(
                "达人秒杀 CreatorPromotion flash_sale\n",
                encoding="utf-8",
            )
            (repo_root / "handler").mkdir(parents=True)
            (repo_root / "biz" / "service").mkdir(parents=True)
            (repo_root / "handler" / "create_creator_promotion.go").write_text(
                "package handler\nfunc CreateSellerFlashSalePromotions() {}\n",
                encoding="utf-8",
            )
            (repo_root / "biz" / "service" / "create_creator_promotion_service.go").write_text(
                "package service\nconst PromotionTypeExclusiveFlashSale = 1\nfunc CreateSellerFlashSalePromotions() {}\n",
                encoding="utf-8",
            )
            (repo_root / "handler" / "callback_create_next_cycle_promotion.go").write_text(
                "package handler\nfunc CallbackCreateNextCyclePromotion() {}\n",
                encoding="utf-8",
            )
            (repo_root / "service" / "billboard" / "billboard_operate_service").mkdir(parents=True)
            (repo_root / "service" / "billboard" / "billboard_operate_service" / "operate.go").write_text(
                "package billboard\nfunc OperateBillboard() {}\n",
                encoding="utf-8",
            )

            store = KnowledgeStore(settings)
            result = store.create_drafts(
                KnowledgeDraftInput(
                    title="达人秒杀",
                    description="这是达人秒杀知识，有创建，更新链路。",
                    selected_paths=[str(repo_root)],
                    kinds=["flow"],
                    notes="",
                )
            )

            trace = store.get_trace(result.trace_id)
            repo_research = next(iter(trace.repo_research.values()))
            self.assertIn("handler/create_creator_promotion.go", repo_research["candidate_files"])
            self.assertIn("biz/service/create_creator_promotion_service.go", repo_research["candidate_files"])
            self.assertNotIn("service/billboard/billboard_operate_service", " ".join(repo_research["open_questions"]))

    def test_native_synthesis_falls_back_on_unsupported_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, knowledge_executor="native")
            repo_root = root / "promotion-core"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "biz" / "service").mkdir(parents=True)
            (repo_root / "biz" / "router").mkdir(parents=True)
            (repo_root / "biz" / "service" / "entry.go").write_text(
                "package service\nconst PromotionTypeExclusiveFlashSale = 1\n",
                encoding="utf-8",
            )
            (repo_root / "biz" / "router" / "live_promotion.go").write_text(
                'package router\nvar route = "/api/v1/live_promotion/flash_sale/create"\n',
                encoding="utf-8",
            )

            store = KnowledgeStore(settings)
            with patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_prompt_only",
                side_effect=[
                    (
                        '{"mapped_terms":[{"user_term":"达人秒杀","repo_terms":["ExclusiveFlashSale","CreatorPromotion"],'
                        '"repo_ids":["promotion-core"],"confidence":"high","reason":"命中业务枚举和服务名"}],'
                        '"search_terms":["ExclusiveFlashSale","CreatorPromotion"],"open_questions":[]}'
                    ),
                    (
                        '{"primary_files":["biz/router/live_promotion.go","biz/service/entry.go"],'
                        '"secondary_files":[],"primary_dirs":["biz/router","biz/service"],'
                        '"preferred_symbols":["PromotionTypeExclusiveFlashSale","CreateCreatorPromotion"],'
                        '"preferred_routes":["biz/router/live_promotion.go#/api/v1/live_promotion/flash_sale/create"],'
                        '"discarded_noise":[],"reason":"route 和业务常量共同构成主候选。","open_questions":[]}'
                    ),
                    (
                        '{"strongest_terms":["ExclusiveFlashSale","CreatorPromotion"],'
                        '"entry_files":["biz/router/live_promotion.go","biz/service/entry.go"],'
                        '"business_symbols":["PromotionTypeExclusiveFlashSale","CreateCreatorPromotion"],'
                        '"route_signals":["biz/router/live_promotion.go#/api/v1/live_promotion/flash_sale/create"],'
                        '"discarded_noise":[],"reason":"route 和业务常量共同构成主锚点。","open_questions":[]}'
                    ),
                    (
                        '{"primary_family":["ExclusiveFlashSale","CreatorPromotion","flash_sale"],'
                        '"secondary_families":[["create"]],"noise_terms":[],"reason":"这些词跨 route、symbol、entry file 共现。","open_questions":[]}'
                    ),
                    (
                        '{"primary_subject":"达人秒杀链路","related_subjects":["ExclusiveFlashSale","CreatorPromotion"],'
                        '"adjacent_subjects":["save_template"],"suppressed_terms":["save_template"],'
                        '"suppressed_modules":[],"suppressed_routes":["/save_template"],'
                        '"reason":"save_template 不应进入主链路。","open_questions":[]}'
                    ),
                    (
                        '{"repos":[{"repo_id":"promotion-core","has_external_entry_signal":true,"has_http_api_signal":true,'
                        '"has_orchestration_signal":false,"has_frontend_assembly_signal":false,"has_shared_capability_signal":false,'
                        '"has_runtime_update_signal":false,"signal_notes":["存在对外入口信号","存在 HTTP/API 信号"],"resolved_role_label":"HTTP/API 入口","open_questions":[]}]}'
                    ),
                    (
                        '{"sync_entry_or_init":{},"async_preview_or_pre_enter":{"repos":["promotion-core"],"summary":"LLM async step","evidence":["llm fact"]},'
                        '"data_orchestration":{},"runtime_update_or_notification":{},"frontend_bff_transform":{},"config_or_experiment_support":{},"open_questions":[]}'
                    ),
                    (
                        '{"system_summary":["LLM summary"],"main_flow_steps":["LLM step"],'
                        '"dependencies":["`promotion-core`：负责入口聚合。"],'
                        '"repo_hints":[{"repo_id":"promotion-core","role_label":"HTTP/API 入口","key_modules":["biz/service"],'
                        '"responsibilities":["承接异步/API 场景请求，并决定是否走新架构或 BFF 路径。"],"upstream":[],"downstream":[],"notes":[]}],'
                        '"domain_summary":["LLM domain summary"],"open_questions":["LLM open question"]}'
                    ),
                    (
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. 通过 /save_template 调整 TemplateSwitcher。\\n\\n'
                        '## Dependencies\\n\\n- `promotion-core`：负责入口聚合。\\n\\n'
                        '## Repo Hints\\n\\n### `promotion-core`\\n\\n- repo: `promotion-core`\\n- role: `服务聚合入口`\\n\\n#### Key Modules\\n- biz/service\\n\\n## Open Questions\\n\\n- LLM open question",'
                        '"open_questions":["LLM open question"]}]}'  # noqa: E501
                    ),
                ],
            ), patch(
                "coco_flow.services.knowledge.generation.CocoACPClient.run_readonly_agent",
                return_value=(
                    '{"role":"primary","likely_modules":["biz/service"],'
                    '"risks":["llm risk"],"facts":["llm fact"],'
                    '"inferences":["llm inference"],"open_questions":["llm question"]}'
                ),
            ):
                result = store.create_drafts(
                    KnowledgeDraftInput(
                        title="达人秒杀链路",
                        description="我想要一份达人秒杀系统链路知识",
                        selected_paths=[str(repo_root)],
                        kinds=["flow"],
                        notes="",
                    )
                )

            self.assertIn("LLM step", result.documents[0].body)
            self.assertIn("## Summary", result.documents[0].body)
            self.assertTrue(
                any("unsupported routes /save_template" in item for item in result.documents[0].evidence.retrievalNotes)
            )

    def test_request_model_accepts_legacy_repos_field(self) -> None:
        payload = CreateKnowledgeDraftsRequest(
            title="竞拍讲解卡表达层",
            description="竞拍讲解卡表达层",
            repos=["/tmp/demo"],
            kinds=["flow"],
        )

        self.assertEqual(payload.selected_paths, ["/tmp/demo"])
        self.assertEqual(payload.repos, ["/tmp/demo"])

    def test_cli_generate_outputs_trace_and_document(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo_root = root / "auction-live"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n",
                encoding="utf-8",
            )

            with patch("coco_flow.cli.load_settings", return_value=settings):
                result = runner.invoke(
                    app,
                    [
                        "knowledge",
                        "generate",
                        "--title",
                        "竞拍讲解卡表达层",
                        "--description",
                        "竞拍讲解卡表达层",
                        "--path",
                        str(repo_root),
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("trace_id:", result.output)
            self.assertIn("[flow]", result.output)

    def test_background_generation_job_reaches_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo_root = root / "auction-live"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n",
                encoding="utf-8",
            )

            job = start_background_generation(
                KnowledgeDraftInput(
                    title="竞拍讲解卡表达层",
                    description="竞拍讲解卡表达层",
                    selected_paths=[str(repo_root)],
                    kinds=["flow"],
                    notes="",
                ),
                settings,
            )
            self.assertEqual(job.status, "queued")

            final_job = job
            for _ in range(100):
                final_job = get_generation_job(job.job_id, settings)
                if final_job.status in {"completed", "failed"}:
                    break
                time.sleep(0.02)

            self.assertEqual(final_job.status, "completed", msg=final_job.model_dump_json())
            self.assertEqual(final_job.progress, 100)
            self.assertEqual(len(final_job.document_ids), 1)
            self.assertTrue(final_job.trace_id.startswith("knowledge-"))

    def test_retry_background_generation_creates_new_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            repo_root = root / "auction-live"
            (repo_root / ".git").mkdir(parents=True)
            (repo_root / "AGENTS.md").write_text("# Repo Guide\n", encoding="utf-8")
            (repo_root / "app" / "explain_card").mkdir(parents=True)
            (repo_root / "app" / "explain_card" / "render_handler.go").write_text(
                "package explain_card\n",
                encoding="utf-8",
            )

            job = start_background_generation(
                KnowledgeDraftInput(
                    title="竞拍讲解卡表达层",
                    description="竞拍讲解卡表达层",
                    selected_paths=[str(repo_root)],
                    kinds=["flow"],
                    notes="",
                ),
                settings,
            )
            retry_job = retry_background_generation(job.job_id, settings)

            self.assertNotEqual(retry_job.job_id, job.job_id)
            self.assertEqual(retry_job.status, "queued")
            final_retry_job = retry_job
            for _ in range(100):
                final_retry_job = get_generation_job(retry_job.job_id, settings)
                if final_retry_job.status in {"completed", "failed"}:
                    break
                time.sleep(0.02)
            self.assertEqual(final_retry_job.status, "completed", msg=final_retry_job.model_dump_json())


if __name__ == "__main__":
    unittest.main()

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
from coco_flow.models.knowledge import CreateKnowledgeDraftsRequest
from coco_flow.services.knowledge.background import get_generation_job, retry_background_generation, start_background_generation
from coco_flow.services.knowledge import KnowledgeDraftInput
from coco_flow.services.knowledge.generation import soften_weak_claims, unique_questions
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
            self.assertIn("auction-live:/", result.documents[0].body)
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
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                        '## Selected Paths\\n\\n- `/tmp/demo`\\n\\n## Dependencies\\n\\n- `auction-live`: role=primary\\n\\n'
                        '## Repo Hints\\n\\n### `auction-live`\\n\\n- role: `primary`\\n\\n## Open Questions\\n\\n- LLM open question",'
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
            self.assertEqual(research["executor"], "native")
            self.assertEqual(research["requested_executor"], "native")
            self.assertEqual(research["likely_modules"], ["llm/app", "llm/service"])
            self.assertEqual(research["facts"], ["llm fact"])
            self.assertEqual(research["inferences"], ["llm inference"])
            self.assertEqual(result.documents[0].title, "系统链路")
            self.assertIn("LLM summary", result.documents[0].body)
            self.assertIn("auction-live:/", result.documents[0].body)
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
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                        '## Selected Paths\\n\\n- `/tmp/demo`\\n\\n## Dependencies\\n\\n- `auction-live`: role=primary\\n\\n'
                        '## Repo Hints\\n\\n### `auction-live`\\n\\n- role: `primary`\\n\\n## Open Questions\\n\\n- LLM open question",'
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
            self.assertIn("当前处于第一阶段知识草稿", result.documents[0].body)
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
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                        '## Selected Paths\\n\\n- `/tmp/demo`\\n\\n## Dependencies\\n\\n- `auction-live`: role=primary\\n\\n'
                        '## Repo Hints\\n\\n### `auction-live`\\n\\n- role: `primary`\\n\\n## Open Questions\\n\\n- LLM open question",'
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
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                        '## Selected Paths\\n\\n- `/tmp/demo`\\n\\n## Dependencies\\n\\n- `promotion-core`: role=primary\\n\\n'
                        '## Repo Hints\\n\\n### `promotion-core`\\n\\n- role: `primary`\\n\\n## Open Questions\\n\\n- LLM open question",'
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
                        '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                        '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. 通过 /save_template 调整 TemplateSwitcher。\\n\\n'
                        '## Selected Paths\\n\\n- `/tmp/demo`\\n\\n## Dependencies\\n\\n- `promotion-core`: role=primary\\n\\n'
                        '## Repo Hints\\n\\n### `promotion-core`\\n\\n- role: `primary`\\n\\n## Open Questions\\n\\n- LLM open question",'
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

            self.assertIn("当前处于第一阶段知识草稿", result.documents[0].body)
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

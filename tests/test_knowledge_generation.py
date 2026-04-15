from __future__ import annotations

from pathlib import Path
import json
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
            self.assertIn("repo-discovery.json", trace.files)
            self.assertIn("auction-live", trace.repo_research)
            self.assertEqual(trace.validation["ok"], True)
            self.assertEqual(trace.repo_research["auction-live"]["executor"], "local")
            self.assertEqual(result.documents[0].title, "系统链路")
            self.assertEqual(result.documents[0].evidence.pathMatches, [str(repo_root)])
            self.assertIn("auction-live:/", result.documents[0].body)

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
                return_value=(
                    '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                    '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                    '## Selected Paths\\n\\n- `/tmp/demo`\\n\\n## Dependencies\\n\\n- `auction-live`: role=primary\\n\\n'
                    '## Repo Hints\\n\\n### `auction-live`\\n\\n- role: `primary`\\n\\n## Open Questions\\n\\n- LLM open question",'
                    '"open_questions":["LLM open question"]}]}'  # noqa: E501
                ),
            ):
                result = store.create_drafts(
                    KnowledgeDraftInput(
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
            self.assertIn("knowledge synthesis executor: native", result.documents[0].evidence.retrievalNotes[1])

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
                return_value=(
                    '{"documents":[{"kind":"flow","title":"LLM 系统链路","desc":"LLM desc",'
                    '"body":"## Summary\\n\\nLLM summary\\n\\n## Main Flow\\n\\n1. LLM step\\n\\n'
                    '## Selected Paths\\n\\n- `/tmp/demo`\\n\\n## Dependencies\\n\\n- `auction-live`: role=primary\\n\\n'
                    '## Repo Hints\\n\\n### `auction-live`\\n\\n- role: `primary`\\n\\n## Open Questions\\n\\n- LLM open question",'
                    '"open_questions":["LLM open question"]}]}'  # noqa: E501
                ),
            ):
                result = store.create_drafts(
                    KnowledgeDraftInput(
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
                side_effect=ValueError("native synthesis exploded"),
            ):
                result = store.create_drafts(
                    KnowledgeDraftInput(
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

    def test_request_model_accepts_legacy_repos_field(self) -> None:
        payload = CreateKnowledgeDraftsRequest(
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

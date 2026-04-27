from __future__ import annotations

import unittest

from coco_flow.engines.shared.diagnostics import diagnosis_payload_from_verify, enrich_verify_payload


class DiagnosticsTest(unittest.TestCase):
    def test_enrich_verify_payload_preserves_legacy_fields(self) -> None:
        payload = enrich_verify_payload(
            stage="plan",
            verify_payload={
                "ok": False,
                "issues": ["must_change repo 未被执行任务覆盖: demo"],
                "reason": "local plan verify failed",
            },
            artifact="plan.md",
        )

        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["issues"], ["must_change repo 未被执行任务覆盖: demo"])
        self.assertEqual(payload["stage"], "plan")
        self.assertEqual(payload["severity"], "blocking")
        self.assertEqual(payload["failure_type"], "missing_work_item_coverage")
        self.assertEqual(payload["next_action"], "repair")

    def test_diagnosis_payload_turns_string_issues_into_actionable_objects(self) -> None:
        payload = diagnosis_payload_from_verify(
            stage="refine",
            verify_payload={
                "ok": False,
                "issues": ["refined markdown 缺少必填章节。"],
                "reason": "local verify failed",
            },
            artifact="prd-refined.md",
        )

        self.assertEqual(payload["stage"], "refine")
        self.assertEqual(payload["failure_type"], "missing_required_section")
        self.assertEqual(payload["next_action"], "repair")
        self.assertEqual(payload["issues"][0]["artifact"], "prd-refined.md")
        self.assertEqual(payload["issues"][0]["path"], "sections")
        self.assertTrue(payload["issues"][0]["auto_repairable"])


if __name__ == "__main__":
    unittest.main()

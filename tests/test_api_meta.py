from __future__ import annotations

import unittest

from coco_flow.api.app import create_app


class ApiMetaTest(unittest.TestCase):
    def test_api_meta_returns_build_fingerprint(self) -> None:
        app = create_app()
        route = next(route for route in app.routes if getattr(route, "path", "") == "/api/meta")
        payload = route.endpoint()

        self.assertEqual(payload["name"], "coco-flow")
        self.assertIn("version", payload)
        self.assertIn("fingerprint", payload)
        self.assertIn("started_at", payload)


if __name__ == "__main__":
    unittest.main()

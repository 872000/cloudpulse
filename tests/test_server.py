"""Tests for the HTTP probe endpoints, status API, and dashboard."""

import json
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cloudpulse.checker import CheckResult  # noqa: E402
from cloudpulse.server import build_handler  # noqa: E402
from cloudpulse.store import HistoryStore  # noqa: E402


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.status, r.read(), r.headers.get_content_type()


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = HistoryStore()
        cls.store.register("web", "https://web.example")
        cls.store.record(
            CheckResult(
                name="web",
                url="https://web.example",
                up=True,
                status_code=200,
                latency_ms=42.0,
                error=None,
                checked_at=1700000000.0,
            )
        )
        # Readiness NOT set: /readyz must be 503 until the first round.
        cls.ready = threading.Event()
        handler = build_handler(cls.store, cls.ready)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_healthz(self):
        status, body, _ = _get(self.port, "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok"})

    def test_readyz_not_ready_then_ready(self):
        with self.assertRaises(Exception):
            # urllib raises HTTPError for 503; assert via raw check below.
            _get(self.port, "/readyz")
        # Use a direct call that surfaces the status code.
        import urllib.error

        try:
            _get(self.port, "/readyz")
            self.fail("expected HTTP 503")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 503)
        self.ready.set()
        status, body, _ = _get(self.port, "/readyz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ready"})
        self.ready.clear()

    def test_metrics_endpoint(self):
        status, body, ctype = _get(self.port, "/metrics")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", ctype)
        text = body.decode()
        self.assertIn('cloudpulse_up{target="web"} 1', text)
        self.assertIn('cloudpulse_latency_milliseconds{target="web"} 42.0', text)

    def test_status_api(self):
        status, body, _ = _get(self.port, "/api/status")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(len(data["targets"]), 1)
        target = data["targets"][0]
        self.assertEqual(target["name"], "web")
        self.assertTrue(target["up"])
        self.assertEqual(target["status_code"], 200)
        self.assertEqual(target["checks_total"], 1)

    def test_dashboard_html(self):
        status, body, ctype = _get(self.port, "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        text = body.decode()
        self.assertIn("CloudPulse", text)
        self.assertIn("web", text)
        self.assertIn("UP", text)

    def test_unknown_path_404(self):
        import urllib.error

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            _get(self.port, "/nope")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()

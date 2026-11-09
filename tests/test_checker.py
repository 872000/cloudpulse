"""Tests for the endpoint checker (offline, local HTTP server)."""

import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cloudpulse.checker import check_target  # noqa: E402
from cloudpulse.config import Target  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/ok":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path == "/notfound":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"nope")
        elif self.path == "/teapot":
            self.send_response(418)
            self.end_headers()
            self.wfile.write(b"teapot")

    def do_HEAD(self):
        self.do_GET()


class CheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_up_on_expected_status(self):
        result = check_target(
            Target(name="ok", url=self.url("/ok")), timeout=5
        )
        self.assertTrue(result.up)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.error)
        self.assertGreaterEqual(result.latency_ms, 0)

    def test_down_on_unexpected_status(self):
        result = check_target(
            Target(name="nf", url=self.url("/notfound")), timeout=5
        )
        self.assertFalse(result.up)
        self.assertEqual(result.status_code, 404)
        self.assertIsNotNone(result.error)

    def test_custom_expected_status_counts_as_up(self):
        result = check_target(
            Target(name="tea", url=self.url("/teapot"), expected_status=418),
            timeout=5,
        )
        self.assertTrue(result.up)
        self.assertEqual(result.status_code, 418)

    def test_connection_refused_is_down_not_an_exception(self):
        result = check_target(
            Target(name="dead", url="http://127.0.0.1:1/"), timeout=2
        )
        self.assertFalse(result.up)
        self.assertIsNone(result.status_code)
        self.assertIsNotNone(result.error)

    def test_head_method(self):
        result = check_target(
            Target(name="head", url=self.url("/ok"), method="HEAD"), timeout=5
        )
        self.assertTrue(result.up)
        self.assertEqual(result.status_code, 200)


if __name__ == "__main__":
    unittest.main()

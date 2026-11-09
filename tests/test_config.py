"""Tests for config parsing (YAML + JSON) and validation."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cloudpulse.config import Target, load_config  # noqa: E402

VALID_YAML = """\
interval_seconds: 10
timeout_seconds: 3
port: 9090
targets:
  - name: example
    url: https://example.com
  - name: custom
    url: http://localhost:8000/health
    expected_status: 204
    method: HEAD
    timeout_seconds: 2
"""

VALID_JSON = {
    "interval_seconds": 15,
    "timeout_seconds": 4,
    "targets": [{"name": "j", "url": "https://example.org"}],
}


class ConfigTests(unittest.TestCase):
    def _write(self, tmpdir, name, text):
        path = Path(tmpdir) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_valid_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = load_config(self._write(tmpdir, "c.yaml", VALID_YAML))
        self.assertEqual(cfg.interval_seconds, 10)
        self.assertEqual(cfg.timeout_seconds, 3)
        self.assertEqual(cfg.port, 9090)
        self.assertEqual(len(cfg.targets), 2)
        self.assertEqual(cfg.targets[0].name, "example")
        self.assertEqual(cfg.targets[0].expected_status, 200)
        self.assertEqual(cfg.targets[1].expected_status, 204)
        self.assertEqual(cfg.targets[1].method, "HEAD")
        self.assertEqual(cfg.targets[1].timeout_seconds, 2)

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = load_config(
                self._write(tmpdir, "c.json", json.dumps(VALID_JSON))
            )
        self.assertEqual(cfg.interval_seconds, 15)
        self.assertEqual(len(cfg.targets), 1)
        self.assertEqual(cfg.targets[0].url, "https://example.org")

    def test_repo_default_config_loads(self):
        repo_config = Path(__file__).resolve().parent.parent / "config.yaml"
        cfg = load_config(repo_config)
        self.assertGreaterEqual(len(cfg.targets), 1)
        self.assertEqual(cfg.port, 8080)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")

    def test_empty_targets_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "c.yaml", "targets: []\n")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_missing_targets_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "c.yaml", "interval_seconds: 10\n")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_bad_url_rejected(self):
        with self.assertRaises(ValueError):
            Target(name="x", url="not-a-url")
        with self.assertRaises(ValueError):
            Target(name="x", url="ftp://example.com")

    def test_duplicate_names_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            text = (
                "targets:\n"
                "  - name: dup\n    url: https://a.example\n"
                "  - name: dup\n    url: https://b.example\n"
            )
            with self.assertRaises(ValueError):
                load_config(self._write(tmpdir, "c.yaml", text))

    def test_duplicate_urls_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            text = (
                "targets:\n"
                "  - name: a\n    url: https://a.example\n"
                "  - name: b\n    url: https://a.example\n"
            )
            with self.assertRaises(ValueError):
                load_config(self._write(tmpdir, "c.yaml", text))

    def test_nonpositive_interval_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            text = (
                "interval_seconds: 0\n"
                "targets:\n"
                "  - name: a\n    url: https://a.example\n"
            )
            with self.assertRaises(ValueError):
                load_config(self._write(tmpdir, "c.yaml", text))

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            Target(name="x", url="https://example.com", expected_status=99)
        with self.assertRaises(ValueError):
            Target(name="x", url="https://example.com", method="POST")

    def test_invalid_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                load_config(self._write(tmpdir, "c.json", "{not json"))

    def test_unsupported_extension_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                load_config(self._write(tmpdir, "c.txt", "targets: []"))


if __name__ == "__main__":
    unittest.main()

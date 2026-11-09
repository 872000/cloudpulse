"""Tests for Prometheus metrics output and the history store."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cloudpulse.checker import CheckResult  # noqa: E402
from cloudpulse.metrics import render_metrics  # noqa: E402
from cloudpulse.store import HistoryStore  # noqa: E402


def _result(name, up, latency=12.5, status=200):
    return CheckResult(
        name=name,
        url=f"https://{name}.example",
        up=up,
        status_code=status if up else 500,
        latency_ms=latency,
        error=None if up else "HTTP 500",
        checked_at=1700000000.0,
    )


class StoreTests(unittest.TestCase):
    def test_record_and_latest(self):
        store = HistoryStore(history_size=10)
        store.register("a", "https://a.example")
        self.assertIsNone(store.latest("a"))
        store.record(_result("a", True))
        store.record(_result("a", False))
        latest = store.latest("a")
        self.assertFalse(latest.up)
        self.assertEqual(len(store.history("a")), 2)

    def test_uptime_ratio(self):
        store = HistoryStore(history_size=10)
        store.register("a", "https://a.example")
        self.assertIsNone(store.uptime_ratio("a"))
        for up in (True, True, False, True):
            store.record(_result("a", up))
        self.assertAlmostEqual(store.uptime_ratio("a"), 0.75)

    def test_history_bounded(self):
        store = HistoryStore(history_size=3)
        store.register("a", "https://a.example")
        for _ in range(5):
            store.record(_result("a", True))
        self.assertEqual(len(store.history("a")), 3)
        # Counters are NOT bounded: all 5 checks still count.
        self.assertEqual(store.snapshot()["targets"][0]["checks_total"], 5)

    def test_snapshot_shape(self):
        store = HistoryStore()
        store.register("a", "https://a.example")
        store.record(_result("a", True))
        snap = store.snapshot()
        target = snap["targets"][0]
        self.assertEqual(target["name"], "a")
        self.assertTrue(target["up"])
        self.assertEqual(target["checks_total"], 1)
        self.assertEqual(target["uptime_ratio"], 1.0)
        self.assertEqual(len(target["history"]), 1)


class MetricsTests(unittest.TestCase):
    def _store_with(self, name, ups):
        store = HistoryStore()
        store.register(name, f"https://{name}.example")
        for up in ups:
            store.record(_result(name, up))
        return store

    def test_up_gauge_and_latency_present(self):
        out = render_metrics(self._store_with("web", [True]))
        self.assertIn('cloudpulse_up{target="web"} 1', out)
        self.assertIn('cloudpulse_latency_milliseconds{target="web"} 12.5', out)
        self.assertIn("# TYPE cloudpulse_up gauge", out)

    def test_down_gauge_is_zero(self):
        out = render_metrics(self._store_with("web", [False]))
        self.assertIn('cloudpulse_up{target="web"} 0', out)

    def test_checks_total_counter(self):
        out = render_metrics(self._store_with("web", [True, True, False]))
        self.assertIn('cloudpulse_checks_total{target="web",status="up"} 2', out)
        self.assertIn(
            'cloudpulse_checks_total{target="web",status="down"} 1', out
        )
        self.assertIn("# TYPE cloudpulse_checks_total counter", out)

    def test_uptime_ratio(self):
        out = render_metrics(self._store_with("web", [True, True, False, True]))
        self.assertIn('cloudpulse_uptime_ratio{target="web"} 0.75', out)

    def test_no_checks_yields_no_gauge_lines(self):
        store = HistoryStore()
        store.register("fresh", "https://fresh.example")
        out = render_metrics(store)
        self.assertNotIn('target="fresh"', out)
        # HELP/TYPE headers are still emitted.
        self.assertIn("# HELP cloudpulse_up", out)

    def test_output_ends_with_newline_and_no_blank_metric_lines(self):
        out = render_metrics(self._store_with("web", [True]))
        self.assertTrue(out.endswith("\n"))
        for line in out.splitlines():
            self.assertTrue(line.strip(), "no blank lines in exposition output")


if __name__ == "__main__":
    unittest.main()

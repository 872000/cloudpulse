"""HTTP server: probes, metrics, status API, and a small dashboard UI.

Endpoints:
- ``GET /healthz`` — liveness: 200 while the process is running.
- ``GET /readyz`` — readiness: 200 once the first check round has run
  (or no targets are configured, which cannot happen — config validation
  requires at least one target), else 503.
- ``GET /metrics`` — Prometheus exposition format.
- ``GET /api/status`` — JSON snapshot of every target + history.
- ``GET /`` — HTML dashboard.
"""

from __future__ import annotations

import html
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .checker import check_target
from .config import Config
from .metrics import render_metrics
from .store import HistoryStore

_DASHBOARD_TEMPLATE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>CloudPulse</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
.up {{ color: green; font-weight: bold; }} .down {{ color: red; font-weight: bold; }}
</style></head>
<body>
<h1>CloudPulse</h1>
<p>Uptime monitor &mdash; <a href="/api/status">JSON API</a> &middot;
<a href="/metrics">Prometheus metrics</a> &middot;
<a href="/healthz">/healthz</a> &middot; <a href="/readyz">/readyz</a></p>
<table><tr><th>Target</th><th>URL</th><th>Status</th><th>Latency</th>
<th>Uptime</th><th>Checks</th></tr>
{rows}
</table>
<p><small>Refreshed at render time; reload to update.</small></p>
</body></html>
"""


def build_handler(store: HistoryStore, ready_event: threading.Event):
    """Build a request-handler class bound to a store and readiness flag."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep stdout clean
            pass

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _send_json(self, status: int, payload: object) -> None:
            self._send(
                status,
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler naming
            if self.path == "/healthz":
                self._send_json(200, {"status": "ok"})
            elif self.path == "/readyz":
                if ready_event.is_set():
                    self._send_json(200, {"status": "ready"})
                else:
                    self._send_json(503, {"status": "not ready"})
            elif self.path == "/metrics":
                self._send(
                    200,
                    render_metrics(store).encode("utf-8"),
                    "text/plain; version=0.0.4; charset=utf-8",
                )
            elif self.path == "/api/status":
                self._send_json(200, store.snapshot())
            elif self.path in ("/", "/index.html"):
                self._send(
                    200, _render_dashboard(store).encode("utf-8"), "text/html"
                )
            else:
                self._send_json(404, {"error": "not found"})

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

    return Handler


def _render_dashboard(store: HistoryStore) -> str:
    rows = []
    for target in store.snapshot()["targets"]:
        if target["up"] is None:
            status = '<span>pending</span>'
            latency = "&mdash;"
            uptime = "&mdash;"
        else:
            cls = "up" if target["up"] else "down"
            status = f'<span class="{cls}">{"UP" if target["up"] else "DOWN"}</span>'
            latency = f'{target["latency_ms"]} ms'
            uptime = (
                f'{target["uptime_ratio"] * 100:.1f}%'
                if target["uptime_ratio"] is not None
                else "&mdash;"
            )
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "<td>{}</td><td>{}</td></tr>".format(
                html.escape(target["name"]),
                html.escape(target["url"]),
                status,
                latency,
                uptime,
                target["checks_total"],
            )
        )
    return _DASHBOARD_TEMPLATE.format(
        rows="\n".join(rows) or "<tr><td colspan=6>No targets</td></tr>"
    )


def run_scheduler(
    config: Config,
    store: HistoryStore,
    ready_event: threading.Event,
    stop_event: threading.Event,
) -> None:
    """Loop forever (until ``stop_event``): check every due target.

    Each target is checked every ``config.interval_seconds``. Checks run
    sequentially in this thread so a slow target delays only the next
    round, never the HTTP server.
    """
    for target in config.targets:
        store.register(target.name, target.url)
    while not stop_event.is_set():
        round_started = time.monotonic()
        for target in config.targets:
            if stop_event.is_set():
                break
            store.record(check_target(target, config.timeout_seconds))
        ready_event.set()
        elapsed = time.monotonic() - round_started
        stop_event.wait(timeout=max(0.0, config.interval_seconds - elapsed))


def create_server(
    config: Config, store: HistoryStore, ready_event: threading.Event
) -> ThreadingHTTPServer:
    handler = build_handler(store, ready_event)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    server.daemon_threads = True
    return server

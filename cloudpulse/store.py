"""Thread-safe in-memory store for check history and rollups."""

from __future__ import annotations

import threading
from collections import deque

from .checker import CheckResult


class HistoryStore:
    """Keeps the last N results per target, plus counters.

    The HTTP server reads from this store while the scheduler thread
    writes to it, so every access goes through one lock.
    """

    def __init__(self, history_size: int = 100) -> None:
        self._history_size = history_size
        self._lock = threading.Lock()
        self._history: dict[str, deque[CheckResult]] = {}
        self._total: dict[str, int] = {}
        self._up_count: dict[str, int] = {}
        self._targets: dict[str, str] = {}  # name -> url

    def register(self, name: str, url: str) -> None:
        with self._lock:
            self._targets[name] = url
            self._history.setdefault(name, deque(maxlen=self._history_size))
            self._total.setdefault(name, 0)
            self._up_count.setdefault(name, 0)

    def record(self, result: CheckResult) -> None:
        with self._lock:
            self._history.setdefault(
                result.name, deque(maxlen=self._history_size)
            ).append(result)
            self._total[result.name] = self._total.get(result.name, 0) + 1
            if result.up:
                self._up_count[result.name] = self._up_count.get(result.name, 0) + 1

    def latest(self, name: str) -> CheckResult | None:
        with self._lock:
            history = self._history.get(name)
            return history[-1] if history else None

    def history(self, name: str) -> list[CheckResult]:
        with self._lock:
            return list(self._history.get(name, []))

    def uptime_ratio(self, name: str) -> float | None:
        """Fraction of recorded checks that were up (None if no checks)."""
        with self._lock:
            total = self._total.get(name, 0)
            if not total:
                return None
            return self._up_count.get(name, 0) / total

    def snapshot(self) -> dict:
        """Full JSON-friendly snapshot for the status API / UI."""
        with self._lock:
            targets = []
            for name, url in self._targets.items():
                history = self._history.get(name, deque())
                last = history[-1] if history else None
                total = self._total.get(name, 0)
                targets.append(
                    {
                        "name": name,
                        "url": url,
                        "up": last.up if last else None,
                        "status_code": last.status_code if last else None,
                        "latency_ms": round(last.latency_ms, 2) if last else None,
                        "error": last.error if last else None,
                        "checked_at": last.checked_at if last else None,
                        "checks_total": total,
                        "up_count": self._up_count.get(name, 0),
                        "uptime_ratio": (
                            round(self._up_count.get(name, 0) / total, 4)
                            if total
                            else None
                        ),
                        "history": [
                            {
                                "up": r.up,
                                "status_code": r.status_code,
                                "latency_ms": round(r.latency_ms, 2),
                                "checked_at": r.checked_at,
                            }
                            for r in history
                        ],
                    }
                )
            return {"targets": targets}

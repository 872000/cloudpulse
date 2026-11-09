"""Endpoint checker: one HTTP probe, one recorded result."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Target


@dataclass(frozen=True)
class CheckResult:
    """The outcome of a single probe of one target."""

    name: str
    url: str
    up: bool
    status_code: int | None
    latency_ms: float
    error: str | None
    checked_at: float  # epoch seconds


def check_target(target: Target, timeout: float) -> CheckResult:
    """Probe ``target`` once and return a :class:`CheckResult`.

    A target is "up" when the request succeeds and the HTTP status
    matches ``target.expected_status``. Any transport error, timeout,
    or unexpected status is "down" — the error is recorded, never raised,
    so one bad target cannot break the monitoring loop.
    """
    effective_timeout = target.timeout_seconds or timeout
    request = urllib.request.Request(target.url, method=target.method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=effective_timeout) as resp:
            status = resp.status
            # Read (and discard) the body so latency reflects a full fetch.
            resp.read(1)
    except urllib.error.HTTPError as exc:
        # HTTPError still carries a real status code: up only if it matches.
        latency_ms = (time.monotonic() - started) * 1000.0
        return CheckResult(
            name=target.name,
            url=target.url,
            up=exc.code == target.expected_status,
            status_code=exc.code,
            latency_ms=latency_ms,
            error=None if exc.code == target.expected_status else f"HTTP {exc.code}",
            checked_at=time.time(),
        )
    except Exception as exc:  # URLError, TimeoutError, socket errors, ...
        latency_ms = (time.monotonic() - started) * 1000.0
        return CheckResult(
            name=target.name,
            url=target.url,
            up=False,
            status_code=None,
            latency_ms=latency_ms,
            error=f"{type(exc).__name__}: {exc}",
            checked_at=time.time(),
        )
    latency_ms = (time.monotonic() - started) * 1000.0
    return CheckResult(
        name=target.name,
        url=target.url,
        up=status == target.expected_status,
        status_code=status,
        latency_ms=latency_ms,
        error=None if status == target.expected_status else f"HTTP {status}",
        checked_at=time.time(),
    )

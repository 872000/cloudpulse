"""Prometheus-format metrics rendering for CloudPulse."""

from __future__ import annotations

from .store import HistoryStore


def _escape_label(value: str) -> str:
    return (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )


def render_metrics(store: HistoryStore) -> str:
    """Render the current state as Prometheus exposition text.

    Metrics:
    - ``cloudpulse_up{target}`` — 1 if the last check was up, else 0
      (absent until the first check for a target).
    - ``cloudpulse_latency_milliseconds{target}`` — last check latency.
    - ``cloudpulse_checks_total{target,status}`` — cumulative checks.
    - ``cloudpulse_uptime_ratio{target}`` — up checks / total checks.
    """
    snapshot = store.snapshot()
    lines = [
        "# HELP cloudpulse_up Whether the target was up on the last check (1) or down (0).",
        "# TYPE cloudpulse_up gauge",
    ]
    for target in snapshot["targets"]:
        if target["up"] is None:
            continue
        lines.append(
            f'cloudpulse_up{{target="{_escape_label(target["name"])}"}} '
            f"{1 if target['up'] else 0}"
        )
    lines += [
        "# HELP cloudpulse_latency_milliseconds Latency of the last check in milliseconds.",
        "# TYPE cloudpulse_latency_milliseconds gauge",
    ]
    for target in snapshot["targets"]:
        if target["latency_ms"] is None:
            continue
        lines.append(
            f'cloudpulse_latency_milliseconds{{target="{_escape_label(target["name"])}"}} '
            f"{target['latency_ms']}"
        )
    lines += [
        "# HELP cloudpulse_checks_total Total number of checks performed, by outcome.",
        "# TYPE cloudpulse_checks_total counter",
    ]
    for target in snapshot["targets"]:
        if target["checks_total"] == 0:
            continue
        up_total = target["up_count"]
        lines.append(
            f'cloudpulse_checks_total{{target="{_escape_label(target["name"])}",status="up"}} '
            f"{up_total}"
        )
        lines.append(
            f'cloudpulse_checks_total{{target="{_escape_label(target["name"])}",status="down"}} '
            f"{target['checks_total'] - up_total}"
        )
    lines += [
        "# HELP cloudpulse_uptime_ratio Fraction of checks that were up (0-1).",
        "# TYPE cloudpulse_uptime_ratio gauge",
    ]
    for target in snapshot["targets"]:
        if target["uptime_ratio"] is None:
            continue
        lines.append(
            f'cloudpulse_uptime_ratio{{target="{_escape_label(target["name"])}"}} '
            f"{target['uptime_ratio']}"
        )
    return "\n".join(lines) + "\n"

"""Configuration loading and validation for CloudPulse.

Supports JSON config files and a small, well-defined subset of YAML
(the subset used by ``config.yaml``): top-level scalar keys and a
``targets:`` list of mappings. Keeping the YAML parser in the standard
library means the service runs anywhere with no extra installs.

Example config (YAML)::

    interval_seconds: 30
    timeout_seconds: 5
    targets:
      - name: example
        url: https://example.com
        expected_status: 200

The same shape works as JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Target:
    """One endpoint to monitor."""

    name: str
    url: str
    expected_status: int = 200
    method: str = "GET"
    timeout_seconds: float | None = None  # None -> use global timeout

    def __post_init__(self) -> None:
        if not self.name or not str(self.name).strip():
            raise ValueError("target name must be a non-empty string")
        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(
                f"target {self.name!r}: url {self.url!r} must be an "
                "absolute http(s) URL"
            )
        if not 100 <= self.expected_status <= 599:
            raise ValueError(
                f"target {self.name!r}: expected_status "
                f"{self.expected_status!r} must be between 100 and 599"
            )
        if self.method.upper() not in ("GET", "HEAD"):
            raise ValueError(
                f"target {self.name!r}: method must be GET or HEAD, "
                f"got {self.method!r}"
            )
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError(
                f"target {self.name!r}: timeout_seconds must be > 0"
            )


@dataclass
class Config:
    """Whole-service configuration."""

    targets: list[Target] = field(default_factory=list)
    interval_seconds: float = 30.0
    timeout_seconds: float = 5.0
    host: str = "0.0.0.0"
    port: int = 8080
    history_size: int = 100

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.history_size <= 0:
            raise ValueError("history_size must be > 0")
        if not self.targets:
            raise ValueError("config must list at least one target")
        names = [t.name for t in self.targets]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate target names: {names}")
        urls = [t.url for t in self.targets]
        if len(set(urls)) != len(urls):
            raise ValueError(f"duplicate target urls: {urls}")


def _coerce_number(value, field_name: str):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number, got {value!r}")
    return value


def _parse_simple_yaml(text: str) -> dict:
    """Parse the small YAML subset used by CloudPulse configs.

    Supports top-level ``key: value`` scalars, ``#`` comments, and one
    list of mappings under a top-level key (``targets:``). Anything
    outside that subset raises ValueError so a malformed file fails
    loudly instead of being silently misread.
    """
    result: dict = {}
    current_list_key: str | None = None
    current_item: dict | None = None

    def scalar(raw: str):
        raw = raw.strip()
        if raw in ("true", "True"):
            return True
        if raw in ("false", "False"):
            return False
        if raw in ("null", "~", ""):
            return None
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        if re.fullmatch(r"-?\d+\.\d+", raw):
            return float(raw)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            return raw[1:-1]
        return raw

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0] if not raw_line.lstrip().startswith("#") else ""
        # Strip inline comments only when preceded by a space.
        if "#" in raw_line and not raw_line.lstrip().startswith("#"):
            before, _, _after = raw_line.partition(" #")
            line = before
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0:
            if ":" not in stripped:
                raise ValueError(f"config.yaml line {lineno}: expected 'key: value'")
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            current_item = None
            if value == "":
                current_list_key = key
                result[key] = []
            else:
                current_list_key = None
                result[key] = scalar(value)
        elif stripped.startswith("- "):
            if current_list_key is None:
                raise ValueError(
                    f"config.yaml line {lineno}: list item without a list key"
                )
            current_item = {}
            result[current_list_key].append(current_item)
            rest = stripped[2:].strip()
            if rest:
                if ":" not in rest:
                    raise ValueError(
                        f"config.yaml line {lineno}: expected 'key: value'"
                    )
                key, _, value = rest.partition(":")
                current_item[key.strip()] = scalar(value.strip())
        elif current_item is not None and indent >= 2:
            if ":" not in stripped:
                raise ValueError(f"config.yaml line {lineno}: expected 'key: value'")
            key, _, value = stripped.partition(":")
            current_item[key.strip()] = scalar(value.strip())
        else:
            raise ValueError(
                f"config.yaml line {lineno}: unsupported indentation/content: "
                f"{stripped!r}"
            )
    return result


def _build_config(data: dict) -> Config:
    if not isinstance(data, dict):
        raise ValueError("config top level must be a mapping")
    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("config must contain a non-empty 'targets' list")
    targets = []
    for i, raw in enumerate(raw_targets):
        if not isinstance(raw, dict):
            raise ValueError(f"targets[{i}] must be a mapping")
        if "name" not in raw or "url" not in raw:
            raise ValueError(f"targets[{i}] needs 'name' and 'url'")
        timeout = raw.get("timeout_seconds")
        if timeout is not None:
            timeout = _coerce_number(timeout, f"targets[{i}].timeout_seconds")
        expected = raw.get("expected_status", 200)
        expected = _coerce_number(expected, f"targets[{i}].expected_status")
        targets.append(
            Target(
                name=str(raw["name"]),
                url=str(raw["url"]),
                expected_status=int(expected),
                method=str(raw.get("method", "GET")).upper(),
                timeout_seconds=float(timeout) if timeout is not None else None,
            )
        )
    interval = _coerce_number(
        data.get("interval_seconds", 30), "interval_seconds"
    )
    timeout = _coerce_number(data.get("timeout_seconds", 5), "timeout_seconds")
    port = _coerce_number(data.get("port", 8080), "port")
    history = _coerce_number(data.get("history_size", 100), "history_size")
    return Config(
        targets=targets,
        interval_seconds=float(interval),
        timeout_seconds=float(timeout),
        host=str(data.get("host", "0.0.0.0")),
        port=int(port),
        history_size=int(history),
    )


def load_config(path: str | Path) -> Config:
    """Load and validate a config file (``.json`` or ``.yaml``/``.yml``)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    elif suffix in (".yaml", ".yml"):
        data = _parse_simple_yaml(text)
    else:
        raise ValueError(
            f"unsupported config extension {suffix!r}: use .json or .yaml"
        )
    return _build_config(data)

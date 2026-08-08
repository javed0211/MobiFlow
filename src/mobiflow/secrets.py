"""Env injection for Maestro and secret redaction in reports/logs."""

from __future__ import annotations

import os
import re
from typing import Any

_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|access[_-]?key|auth|credential)",
    re.IGNORECASE,
)


def merge_flow_env(
    *maps: dict[str, str] | None,
    resolve_from_process: bool = True,
) -> dict[str, str]:
    """Merge env maps; values that look like ENV NAMES are resolved from the process.

    If a value matches ``^[A-Z_][A-Z0-9_]*$`` and exists in ``os.environ``, the
    process value is used (so config can store ``PASSWORD: MOBIFLOW_PASSWORD``).
    """
    out: dict[str, str] = {}
    for m in maps:
        if not m:
            continue
        for key, val in m.items():
            k = str(key).strip()
            if not k:
                continue
            v = "" if val is None else str(val)
            if (
                resolve_from_process
                and re.fullmatch(r"[A-Z_][A-Z0-9_]*", v)
                and v in os.environ
            ):
                out[k] = os.environ[v]
                continue
            # Also: empty value + key present in process → use process
            if resolve_from_process and not v and k in os.environ:
                out[k] = os.environ[k]
                continue
            out[k] = v
    return out


def maestro_env_args(env: dict[str, str]) -> list[str]:
    """Build ``--env KEY=VALUE`` argv fragments for Maestro CLI."""
    args: list[str] = []
    for key, val in sorted(env.items()):
        args.extend(["--env", f"{key}={val}"])
    return args


def is_secret_key(name: str) -> bool:
    return bool(_SECRET_KEY_RE.search(name or ""))


def redact_text(text: str, secrets: dict[str, str] | None = None) -> str:
    """Replace known secret values (and obvious key=value pairs) in text."""
    if not text:
        return text
    out = text
    for key, val in (secrets or {}).items():
        if not val or len(val) < 4:
            continue
        if is_secret_key(key) or len(val) >= 8:
            out = out.replace(val, "***")
    # Generic KEY=secret patterns for common names
    out = re.sub(
        r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)\s*[=:]\s*\S+",
        r"\1=***",
        out,
    )
    return out


def redact_mapping(data: dict[str, Any], secrets: dict[str, str] | None = None) -> dict[str, Any]:
    """Shallow-redact string values in a dict for JSON reports."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str):
            if is_secret_key(str(k)):
                out[k] = "***"
            else:
                out[k] = redact_text(v, secrets)
        else:
            out[k] = v
    return out

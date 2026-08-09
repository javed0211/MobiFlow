"""External test data files for cases (``data: path``).

Supported formats: ``.json``, ``.yaml`` / ``.yml``, ``.env``.
Values are flattened to string env vars for Maestro ``--env`` / ``${KEY}``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def resolve_data_path(
    raw: str,
    *,
    case_path: Path | None = None,
    repo: Path | None = None,
) -> Path:
    """Resolve relative/absolute data path.

    Order for relative paths:
    1. Beside the case file
    2. Project repo root
    3. CWD
    """
    text = (raw or "").strip().strip("\"'")
    if not text:
        raise ValueError("data: path is empty")
    p = Path(text).expanduser()
    if p.is_absolute():
        if not p.is_file():
            raise FileNotFoundError(f"Data file not found: {p}")
        return p.resolve()

    candidates: list[Path] = []
    if case_path is not None:
        candidates.append((case_path.parent / p).resolve())
    if repo is not None:
        candidates.append((Path(repo).resolve() / p).resolve())
    candidates.append((Path.cwd() / p).resolve())

    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        f"Data file not found: {text} (tried: {', '.join(str(c) for c in candidates)})"
    )


def flatten_data(obj: Any, *, prefix: str = "") -> dict[str, str]:
    """Flatten nested dict/list into UPPER_SNAKE Maestro env keys."""
    out: dict[str, str] = {}

    def _key(parts: list[str]) -> str:
        raw = "_".join(parts)
        raw = re.sub(r"[^A-Za-z0-9_]+", "_", raw)
        raw = re.sub(r"_+", "_", raw).strip("_")
        if not raw:
            raw = "VALUE"
        if raw[0].isdigit():
            raw = f"N_{raw}"
        return raw.upper()

    def walk(node: Any, parts: list[str]) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, parts + [str(k)])
            return
        if isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, parts + [str(i)])
            return
        if node is None:
            return
        if isinstance(node, bool):
            out[_key(parts)] = "true" if node else "false"
            return
        out[_key(parts)] = str(node)

    root_parts = [prefix] if prefix else []
    if isinstance(obj, dict):
        walk(obj, root_parts)
    elif isinstance(obj, list):
        # Prefer first object row for single-record data files
        if obj and isinstance(obj[0], dict) and len(obj) == 1:
            walk(obj[0], root_parts)
        else:
            walk(obj, root_parts or ["ITEM"])
    else:
        walk(obj, root_parts or ["VALUE"])
    return out


def load_data_file(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Load a data file → (raw object, flattened string env map)."""
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        raw: Any = json.loads(text) if text.strip() else {}
    elif suffix in {".yaml", ".yml"}:
        import yaml

        raw = yaml.safe_load(text) if text.strip() else {}
    elif suffix == ".env" or path.name.startswith(".env"):
        raw = {}
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("export "):
                s = s[7:].strip()
            m = _ENV_LINE.match(s)
            if not m:
                continue
            val = m.group(2).strip().strip("\"'")
            raw[m.group(1)] = val
    else:
        raise ValueError(
            f"Unsupported data file type '{suffix or path.name}'. "
            "Use .json, .yaml/.yml, or .env"
        )

    if raw is None:
        raw = {}
    flat = flatten_data(raw)
    return (raw if isinstance(raw, dict) else {"data": raw}), flat


def format_data_prompt_block(
    flat: dict[str, str],
    *,
    path: str = "",
    limit: int = 40,
) -> str:
    """Compact block injected into explore/codegen goals."""
    if not flat:
        return ""
    lines = [f"{k}={v}" for k, v in sorted(flat.items())[:limit]]
    more = ""
    if len(flat) > limit:
        more = f"\n… ({len(flat) - limit} more keys)"
    head = f"Test data from {path}:" if path else "Test data:"
    return (
        f"{head}\n"
        "Use these values via Maestro ${KEY} / --env (do not hardcode secrets):\n"
        + "\n".join(lines)
        + more
    )

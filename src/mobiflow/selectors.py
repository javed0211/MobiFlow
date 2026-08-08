"""Durable selector memory across explore / codegen runs."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _safe_app_key(app_id: str) -> str:
    raw = (app_id or "unknown").strip() or "unknown"
    return re.sub(r"[^\w.\-]+", "_", raw)[:120]


def selectors_path(artifacts_dir: Path, app_id: str) -> Path:
    return Path(artifacts_dir) / "selectors" / f"{_safe_app_key(app_id)}.json"


def load_selector_memory(artifacts_dir: Path, app_id: str) -> dict[str, Any]:
    path = selectors_path(artifacts_dir, app_id)
    if not path.is_file():
        return {"app_id": app_id, "selectors": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"app_id": app_id, "selectors": []}
    if not isinstance(data, dict):
        return {"app_id": app_id, "selectors": []}
    data.setdefault("app_id", app_id)
    data.setdefault("selectors", [])
    return data


def save_selector_memory(
    artifacts_dir: Path,
    app_id: str,
    memory: dict[str, Any],
) -> Path:
    path = selectors_path(artifacts_dir, app_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    memory = dict(memory)
    memory["app_id"] = app_id
    memory["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(memory, indent=2) + "\n", encoding="utf-8")
    return path


def merge_selectors(
    memory: dict[str, Any],
    selectors: list[dict[str, Any]],
    *,
    success: bool = True,
) -> dict[str, Any]:
    """Upsert selectors; bump hits on success, demote on failure."""
    existing = {
        (str(s.get("label") or ""), str(s.get("text") or "")): s
        for s in memory.get("selectors") or []
        if isinstance(s, dict)
    }
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for sel in selectors:
        if not isinstance(sel, dict):
            continue
        label = str(sel.get("label") or "").strip()
        text = str(sel.get("text") or "").strip()
        if not text and not label:
            continue
        key = (label, text)
        row = existing.get(key) or {
            "label": label,
            "text": text,
            "hits": 0,
            "misses": 0,
        }
        if success:
            row["hits"] = int(row.get("hits") or 0) + 1
            row["last_success"] = now
        else:
            row["misses"] = int(row.get("misses") or 0) + 1
            row["last_miss"] = now
        existing[key] = row
    # Prefer high-hit selectors
    ordered = sorted(
        existing.values(),
        key=lambda s: (int(s.get("hits") or 0) - int(s.get("misses") or 0)),
        reverse=True,
    )
    memory["selectors"] = ordered[:80]
    return memory


def memory_to_prompt_block(memory: dict[str, Any], *, limit: int = 20) -> str:
    sels = list(memory.get("selectors") or [])[:limit]
    if not sels:
        return ""
    lines = ["Known working selectors (from prior runs):"]
    for s in sels:
        if int(s.get("hits") or 0) <= 0 and int(s.get("misses") or 0) > 0:
            continue
        label = s.get("label") or "-"
        text = s.get("text") or "-"
        hits = s.get("hits") or 0
        lines.append(f"- {label} → {text} (hits={hits})")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def ensure_expect_asserts(flow_yaml: str, expect: list[str]) -> str:
    """Append assertVisible lines for expect texts not already present."""
    texts = [t.strip() for t in expect if t and str(t).strip()]
    if not texts:
        return flow_yaml
    body = flow_yaml or ""
    additions: list[str] = []
    for text in texts:
        needle = f'assertVisible: "{text}"'
        needle2 = f"assertVisible: {text}"
        if needle in body or needle2 in body:
            continue
        additions.append(f'- assertVisible: "{text}"')
    if not additions:
        return body
    if not body.endswith("\n"):
        body += "\n"
    return body + "\n".join(additions) + "\n"

"""Incremental / extend-explore helpers (WebQA-style case growth).

Modes:
- ``unchanged`` — prior guidance matches; reuse frozen YAML
- ``append`` — new steps only after a common prefix; explore the gap, extend YAML
- ``dirty`` — earlier steps changed; full regenerate seeded with prior YAML
- ``fresh`` — no prior guidance / no prior flow
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_NUMBERED_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$")
_STOP_APP_RE = re.compile(r"(?m)^\s*-\s*stopApp\b.*(?:\n(?:[ \t]+.+)*)?")


@dataclass
class GuidanceDiff:
    mode: str  # unchanged | append | dirty | fresh
    common_prefix: int = 0
    prior_guidance: list[str] = field(default_factory=list)
    current_guidance: list[str] = field(default_factory=list)

    @property
    def new_guidance(self) -> list[str]:
        return self.current_guidance[self.common_prefix :]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "common_prefix": self.common_prefix,
            "prior_guidance": list(self.prior_guidance),
            "current_guidance": list(self.current_guidance),
            "new_guidance": list(self.new_guidance),
        }


def extract_numbered_steps(text: str) -> list[str]:
    """Pull ``1. …`` / ``2. …`` lines from free text (task body or case file)."""
    steps: list[str] = []
    for line in (text or "").splitlines():
        m = _NUMBERED_RE.match(line.rstrip())
        if m:
            steps.append(m.group(2).strip())
    return steps


def normalize_guidance(steps: list[str] | None) -> list[str]:
    return [str(s).strip() for s in (steps or []) if str(s).strip()]


def classify_guidance(
    prior_guidance: list[str] | None,
    current_guidance: list[str] | None,
) -> GuidanceDiff:
    prior = normalize_guidance(prior_guidance)
    current = normalize_guidance(current_guidance)
    if not prior:
        return GuidanceDiff(mode="fresh", prior_guidance=prior, current_guidance=current)
    if prior == current:
        return GuidanceDiff(
            mode="unchanged",
            common_prefix=len(prior),
            prior_guidance=prior,
            current_guidance=current,
        )
    n = 0
    for a, b in zip(prior, current):
        if a != b:
            break
        n += 1
    if n == len(prior) and len(current) > len(prior):
        return GuidanceDiff(
            mode="append",
            common_prefix=n,
            prior_guidance=prior,
            current_guidance=current,
        )
    return GuidanceDiff(
        mode="dirty",
        common_prefix=n,
        prior_guidance=prior,
        current_guidance=current,
    )


def format_gap_task(
    *,
    title: str,
    new_steps: list[str],
    start_index: int = 1,
    app_id: str = "",
) -> str:
    """Narrow explore/codegen goal for newly appended steps only."""
    if not new_steps:
        return title or "Verify the current screen state."
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(new_steps, start_index))
    head = (title or "Continue the scenario").strip().split("\n")[0]
    app_hint = f" App under test: {app_id}." if app_id else ""
    return (
        f"{head}\n\n"
        f"You are ALREADY past the earlier completed steps of this flow.{app_hint} "
        f"Do NOT relaunch the app or redo onboarding/search/setup already done. "
        f"Execute ONLY the following new steps from the current screen:\n{numbered}"
    )


def guidance_path(repo: Path, case_name: str) -> Path:
    return Path(repo).resolve() / ".mobiflow" / "guidance" / f"{case_name}.json"


def load_guidance(repo: Path, case_name: str) -> list[str]:
    path = guidance_path(repo, case_name)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw = data.get("guidance_steps") if isinstance(data, dict) else None
    if isinstance(raw, list):
        return normalize_guidance([str(x) for x in raw])
    return []


def save_guidance(
    repo: Path,
    case_name: str,
    guidance_steps: list[str],
    *,
    flow_path: str = "",
    mode: str = "",
) -> Path:
    path = guidance_path(repo, case_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "case": case_name,
        "guidance_steps": normalize_guidance(guidance_steps),
        "flow_path": flow_path,
        "mode": mode,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def strip_trailing_stop_app(flow_yaml: str) -> str:
    """Remove final stopApp so a prefix flow can leave the app open for gap explore."""
    text = (flow_yaml or "").rstrip() + "\n"
    # Remove all stopApp commands for replay-as-prefix; caller may re-add later
    cleaned = _STOP_APP_RE.sub("", text)
    # Collapse excess blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).rstrip() + "\n"
    return cleaned


def merge_flow_yaml(prior_yaml: str, extension_yaml: str, *, app_id: str = "") -> str:
    """Merge prior flow with an extension (full rewrite or delta commands).

    If ``extension_yaml`` looks like a complete flow (has appId / ---), prefer it
    when it already contains prior commands; otherwise append extension body
    commands after the prior prefix (minus stopApp).
    """
    from mobiflow.maestro import ensure_flow_yaml, ensure_stop_app, looks_like_maestro_yaml

    prior = (prior_yaml or "").strip()
    ext = (extension_yaml or "").strip()
    if not prior:
        return ensure_stop_app(ensure_flow_yaml(ext, app_id))
    if not ext:
        return ensure_stop_app(prior)

    # If extension is a full flow and substantially longer / includes launchApp,
    # trust the LLM rewrite (extend prompt asks for complete YAML).
    if looks_like_maestro_yaml(ext) and (
        "launchApp" in ext or len(ext) >= max(80, int(len(prior) * 0.6))
    ):
        return ensure_stop_app(ensure_flow_yaml(ext, app_id))

    # Treat extension as command delta
    body = ext
    if "---" in body:
        body = body.split("---", 1)[-1]
    body = body.strip()
    # Drop leading launchApp from delta (already in prior)
    body_lines = [
        ln
        for ln in body.splitlines()
        if not re.match(r"^\s*-\s*launchApp\b", ln)
    ]
    delta = "\n".join(body_lines).strip()
    prefix = strip_trailing_stop_app(prior).rstrip()
    merged = prefix + "\n" + delta + "\n" if delta else prefix + "\n"
    return ensure_stop_app(merged)

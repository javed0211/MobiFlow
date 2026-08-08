"""Plain-text mobile test cases."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

EXAMPLE_CASE = """\
# Intent-style mobile case — copy to make new ones
appId: org.wikipedia
platform: android
task: Open the Wikipedia app, dismiss any onboarding, and confirm Search is visible
# device: emulator-5554
"""


@dataclass
class TestCase:
    name: str
    task: str
    app_id: str = ""
    platform: str = "android"
    device_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    source_path: Optional[Path] = None

    def explore_task(self) -> str:
        if self.steps:
            numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(self.steps, 1))
            return f"{self.task.strip()}\n\nGuided steps:\n{numbered}".strip()
        return self.task.strip()


_META_RE = re.compile(
    r"^(appId|app_id|platform|device|device_id|task|goal)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"^@(\w+)\s*$")
_STEP_RE = re.compile(r"^\d+\.\s+(.+)$")


def parse_case_text(text: str, *, name: str = "case") -> TestCase:
    app_id = ""
    platform = "android"
    device_id = None
    task_parts: list[str] = []
    tags: list[str] = []
    steps: list[str] = []
    in_task = False

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tag_m = _TAG_RE.match(stripped)
        if tag_m:
            tags.append(tag_m.group(1))
            continue
        meta_m = _META_RE.match(stripped)
        if meta_m:
            key = meta_m.group(1).lower().replace("_", "")
            val = meta_m.group(2).strip()
            if key in ("appid",):
                app_id = val
            elif key == "platform":
                platform = val.lower()
            elif key in ("device", "deviceid"):
                device_id = val
            elif key in ("task", "goal"):
                task_parts = [val]
                in_task = True
            continue
        step_m = _STEP_RE.match(stripped)
        if step_m:
            steps.append(step_m.group(1).strip())
            in_task = False
            continue
        if in_task:
            task_parts.append(stripped)
        elif not task_parts and not steps:
            # bare paragraph = task
            task_parts.append(stripped)
            in_task = True

    task = " ".join(task_parts).strip() or "\n".join(steps).strip()
    if not task:
        raise ValueError("Case needs a task: line or numbered steps.")
    return TestCase(
        name=name,
        task=task,
        app_id=app_id,
        platform=platform,
        device_id=device_id,
        tags=tags,
        steps=steps,
    )


def load_case(path: Path | str) -> TestCase:
    p = Path(path).expanduser().resolve()
    text = p.read_text(encoding="utf-8")
    case = parse_case_text(text, name=p.stem)
    case.source_path = p
    return case

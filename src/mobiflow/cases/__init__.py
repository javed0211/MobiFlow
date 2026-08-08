"""Plain-text mobile test cases."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

EXAMPLE_CASE = """\
# Intent-style mobile case — copy to make new ones
@smoke
appId: org.wikipedia
platform: android
task: Open the Wikipedia app, dismiss any onboarding, and confirm Search is visible
# device: emulator-5554
# flow: flows/example.yaml
# clearState: false
"""


@dataclass
class TestCase:
    name: str
    task: str
    app_id: str = ""
    platform: str = "android"
    device_id: str | None = None
    tags: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    flow: str = ""  # optional frozen Maestro YAML path
    clear_state: bool = False
    env: dict[str, str] = field(default_factory=dict)
    expect: list[str] = field(default_factory=list)  # forced assertVisible texts
    source_path: Path | None = None

    def explore_task(self) -> str:
        if self.steps:
            numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(self.steps, 1))
            return f"{self.task.strip()}\n\nGuided steps:\n{numbered}".strip()
        return self.task.strip()

    def has_tag(self, tag: str) -> bool:
        want = tag.strip().lstrip("@").lower()
        return any(t.lower() == want for t in self.tags)


_META_RE = re.compile(
    r"^(appId|app_id|platform|device|device_id|task|goal|flow|clearState|clear_state|"
    r"env|expect)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"^@(\w+)\s*$")
_STEP_RE = re.compile(r"^\d+\.\s+(.+)$")
_ENV_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def _parse_bool(val: str) -> bool:
    return val.strip().lower() in {"1", "true", "yes", "on", "y"}


def parse_case_text(text: str, *, name: str = "case") -> TestCase:
    app_id = ""
    platform = "android"
    device_id = None
    task_parts: list[str] = []
    tags: list[str] = []
    steps: list[str] = []
    flow = ""
    clear_state = False
    env: dict[str, str] = {}
    expect: list[str] = []
    in_task = False
    in_env = False
    in_expect = False

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tag_m = _TAG_RE.match(stripped)
        if tag_m:
            tags.append(tag_m.group(1))
            in_env = False
            in_expect = False
            continue
        meta_m = _META_RE.match(stripped)
        if meta_m:
            key = meta_m.group(1).lower().replace("_", "")
            val = meta_m.group(2).strip()
            in_env = False
            in_expect = False
            if key in ("appid",):
                app_id = val
            elif key == "platform":
                platform = val.lower()
            elif key in ("device", "deviceid"):
                device_id = val
            elif key in ("task", "goal"):
                task_parts = [val]
                in_task = True
            elif key == "flow":
                flow = val
            elif key in ("clearstate",):
                clear_state = _parse_bool(val)
            elif key == "env":
                in_env = True
                in_task = False
                # inline KEY=VALUE on same line
                if val and val not in {"|", ">"}:
                    em = _ENV_LINE_RE.match(val)
                    if em:
                        env[em.group(1)] = em.group(2).strip().strip("\"'")
            elif key == "expect":
                in_expect = True
                in_task = False
                if val and val not in {"|", ">"}:
                    expect.append(val.strip().strip("\"'"))
            continue
        if in_env:
            em = _ENV_LINE_RE.match(stripped)
            if em:
                env[em.group(1)] = em.group(2).strip().strip("\"'")
                continue
            in_env = False
        if in_expect:
            step_m = _STEP_RE.match(stripped)
            if step_m:
                expect.append(step_m.group(1).strip())
                continue
            if stripped.startswith("-"):
                expect.append(stripped.lstrip("-").strip().strip("\"'"))
                continue
            # bare line under expect
            if not _META_RE.match(stripped) and not _TAG_RE.match(stripped):
                expect.append(stripped.strip("\"'"))
                continue
        step_m = _STEP_RE.match(stripped)
        if step_m:
            steps.append(step_m.group(1).strip())
            in_task = False
            in_env = False
            in_expect = False
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
        flow=flow,
        clear_state=clear_state,
        env=env,
        expect=expect,
    )


def load_case(path: Path | str) -> TestCase:
    p = Path(path).expanduser().resolve()
    text = p.read_text(encoding="utf-8")
    case = parse_case_text(text, name=p.stem)
    case.source_path = p
    return case


def discover_cases(
    root: Path | str,
    *,
    tags: list[str] | None = None,
    recursive: bool = True,
) -> list[TestCase]:
    """Load ``*.txt`` cases under ``root`` (file or directory), optionally filtered by tags."""
    path = Path(root).expanduser().resolve()
    files: list[Path]
    if path.is_file():
        files = [path]
    elif path.is_dir():
        pattern = "**/*.txt" if recursive else "*.txt"
        files = sorted(p for p in path.glob(pattern) if p.is_file())
    else:
        raise FileNotFoundError(f"Case path not found: {path}")

    cases: list[TestCase] = []
    for fp in files:
        if fp.name.startswith("."):
            continue
        cases.append(load_case(fp))

    if tags:
        wanted = {t.strip().lstrip("@").lower() for t in tags if t and t.strip()}
        if wanted:
            cases = [c for c in cases if any(c.has_tag(t) for t in wanted)]
    return cases

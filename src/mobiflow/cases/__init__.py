"""Plain-text mobile test cases.

Canonical template (see ``EXAMPLE_CASE``)::

    @smoke
    appId: org.wikipedia
    platform: android
    # Run knobs (optional — CLI overrides these; these override config)
    codegen: true
    retries: 0
    heal: 2
    task: |
      1. …
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXAMPLE_CASE = """\
# MobiFlow case template — copy to cases/<name>.txt and edit.
# Precedence for run knobs: CLI flags > this file > mobiflow.config.yaml
#
# Required: task (or numbered steps). Recommended: appId, platform.
# Numbered steps enable --incremental / incremental: true gap-explore.

@smoke
appId: org.wikipedia
platform: android
# device: emulator-5554
# flow: flows/example.yaml
# clearState: false

# --- Run options (all optional) ---
codegen: true            # false → reuse frozen flows/<case>.yaml (no LLM)
# reuseFlow: false       # alias of codegen: false when true
# incremental: false     # gap-explore only newly appended numbered steps
# extendExplore: false   # full explore + extend codegen from prior YAML
retries: 0               # re-run same YAML before heal
heal: 2                  # YAML repair attempts (0 = off)
explore: true            # discovery LLM before codegen
# exploreSteps: 5
# genOnly: false         # author YAML only (skip device)
# adaptive: true
# timeout: 180

# env:
#   USERNAME = MY_USER
data: data/example.json   # relative to case dir or repo; also absolute OK
# expect:
#   - Search

task: |
  Open the Wikipedia app, dismiss any onboarding, and confirm Search is visible.
  Use test data via Maestro ${SEARCH_QUERY} / ${ARTICLE_HINT} / ${USER_NAME}.

  1. Launch the app
  2. Dismiss onboarding if shown
  3. Confirm Search is visible
  4. Tap Search and type ${SEARCH_QUERY}
"""

# Canonical meta keys → attribute / CaseRunOptions field
_META_ALIASES: dict[str, str] = {
    "appid": "app_id",
    "platform": "platform",
    "device": "device_id",
    "deviceid": "device_id",
    "task": "task",
    "goal": "task",
    "flow": "flow",
    "clearstate": "clear_state",
    "env": "env",
    "expect": "expect",
    "data": "data_path",
    "datapath": "data_path",
    "datafile": "data_path",
    "testdata": "data_path",
    # Run knobs
    "codegen": "codegen",
    "reuse": "reuse_flow",
    "reuseflow": "reuse_flow",
    "incremental": "incremental",
    "extendexplore": "extend_explore",
    "retries": "retries",
    "retry": "retries",
    "heal": "heal",
    "noheal": "no_heal",
    "explore": "explore",
    "exploresteps": "explore_steps",
    "genonly": "gen_only",
    "adaptive": "adaptive",
    "timeout": "timeout_s",
    "timeouts": "timeout_s",
    "strict": "strict",
}

_KNOWN_META_DISPLAY = sorted(
    {
        "appId",
        "platform",
        "device",
        "task",
        "goal",
        "flow",
        "clearState",
        "env",
        "expect",
        "data",
        "codegen",
        "reuseFlow",
        "incremental",
        "extendExplore",
        "retries",
        "heal",
        "noHeal",
        "explore",
        "exploreSteps",
        "genOnly",
        "adaptive",
        "timeout",
        "strict",
    }
)


@dataclass
class CaseRunOptions:
    """Optional per-case run overrides (None = inherit from CLI/config)."""

    codegen: bool | None = None
    reuse_flow: bool | None = None
    incremental: bool | None = None
    extend_explore: bool | None = None
    retries: int | None = None
    heal: int | None = None
    no_heal: bool | None = None
    explore: bool | None = None
    explore_steps: int | None = None
    gen_only: bool | None = None
    adaptive: bool | None = None
    timeout_s: int | None = None
    strict: bool = False


@dataclass
class ResolvedRunOptions:
    """Effective run settings after CLI > case > config merge."""

    gen_only: bool
    reuse_flow: bool
    incremental: bool
    extend_explore: bool
    heal: int
    retries: int
    explore: bool
    explore_steps: int
    adaptive: bool
    timeout_s: int | None
    sources: dict[str, str] = field(default_factory=dict)


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
    data_path: str = ""  # relative or absolute path to JSON/YAML/.env
    run: CaseRunOptions = field(default_factory=CaseRunOptions)
    parse_warnings: list[str] = field(default_factory=list)
    source_path: Path | None = None

    def explore_task(self, *, data_block: str = "") -> str:
        parts: list[str] = []
        if self.steps:
            numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(self.steps, 1))
            parts.append(
                f"{self.task.strip()}\n\nGuided steps:\n{numbered}".strip()
            )
        else:
            parts.append(self.task.strip())
        if data_block.strip():
            parts.append(data_block.strip())
        return "\n\n".join(parts)

    def guidance_steps(self) -> list[str]:
        """Numbered guidance used for incremental classify (steps field or task body)."""
        from mobiflow.incremental import extract_numbered_steps, normalize_guidance

        if self.steps:
            return normalize_guidance(self.steps)
        return extract_numbered_steps(self.task)

    def has_tag(self, tag: str) -> bool:
        want = tag.strip().lstrip("@").lower()
        return any(t.lower() == want for t in self.tags)

    def load_data(
        self,
        *,
        repo: Path | str | None = None,
    ) -> tuple[Path | None, dict[str, Any], dict[str, str]]:
        """Resolve ``data:`` path and load flattened env map.

        Returns ``(resolved_path, raw_dict, flat_env)``. Empty when no data set.
        """
        from mobiflow.casedata import load_data_file, resolve_data_path

        if not (self.data_path or "").strip():
            return None, {}, {}
        path = resolve_data_path(
            self.data_path,
            case_path=self.source_path,
            repo=Path(repo).resolve() if repo else None,
        )
        raw, flat = load_data_file(path)
        flat = dict(flat)
        flat.setdefault("DATA_PATH", str(path))
        return path, raw, flat



_META_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
_TAG_RE = re.compile(r"^@(\w+)\s*$")
_STEP_RE = re.compile(r"^\d+\.\s+(.+)$")
_ENV_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_LOOSE_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:")


def _parse_bool(val: str) -> bool:
    return val.strip().lower() in {"1", "true", "yes", "on", "y"}


def _strip_inline_comment(val: str) -> str:
    """Drop trailing ``# comment`` from meta values (not inside quotes)."""
    s = val.strip()
    if not s or s.startswith("#"):
        return s
    in_single = False
    in_double = False
    for i, ch in enumerate(s):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or s[i - 1].isspace():
                return s[:i].rstrip()
    return s



def _parse_optional_bool(val: str) -> bool | None:
    s = val.strip().lower()
    if s in {"", "-", "null", "none", "default", "inherit"}:
        return None
    if s in {"1", "true", "yes", "on", "y"}:
        return True
    if s in {"0", "false", "no", "off", "n"}:
        return False
    raise ValueError(f"Expected boolean, got {val!r}")


def _parse_optional_int(val: str, *, lo: int, hi: int) -> int | None:
    s = val.strip().lower()
    if s in {"", "-", "null", "none", "default", "inherit"}:
        return None
    n = int(s)
    return max(lo, min(hi, n))


def _normalize_meta_key(raw: str) -> str | None:
    key = raw.strip().lower().replace("-", "").replace("_", "")
    return _META_ALIASES.get(key)


def _pick(
    cli: Any,
    case_val: Any,
    config_val: Any,
    *,
    name: str,
    sources: dict[str, str],
) -> Any:
    if cli is not None:
        sources[name] = "cli"
        return cli
    if case_val is not None:
        sources[name] = "case"
        return case_val
    sources[name] = "config"
    return config_val


def resolve_run_options(
    case: TestCase,
    cfg: Any,
    *,
    gen_only: bool = False,
    no_heal: bool = False,
    reuse_flow: bool | None = None,
    incremental: bool | None = None,
    extend_explore: bool | None = None,
) -> ResolvedRunOptions:
    """Merge CLI > case > ``cfg.run`` into effective options.

    ``codegen: false`` on the case implies ``reuse_flow`` unless the case also
    sets ``reuseFlow`` / incremental / extendExplore explicitly.
    """
    run = case.run
    sources: dict[str, str] = {}

    # Derive case-level reuse from codegen when reuseFlow omitted
    case_reuse = run.reuse_flow
    if case_reuse is None and run.codegen is not None:
        case_reuse = not run.codegen
        sources["reuse_flow"] = "case(codegen)"

    case_heal = run.heal
    if case_heal is None and run.no_heal is True:
        case_heal = 0

    # CLI gen_only / no_heal are flags (False means unset)
    cli_gen = True if gen_only else None
    effective_gen = bool(
        _pick(cli_gen, run.gen_only, False, name="gen_only", sources=sources)
    )

    effective_reuse = bool(
        _pick(
            reuse_flow,
            case_reuse,
            bool(getattr(cfg.run, "reuse_flow", False)),
            name="reuse_flow",
            sources=sources,
        )
    )
    effective_incr = bool(
        _pick(
            incremental,
            run.incremental,
            bool(getattr(cfg.run, "incremental", False)),
            name="incremental",
            sources=sources,
        )
    )
    effective_extend = bool(
        _pick(
            extend_explore,
            run.extend_explore,
            bool(getattr(cfg.run, "extend_explore", False)),
            name="extend_explore",
            sources=sources,
        )
    )

    # codegen:true with reuse still unset → force off reuse when only codegen said true
    if (
        reuse_flow is None
        and run.codegen is True
        and run.reuse_flow is None
        and sources.get("reuse_flow") == "case(codegen)"
    ):
        effective_reuse = False

    exclusive = sum(
        bool(x) for x in (effective_reuse, effective_incr, effective_extend)
    )
    if exclusive > 1:
        raise ValueError(
            "Use only one of reuseFlow / incremental / extendExplore "
            "(case file or CLI). Conflict: "
            f"reuse={effective_reuse} incremental={effective_incr} "
            f"extendExplore={effective_extend}"
        )

    cli_heal: int | None = 0 if no_heal else None
    effective_heal = int(
        _pick(
            cli_heal,
            case_heal,
            int(getattr(cfg.run, "heal", 2)),
            name="heal",
            sources=sources,
        )
    )
    if effective_gen:
        effective_heal = 0

    effective_retries = int(
        _pick(
            None,  # no CLI flag today for retries on single run (suite uses config)
            run.retries,
            int(getattr(cfg.run, "retries", 0)),
            name="retries",
            sources=sources,
        )
    )
    effective_explore = bool(
        _pick(
            None,
            run.explore,
            bool(getattr(cfg.run, "explore", True)),
            name="explore",
            sources=sources,
        )
    )
    effective_explore_steps = int(
        _pick(
            None,
            run.explore_steps,
            int(getattr(cfg.run, "explore_steps", 5)),
            name="explore_steps",
            sources=sources,
        )
    )
    effective_adaptive = bool(
        _pick(
            None,
            run.adaptive,
            bool(getattr(cfg.run, "adaptive", True)),
            name="adaptive",
            sources=sources,
        )
    )
    timeout_s = _pick(
        None,
        run.timeout_s,
        None,
        name="timeout_s",
        sources=sources,
    )

    return ResolvedRunOptions(
        gen_only=effective_gen,
        reuse_flow=effective_reuse,
        incremental=effective_incr,
        extend_explore=effective_extend,
        heal=max(0, int(effective_heal)),
        retries=max(0, min(int(effective_retries), 10)),
        explore=effective_explore,
        explore_steps=max(1, min(int(effective_explore_steps), 12)),
        adaptive=effective_adaptive,
        timeout_s=int(timeout_s) if timeout_s is not None else None,
        sources=sources,
    )


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
    data_path = ""
    run = CaseRunOptions()
    warnings: list[str] = []
    in_task = False
    in_env = False
    in_expect = False
    strict = False

    def _apply_run(field: str, raw_val: str) -> None:
        nonlocal strict
        try:
            if field == "codegen":
                run.codegen = _parse_optional_bool(raw_val)
            elif field == "reuse_flow":
                run.reuse_flow = _parse_optional_bool(raw_val)
            elif field == "incremental":
                run.incremental = _parse_optional_bool(raw_val)
            elif field == "extend_explore":
                run.extend_explore = _parse_optional_bool(raw_val)
            elif field == "retries":
                run.retries = _parse_optional_int(raw_val, lo=0, hi=10)
            elif field == "heal":
                run.heal = _parse_optional_int(raw_val, lo=0, hi=20)
            elif field == "no_heal":
                run.no_heal = _parse_optional_bool(raw_val)
            elif field == "explore":
                run.explore = _parse_optional_bool(raw_val)
            elif field == "explore_steps":
                run.explore_steps = _parse_optional_int(raw_val, lo=1, hi=12)
            elif field == "gen_only":
                run.gen_only = _parse_optional_bool(raw_val)
            elif field == "adaptive":
                run.adaptive = _parse_optional_bool(raw_val)
            elif field == "timeout_s":
                run.timeout_s = _parse_optional_int(raw_val, lo=30, hi=7200)
            elif field == "strict":
                strict = bool(_parse_optional_bool(raw_val))
                run.strict = strict
        except ValueError as exc:
            raise ValueError(f"Invalid {field}: {exc}") from exc

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
            raw_key = meta_m.group(1)
            val = _strip_inline_comment(meta_m.group(2).strip())
            field = _normalize_meta_key(raw_key)
            if field is None:
                msg = (
                    f"Unknown case key '{raw_key}'. "
                    f"Known keys: {', '.join(_KNOWN_META_DISPLAY)}"
                )
                if strict or run.strict:
                    raise ValueError(msg)
                warnings.append(msg)
                # Do not fold unknown keys into the task
                continue

            in_env = False
            in_expect = False
            if field == "app_id":
                app_id = val
                in_task = False
            elif field == "platform":
                platform = val.lower()
                in_task = False
            elif field == "device_id":
                device_id = val
                in_task = False
            elif field == "task":
                task_parts = [val]
                in_task = True
                sm = _STEP_RE.match(val)
                if sm:
                    steps.append(sm.group(1).strip())
                    task_parts = [val]
            elif field == "flow":
                flow = val
                in_task = False
            elif field == "data_path":
                data_path = val.strip().strip("\"'")
                in_task = False
            elif field == "clear_state":
                clear_state = _parse_bool(val)
                in_task = False
            elif field == "env":
                in_env = True
                in_task = False
                if val and val not in {"|", ">"}:
                    em = _ENV_LINE_RE.match(val)
                    if em:
                        env[em.group(1)] = em.group(2).strip().strip("\"'")
            elif field == "expect":
                in_expect = True
                in_task = False
                if val and val not in {"|", ">"}:
                    expect.append(val.strip().strip("\"'"))
            else:
                # run knobs
                _apply_run(field, val)
                in_task = False
            continue

        # Bare "MaybeKey: …" that didn't match? already handled.
        # Unknown key-looking lines outside meta: warn if looks like key
        if not in_task and not in_env and not in_expect:
            loose = _LOOSE_KEY_RE.match(stripped)
            if loose and _normalize_meta_key(loose.group(1)) is None:
                msg = f"Unknown case key '{loose.group(1)}' (ignored)"
                if strict or run.strict:
                    raise ValueError(msg)
                warnings.append(msg)
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
            if not _META_RE.match(stripped) and not _TAG_RE.match(stripped):
                expect.append(stripped.strip("\"'"))
                continue
        step_m = _STEP_RE.match(stripped)
        if step_m:
            steps.append(step_m.group(1).strip())
            if in_task:
                task_parts.append(stripped)
            else:
                in_env = False
                in_expect = False
            continue
        if in_task:
            task_parts.append(stripped)
        elif not task_parts and not steps:
            # bare paragraph = task
            task_parts.append(stripped)
            in_task = True

    # Prefer preserving multiline task text for NL goals
    task = "\n".join(task_parts).strip() or "\n".join(steps).strip()
    if task in {"|", ">"}:
        task = "\n".join(steps).strip()
    # Drop YAML block markers left in task
    if task.startswith("|") or task.startswith(">"):
        task = task.lstrip("|>").strip()
    if not task:
        raise ValueError("Case needs a task: line or numbered steps.")
    # If numbered steps only appeared inside the task body, keep them on the case
    if not steps:
        from mobiflow.incremental import extract_numbered_steps

        steps = extract_numbered_steps(task)

    # Soft conflict check on case alone
    case_reuse = run.reuse_flow
    if case_reuse is None and run.codegen is False:
        case_reuse = True
    modes = [
        m
        for m, on in (
            ("reuseFlow", case_reuse),
            ("incremental", run.incremental),
            ("extendExplore", run.extend_explore),
        )
        if on
    ]
    if len(modes) > 1:
        raise ValueError(
            "Case sets multiple exclusive modes: " + ", ".join(modes)
        )

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
        data_path=data_path,
        run=run,
        parse_warnings=warnings,
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

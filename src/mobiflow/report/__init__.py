"""Rich execution report packs (Vite/React SPA + JSON inject)."""

from __future__ import annotations

import json
import platform
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from mobiflow.reporting import ReportCase


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0

    def merged(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost=self.cost + other.cost,
        )


@dataclass
class StepRecord:
    index: int
    action: str
    status: str  # pass | fail | skipped | info
    raw: str = ""
    detail: str = ""
    duration_ms: int = 0
    screenshot: str | None = None
    url: str | None = None
    value: str | None = None
    locator: str | None = None


@dataclass
class PhaseStatus:
    name: str
    status: str  # success | failed | skipped | not_run
    detail: str = ""
    duration_ms: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass
class CaseRecord:
    id: str
    name: str
    status: str  # passed | failed | skipped | error
    mode: str  # ai | scripted
    url: str = ""
    tags: list[str] = field(default_factory=list)
    title: str | None = None
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str = field(default_factory=utc_now_iso)
    duration_ms: int = 0
    phases: list[PhaseStatus] = field(default_factory=list)
    steps: list[StepRecord] = field(default_factory=list)
    explore_usage: TokenUsage = field(default_factory=TokenUsage)
    codegen_usage: TokenUsage = field(default_factory=TokenUsage)
    files_generated: list[str] = field(default_factory=list)
    heal_attempts: int = 0
    failure_output: str = ""
    errors: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    source_case: str | None = None
    prompt: str | None = None

    @property
    def total_usage(self) -> TokenUsage:
        return self.explore_usage.merged(self.codegen_usage)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_usage"] = asdict(self.total_usage)
        return data


@dataclass
class EnvInfo:
    generated_at: str = field(default_factory=utc_now_iso)
    python: str = ""
    platform: str = ""  # host OS
    mobiflow_version: str = ""
    maestro: str = ""
    llm_provider: str = ""
    stack_tool: str = "maestro"
    stack_language: str = ""
    stack_runner: str = "maestro"
    repo_path: str = ""
    # Mobile target
    device: str = ""
    app_id: str = ""
    mobile_platform: str = ""
    device_provider: str = ""
    # Legacy aliases (older SPA / packs)
    browser: str = ""  # → device
    url: str = ""  # → app_id
    playwright: str = ""
    explore_model: str = ""
    codegen_model: str = ""
    headless: bool = False
    azure_endpoint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Prefer explicit mobile fields; keep aliases populated for older UIs
        device = self.device or self.browser
        app_id = self.app_id or self.url
        data["device"] = device
        data["app_id"] = app_id
        data["browser"] = device
        data["url"] = app_id
        # Drop browser-automation noise from packs unless set
        for key in ("playwright", "explore_model", "codegen_model", "azure_endpoint"):
            if not data.get(key):
                data.pop(key, None)
        if not data.get("headless"):
            data.pop("headless", None)
        return data


@dataclass
class PackSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error: int = 0
    duration_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    pass_rate: float = 0.0


@dataclass
class TrendPoint:
    label: str
    pass_rate: float
    duration_ms: int
    cost: float
    total: int
    passed: int
    failed: int
    at: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class Insight:
    severity: str
    title: str
    body: str


@dataclass
class ReportPack:
    id: str
    title: str
    generated_at: str
    env: EnvInfo
    summary: PackSummary
    cases: list[CaseRecord] = field(default_factory=list)
    trends: list[TrendPoint] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "generated_at": self.generated_at,
            "env": self.env.to_dict(),
            "summary": asdict(self.summary),
            "cases": [c.to_dict() for c in self.cases],
            "trends": [asdict(t) for t in self.trends],
            "insights": [asdict(i) for i in self.insights],
        }


_PLACEHOLDER_RE = re.compile(
    r"<script>\s*window\.__MOBIFLOW_REPORT__\s*=\s*window\.__MOBIFLOW_REPORT__\s*\|\|\s*null\s*;\s*</script>",
    re.MULTILINE,
)


def _load_template() -> str:
    try:
        root = resources.files("mobiflow.report")
        static = root.joinpath("static", "index.html")
        if static.is_file():
            return static.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    fallback = Path(__file__).resolve().parent / "static" / "index.html"
    if fallback.is_file():
        return fallback.read_text(encoding="utf-8")
    raise FileNotFoundError(
        "Report UI bundle missing. Build it with: "
        "cd report-ui && npm install && npm run build"
    )


def render_html(pack: ReportPack) -> str:
    template = _load_template()
    payload = json.dumps(pack.to_dict(), ensure_ascii=False, default=str)
    safe = payload.replace("<", "\\u003c").replace(">", "\\u003e")
    injection = f"<script>window.__MOBIFLOW_REPORT__ = {safe};</script>"
    html = _PLACEHOLDER_RE.sub("", template)
    if re.search(r"<head[^>]*>", html, flags=re.IGNORECASE):
        html = re.sub(
            r"(<head[^>]*>)",
            lambda m: f"{m.group(1)}\n    {injection}",
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        html = injection + html
    title = pack.title.replace("<", "&lt;")
    html = re.sub(
        r"<title>.*?</title>",
        f"<title>{title}</title>",
        html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html


def write_pack_html(pack: ReportPack, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(pack), encoding="utf-8")
    return out_path


def write_pack_json(pack: ReportPack, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(pack.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


def _abs_shots(case: ReportCase) -> list[str]:
    shots: list[str] = []
    base = Path(case.artifact_dir) if case.artifact_dir else None
    for rel in case.screenshot_paths or []:
        p = Path(rel)
        if not p.is_absolute() and base is not None:
            # report may store ../screenshots/x relative to report dir
            cand = (base / "screenshots" / p.name).resolve()
            if cand.is_file():
                shots.append(str(cand))
                continue
            cand2 = (base / p).resolve()
            if cand2.is_file():
                shots.append(str(cand2))
                continue
        if p.is_file():
            shots.append(str(p.resolve()))
        else:
            shots.append(str(p))
    return shots


def _token_usage_from(raw: Any) -> TokenUsage:
    if isinstance(raw, TokenUsage):
        return raw
    if not isinstance(raw, dict):
        return TokenUsage()
    return TokenUsage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        total_tokens=int(raw.get("total_tokens") or 0),
        cost=float(raw.get("cost") or 0.0),
    )


def case_record_from_report_case(
    case: ReportCase,
    *,
    app_id: str = "",
    mode: str = "ai",
    tags: list[str] | None = None,
    heal_attempts: int = 0,
    source_case: str | None = None,
) -> CaseRecord:
    status = "passed" if case.success else "failed"
    if case.synthesis_only and case.success:
        status = "passed"
    duration_ms = int(max(0.0, float(case.duration_s or 0.0)) * 1000)
    started = case.started_at or utc_now_iso()
    phases: list[PhaseStatus] = []
    if case.logs:
        phases.append(
            PhaseStatus(
                name="run",
                status="success" if case.success else "failed",
                detail=case.summary or ("passed" if case.success else "failed"),
                duration_ms=duration_ms,
            )
        )
    steps: list[StepRecord] = []
    for i, line in enumerate(case.logs or [], start=1):
        steps.append(
            StepRecord(
                index=i,
                action="log",
                status="pass" if case.success else "info",
                raw=line,
                detail=line,
            )
        )
    if not phases:
        phases.append(
            PhaseStatus(
                name="run",
                status="success" if case.success else "failed",
                detail=case.summary or ("passed" if case.success else "failed"),
                duration_ms=duration_ms,
            )
        )
    shots = _abs_shots(case)
    artifacts: dict[str, Any] = {}
    if shots:
        artifacts["screenshot"] = shots[0]
        artifacts["screenshots"] = shots
    if case.video_url:
        artifacts["video_path"] = case.video_url
    if case.artifact_dir:
        artifacts["artifact_dir"] = case.artifact_dir
    if case.flow_path:
        artifacts["flow"] = case.flow_path
    if case.provider:
        artifacts["provider"] = case.provider
    if case.device_id:
        artifacts["device_id"] = case.device_id
    if case.dashboard_url:
        artifacts["dashboard_url"] = case.dashboard_url
    if case.build_id:
        artifacts["build_id"] = case.build_id
    tag_list = list(tags or [])
    if case.provider and case.provider not in tag_list:
        tag_list.append(case.provider)
    if case.platform and case.platform not in tag_list:
        tag_list.append(case.platform)
    errors = [e for e in (case.error, case.summary) if e and not case.success]
    return CaseRecord(
        id=case.name,
        name=case.name,
        status=status,
        mode=mode,
        url=(app_id or "").strip() or (case.platform or ""),
        tags=tag_list,
        title=(case.task or case.name).split("\n", 1)[0][:160],
        started_at=started,
        finished_at=utc_now_iso(),
        duration_ms=duration_ms,
        phases=phases,
        steps=steps,
        explore_usage=_token_usage_from(case.explore_usage),
        codegen_usage=_token_usage_from(case.codegen_usage),
        files_generated=[case.flow_path] if case.flow_path else [],
        heal_attempts=max(0, int(heal_attempts)),
        failure_output=(case.stderr or case.stdout or case.error or "")[:20000],
        errors=errors,
        artifacts=artifacts,
        source_case=source_case,
        prompt=case.task or None,
    )


def build_insights(cases: list[CaseRecord], summary: PackSummary) -> list[Insight]:
    insights: list[Insight] = []
    if summary.total == 0:
        insights.append(
            Insight(
                severity="warn",
                title="No cases in pack",
                body="Run mobiflow against one or more cases, then regenerate the report.",
            )
        )
        return insights
    if summary.failed or summary.error:
        insights.append(
            Insight(
                severity="fail",
                title=f"{summary.failed + summary.error} failing case(s)",
                body="Open Failures for stderr, screenshots, and heal attempts.",
            )
        )
    else:
        insights.append(
            Insight(
                severity="pass",
                title=f"Pass rate {summary.pass_rate:.0f}%",
                body="All cases passed in this pack.",
            )
        )
    healed = [c for c in cases if c.heal_attempts > 0]
    if healed:
        insights.append(
            Insight(
                severity="warn",
                title=f"{len(healed)} case(s) needed heal/retry",
                body="Review Flaky Tests for instability signals.",
            )
        )
    return insights


def build_pack(
    cases: list[CaseRecord],
    *,
    title: str = "MobiFlow Execution Report",
    env: EnvInfo | None = None,
    pack_id: str | None = None,
) -> ReportPack:
    passed = sum(1 for c in cases if c.status == "passed")
    failed = sum(1 for c in cases if c.status == "failed")
    skipped = sum(1 for c in cases if c.status == "skipped")
    error = sum(1 for c in cases if c.status == "error")
    total = len(cases)
    duration_ms = sum(int(c.duration_ms or 0) for c in cases)
    usage = TokenUsage()
    for c in cases:
        usage = usage.merged(c.total_usage)
    pass_rate = (100.0 * passed / total) if total else 0.0
    summary = PackSummary(
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        error=error,
        duration_ms=duration_ms,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cost=usage.cost,
        pass_rate=pass_rate,
    )
    env_info = env or EnvInfo(
        python=platform.python_version(),
        platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
        stack_tool="maestro",
        stack_runner="maestro",
    )
    if not env_info.python:
        env_info.python = platform.python_version()
    pack = ReportPack(
        id=pack_id or uuid.uuid4().hex[:8],
        title=title,
        generated_at=utc_now_iso(),
        env=env_info,
        summary=summary,
        cases=list(cases),
        trends=[],
        insights=build_insights(cases, summary),
    )
    return pack


def _detect_maestro_version() -> str:
    import re
    import shutil
    import subprocess

    binary = shutil.which("maestro")
    if not binary:
        return ""
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        text = (proc.stdout or proc.stderr or "").strip()
        if not text:
            return ""
        first = text.splitlines()[0].strip()
        # Ignore JVM / install errors masquerading as version output
        if re.search(r"(?i)unable to locate|error|exception|not found", first):
            return ""
        if not re.search(r"\d+\.\d+", first):
            return ""
        return first[:120]
    except (OSError, subprocess.SubprocessError):
        return ""


def env_from_config(
    cfg: Any | None = None,
    *,
    device_label: str = "",
    app_id: str = "",
    mobile_platform: str = "",
    device_provider: str = "",
) -> EnvInfo:
    from importlib.metadata import PackageNotFoundError, version

    try:
        ver = version("mobiflow")
    except PackageNotFoundError:
        ver = "0.2.0"
    llm_provider = ""
    lang = "yaml+js"
    repo = ""
    if cfg is not None:
        try:
            repo = str(cfg.repo_path())
            lang = str(getattr(cfg.stack, "language", lang) or lang)
            try:
                prof = cfg.codegen_profile()
                llm_provider = str(getattr(prof, "provider", "") or "")
            except Exception:  # noqa: BLE001
                pass
            app_id = app_id or str(getattr(cfg.device, "app_id", "") or "")
            device_label = device_label or str(
                getattr(cfg.device, "device_id", "") or ""
            )
            mobile_platform = mobile_platform or str(
                getattr(cfg.device, "platform", "") or ""
            )
            device_provider = device_provider or str(
                getattr(cfg.device, "provider", "") or "local"
            )
        except Exception:  # noqa: BLE001
            pass
    return EnvInfo(
        python=platform.python_version(),
        platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
        mobiflow_version=ver,
        maestro=_detect_maestro_version(),
        llm_provider=llm_provider,
        stack_tool="maestro",
        stack_language=lang,
        stack_runner="maestro",
        repo_path=repo,
        device=device_label,
        app_id=app_id,
        mobile_platform=mobile_platform,
        device_provider=device_provider or "local",
        browser=device_label,
        url=app_id,
    )


def write_rich_reports(
    cases: list[ReportCase],
    report_dir: Path,
    *,
    title: str = "MobiFlow Execution Report",
    cfg: Any | None = None,
    app_id: str = "",
) -> dict[str, str]:
    """Write pack.json + SPA index.html into report_dir."""
    records = [
        case_record_from_report_case(
            c,
            app_id=app_id,
            mode="scripted" if c.synthesis_only else "ai",
        )
        for c in cases
    ]
    device = next((c.device_id for c in cases if c.device_id), "")
    mobile_platform = next((c.platform for c in cases if c.platform), "")
    device_provider = next((c.provider for c in cases if c.provider), "local")
    if not app_id:
        # Prefer real app ids over platform labels stuffed into case.url
        for rec in records:
            if rec.url and rec.url.lower() not in {"ios", "android"}:
                app_id = rec.url
                break
    pack = build_pack(
        records,
        title=title,
        env=env_from_config(
            cfg,
            device_label=device,
            app_id=app_id,
            mobile_platform=mobile_platform,
            device_provider=device_provider,
        ),
    )
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    html_path = write_pack_html(pack, report_dir / "index.html")
    json_path = write_pack_json(pack, report_dir / "pack.json")
    # Also mirror as report.html for existing links
    (report_dir / "report.html").write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"html": str(html_path), "json": str(json_path), "report": str(report_dir / "report.html")}

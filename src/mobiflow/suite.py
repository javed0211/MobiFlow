"""Suite runner: discover cases, execute sequentially, aggregate reports."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from mobiflow.cases import TestCase, discover_cases
from mobiflow.config import MobiflowConfig
from mobiflow.pipeline import run_pipeline
from mobiflow.reporting import ReportCase, write_suite_reports

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class SuiteResult:
    name: str
    cases: list[ReportCase] = field(default_factory=list)
    started_at: str = ""
    duration_s: float = 0.0
    reports: dict[str, str] = field(default_factory=dict)
    suite_dir: str = ""

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.success)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.cases if not c.success)

    @property
    def success(self) -> bool:
        return self.total > 0 and self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "success": self.success,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "duration_s": self.duration_s,
            "started_at": self.started_at,
            "suite_dir": self.suite_dir,
            "reports": self.reports,
            "cases": [
                {
                    "name": c.name,
                    "success": c.success,
                    "summary": c.summary,
                    "error": c.error,
                    "duration_s": c.duration_s,
                    "provider": c.provider,
                    "platform": c.platform,
                    "device_id": c.device_id,
                    "artifact_dir": c.artifact_dir,
                    "flow_path": c.flow_path,
                    "dashboard_url": c.dashboard_url,
                }
                for c in self.cases
            ],
        }


def _result_to_report_case(
    case: TestCase,
    result: dict[str, Any],
    *,
    provider: str,
    platform: str,
    device_id: str | None,
    duration_s: float,
    started_at: str,
) -> ReportCase:
    run_meta = result.get("run") or {}
    return ReportCase(
        name=case.name,
        success=bool(result.get("success")),
        summary=str(result.get("summary") or ""),
        error=str(result.get("error") or ""),
        task=case.explore_task(),
        platform=str(result.get("platform") or platform or ""),
        provider=str(result.get("provider") or provider),
        device_id=str(result.get("device_id") or device_id or ""),
        duration_s=float(result.get("duration_s") or duration_s),
        flow_path=str(result.get("flow_path") or ""),
        dashboard_url=str(run_meta.get("dashboard_url") or ""),
        build_id=str(run_meta.get("build_id") or ""),
        stdout=str(run_meta.get("stdout") or ""),
        stderr=str(run_meta.get("stderr") or ""),
        logs=list(result.get("logs") or []),
        synthesis_only=bool(result.get("synthesis_only")),
        screenshot_paths=list(result.get("screenshots") or []),
        artifact_dir=str(result.get("artifact_dir") or ""),
        started_at=started_at,
    )


def run_suite(
    target: Path | str,
    cfg: MobiflowConfig,
    *,
    tags: list[str] | None = None,
    gen_only: bool = False,
    device_id: str | None = None,
    no_heal: bool = False,
    fail_fast: bool | None = None,
    suite_name: str | None = None,
) -> SuiteResult:
    """Discover and run cases under ``target`` (file or directory)."""
    path = Path(target).expanduser().resolve()
    cases = discover_cases(path, tags=tags)
    name = suite_name or (path.name if path.is_dir() else path.stem)
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    stop_on_fail = cfg.run.fail_fast if fail_fast is None else fail_fast

    result = SuiteResult(name=name, started_at=started_at)
    if not cases:
        console.print(
            f"[yellow]No cases matched[/yellow] path={path} "
            f"tags={tags or '(any)'}"
        )
        return result

    console.print(
        f"[bold]Suite[/bold] {name}  cases={len(cases)}  "
        f"tags={','.join(tags) if tags else '(any)'}  "
        f"fail_fast={str(stop_on_fail).lower()}"
    )

    t0 = time.monotonic()
    provider = cfg.device.provider or "local"
    for i, case in enumerate(cases, 1):
        console.print(
            f"\n[bold cyan][{i}/{len(cases)}][/bold cyan] {case.name}"
            + (f"  @{'/'.join(case.tags)}" if case.tags else "")
        )
        case_started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        case_t0 = time.monotonic()
        try:
            case_path = case.source_path
            if case_path is None:
                raise FileNotFoundError(f"Case {case.name} has no source_path")
            raw = run_pipeline(
                case_path,
                cfg,
                gen_only=gen_only,
                device_id=device_id,
                no_heal=no_heal,
            )
        except Exception as exc:
            logger.exception("Suite case failed: %s", case.name)
            raw = {
                "success": False,
                "summary": f"suite error: {exc}",
                "error": str(exc),
                "logs": [],
            }
        case_dur = time.monotonic() - case_t0
        # Prefer paths from pipeline payload when present
        if not raw.get("flow_path") and raw.get("flow_yaml"):
            raw["flow_path"] = str(cfg.flow_dir_path() / f"{case.name}.yaml")
        report_case = _result_to_report_case(
            case,
            raw,
            provider=provider,
            platform=case.platform or cfg.device.platform,
            device_id=device_id or case.device_id or cfg.device.device_id,
            duration_s=case_dur,
            started_at=case_started,
        )
        result.cases.append(report_case)
        if stop_on_fail and not report_case.success:
            console.print("[yellow]fail_fast: stopping suite[/yellow]")
            break

    result.duration_s = time.monotonic() - t0

    suite_dir = cfg.report_dir_path() / f"suite-{name}-{stamp}"
    suite_dir.mkdir(parents=True, exist_ok=True)
    result.suite_dir = str(suite_dir)

    if cfg.run.reports:
        result.reports = write_suite_reports(
            result.cases,
            suite_dir,
            formats=cfg.run.reports,
            suite_name=name,
            started_at=started_at,
            duration_s=result.duration_s,
        )
        if result.reports.get("html"):
            console.print(f"[green]Suite HTML[/green] → {result.reports['html']}")
        if result.reports.get("junit"):
            console.print(f"[green]Suite JUnit[/green] → {result.reports['junit']}")

    summary_path = suite_dir / "suite.json"
    summary_path.write_text(
        json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    latest = cfg.report_dir_path() / "suite.latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")

    status = "OK" if result.success else "FAIL"
    color = "green" if result.success else "red"
    console.print(
        f"\n[bold {color}]Suite {status}[/bold {color}]  "
        f"{result.passed}/{result.total} passed  "
        f"({result.duration_s:.1f}s)  → {suite_dir}"
    )
    return result

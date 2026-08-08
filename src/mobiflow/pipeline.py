"""Orchestrate case → generate → run → heal → reports."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from mobiflow.cases import load_case
from mobiflow.config import MobiflowConfig
from mobiflow.maestro import run_mobile_task
from mobiflow.reporting import (
    ReportCase,
    collect_screenshots,
    index_artifacts,
    write_run_reports,
)

logger = logging.getLogger(__name__)
console = Console()


def _write_scripts(flow_dir: Path, scripts: dict[str, str]) -> list[Path]:
    written: list[Path] = []
    for rel, body in (scripts or {}).items():
        # Scripts are relative to flow dir (e.g. scripts/helpers.js)
        path = flow_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        written.append(path)
    return written


def resolve_reuse_flow_path(
    case: Any,
    cfg: MobiflowConfig,
    *,
    reuse_flow: bool | None = None,
) -> Path | None:
    """Return a frozen YAML path from case.flow or flows/<case>.yaml when enabled."""
    if case.flow:
        p = Path(case.flow).expanduser()
        if not p.is_absolute():
            p = cfg.repo_path() / p
        return p.resolve() if p.is_file() else None
    want = cfg.run.reuse_flow if reuse_flow is None else reuse_flow
    if not want:
        return None
    candidate = cfg.flow_dir_path() / f"{case.name}.yaml"
    return candidate if candidate.is_file() else None


def _load_companion_scripts(flow_path: Path, cfg: MobiflowConfig) -> dict[str, str]:
    scripts: dict[str, str] = {}
    # Prefer scripts next to the flow, then stack.scripts_dir
    for root in (flow_path.parent, cfg.scripts_dir_path(), cfg.flow_dir_path()):
        scripts_dir = root / "scripts" if (root / "scripts").is_dir() else root
        if not scripts_dir.is_dir():
            continue
        for js in scripts_dir.rglob("*.js"):
            try:
                rel = js.relative_to(flow_path.parent)
            except ValueError:
                rel = Path("scripts") / js.name
            key = str(rel).replace("\\", "/")
            if key not in scripts:
                scripts[key] = js.read_text(encoding="utf-8")
    return scripts


def run_pipeline(
    case_file: Path | str,
    cfg: MobiflowConfig,
    *,
    gen_only: bool = False,
    device_id: str | None = None,
    no_heal: bool = False,
    reuse_flow: bool | None = None,
) -> dict[str, Any]:
    case = load_case(case_file)
    flow_dir = cfg.flow_dir_path()
    flow_dir.mkdir(parents=True, exist_ok=True)

    app_id = case.app_id or cfg.device.app_id
    platform = case.platform or cfg.device.platform
    selected_device = device_id or case.device_id or cfg.device.device_id
    allow_js = cfg.stack.js_enabled()

    codegen = cfg.codegen_profile()
    discovery = cfg.discovery_profile()

    def progress(msg: str) -> None:
        console.print(f"  [dim]→[/dim] {msg}")

    console.print(f"[bold]Case[/bold] {case.name}")
    console.print(f"  task: {case.explore_task()[:200]}")
    provider = cfg.device.provider or "local"
    console.print(
        f"  provider={provider}  platform={platform}  appId={app_id or '(infer)'}  "
        f"device={selected_device or '(auto)'}"
    )
    if cfg.device.is_cloud():
        console.print(
            f"  cloud app_path={cfg.device.app_path or '-'}  "
            f"app_url={cfg.device.app_url or '-'}"
        )
    console.print(
        f"  LLM codegen={cfg.llm.codegen}  discovery={cfg.llm.discovery}  "
        f"lang={cfg.stack.language}"
    )

    reuse_path = None if gen_only else resolve_reuse_flow_path(
        case, cfg, reuse_flow=reuse_flow
    )
    reuse_yaml = None
    reuse_scripts: dict[str, str] = {}
    if reuse_path is not None:
        reuse_yaml = reuse_path.read_text(encoding="utf-8")
        reuse_scripts = _load_companion_scripts(reuse_path, cfg)
        console.print(f"  [cyan]reuse-flow[/cyan] {reuse_path}")
    elif (reuse_flow or cfg.run.reuse_flow) and not case.flow and not gen_only:
        console.print(
            f"  [yellow]reuse-flow requested but no YAML at "
            f"{cfg.flow_dir_path() / (case.name + '.yaml')} — generating[/yellow]"
        )

    from mobiflow.secrets import merge_flow_env, redact_text

    flow_env = merge_flow_env(cfg.run.env, case.env)
    if flow_env:
        console.print(f"  env keys: {', '.join(sorted(flow_env))}")

    import asyncio

    run_timeout = max(cfg.run.timeout_s, cfg.device.boot_timeout_s)
    if cfg.device.is_cloud():
        run_timeout = max(run_timeout, int(cfg.device.cloud_timeout_s or 1800))

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_artifact_dir: Path | None = None
    if cfg.run.save_artifacts and not gen_only:
        run_artifact_dir = cfg.artifacts_dir() / "runs" / f"{case.name}-{stamp}"
        run_artifact_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    result = asyncio.run(
        run_mobile_task(
            case.explore_task(),
            codegen_profile=codegen,
            discovery_profile=discovery,
            app_id=app_id,
            platform=platform,
            device_id=selected_device,
            heal=0 if (no_heal or gen_only) else cfg.run.heal,
            adaptive=cfg.run.adaptive and not gen_only,
            explore=cfg.run.explore and not gen_only and reuse_yaml is None,
            explore_steps=cfg.run.explore_steps,
            timeout_s=run_timeout,
            live=not gen_only,
            allow_js=allow_js,
            auto_start_device=cfg.device.auto_start and not gen_only and not cfg.device.is_cloud(),
            progress=progress,
            device_config=cfg.device,
            artifact_dir=run_artifact_dir,
            clear_state=bool(case.clear_state),
            preflight=list(cfg.run.preflight or []),
            app_path=cfg.device.app_path or "",
            retries=0 if gen_only else cfg.run.retries,
            reuse_flow_yaml=reuse_yaml,
            reuse_scripts=reuse_scripts or None,
            flow_env=flow_env or None,
            expect=list(case.expect or []),
        )
    )
    duration_s = time.monotonic() - t0

    flow_yaml = result.get("flow_yaml") or ""
    scripts = result.get("scripts") or {}
    out_flow = flow_dir / f"{case.name}.yaml"
    if flow_yaml:
        out_flow.write_text(flow_yaml, encoding="utf-8")
        console.print(f"[green]Wrote flow[/green] → {out_flow}")
    for sp in _write_scripts(flow_dir, scripts):
        console.print(f"[green]Wrote script[/green] → {sp}")

    run_meta = result.get("run") or {}
    reports_written: dict[str, str] = {}
    screenshot_rels: list[str] = []

    if cfg.run.save_artifacts:
        art = cfg.artifacts_dir()
        art.mkdir(parents=True, exist_ok=True)
        (art / "runs").mkdir(exist_ok=True)

        # Prefer the durable per-run dir created above
        if run_artifact_dir is None:
            run_artifact_dir = art / "runs" / f"{case.name}-{stamp}"
            run_artifact_dir.mkdir(parents=True, exist_ok=True)

        # Collect screenshots from Maestro debug/output dirs (all attempts)
        shot_paths: list[Path] = []
        for candidate in (
            run_artifact_dir,
            Path(run_meta.get("maestro_debug_dir") or ""),
            Path(run_meta.get("maestro_output_dir") or ""),
            Path(run_meta.get("artifact_dir") or ""),
        ):
            if candidate and str(candidate) not in {"", "."}:
                shot_paths.extend(collect_screenshots(candidate))
        # Dedupe while preserving order
        seen: set[str] = set()
        unique_shots: list[Path] = []
        for p in shot_paths:
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            unique_shots.append(p)

        shots_dir = run_artifact_dir / "screenshots"
        if unique_shots:
            shots_dir.mkdir(parents=True, exist_ok=True)
            for i, src in enumerate(unique_shots[:40], start=1):
                dest = shots_dir / f"{i:02d}-{src.name}"
                try:
                    if not dest.exists():
                        dest.write_bytes(src.read_bytes())
                    screenshot_rels.append(str(Path("screenshots") / dest.name))
                except OSError:
                    continue

        # Reports live under report_dir/<case>-<stamp>/ and also copied into run dir
        case_report_dir = cfg.report_dir_path() / f"{case.name}-{stamp}"
        report_case = ReportCase(
            name=case.name,
            success=bool(result.get("success")),
            summary=str(result.get("summary") or ""),
            error=str(result.get("error") or ""),
            task=case.explore_task(),
            platform=str(result.get("platform") or platform or ""),
            provider=str(result.get("provider") or provider),
            device_id=str(result.get("device_id") or selected_device or ""),
            duration_s=duration_s,
            flow_path=str(out_flow) if flow_yaml else "",
            dashboard_url=str(run_meta.get("dashboard_url") or ""),
            build_id=str(run_meta.get("build_id") or ""),
            stdout=redact_text(str(run_meta.get("stdout") or ""), flow_env),
            stderr=redact_text(str(run_meta.get("stderr") or ""), flow_env),
            logs=[redact_text(str(x), flow_env) for x in (result.get("logs") or [])],
            synthesis_only=bool(result.get("synthesis_only")),
            screenshot_paths=screenshot_rels,
            artifact_dir=str(run_artifact_dir),
            started_at=started_at,
            video_url=str(run_meta.get("video_url") or ""),
        )
        maestro_junit = None
        if run_meta.get("maestro_junit"):
            maestro_junit = Path(str(run_meta["maestro_junit"]))
        # Prefer last attempt junit inside run dir
        if maestro_junit is None:
            found = list(run_artifact_dir.rglob("maestro-junit.xml"))
            if found:
                maestro_junit = found[-1]

        if cfg.run.reports:
            # Write into run dir/report so screenshot relative paths resolve in HTML
            embedded_report_dir = run_artifact_dir / "report"
            # Fix screenshot paths relative to report dir
            report_case.screenshot_paths = [
                f"../screenshots/{Path(p).name}" for p in screenshot_rels
            ]
            reports_written = write_run_reports(
                report_case,
                embedded_report_dir,
                formats=cfg.run.reports,
                maestro_junit=maestro_junit,
            )
            # Also mirror under configured report_dir for CI convenience
            mirrored = write_run_reports(
                report_case,
                case_report_dir,
                formats=cfg.run.reports,
                maestro_junit=maestro_junit,
            )
            # Copy screenshots next to mirrored HTML so it still renders
            if screenshot_rels:
                mirror_shots = case_report_dir / "screenshots"
                mirror_shots.mkdir(parents=True, exist_ok=True)
                src_shots = run_artifact_dir / "screenshots"
                if src_shots.is_dir():
                    for img in src_shots.iterdir():
                        if img.is_file():
                            (mirror_shots / img.name).write_bytes(img.read_bytes())
            reports_written = {**mirrored, **{f"run_{k}": v for k, v in reports_written.items()}}
            if reports_written.get("html"):
                console.print(f"[green]HTML report[/green] → {reports_written['html']}")
            if reports_written.get("junit"):
                console.print(f"[green]JUnit[/green] → {reports_written['junit']}")

        inventory = index_artifacts(run_artifact_dir)
        payload = {
            "case": case.name,
            "task": case.explore_task(),
            "success": result.get("success"),
            "summary": result.get("summary"),
            "flow_path": str(out_flow),
            "scripts": list(scripts.keys()),
            "language": cfg.stack.language,
            "device_id": result.get("device_id"),
            "platform": result.get("platform"),
            "provider": result.get("provider") or provider,
            "synthesis_only": result.get("synthesis_only"),
            "logs": result.get("logs"),
            "error": result.get("error"),
            "run": result.get("run"),
            "attempts": result.get("attempts"),
            "exploration": result.get("exploration"),
            "duration_s": duration_s,
            "started_at": started_at,
            "artifact_dir": str(run_artifact_dir),
            "screenshots": screenshot_rels,
            "artifacts": inventory,
            "reports": reports_written,
        }
        run_json = run_artifact_dir / "run.json"
        run_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        # Compat: also keep flat latest pointer under .mobiflow/runs/
        latest = art / "runs" / f"{case.name}.latest.json"
        latest.write_text(run_json.read_text(encoding="utf-8"), encoding="utf-8")
        stamp_json = art / "runs" / f"{case.name}-{stamp}.json"
        stamp_json.write_text(run_json.read_text(encoding="utf-8"), encoding="utf-8")
        if flow_yaml:
            (art / "flows").mkdir(exist_ok=True)
            (art / "flows" / f"{case.name}.yaml").write_text(flow_yaml, encoding="utf-8")
            for rel, body in scripts.items():
                sp = art / "flows" / rel
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(body, encoding="utf-8")
        console.print(f"[dim]Artifacts → {run_artifact_dir}[/dim]")
        result["reports"] = reports_written
        result["artifact_dir"] = str(run_artifact_dir)
        result["screenshots"] = screenshot_rels

    result["duration_s"] = duration_s
    result["started_at"] = started_at
    result["flow_path"] = str(out_flow) if flow_yaml else str(result.get("flow_path") or "")
    result["case"] = case.name

    ok = bool(result.get("success"))
    if ok:
        console.print(f"[bold green]OK[/bold green] {result.get('summary')}")
    else:
        console.print(
            f"[bold red]FAIL[/bold red] {result.get('summary') or result.get('error')}"
        )
    return result

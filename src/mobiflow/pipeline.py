"""Orchestrate case → generate → run → heal."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from mobiflow.cases import load_case
from mobiflow.config import MobiflowConfig
from mobiflow.maestro import run_mobile_task

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


def run_pipeline(
    case_file: Path | str,
    cfg: MobiflowConfig,
    *,
    gen_only: bool = False,
    device_id: Optional[str] = None,
    no_heal: bool = False,
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

    import asyncio

    run_timeout = max(cfg.run.timeout_s, cfg.device.boot_timeout_s)
    if cfg.device.is_cloud():
        run_timeout = max(run_timeout, int(cfg.device.cloud_timeout_s or 1800))

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
            timeout_s=run_timeout,
            live=not gen_only,
            allow_js=allow_js,
            auto_start_device=cfg.device.auto_start and not gen_only and not cfg.device.is_cloud(),
            progress=progress,
            device_config=cfg.device,
        )
    )

    flow_yaml = result.get("flow_yaml") or ""
    scripts = result.get("scripts") or {}
    out_flow = flow_dir / f"{case.name}.yaml"
    if flow_yaml:
        out_flow.write_text(flow_yaml, encoding="utf-8")
        console.print(f"[green]Wrote flow[/green] → {out_flow}")
    for sp in _write_scripts(flow_dir, scripts):
        console.print(f"[green]Wrote script[/green] → {sp}")

    if cfg.run.save_artifacts:
        art = cfg.artifacts_dir()
        art.mkdir(parents=True, exist_ok=True)
        (art / "runs").mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_path = art / "runs" / f"{case.name}-{stamp}.json"
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
        }
        run_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        latest = art / "runs" / f"{case.name}.latest.json"
        latest.write_text(run_path.read_text(encoding="utf-8"), encoding="utf-8")
        if flow_yaml:
            (art / "flows").mkdir(exist_ok=True)
            (art / "flows" / f"{case.name}.yaml").write_text(flow_yaml, encoding="utf-8")
            for rel, body in scripts.items():
                sp = art / "flows" / rel
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(body, encoding="utf-8")
        console.print(f"[dim]Artifacts → {run_path}[/dim]")

    ok = bool(result.get("success"))
    if ok:
        console.print(f"[bold green]OK[/bold green] {result.get('summary')}")
    else:
        console.print(
            f"[bold red]FAIL[/bold red] {result.get('summary') or result.get('error')}"
        )
    return result

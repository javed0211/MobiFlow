"""Terminal CLI entrypoint — no UI."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click
import yaml
from pydantic import ValidationError
from rich.console import Console

from mobiflow import __version__
from mobiflow.config import (
    config_warnings,
    effective_config_dict,
    find_config,
    load_config,
)
from mobiflow.init import run_init

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")


def _load_config_or_exit(repo: str | None):
    try:
        try:
            return load_config(repo)
        except FileNotFoundError as e:
            found = find_config()
            if not found:
                console.print(f"[red]{e}[/red]")
                sys.exit(1)
            return load_config(found.parent)
    except yaml.YAMLError as e:
        console.print(f"[red]Invalid mobiflow.config.yaml:[/red] {e}")
        sys.exit(1)
    except ValidationError as e:
        console.print("[red]Invalid mobiflow.config.yaml:[/red]")
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            console.print(f"  [yellow]{loc}[/yellow]: {err['msg']}")
        sys.exit(1)


def _print_warnings(cfg) -> None:
    for w in config_warnings(cfg):
        console.print(f"[yellow]warning:[/yellow] {w}")


@click.group()
@click.version_option(__version__, prog_name="mobiflow")
@click.option("-v", "--verbose", is_flag=True, help="Debug logging")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """mobiflow — NL → Maestro mobile flows via LLM (CLI only)."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _setup_logging(verbose)


@main.command("init")
@click.option(
    "--mode",
    type=click.Choice(["existing", "local", "new"]),
    default=None,
    help="Setup mode (skip prompt)",
)
@click.option("--path", "project_path", default=None, help="Project path")
@click.option("--yes", "-y", is_flag=True, help="Non-interactive defaults")
@click.option(
    "--install-deps/--no-install-deps",
    default=None,
    help="Auto-install missing Maestro/JDK/Python packages (default: ask, or on with --yes)",
)
def init_cmd(
    mode: str | None,
    project_path: str | None,
    yes: bool,
    install_deps: bool | None,
) -> None:
    """Interactive project setup (LLM catalog, device defaults, example case)."""
    try:
        run_init(
            mode=mode,
            path=project_path,
            yes=yes,
            install_deps=install_deps,
        )
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]mobiflow init failed:[/red] {e}")
        sys.exit(1)


@main.command("setup")
@click.option("--repo", default=None, help="Project path (for Anthropic profile detection)")
@click.option(
    "--install-adb/--no-install-adb",
    default=False,
    help="Also install Android platform-tools (adb) via Homebrew",
)
@click.option(
    "--check-only",
    is_flag=True,
    help="Only report status; do not install",
)
def setup_cmd(repo: str | None, install_adb: bool, check_only: bool) -> None:
    """Detect missing packages/tools and optionally install them."""
    from mobiflow.deps import (
        catalog_wants_anthropic,
        install_missing,
        probe_dependencies,
    )

    root = Path(repo).expanduser().resolve() if repo else Path.cwd()
    want_anthropic = catalog_wants_anthropic(root)

    items = probe_dependencies(want_anthropic=want_anthropic)
    console.print("[bold]Dependency check[/bold]\n")
    for item in items:
        mark = "[green]OK[/green]" if item.ok else "[yellow]MISSING[/yellow]"
        req = "required" if item.required else "optional"
        console.print(f"  {mark}  {item.label}  [dim]({req})[/dim]")
        if not item.ok and item.detail:
            console.print(f"       [dim]{item.detail}[/dim]")

    missing_req = [i for i in items if not i.ok and i.required]
    if check_only:
        if missing_req:
            console.print(f"\n[yellow]{len(missing_req)} required dependency(ies) missing.[/yellow]")
            sys.exit(1)
        console.print("\n[green]All required dependencies available.[/green]")
        return

    installable = [i for i in items if not i.ok and i.installable]
    if not installable:
        if missing_req:
            console.print("\n[yellow]Missing items are not auto-installable — see notes above.[/yellow]")
            sys.exit(1)
        console.print("\n[green]Nothing to install.[/green]")
        return

    def _log(msg: str) -> None:
        console.print(f"[dim]{msg}[/dim]")

    console.print("\n[bold]Installing missing packages…[/bold]")
    report = install_missing(
        want_anthropic=want_anthropic,
        install_adb=install_adb,
        log=_log,
    )
    for a in report.actions:
        console.print(f"  [green]✓[/green] {a}")
    for e in report.errors:
        console.print(f"  [yellow]![/yellow] {e}")

    still = [i for i in report.items if not i.ok and i.required]
    if still:
        console.print("\n[yellow]Still missing (manual):[/yellow]")
        for i in still:
            console.print(f"  · {i.label}: {i.detail}")
        sys.exit(1)
    console.print("\n[green]Required dependencies look good.[/green]")


@main.group("config")
def config_group() -> None:
    """Show / inspect configuration."""


@config_group.command("show")
@click.option("--repo", default=None, help="Project path containing mobiflow.config.yaml")
def config_show(repo: str | None) -> None:
    cfg = _load_config_or_exit(repo)
    _print_warnings(cfg)
    console.print_json(data=effective_config_dict(cfg))


@main.group("llm")
def llm_group() -> None:
    """List / inspect models from llm.json."""


@llm_group.command("list")
@click.option("--repo", default=None, help="Project path containing llm.json")
def llm_list(repo: str | None) -> None:
    """Show catalog profiles and which ones config selects."""
    from mobiflow.llm_catalog import load_catalog

    cfg = None
    try:
        cfg = _load_config_or_exit(repo)
        root = cfg.repo_path()
    except SystemExit:
        root = Path(repo).expanduser().resolve() if repo else Path.cwd()
        cfg = None

    try:
        catalog = load_catalog(root)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from e

    console.print(
        f"[bold]llm.json[/bold] — {len(catalog.models)} profile(s) in {root / 'llm.json'}\n"
    )
    for name in catalog.names():
        entry = catalog.models[name]
        mark = ""
        if cfg:
            if cfg.llm.discovery == name:
                mark += " [cyan]discovery[/cyan]"
            if cfg.llm.codegen == name:
                mark += " [magenta]codegen[/magenta]"
        key_ok = "OK" if __import__("os").environ.get(entry.api_key_env) else "-"
        console.print(
            f"  [bold]{name}[/bold]{mark}\n"
            f"    {entry.display_name} · {entry.provider}/{entry.model}\n"
            f"    key {key_ok} ${entry.api_key_env}"
            + (f" · endpoint {entry.endpoint}" if entry.endpoint else "")
        )
    if cfg:
        console.print(
            f"\n[dim]Selected: discovery={cfg.llm.discovery}  codegen={cfg.llm.codegen}[/dim]"
        )


@main.command("status")
@click.option("--repo", default=None, help="Project path")
def status_cmd(repo: str | None) -> None:
    """Show Maestro CLI, Java, and connected / startable devices."""
    from mobiflow.maestro import get_status

    # Config optional for status
    try:
        cfg = _load_config_or_exit(repo)
        _print_warnings(cfg)
    except SystemExit:
        pass

    status = asyncio.run(get_status())
    console.print(f"[bold]Maestro[/bold]  installed={status['installed']}  "
                  f"version={status.get('version') or '-'}  ready={status['ready']}")
    console.print(f"  binary: {status.get('binary') or '-'}")
    console.print(f"  JAVA_HOME: {status.get('java_home') or '-'}")
    host = status.get("host") or {}
    console.print(
        f"  host: {host.get('os')}  adb={host.get('android_adb') or '-'}  "
        f"emulator={host.get('android_emulator') or '-'}  "
        f"ios_simctl={host.get('ios_simctl')}"
    )
    console.print(f"  {status.get('message')}")
    devices = status.get("devices") or []
    if devices:
        console.print(f"\n[bold]Online[/bold] ({len(devices)})")
        for d in devices:
            plat = (d.get("platform") or "?").replace("[", "\\[")
            console.print(
                f"  · \\[{plat}] {d.get('name')}  id={d.get('id')}  "
                f"({d.get('source')})"
            )
    startable = [t for t in (status.get("targets") or []) if t.get("startable") == "true"]
    if startable:
        console.print(f"\n[bold]Can auto-start[/bold] ({len(startable)})")
        for d in startable[:12]:
            plat = (d.get("platform") or "?").replace("[", "\\[")
            console.print(
                f"  · \\[{plat}] {d.get('name')}  id={d.get('id')}  "
                f"({d.get('source')})"
            )


@main.command("devices")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Include startable AVDs / shutdown iOS simulators",
)
@click.option(
    "--start/--no-start",
    default=False,
    help="Auto-start an emulator/simulator if none are online",
)
@click.option("--platform", default=None, help="android|ios (used with --start)")
@click.option("--id", "device_id", default=None, help="AVD name, adb serial, or iOS UDID")
@click.option("--repo", default=None, help="Project path (reads device.auto_start defaults)")
def devices_cmd(
    show_all: bool,
    start: bool,
    platform: str | None,
    device_id: str | None,
    repo: str | None,
) -> None:
    """List connected devices; optionally auto-start Android AVD or iOS Simulator."""
    from mobiflow.devices import ensure_device, host_capabilities, list_all_targets, list_connected_devices

    caps = host_capabilities()
    console.print(
        f"[dim]OS={caps['os']}  can_start_android={caps['can_start_android']}  "
        f"can_start_ios={caps['can_start_ios']}[/dim]\n"
    )

    if start:
        plat = platform
        auto = True
        boot_timeout = 120
        try:
            cfg = _load_config_or_exit(repo)
            plat = plat or cfg.device.platform
            boot_timeout = cfg.device.boot_timeout_s
            device_id = device_id or cfg.device.device_id
        except SystemExit:
            plat = plat or "android"

        def progress(msg: str) -> None:
            console.print(f"  [dim]→[/dim] {msg}")

        result = asyncio.run(
            ensure_device(
                platform_pref=plat or "android",
                device_id=device_id,
                auto_start=auto,
                timeout_s=float(boot_timeout),
                progress=progress,
            )
        )
        if result.get("ok"):
            d = result["device"]
            started = "auto-started" if result.get("started") else "already online"
            plat = (d.get("platform") or "?").replace("[", "\\[")
            console.print(
                f"[green]OK[/green] \\[{plat}] {d.get('name')}  "
                f"id={d.get('id')}  ({started})"
            )
            return
        console.print(f"[red]{result.get('message') or result.get('error')}[/red]")
        sys.exit(1)

    devices = asyncio.run(list_all_targets() if show_all else list_connected_devices())
    if not devices:
        console.print(
            "[yellow]No devices found.[/yellow]\n"
            "  • Android: install Android Studio, create an AVD, ensure emulator on PATH\n"
            "  • iOS (macOS): install Xcode, open Simulator once\n"
            "  • Then: [cyan]mobiflow devices --start[/cyan]"
        )
        return
    for d in devices:
        state = d.get("state") or ("online" if d.get("startable") != "true" else "available")
        flag = "online" if state == "online" else "startable"
        # Escape brackets — Rich treats [ios] as markup
        plat = (d.get("platform") or "?").replace("[", "\\[")
        console.print(
            f"\\[{plat}] {d.get('name')}  id={d.get('id')}  "
            f"{flag}  ({d.get('source')})"
        )


@main.command("run")
@click.argument("case_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--repo", default=None, help="Project path containing mobiflow.config.yaml")
@click.option("--device", "device_id", default=None, help="Override device id")
@click.option("--gen-only", is_flag=True, help="Author YAML only (skip device run)")
@click.option("--no-heal", is_flag=True, help="Skip YAML repair loop")
def run_cmd(
    case_file: str,
    repo: str | None,
    device_id: str | None,
    gen_only: bool,
    no_heal: bool,
) -> None:
    """Run a case: LLM → Maestro YAML → device (with optional heal)."""
    from mobiflow.pipeline import run_pipeline

    cfg = _load_config_or_exit(repo)
    _print_warnings(cfg)
    result = run_pipeline(
        case_file,
        cfg,
        gen_only=gen_only,
        device_id=device_id,
        no_heal=no_heal,
    )
    if not result.get("success"):
        sys.exit(1)


@main.command("gen")
@click.argument("goal")
@click.option("--repo", default=None, help="Project path")
@click.option("--platform", default=None, help="android|ios")
@click.option("--app-id", "app_id", default=None, help="Maestro appId")
@click.option(
    "--out",
    "out_path",
    default=None,
    type=click.Path(dir_okay=False),
    help="Write YAML to this path (JS scripts go beside it under scripts/)",
)
@click.option(
    "--js/--no-js",
    default=None,
    help="Allow Maestro JavaScript (default: from stack.language)",
)
def gen_cmd(
    goal: str,
    repo: str | None,
    platform: str | None,
    app_id: str | None,
    out_path: str | None,
    js: bool | None,
) -> None:
    """Generate Maestro YAML (+ optional JS) from a natural-language goal."""
    from mobiflow.maestro import generate_flow_bundle

    cfg = _load_config_or_exit(repo)
    _print_warnings(cfg)
    plat = platform or cfg.device.platform
    aid = app_id or cfg.device.app_id
    allow_js = cfg.stack.js_enabled() if js is None else js

    def progress(msg: str) -> None:
        console.print(f"  [dim]→[/dim] {msg}")

    bundle = asyncio.run(
        generate_flow_bundle(
            goal,
            app_id=aid,
            platform=plat,
            profile=cfg.codegen_profile(),
            allow_js=allow_js,
            progress=progress,
        )
    )
    if out_path:
        p = Path(out_path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(bundle.flow_yaml, encoding="utf-8")
        console.print(f"[green]Wrote[/green] {p}")
        for rel, body in bundle.scripts.items():
            sp = p.parent / rel
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(body, encoding="utf-8")
            console.print(f"[green]Wrote[/green] {sp}")
    else:
        console.print(bundle.flow_yaml)
        for rel, body in bundle.scripts.items():
            console.print(f"\n[bold]// {rel}[/bold]\n{body}")


@main.command("test-flow")
@click.argument("flow_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--device", "device_id", default=None, help="Device id")
@click.option("--repo", default=None, help="Project path (for timeout/config)")
def test_flow_cmd(flow_file: str, device_id: str | None, repo: str | None) -> None:
    """Run an existing Maestro YAML file on a device."""
    from mobiflow.maestro import run_flow_yaml

    cfg = None
    timeout = 180
    try:
        cfg = _load_config_or_exit(repo)
        timeout = cfg.run.timeout_s
        device_id = device_id or cfg.device.device_id
    except SystemExit:
        pass

    yaml_text = Path(flow_file).read_text(encoding="utf-8")

    def progress(msg: str) -> None:
        console.print(f"  [dim]→[/dim] {msg}")

    result = asyncio.run(
        run_flow_yaml(yaml_text, device_id=device_id, timeout_s=timeout, progress=progress)
    )
    if result.get("ok"):
        console.print("[bold green]PASSED[/bold green]")
    else:
        console.print("[bold red]FAILED[/bold red]")
        err = (result.get("stderr") or result.get("stdout") or "")[:2000]
        if err:
            console.print(err)
        sys.exit(1)

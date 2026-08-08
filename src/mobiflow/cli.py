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
    """Show Maestro CLI, Java, local devices, and cloud lab readiness."""
    from mobiflow.cloud import cloud_readiness
    from mobiflow.maestro import get_status

    cfg = None
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

    if cfg is not None:
        ready = cloud_readiness(cfg.device)
        console.print(
            f"\n[bold]Cloud[/bold]  provider={ready.get('provider')}  "
            f"ready={ready.get('ready')}"
        )
        console.print(f"  {ready.get('message')}")
        if ready.get("cloud"):
            console.print(
                f"  app_path={ready.get('app_path') or '-'}  "
                f"app_url={ready.get('app_url') or '-'}"
            )
            if ready.get("username_env"):
                console.print(
                    f"  creds: ${ready.get('username_env')} / "
                    f"${ready.get('access_key_env')}"
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
@click.argument("case_path", type=click.Path(exists=True))
@click.option("--repo", default=None, help="Project path containing mobiflow.config.yaml")
@click.option("--device", "device_id", default=None, help="Override device id")
@click.option("--gen-only", is_flag=True, help="Author YAML only (skip device run)")
@click.option("--no-heal", is_flag=True, help="Skip YAML repair loop")
@click.option(
    "--reuse-flow/--no-reuse-flow",
    default=None,
    help="Use flows/<case>.yaml (or case flow:) instead of LLM codegen",
)
@click.option(
    "--tag",
    "tags",
    multiple=True,
    help="Suite only: include cases with this @tag (repeatable)",
)
@click.option(
    "--fail-fast/--no-fail-fast",
    default=None,
    help="Suite only: stop after first failure (default: run.fail_fast)",
)
@click.option(
    "--jobs",
    default=None,
    type=int,
    help="Suite only: parallel case workers (default: run.jobs)",
)
def run_cmd(
    case_path: str,
    repo: str | None,
    device_id: str | None,
    gen_only: bool,
    no_heal: bool,
    reuse_flow: bool | None,
    tags: tuple[str, ...],
    fail_fast: bool | None,
    jobs: int | None,
) -> None:
    """Run a case file, or a directory of cases as a suite.

    Examples::

        mobiflow run cases/example.txt
        mobiflow run cases/ --tag smoke
    """
    from mobiflow.pipeline import run_pipeline
    from mobiflow.suite import run_suite

    cfg = _load_config_or_exit(repo)
    _print_warnings(cfg)
    path = Path(case_path)
    if path.is_dir():
        if jobs is not None:
            cfg.run.jobs = max(1, min(int(jobs), 32))
        suite = run_suite(
            path,
            cfg,
            tags=list(tags) or None,
            gen_only=gen_only,
            device_id=device_id,
            no_heal=no_heal,
            fail_fast=fail_fast,
            reuse_flow=reuse_flow,
        )
        if not suite.success:
            sys.exit(1)
        return

    if tags:
        console.print(
            "[yellow]--tag is ignored for a single case file "
            "(use a cases/ directory).[/yellow]"
        )
    result = run_pipeline(
        path,
        cfg,
        gen_only=gen_only,
        device_id=device_id,
        no_heal=no_heal,
        reuse_flow=reuse_flow,
    )
    if not result.get("success"):
        sys.exit(1)


@main.command("suite")
@click.argument(
    "cases_path",
    required=False,
    default=None,
    type=click.Path(exists=True),
)
@click.option("--repo", default=None, help="Project path containing mobiflow.config.yaml")
@click.option("--device", "device_id", default=None, help="Override device id")
@click.option("--gen-only", is_flag=True, help="Author YAML only (skip device run)")
@click.option("--no-heal", is_flag=True, help="Skip YAML repair loop")
@click.option(
    "--reuse-flow/--no-reuse-flow",
    default=None,
    help="Use flows/<case>.yaml instead of LLM codegen",
)
@click.option(
    "--tag",
    "tags",
    multiple=True,
    help="Include cases with this @tag (repeatable)",
)
@click.option(
    "--fail-fast/--no-fail-fast",
    default=None,
    help="Stop after first failure (default: run.fail_fast)",
)
@click.option(
    "--jobs",
    default=None,
    type=int,
    help="Parallel case workers (default: run.jobs)",
)
def suite_cmd(
    cases_path: str | None,
    repo: str | None,
    device_id: str | None,
    gen_only: bool,
    no_heal: bool,
    reuse_flow: bool | None,
    tags: tuple[str, ...],
    fail_fast: bool | None,
    jobs: int | None,
) -> None:
    """Run a suite of cases and write aggregate JUnit/HTML reports.

    Defaults to ``stack.cases_dir`` when no path is given. Equivalent to
    ``mobiflow run <dir>``.
    """
    from mobiflow.suite import run_suite

    cfg = _load_config_or_exit(repo)
    _print_warnings(cfg)
    if jobs is not None:
        cfg.run.jobs = max(1, min(int(jobs), 32))
    target = Path(cases_path) if cases_path else cfg.cases_dir_path()
    if not target.exists():
        console.print(f"[red]Cases path not found:[/red] {target}")
        sys.exit(1)
    suite = run_suite(
        target,
        cfg,
        tags=list(tags) or None,
        gen_only=gen_only,
        device_id=device_id,
        no_heal=no_heal,
        fail_fast=fail_fast,
        reuse_flow=reuse_flow,
    )
    if not suite.cases:
        sys.exit(2)
    if not suite.success:
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


@main.command("explore")
@click.argument("goal", required=False, default=None)
@click.option("--repo", default=None, help="Project path")
@click.option("--device", "device_id", default=None, help="adb serial / UDID")
@click.option("--platform", default=None, help="android|ios")
@click.option("--app-id", "app_id", default=None, help="Maestro appId")
@click.option(
    "--interactive/--auto",
    default=False,
    help="Confirm each discovery action (separate interactive session mode)",
)
@click.option("--steps", default=None, type=int, help="Max explore steps (default from config)")
@click.option(
    "--gen/--no-gen",
    default=False,
    help="After explore, run codegen and print/write YAML",
)
@click.option(
    "--out",
    "out_path",
    default=None,
    type=click.Path(dir_okay=False),
    help="With --gen, write YAML to this path",
)
@click.option("--case", "case_file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Load goal/appId/platform from a case file")
def explore_cmd(
    goal: str | None,
    repo: str | None,
    device_id: str | None,
    platform: str | None,
    app_id: str | None,
    interactive: bool,
    steps: int | None,
    gen: bool,
    out_path: str | None,
    case_file: str | None,
) -> None:
    """Explore an app with the discovery LLM (auto or interactive).

    Separate from ``mobiflow run``: does not execute the final test unless
    you pass ``--gen`` (codegen only) or use ``run`` afterward.

    Interactive mode prompts Accept / Edit / Skip / Done for each proposed
    Maestro action. It does not start Maestro Studio (see ``mobiflow studio``).
    """
    import json
    from datetime import UTC, datetime

    from mobiflow.cases import load_case
    from mobiflow.devices import ensure_device
    from mobiflow.explore import explore_app, plan_only_explore
    from mobiflow.maestro import generate_flow_bundle

    cfg = _load_config_or_exit(repo)
    _print_warnings(cfg)

    case_goal = ""
    if case_file:
        case = load_case(case_file)
        case_goal = case.explore_task()
        app_id = app_id or case.app_id or cfg.device.app_id
        platform = platform or case.platform or cfg.device.platform
        device_id = device_id or case.device_id or cfg.device.device_id
    else:
        app_id = app_id or cfg.device.app_id
        platform = platform or cfg.device.platform
        device_id = device_id or cfg.device.device_id

    goal_text = (goal or case_goal or "").strip()
    if not goal_text:
        console.print("[red]Provide a goal argument or --case file.[/red]")
        sys.exit(1)

    if cfg.device.is_cloud():
        console.print(
            "[yellow]Explore interactive/live device mode is local-only. "
            "Using plan-only explore for cloud provider.[/yellow]"
        )

    max_steps = steps if steps is not None else cfg.run.explore_steps

    def progress(msg: str) -> None:
        console.print(f"  [dim]→[/dim] {msg}")

    async def _run():
        if cfg.device.is_cloud():
            return await plan_only_explore(
                goal=goal_text,
                app_id=app_id or "",
                platform=platform or "android",
                profile=cfg.discovery_profile(),
                progress=progress,
            )

        ensured = await ensure_device(
            platform_pref=platform or "android",
            device_id=device_id,
            auto_start=cfg.device.auto_start,
            timeout_s=float(cfg.device.boot_timeout_s),
            progress=progress,
        )
        if not ensured.get("ok") or not ensured.get("device"):
            console.print(
                f"[yellow]{ensured.get('message') or 'No device'} — plan-only explore.[/yellow]"
            )
            return await plan_only_explore(
                goal=goal_text,
                app_id=app_id or "",
                platform=platform or "android",
                profile=cfg.discovery_profile(),
                progress=progress,
            )
        selected = ensured["device"].get("id") or device_id
        if interactive:
            console.print(
                "[bold]Interactive explore[/bold] — confirm each discovery action. "
                "Maestro Studio is separate: [cyan]mobiflow studio[/cyan]"
            )
        return await explore_app(
            goal_text,
            app_id=app_id or "",
            platform=platform or "android",
            device_id=str(selected),
            profile=cfg.discovery_profile(),
            max_steps=max_steps,
            progress=progress,
            interactive=interactive,
        )

    exploration = asyncio.run(_run())

    console.print(
        f"\n[bold]Exploration[/bold] mode={exploration.mode}  "
        f"completed={exploration.completed}  steps={len(exploration.steps)}"
    )
    if exploration.plan:
        console.print("[bold]Plan[/bold]")
        for i, step in enumerate(exploration.plan, 1):
            console.print(f"  {i}. {step}")
    if exploration.selectors:
        console.print("[bold]Selectors[/bold]")
        for sel in exploration.selectors[:20]:
            console.print(
                f"  · {sel.get('label') or '-'} → {sel.get('text') or '-'}"
            )

    art = cfg.artifacts_dir() / "explore"
    art.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_json = art / f"explore-{stamp}.json"
    out_json.write_text(
        json.dumps(exploration.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    console.print(f"[dim]Saved → {out_json}[/dim]")

    if not gen:
        return

    def progress_gen(msg: str) -> None:
        console.print(f"  [dim]→[/dim] {msg}")

    bundle = asyncio.run(
        generate_flow_bundle(
            goal_text,
            app_id=app_id or exploration.app_id,
            platform=platform or exploration.platform,
            profile=cfg.codegen_profile(),
            hierarchy=exploration.final_hierarchy,
            exploration=exploration.to_prompt_block(),
            allow_js=cfg.stack.js_enabled(),
            progress=progress_gen,
        )
    )
    if out_path:
        p = Path(out_path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(bundle.flow_yaml, encoding="utf-8")
        console.print(f"[green]Wrote[/green] {p}")
    else:
        console.print("\n[bold]Generated flow[/bold]\n")
        console.print(bundle.flow_yaml)


@main.command("import-flow")
@click.argument("flow_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--repo", default=None, help="Project path")
@click.option(
    "--case",
    "case_out",
    default=None,
    type=click.Path(dir_okay=False),
    help="Write case file here (default: cases/<stem>.txt)",
)
@click.option("--tag", "tags", multiple=True, help="Add @tag to the case (repeatable)")
@click.option(
    "--copy-flow/--no-copy-flow",
    default=True,
    help="Copy YAML into flows/ and set flow: meta (default: on)",
)
def import_flow_cmd(
    flow_file: str,
    repo: str | None,
    case_out: str | None,
    tags: tuple[str, ...],
    copy_flow: bool,
) -> None:
    """Turn a Maestro YAML (e.g. Studio export) into a MobiFlow case.

    The case uses paste-YAML / reuse-flow so ``mobiflow run`` executes it
    without LLM authoring.
    """
    import re

    from mobiflow.maestro import looks_like_maestro_yaml

    cfg = _load_config_or_exit(repo)
    src = Path(flow_file).expanduser().resolve()
    text = src.read_text(encoding="utf-8")
    if not looks_like_maestro_yaml(text):
        console.print("[red]File does not look like Maestro YAML.[/red]")
        sys.exit(1)

    app_id = ""
    platform = cfg.device.platform or "android"
    m = re.search(r"(?m)^appId:\s*(\S+)", text)
    if m:
        app_id = m.group(1).strip().strip("\"'")

    flow_rel = ""
    if copy_flow:
        dest = cfg.flow_dir_path() / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        try:
            flow_rel = str(dest.relative_to(cfg.repo_path()))
        except ValueError:
            flow_rel = str(dest)
        console.print(f"[green]Copied flow[/green] → {dest}")

    case_path = (
        Path(case_out).expanduser().resolve()
        if case_out
        else cfg.cases_dir_path() / f"{src.stem}.txt"
    )
    case_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Imported from Maestro YAML / Studio export", ""]
    for tag in tags:
        lines.append(f"@{tag.lstrip('@')}")
    if app_id:
        lines.append(f"appId: {app_id}")
    lines.append(f"platform: {platform}")
    if flow_rel:
        lines.append(f"flow: {flow_rel}")
    lines.append(f"task: Run imported Maestro flow {src.name}")
    # Embed YAML so paste-to-run works even without reuse-flow
    if not flow_rel:
        lines.append("")
        lines.append(text.rstrip())
    case_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]Wrote case[/green] → {case_path}")
    console.print(
        f"[dim]Run with:[/dim] mobiflow run {case_path}"
        + (" --reuse-flow" if flow_rel else "")
    )


@main.group("baseline")
def baseline_group() -> None:
    """Manage visual screenshot baselines."""


@baseline_group.command("update")
@click.argument("case_name")
@click.argument("image", type=click.Path(exists=True, dir_okay=False))
@click.option("--repo", default=None, help="Project path")
def baseline_update_cmd(case_name: str, image: str, repo: str | None) -> None:
    """Save ``image`` as the baseline PNG for ``case_name``."""
    from mobiflow.baseline import update_baseline

    cfg = _load_config_or_exit(repo)
    dest = update_baseline(case_name, Path(image), cfg.artifacts_dir())
    console.print(f"[green]Baseline updated[/green] → {dest}")


@baseline_group.command("compare")
@click.argument("case_name")
@click.argument("image", type=click.Path(exists=True, dir_okay=False))
@click.option("--repo", default=None, help="Project path")
@click.option("--threshold", default=0.02, type=float, help="Max mismatch ratio")
def baseline_compare_cmd(
    case_name: str, image: str, repo: str | None, threshold: float
) -> None:
    """Compare a screenshot to the stored baseline."""
    from mobiflow.baseline import compare_case_screenshot

    cfg = _load_config_or_exit(repo)
    result = compare_case_screenshot(
        case_name,
        Path(image),
        cfg.artifacts_dir(),
        threshold=threshold,
    )
    if result.ok:
        console.print(
            f"[green]PASS[/green] {case_name} mismatch={result.mismatch_ratio:.3%}"
        )
    else:
        console.print(
            f"[red]FAIL[/red] {case_name}: {result.message}"
            + (f"\n  diff → {result.diff_path}" if result.diff_path else "")
        )
        sys.exit(1)


@main.command("studio")
@click.option("--repo", default=None, help="Project path")
@click.option("--device", "device_id", default=None, help="adb serial / UDID")
def studio_cmd(repo: str | None, device_id: str | None) -> None:
    """Open Maestro Studio (official interactive UI) for a local device.

    This is separate from ``mobiflow explore --interactive`` (LLM-guided
    confirmations in the terminal).
    """
    import os
    import subprocess

    from mobiflow.maestro import resolve_java_home, resolve_maestro_binary

    cfg = None
    try:
        cfg = _load_config_or_exit(repo)
        device_id = device_id or cfg.device.device_id
        if cfg.device.is_cloud():
            console.print(
                "[red]Maestro Studio requires a local device "
                "(device.provider=local).[/red]"
            )
            sys.exit(1)
    except SystemExit:
        if repo:
            raise

    binary = resolve_maestro_binary()
    if not binary:
        console.print(
            "[red]Maestro CLI not found.[/red] Install: "
            "curl -Ls https://get.maestro.mobile.dev | bash"
        )
        sys.exit(1)

    args = [binary, "studio"]
    if device_id:
        args.extend(["--device", device_id])

    env = dict(os.environ)
    env.setdefault("MAESTRO_CLI_NO_ANALYTICS", "1")
    jh = resolve_java_home()
    if jh:
        env.setdefault("JAVA_HOME", jh)
    env["PATH"] = str(Path(binary).parent) + os.pathsep + env.get("PATH", "")

    console.print(f"[dim]Launching:[/dim] {' '.join(args)}")
    try:
        raise SystemExit(subprocess.call(args, env=env))
    except FileNotFoundError:
        console.print(f"[red]Failed to launch[/red] {binary}")
        sys.exit(1)


@main.command("test-flow")
@click.argument("flow_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--device", "device_id", default=None, help="Local device id or cloud device name")
@click.option("--repo", default=None, help="Project path (for timeout/config)")
def test_flow_cmd(flow_file: str, device_id: str | None, repo: str | None) -> None:
    """Run an existing Maestro YAML file on a local or cloud device."""
    import time
    from datetime import datetime, timezone

    from mobiflow.maestro import run_flow_yaml
    from mobiflow.reporting import (
        ReportCase,
        collect_screenshots,
        write_run_reports,
    )

    cfg = None
    timeout = 180
    device_config = None
    platform = None
    try:
        cfg = _load_config_or_exit(repo)
        timeout = cfg.run.timeout_s
        if cfg.device.is_cloud():
            timeout = max(timeout, int(cfg.device.cloud_timeout_s or 1800))
        device_id = device_id or cfg.device.device_id
        device_config = cfg.device
        platform = cfg.device.platform
    except SystemExit:
        pass

    yaml_text = Path(flow_file).read_text(encoding="utf-8")
    case_name = Path(flow_file).stem
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_dir = None
    if cfg is not None and cfg.run.save_artifacts:
        artifact_dir = cfg.artifacts_dir() / "runs" / f"{case_name}-{stamp}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

    def progress(msg: str) -> None:
        console.print(f"  [dim]→[/dim] {msg}")

    t0 = time.monotonic()
    result = asyncio.run(
        run_flow_yaml(
            yaml_text,
            device_id=device_id,
            timeout_s=timeout,
            progress=progress,
            device_config=device_config,
            platform=platform,
            artifact_dir=artifact_dir,
        )
    )
    duration_s = time.monotonic() - t0

    if cfg is not None and cfg.run.save_artifacts and artifact_dir is not None:
        shots_dir = artifact_dir / "screenshots"
        shot_rels: list[str] = []
        for src in collect_screenshots(artifact_dir):
            shots_dir.mkdir(parents=True, exist_ok=True)
            dest = shots_dir / src.name
            if not dest.exists():
                dest.write_bytes(src.read_bytes())
            shot_rels.append(f"../screenshots/{dest.name}")
        if cfg.run.reports:
            report_case = ReportCase(
                name=case_name,
                success=bool(result.get("ok")),
                summary="passed" if result.get("ok") else (result.get("error") or "failed"),
                error=str(result.get("error") or ""),
                platform=str(platform or ""),
                provider=str(
                    (cfg.device.provider if cfg is not None else "local") or "local"
                ),
                device_id=str(device_id or ""),
                duration_s=duration_s,
                flow_path=str(Path(flow_file).resolve()),
                dashboard_url=str(result.get("dashboard_url") or ""),
                build_id=str(result.get("build_id") or ""),
                stdout=str(result.get("stdout") or ""),
                stderr=str(result.get("stderr") or ""),
                screenshot_paths=shot_rels,
                artifact_dir=str(artifact_dir),
            )
            junit_src = (
                Path(result["maestro_junit"]) if result.get("maestro_junit") else None
            )
            write_run_reports(
                report_case,
                artifact_dir / "report",
                formats=cfg.run.reports,
                maestro_junit=junit_src,
            )
            mirror_dir = cfg.report_dir_path() / f"{case_name}-{stamp}"
            mirrored = write_run_reports(
                report_case,
                mirror_dir,
                formats=cfg.run.reports,
                maestro_junit=junit_src,
            )
            src_shots = artifact_dir / "screenshots"
            if src_shots.is_dir():
                mirror_shots = mirror_dir / "screenshots"
                mirror_shots.mkdir(parents=True, exist_ok=True)
                for img in src_shots.iterdir():
                    if img.is_file():
                        (mirror_shots / img.name).write_bytes(img.read_bytes())
            if mirrored.get("html"):
                console.print(f"[green]HTML report[/green] → {mirrored['html']}")
            if mirrored.get("junit"):
                console.print(f"[green]JUnit[/green] → {mirrored['junit']}")
            console.print(f"[dim]Artifacts → {artifact_dir}[/dim]")

    if result.get("ok"):
        console.print("[bold green]PASSED[/bold green]")
        if result.get("dashboard_url"):
            console.print(f"[dim]Dashboard:[/dim] {result['dashboard_url']}")
    else:
        console.print("[bold red]FAILED[/bold red]")
        err = (result.get("stderr") or result.get("stdout") or "")[:2000]
        if err:
            console.print(err)
        if result.get("dashboard_url"):
            console.print(f"[dim]Dashboard:[/dim] {result['dashboard_url']}")
        sys.exit(1)

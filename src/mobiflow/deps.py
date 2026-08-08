"""Detect and auto-install missing runtime packages / tools.

Installable during ``mobiflow init`` / ``mobiflow setup``:

- Python extras: ``openai``, optional ``anthropic``
- Maestro CLI (official curl installer)
- JDK via Homebrew ``openjdk`` when ``brew`` is available

Not auto-installed (reported only): Android ``adb`` / full SDK, Xcode simctl.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

PrintFn = Callable[[str], None]


@dataclass
class DepStatus:
    id: str
    label: str
    ok: bool
    detail: str = ""
    installable: bool = False
    required: bool = True


@dataclass
class SetupReport:
    items: list[DepStatus] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def missing(self) -> list[DepStatus]:
        return [i for i in self.items if not i.ok]

    @property
    def missing_installable(self) -> list[DepStatus]:
        return [i for i in self.missing if i.installable]

    @property
    def missing_manual(self) -> list[DepStatus]:
        return [i for i in self.missing if not i.installable and i.required]


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ModuleNotFoundError, ValueError, AttributeError):
        return False


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _maestro_binary() -> Optional[str]:
    from mobiflow.maestro import resolve_maestro_binary

    return resolve_maestro_binary()


def _java_home() -> Optional[str]:
    from mobiflow.maestro import resolve_java_home

    return resolve_java_home()


def _adb_binary() -> Optional[str]:
    adb = _which("adb")
    if adb:
        return adb
    for candidate in (
        Path.home() / "Library/Android/sdk/platform-tools/adb",
        Path(os.environ.get("ANDROID_HOME") or "") / "platform-tools" / "adb",
        Path(os.environ.get("ANDROID_SDK_ROOT") or "") / "platform-tools" / "adb",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def probe_dependencies(*, want_anthropic: bool = False) -> list[DepStatus]:
    """Return status for each known dependency."""
    items: list[DepStatus] = []

    # Python core (should already be present if mobiflow is installed)
    for mod, label, required in (
        ("openai", "Python package: openai", True),
        ("httpx", "Python package: httpx", True),
        ("yaml", "Python package: pyyaml", True),
        ("pydantic", "Python package: pydantic", True),
        ("click", "Python package: click", True),
        ("rich", "Python package: rich", True),
        ("questionary", "Python package: questionary", True),
    ):
        ok = _has_module(mod)
        items.append(
            DepStatus(
                id=f"py:{mod}",
                label=label,
                ok=ok,
                detail="importable" if ok else "missing — will pip install",
                installable=True,
                required=required,
            )
        )

    anth_ok = _has_module("anthropic")
    if anth_ok:
        anth_detail = "importable"
    elif want_anthropic:
        anth_detail = "missing — needed for Anthropic profiles"
    else:
        anth_detail = "optional — install if using Anthropic codegen"
    items.append(
        DepStatus(
            id="py:anthropic",
            label="Python package: anthropic",
            ok=anth_ok,
            detail=anth_detail,
            installable=True,
            required=want_anthropic,
        )
    )

    maestro = _maestro_binary()
    items.append(
        DepStatus(
            id="maestro",
            label="Maestro CLI",
            ok=bool(maestro),
            detail=maestro or "not found — install via get.maestro.mobile.dev",
            installable=True,
            required=True,
        )
    )

    jh = _java_home()
    java_bin = _which("java")
    java_ok = bool(jh or java_bin)
    items.append(
        DepStatus(
            id="java",
            label="JDK (JAVA_HOME / java)",
            ok=java_ok,
            detail=jh or java_bin or "not found — Maestro needs a JDK",
            installable=bool(_which("brew")) or platform.system() == "Darwin",
            required=True,
        )
    )

    adb = _adb_binary()
    items.append(
        DepStatus(
            id="adb",
            label="Android adb (optional)",
            ok=bool(adb),
            detail=adb or "not found — needed for Android emulators/devices",
            installable=bool(_which("brew")),
            required=False,
        )
    )

    if platform.system() == "Darwin":
        xcrun = _which("xcrun")
        items.append(
            DepStatus(
                id="xcrun",
                label="Xcode xcrun / simctl (optional)",
                ok=bool(xcrun),
                detail=xcrun or "not found — needed for iOS Simulator",
                installable=False,
                required=False,
            )
        )

    return items


def _pip_install(*packages: str, log: PrintFn) -> bool:
    if not packages:
        return True
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--prefer-binary",
        *packages,
    ]
    log(f"  $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, text=True)
    return proc.returncode == 0


def _install_maestro(*, log: PrintFn) -> bool:
    if _maestro_binary():
        return True
    if not _which("curl"):
        log("  curl not found — cannot download Maestro installer.")
        return False
    log("  Installing Maestro CLI (https://get.maestro.mobile.dev)…")
    # Official installer; non-interactive
    cmd = "curl -Ls 'https://get.maestro.mobile.dev' | bash"
    log(f"  $ {cmd}")
    proc = subprocess.run(cmd, shell=True, text=True)
    if proc.returncode != 0:
        return False
    # Ensure ~/.maestro/bin is discoverable in this process
    home_bin = Path.home() / ".maestro" / "bin"
    if home_bin.is_dir():
        os.environ["PATH"] = str(home_bin) + os.pathsep + os.environ.get("PATH", "")
    return bool(_maestro_binary())


def _install_java(*, log: PrintFn) -> bool:
    if _java_home() or _which("java"):
        return True
    brew = _which("brew")
    if not brew:
        log("  Homebrew not found — install a JDK manually, then set JAVA_HOME.")
        return False
    log("  Installing OpenJDK via Homebrew…")
    cmd = [brew, "install", "openjdk"]
    log(f"  $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, text=True)
    if proc.returncode != 0:
        return False
    # Common brew link path
    for candidate in (
        "/opt/homebrew/opt/openjdk",
        "/usr/local/opt/openjdk",
    ):
        if Path(candidate).is_dir():
            os.environ.setdefault("JAVA_HOME", candidate)
            os.environ["PATH"] = str(Path(candidate) / "bin") + os.pathsep + os.environ.get(
                "PATH", ""
            )
            break
    return bool(_java_home() or _which("java"))


def _install_adb(*, log: PrintFn) -> bool:
    if _adb_binary():
        return True
    brew = _which("brew")
    if not brew:
        log("  Homebrew not found — install Android platform-tools manually.")
        return False
    log("  Installing Android platform-tools (adb) via Homebrew…")
    cmd = [brew, "install", "android-platform-tools"]
    log(f"  $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, text=True)
    return proc.returncode == 0 and bool(_adb_binary())


def install_missing(
    *,
    want_anthropic: bool = False,
    install_adb: bool = False,
    log: Optional[PrintFn] = None,
) -> SetupReport:
    """Probe then install anything missing that we can auto-fix."""
    _log = log or (lambda m: print(m, file=sys.stderr))
    report = SetupReport(items=probe_dependencies(want_anthropic=want_anthropic))

    # Python packages
    py_missing = [
        i.id.removeprefix("py:")
        for i in report.items
        if i.id.startswith("py:") and not i.ok and i.installable
    ]
    # Map import name → pip name
    pip_map = {"yaml": "pyyaml", "anthropic": "anthropic"}
    to_pip = [pip_map.get(m, m) for m in py_missing]
    # Always ensure openai present
    if not _has_module("openai") and "openai" not in to_pip:
        to_pip.append("openai")
    if want_anthropic and not _has_module("anthropic") and "anthropic" not in to_pip:
        to_pip.append("anthropic")

    if to_pip:
        _log("Installing missing Python packages…")
        if _pip_install(*to_pip, log=_log):
            report.actions.append(f"pip install {' '.join(to_pip)}")
        else:
            report.errors.append(f"pip install failed: {' '.join(to_pip)}")

    # Maestro
    maestro_item = next((i for i in report.items if i.id == "maestro"), None)
    if maestro_item and not maestro_item.ok:
        _log("Installing Maestro CLI…")
        if _install_maestro(log=_log):
            report.actions.append("Installed Maestro CLI → ~/.maestro/bin")
        else:
            report.errors.append(
                "Maestro install failed. Manual: curl -Ls https://get.maestro.mobile.dev | bash"
            )

    # Java
    java_item = next((i for i in report.items if i.id == "java"), None)
    if java_item and not java_item.ok:
        _log("Installing JDK…")
        if _install_java(log=_log):
            report.actions.append("Installed OpenJDK (Homebrew)")
        else:
            report.errors.append(
                "JDK install failed. Install a JDK and export JAVA_HOME."
            )

    # adb (optional)
    adb_item = next((i for i in report.items if i.id == "adb"), None)
    if install_adb and adb_item and not adb_item.ok and adb_item.installable:
        _log("Installing Android platform-tools…")
        if _install_adb(log=_log):
            report.actions.append("Installed android-platform-tools (adb)")
        else:
            report.errors.append("adb install failed.")

    # Re-probe
    report.items = probe_dependencies(want_anthropic=want_anthropic)
    return report


def ensure_runtime_deps(
    *,
    auto_install: bool = True,
    want_anthropic: bool = False,
    log: Optional[PrintFn] = None,
) -> SetupReport:
    """Ensure required tools exist; optionally auto-install missing ones."""
    _log = log or (lambda m: print(m, file=sys.stderr))
    items = probe_dependencies(want_anthropic=want_anthropic)
    missing_req = [i for i in items if not i.ok and i.required]
    if not missing_req:
        return SetupReport(items=items)

    if not auto_install:
        return SetupReport(items=items)

    _log("Missing required dependencies — installing…")
    return install_missing(want_anthropic=want_anthropic, log=_log)


def catalog_wants_anthropic(repo: Path | None = None) -> bool:
    """True if config/catalog selects an Anthropic profile."""
    try:
        from mobiflow.config import find_config, load_config

        cfg_path = find_config(repo) if repo else find_config()
        if not cfg_path:
            return False
        cfg = load_config(cfg_path.parent)
        for name in (cfg.llm.discovery, cfg.llm.codegen):
            if not name:
                continue
            try:
                entry = cfg.load_catalog().get(name)
            except Exception:  # noqa: BLE001
                continue
            if entry.provider.lower() in ("anthropic", "claude"):
                return True
    except Exception:  # noqa: BLE001
        return False
    return False

"""Discover and auto-start Android emulators / iOS simulators (macOS + Windows).

- Android: ``adb`` online devices + ``emulator -list-avds``; start via emulator binary
- iOS: ``xcrun simctl`` (macOS only); boot + open Simulator.app
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

ProgressFn = Optional[Callable[[str], None]]
IS_MAC = platform.system() == "Darwin"
IS_WIN = platform.system() == "Windows"


def _sdk_roots() -> list[Path]:
    roots: list[Path] = []
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        val = os.environ.get(key)
        if val:
            roots.append(Path(val))
    home = Path.home()
    if IS_MAC:
        roots.append(home / "Library/Android/sdk")
    if IS_WIN:
        local = os.environ.get("LOCALAPPDATA") or str(home / "AppData/Local")
        roots.append(Path(local) / "Android" / "Sdk")
        roots.append(home / "AppData/Local/Android/Sdk")
    # Linux common
    roots.append(home / "Android/Sdk")
    # Dedupe
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r.resolve()) if r.exists() else str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def resolve_adb() -> Optional[str]:
    which = shutil.which("adb")
    if which:
        return which
    exe = "adb.exe" if IS_WIN else "adb"
    for root in _sdk_roots():
        candidate = root / "platform-tools" / exe
        if candidate.is_file():
            return str(candidate)
    return None


def resolve_emulator() -> Optional[str]:
    which = shutil.which("emulator")
    if which:
        return which
    exe = "emulator.exe" if IS_WIN else "emulator"
    for root in _sdk_roots():
        for sub in ("emulator", "tools"):
            candidate = root / sub / exe
            if candidate.is_file():
                return str(candidate)
    return None


async def _run_cmd(
    args: list[str],
    *,
    timeout: float = 60.0,
    cwd: Optional[str] = None,
) -> dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=os.environ.copy(),
        )
    except FileNotFoundError as e:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "error": "executable_not_found",
        }
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Timed out after {timeout}s",
            "error": "timeout",
        }
    stdout = (stdout_b or b"").decode("utf-8", errors="replace")
    stderr = (stderr_b or b"").decode("utf-8", errors="replace")
    code = proc.returncode if proc.returncode is not None else -1
    return {
        "ok": code == 0,
        "returncode": code,
        "stdout": stdout,
        "stderr": stderr,
        "error": None if code == 0 else "nonzero_exit",
    }


def _parse_adb_devices(stdout: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            kind = "emulator" if serial.startswith("emulator-") else "device"
            devices.append(
                {
                    "id": serial,
                    "platform": "android",
                    "name": serial,
                    "state": "online",
                    "kind": kind,
                    "source": "adb",
                    "startable": "false",
                }
            )
    return devices


async def list_android_online() -> list[dict[str, str]]:
    adb = resolve_adb()
    if not adb:
        return []
    result = await _run_cmd([adb, "devices"], timeout=15.0)
    return _parse_adb_devices(result.get("stdout") or "")


async def list_android_avds() -> list[dict[str, str]]:
    """AVDs that can be started (may already be running)."""
    emu = resolve_emulator()
    if not emu:
        return []
    result = await _run_cmd([emu, "-list-avds"], timeout=30.0)
    if not result.get("ok") and not (result.get("stdout") or "").strip():
        return []
    online = {d["id"] for d in await list_android_online()}
    # Heuristic: if any emulator-* online, treat first AVD match as running later
    avds: list[dict[str, str]] = []
    for line in (result.get("stdout") or "").splitlines():
        name = line.strip()
        if not name:
            continue
        # We can't map AVD name → emulator-5554 reliably without adb emu avd name;
        # mark as available; online check refined in ensure_device.
        avds.append(
            {
                "id": name,
                "platform": "android",
                "name": name,
                "state": "available",
                "kind": "avd",
                "source": "emulator",
                "startable": "true",
            }
        )
    # Enrich: query running emulators for avd name
    adb = resolve_adb()
    running_avds: set[str] = set()
    if adb:
        for d in await list_android_online():
            if not d["id"].startswith("emulator-"):
                continue
            r = await _run_cmd(
                [adb, "-s", d["id"], "emu", "avd", "name"],
                timeout=10.0,
            )
            # Output is "Pixel_6\nOK\n" or similar
            text = (r.get("stdout") or "") + "\n" + (r.get("stderr") or "")
            for line in text.splitlines():
                line = line.strip()
                if line and line.upper() != "OK" and not line.startswith("error"):
                    running_avds.add(line)
                    break
    for avd in avds:
        if avd["name"] in running_avds:
            avd["state"] = "online"
            avd["startable"] = "false"
    del online  # reserved
    return avds


def _parse_simctl_all(stdout: str) -> list[dict[str, str]]:
    """Parse `simctl list devices available` including Booted and Shutdown."""
    devices: list[dict[str, str]] = []
    current_runtime = ""
    for line in (stdout or "").splitlines():
        rt = re.match(r"^--\s+(.+?)\s+--$", line.strip())
        if rt:
            current_runtime = rt.group(1).strip()
            continue
        m = re.search(
            r"^\s+(.+?)\s+\(([0-9A-Fa-f-]{36})\)\s+\((Booted|Shutdown|Creating)\)",
            line,
        )
        if not m:
            continue
        name, udid, state = m.group(1).strip(), m.group(2), m.group(3)
        if state == "Creating":
            continue
        # Skip unavailable markers in name
        if "unavailable" in name.lower():
            continue
        devices.append(
            {
                "id": udid,
                "platform": "ios",
                "name": name,
                "state": "online" if state == "Booted" else "available",
                "kind": "simulator",
                "source": "simctl",
                "startable": "false" if state == "Booted" else "true",
                "runtime": current_runtime,
            }
        )
    return devices


async def list_ios_simulators(*, include_shutdown: bool = True) -> list[dict[str, str]]:
    if not IS_MAC or not shutil.which("xcrun"):
        return []
    result = await _run_cmd(
        ["xcrun", "simctl", "list", "devices", "available"],
        timeout=25.0,
    )
    devices = _parse_simctl_all(result.get("stdout") or "")
    if not include_shutdown:
        devices = [d for d in devices if d.get("state") == "online"]
    return devices


async def list_connected_devices() -> list[dict[str, str]]:
    """Devices currently usable by Maestro (online adb + booted sims)."""
    devices = await list_android_online()
    if IS_MAC:
        devices.extend(
            [d for d in await list_ios_simulators(include_shutdown=False)]
        )
    return devices


async def list_all_targets() -> list[dict[str, str]]:
    """Online devices + startable AVDs / iOS simulators."""
    connected = await list_connected_devices()
    by_id = {d["id"]: d for d in connected}
    # Add AVDs not already represented
    for avd in await list_android_avds():
        if avd["state"] == "online":
            # Prefer adb serial entries; keep AVD as informational if no serial map
            continue
        if avd["id"] not in by_id:
            by_id[avd["id"]] = avd
    if IS_MAC:
        for sim in await list_ios_simulators(include_shutdown=True):
            by_id[sim["id"]] = sim  # booted overwrites with richer state
    return list(by_id.values())


async def _wait_android_online(
    *,
    timeout_s: float = 120.0,
    progress: ProgressFn = None,
) -> Optional[dict[str, str]]:
    adb = resolve_adb()
    if not adb:
        return None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        # adb wait-for-device is per-default-device; poll instead
        online = await list_android_online()
        emus = [d for d in online if d["id"].startswith("emulator-")]
        if emus:
            # Wait until boot completed
            serial = emus[0]["id"]
            boot = await _run_cmd(
                [adb, "-s", serial, "shell", "getprop", "sys.boot_completed"],
                timeout=15.0,
            )
            val = (boot.get("stdout") or "").strip()
            if val == "1":
                if progress:
                    progress(f"Android emulator ready: {serial}")
                return emus[0]
        await asyncio.sleep(2.0)
        if progress:
            progress("Waiting for Android emulator to finish booting…")
    return None


async def start_android_avd(
    avd_name: str,
    *,
    timeout_s: float = 120.0,
    progress: ProgressFn = None,
) -> dict[str, Any]:
    emu = resolve_emulator()
    if not emu:
        return {
            "ok": False,
            "error": "emulator_not_found",
            "message": "Android emulator binary not found. Install Android Studio / SDK.",
        }
    if progress:
        progress(f"Starting Android AVD: {avd_name}")
    # Launch detached so it keeps running
    try:
        kwargs: dict[str, Any] = {
            "stdout": asyncio.subprocess.DEVNULL,
            "stderr": asyncio.subprocess.DEVNULL,
            "env": os.environ.copy(),
        }
        if IS_WIN:
            # Don't inherit console; detach
            kwargs["creationflags"] = getattr(subprocess_mod(), "DETACHED_PROCESS", 0) | getattr(
                subprocess_mod(), "CREATE_NEW_PROCESS_GROUP", 0
            )
        else:
            kwargs["start_new_session"] = True
        await asyncio.create_subprocess_exec(
            emu,
            "-avd",
            avd_name,
            "-netdelay",
            "none",
            "-netspeed",
            "full",
            **kwargs,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "start_failed", "message": str(e)}

    device = await _wait_android_online(timeout_s=timeout_s, progress=progress)
    if not device:
        return {
            "ok": False,
            "error": "boot_timeout",
            "message": f"AVD {avd_name} started but did not become ready in {timeout_s}s",
        }
    return {"ok": True, "device": device, "avd": avd_name}


def subprocess_mod():
    import subprocess

    return subprocess


async def start_ios_simulator(
    udid: str,
    *,
    timeout_s: float = 90.0,
    progress: ProgressFn = None,
) -> dict[str, Any]:
    if not IS_MAC:
        return {
            "ok": False,
            "error": "ios_mac_only",
            "message": "iOS Simulator can only be started on macOS (Xcode).",
        }
    if progress:
        progress(f"Booting iOS Simulator: {udid}")
    boot = await _run_cmd(["xcrun", "simctl", "boot", udid], timeout=60.0)
    # Already booted is OK
    err = (boot.get("stderr") or "") + (boot.get("stdout") or "")
    if not boot.get("ok") and "current state: Booted" not in err and "Already booted" not in err:
        # simctl returns non-zero if already booted on some versions — continue
        if "Booted" not in err and boot.get("returncode") not in (0,):
            # Still try open
            pass
    # Open Simulator.app UI
    await _run_cmd(["open", "-a", "Simulator"], timeout=30.0)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        sims = await list_ios_simulators(include_shutdown=False)
        match = next((s for s in sims if s["id"] == udid), None)
        if match:
            if progress:
                progress(f"iOS Simulator ready: {match.get('name')} ({udid})")
            return {"ok": True, "device": match}
        await asyncio.sleep(1.5)
        if progress:
            progress("Waiting for iOS Simulator to boot…")
    return {
        "ok": False,
        "error": "boot_timeout",
        "message": f"Simulator {udid} did not boot in {timeout_s}s",
    }


async def _maestro_start_device(
    *,
    platform: str,
    device_model: str = "",
    device_os: str = "",
    device_locale: str = "",
    timeout_s: float = 120.0,
    progress: ProgressFn = None,
) -> dict[str, Any]:
    """Best-effort `maestro start-device` then return a newly online device."""
    from mobiflow.maestro import resolve_maestro_binary

    binary = resolve_maestro_binary()
    if not binary:
        return {"ok": False, "error": "maestro_not_installed"}

    plat = (platform or "android").lower()
    if plat not in {"android", "ios", "web"}:
        plat = "android"

    args = [binary, "start-device", "--platform", plat]
    model = (device_model or "").strip()
    # Don't pass raw UDIDs / emulator-XXXX as --device-model
    if model and not re.fullmatch(r"[0-9A-Fa-f-]{36}", model) and not model.startswith(
        "emulator-"
    ):
        args.extend(["--device-model", model])
    if (device_os or "").strip():
        args.extend(["--device-os", device_os.strip()])
    if (device_locale or "").strip():
        args.extend(["--device-locale", device_locale.strip()])

    if progress:
        progress(f"Starting device via Maestro CLI ({plat})…")
    result = await _run_cmd(args, timeout=max(60.0, float(timeout_s)))
    if not result.get("ok"):
        return {
            "ok": False,
            "error": "maestro_start_device_failed",
            "stderr": result.get("stderr") or result.get("stdout") or "",
        }

    deadline = time.monotonic() + float(timeout_s)
    while time.monotonic() < deadline:
        connected = await list_connected_devices()
        for d in connected:
            if d.get("platform") == plat:
                if progress:
                    progress(
                        f"Maestro device ready: {d.get('name')} ({d.get('id')})"
                    )
                return {
                    "ok": True,
                    "device": d,
                    "started": True,
                    "via": "maestro start-device",
                }
        if connected:
            return {
                "ok": True,
                "device": connected[0],
                "started": True,
                "via": "maestro start-device",
            }
        await asyncio.sleep(1.5)
    return {
        "ok": False,
        "error": "maestro_start_device_timeout",
        "message": f"maestro start-device ran but no {plat} device came online",
    }


async def ensure_device(
    *,
    platform_pref: str = "android",
    device_id: Optional[str] = None,
    auto_start: bool = True,
    timeout_s: float = 120.0,
    progress: ProgressFn = None,
    use_maestro_cli: bool = True,
    device_model: str = "",
    device_os: str = "",
    device_locale: str = "",
) -> dict[str, Any]:
    """Return an online device; optionally start AVD / iOS sim if none connected.

    Preference order when auto-starting:
    - If ``use_maestro_cli``: try ``maestro start-device`` / ``maestro list-devices``
    - If device_id set: start that AVD name or iOS UDID
    - Else platform android: first available AVD
    - Else platform ios (macOS): first available iPhone simulator
    """
    plat = (platform_pref or "android").lower()

    def _p(msg: str) -> None:
        if progress:
            progress(msg)

    # Explicit device already online?
    connected = await list_connected_devices()
    if device_id:
        match = next((d for d in connected if d["id"] == device_id), None)
        if match:
            return {"ok": True, "device": match, "started": False}
    else:
        for d in connected:
            if d.get("platform") == plat:
                _p(f"Using connected {plat} device: {d.get('name')} ({d.get('id')})")
                return {"ok": True, "device": d, "started": False}
        if connected:
            _p(
                f"No {plat} device online — using {connected[0].get('platform')} "
                f"{connected[0].get('name')}"
            )
            return {"ok": True, "device": connected[0], "started": False}

    if not auto_start:
        return {
            "ok": False,
            "error": "no_device",
            "message": "No devices connected. Start an emulator/simulator or enable auto_start.",
            "connected": connected,
            "targets": await list_all_targets(),
        }

    # Prefer Maestro CLI device management when available
    if use_maestro_cli:
        started = await _maestro_start_device(
            platform=plat,
            device_model=device_model or device_id or "",
            device_os=device_os,
            device_locale=device_locale,
            timeout_s=timeout_s,
            progress=progress,
        )
        if started.get("ok"):
            return started

    if device_id:
        # Maybe it's an AVD name or shutdown sim
        avds = await list_android_avds()
        avd = next((a for a in avds if a["id"] == device_id or a["name"] == device_id), None)
        if avd and avd.get("startable") == "true":
            started = await start_android_avd(
                avd["name"], timeout_s=timeout_s, progress=progress
            )
            if started.get("ok"):
                return {
                    "ok": True,
                    "device": started["device"],
                    "started": True,
                    "avd": avd["name"],
                }
            return started
        if IS_MAC and re.fullmatch(r"[0-9A-Fa-f-]{36}", device_id):
            started = await start_ios_simulator(
                device_id, timeout_s=timeout_s, progress=progress
            )
            if started.get("ok"):
                return {"ok": True, "device": started["device"], "started": True}
            return started
        return {
            "ok": False,
            "error": "device_not_found",
            "message": f"Device {device_id!r} not connected and could not be started.",
            "connected": await list_connected_devices(),
        }

    # Auto-start via adb/simctl fallback
    if plat == "ios":
        if not IS_MAC:
            # Fall back to Android on Windows/Linux
            _p("iOS Simulator unavailable on this OS — trying Android AVD…")
            plat = "android"
        else:
            sims = await list_ios_simulators(include_shutdown=True)
            # Prefer iPhone, available (not booted)
            candidates = [
                s
                for s in sims
                if s.get("state") == "available" and "iphone" in s.get("name", "").lower()
            ]
            if not candidates:
                candidates = [s for s in sims if s.get("state") == "available"]
            if not candidates:
                return {
                    "ok": False,
                    "error": "no_ios_simulator",
                    "message": "No iOS simulators available. Install Xcode + run Xcode once.",
                }
            pick = candidates[0]
            started = await start_ios_simulator(
                pick["id"], timeout_s=timeout_s, progress=progress
            )
            if started.get("ok"):
                return {"ok": True, "device": started["device"], "started": True}
            return started

    # Android AVD
    avds = await list_android_avds()
    startable = [a for a in avds if a.get("startable") == "true"]
    if not startable:
        # Maybe emulator binary missing
        if not resolve_emulator():
            return {
                "ok": False,
                "error": "emulator_not_found",
                "message": (
                    "No Android emulator binary. Install Android Studio and create an AVD "
                    "(Tools → Device Manager). Set ANDROID_HOME if needed."
                ),
            }
        return {
            "ok": False,
            "error": "no_avd",
            "message": "No Android Virtual Devices found. Create one in Android Studio Device Manager.",
        }
    pick = startable[0]
    started = await start_android_avd(pick["name"], timeout_s=timeout_s, progress=progress)
    if started.get("ok"):
        return {"ok": True, "device": started["device"], "started": True, "avd": pick["name"]}
    return started


def host_capabilities() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "android_adb": resolve_adb(),
        "android_emulator": resolve_emulator(),
        "ios_simctl": bool(IS_MAC and shutil.which("xcrun")),
        "can_start_android": bool(resolve_emulator()),
        "can_start_ios": bool(IS_MAC and shutil.which("xcrun")),
    }

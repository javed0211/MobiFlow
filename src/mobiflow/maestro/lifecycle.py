"""App lifecycle helpers: install APK/IPA and clearState preflight flows."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def normalize_preflight(value: Any) -> list[str]:
    """Accept list/comma-string; return unique lowercase steps: install, clear."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [p.strip().lower() for p in value.replace(";", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(p).strip().lower() for p in value]
    else:
        items = [str(value).strip().lower()]
    aliases = {
        "install": "install",
        "installapp": "install",
        "apk": "install",
        "clear": "clear",
        "clearstate": "clear",
        "clear_state": "clear",
        "reset": "clear",
    }
    out: list[str] = []
    for item in items:
        if not item or item in {"none", "off", "false", "0"}:
            continue
        step = aliases.get(item.replace("-", "").replace("_", ""), item)
        if step in {"install", "clear"} and step not in out:
            out.append(step)
    return out


def build_preflight_flow_yaml(
    app_id: str,
    *,
    clear_state: bool = True,
    clear_keychain: bool = False,
    platform: str = "android",
) -> str:
    """Tiny Maestro flow: optional clearState (+ iOS clearKeychain) then stopApp."""
    aid = (app_id or "").strip() or "unknown.app"
    lines = [
        f"appId: {aid}",
        "name: MobiFlow preflight",
        "---",
    ]
    if clear_state:
        lines.append("- clearState")
        if clear_keychain and (platform or "").lower() == "ios":
            lines.append("- clearKeychain")
    lines.append("- stopApp")
    return "\n".join(lines) + "\n"


def resolve_adb() -> str | None:
    which = shutil.which("adb")
    if which:
        return which
    for env_key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(env_key)
        if not root:
            continue
        candidate = Path(root) / "platform-tools" / "adb"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    mac = Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb"
    if mac.is_file() and os.access(mac, os.X_OK):
        return str(mac)
    return None


async def install_app_local(
    app_path: str | Path,
    *,
    device_id: str | None = None,
    platform: str = "android",
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """Install a local .apk / .aab / .ipa onto a device or simulator."""
    import asyncio

    path = Path(app_path).expanduser().resolve()
    plat = (platform or "android").lower()
    suffix = path.suffix.lower()
    is_ios_app_bundle = suffix == ".app" and path.is_dir()
    if not path.is_file() and not is_ios_app_bundle:
        return {
            "ok": False,
            "error": "app_not_found",
            "message": f"App package not found: {path}",
        }

    if plat == "android" or suffix in {".apk", ".aab"}:
        adb = resolve_adb()
        if not adb:
            return {
                "ok": False,
                "error": "adb_not_found",
                "message": "adb not found — install Android platform-tools",
            }
        args = [adb]
        if device_id:
            args.extend(["-s", device_id])
        # -r: replace existing; -d: allow version downgrade (helpful in CI)
        args.extend(["install", "-r", "-d", str(path)])
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except TimeoutError:
            return {
                "ok": False,
                "error": "install_timeout",
                "message": f"adb install timed out after {timeout_s}s",
            }
        stdout = (stdout_b or b"").decode("utf-8", errors="replace")
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")
        ok = proc.returncode == 0 and "Success" in (stdout + stderr)
        return {
            "ok": ok,
            "error": "" if ok else "install_failed",
            "message": "Installed via adb" if ok else (stderr or stdout or "adb install failed"),
            "stdout": stdout,
            "stderr": stderr,
            "returncode": proc.returncode,
            "app_path": str(path),
        }

    if plat == "ios" or suffix in {".ipa", ".app"}:
        # Simulator path: xcrun simctl install <udid> <app.app>
        # .ipa needs unzip; prefer .app directories for sims.
        if is_ios_app_bundle:
            udid = device_id or "booted"
            args = ["xcrun", "simctl", "install", udid, str(path)]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s
                )
            except FileNotFoundError:
                return {
                    "ok": False,
                    "error": "simctl_not_found",
                    "message": "xcrun simctl not found (macOS + Xcode required)",
                }
            except TimeoutError:
                return {
                    "ok": False,
                    "error": "install_timeout",
                    "message": f"simctl install timed out after {timeout_s}s",
                }
            stdout = (stdout_b or b"").decode("utf-8", errors="replace")
            stderr = (stderr_b or b"").decode("utf-8", errors="replace")
            ok = proc.returncode == 0
            return {
                "ok": ok,
                "error": "" if ok else "install_failed",
                "message": "Installed via simctl" if ok else (stderr or stdout),
                "stdout": stdout,
                "stderr": stderr,
                "returncode": proc.returncode,
                "app_path": str(path),
            }
        return {
            "ok": False,
            "error": "ios_package_unsupported",
            "message": (
                "Local iOS install supports .app on Simulator. "
                "For .ipa use a cloud provider or install manually."
            ),
            "app_path": str(path),
        }

    return {
        "ok": False,
        "error": "unsupported_package",
        "message": f"Unsupported app package: {path.name}",
        "app_path": str(path),
    }


async def run_preflight(
    *,
    app_id: str,
    platform: str,
    device_id: str | None,
    steps: list[str],
    app_path: str = "",
    clear_state: bool = False,
    progress: Any = None,
    run_flow_yaml: Any = None,
    timeout_s: int = 90,
) -> dict[str, Any]:
    """Run configured lifecycle steps on a local device.

    Cloud labs install via upload — skip local install/clear there.
    """
    from mobiflow.maestro import run_flow_yaml as _default_run

    runner = run_flow_yaml or _default_run
    done: list[str] = []
    notes: list[str] = []

    want = list(steps)
    if clear_state and "clear" not in want:
        want.append("clear")

    if "install" in want and app_path:
        if progress:
            progress(f"Preflight: installing {app_path}…")
        inst = await install_app_local(
            app_path,
            device_id=device_id,
            platform=platform,
            timeout_s=float(timeout_s),
        )
        notes.append(inst.get("message") or "")
        if not inst.get("ok"):
            return {
                "ok": False,
                "steps": done,
                "error": inst.get("error") or "install_failed",
                "message": inst.get("message") or "install failed",
                "install": inst,
            }
        done.append("install")
    elif "install" in want and not app_path:
        notes.append("preflight install skipped — no app_path")

    if "clear" in want:
        if not app_id:
            notes.append("preflight clear skipped — no app_id")
        else:
            if progress:
                progress(f"Preflight: clearState {app_id}…")
            flow = build_preflight_flow_yaml(
                app_id,
                clear_state=True,
                clear_keychain=(platform or "").lower() == "ios",
                platform=platform,
            )
            result = await runner(
                flow,
                device_id=device_id,
                timeout_s=timeout_s,
            )
            if not result.get("ok"):
                return {
                    "ok": False,
                    "steps": done,
                    "error": result.get("error") or "clear_failed",
                    "message": result.get("stderr")
                    or result.get("error")
                    or "clearState failed",
                    "clear": result,
                    "notes": notes,
                }
            done.append("clear")

    return {"ok": True, "steps": done, "notes": notes, "message": "preflight ok"}

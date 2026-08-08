"""Maestro CLI adapter: status, devices, YAML gen, live run."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from mobiflow.llm import (
    extract_fenced_files,
    extract_yaml_fence,
    invoke_chat_text,
    profile_to_llm_config,
)
from mobiflow.llm_catalog import ModelEntry

logger = logging.getLogger(__name__)

ProgressFn = Optional[Callable[[str], None]]


@dataclass
class FlowBundle:
    """Maestro flow YAML plus optional companion JavaScript files."""

    flow_yaml: str
    scripts: dict[str, str] = field(default_factory=dict)

    @property
    def has_js(self) -> bool:
        return bool(self.scripts) or bool(
            re.search(r"(?m)^\s*-\s*(evalScript|runScript)\b", self.flow_yaml or "")
        )

_KNOWN_APP_IDS = {
    "wikipedia": {"android": "org.wikipedia", "ios": "org.wikimedia.wikipedia"},
    "settings": {"android": "com.android.settings", "ios": "com.apple.Preferences"},
    "chrome": {"android": "com.android.chrome", "ios": "com.google.chrome.ios"},
    "safari": {"android": "com.android.chrome", "ios": "com.apple.mobilesafari"},
}


def resolve_maestro_binary() -> str | None:
    which = shutil.which("maestro")
    if which:
        return which
    home = Path.home() / ".maestro" / "bin" / "maestro"
    if home.is_file() and os.access(home, os.X_OK):
        return str(home)
    return None


def resolve_java_home() -> str | None:
    jh = os.environ.get("JAVA_HOME")
    if jh and Path(jh).is_dir():
        return jh
    # Common macOS Homebrew / system locations
    for candidate in (
        "/opt/homebrew/opt/openjdk",
        "/usr/local/opt/openjdk",
    ):
        if Path(candidate).is_dir():
            return candidate
    # Windows: JAVA_HOME usually set by installer; also check Program Files
    if platform_system() == "Windows":
        for base in (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Java",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Eclipse Adoptium",
        ):
            if base.is_dir():
                # pick first jdk-* / jre-* child
                for child in sorted(base.glob("jdk*")) + sorted(base.glob("jre*")):
                    if child.is_dir():
                        return str(child)
    return jh


def platform_system() -> str:
    import platform

    return platform.system()


def _maestro_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("MAESTRO_CLI_NO_ANALYTICS", "1")
    jh = resolve_java_home()
    if jh:
        env.setdefault("JAVA_HOME", jh)
    maestro_bin = resolve_maestro_binary()
    if maestro_bin:
        bin_dir = str(Path(maestro_bin).parent)
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    return env


async def _run_cmd(
    args: list[str],
    *,
    timeout: float = 120.0,
    cwd: str | None = None,
) -> dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=_maestro_env(),
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
    except TimeoutError:
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


async def list_devices() -> list[dict[str, str]]:
    """Online devices only (adb + booted iOS sims)."""
    from mobiflow.devices import list_connected_devices

    return await list_connected_devices()


async def list_device_targets() -> list[dict[str, str]]:
    """Online + startable AVDs / iOS simulators."""
    from mobiflow.devices import list_all_targets

    return await list_all_targets()


async def get_maestro_version() -> str | None:
    binary = resolve_maestro_binary()
    if not binary:
        return None
    result = await _run_cmd([binary, "--version"], timeout=20.0)
    text = "\n".join(
        [(result.get("stdout") or "").strip(), (result.get("stderr") or "").strip()]
    )
    for line in text.splitlines():
        m = re.search(r"\b(\d+\.\d+(?:\.\d+)?)\b", line)
        if m:
            return m.group(1)
    return None


async def get_status() -> dict[str, Any]:
    from mobiflow.devices import (
        host_capabilities,
        list_all_targets,
        list_connected_devices,
    )

    binary = resolve_maestro_binary()
    installed = binary is not None
    java_home = resolve_java_home()
    version = await get_maestro_version() if installed else None
    devices = await list_connected_devices()
    targets = await list_all_targets()
    caps = host_capabilities()
    startable = [t for t in targets if t.get("startable") == "true"]
    ready = bool(installed and java_home and (devices or startable))
    if not installed:
        message = "Maestro CLI not found. Install: curl -Ls https://get.maestro.mobile.dev | bash"
    elif not java_home:
        message = "JAVA_HOME not set — Maestro needs a JDK."
    elif devices:
        message = f"Maestro {version or '?'} ready · {len(devices)} device(s) online"
    elif startable:
        message = (
            f"Maestro {version or '?'} installed · no device online, "
            f"but {len(startable)} emulator/simulator(s) can be auto-started"
        )
    else:
        message = (
            f"Maestro {version or '?'} installed, but no devices/emulators found. "
            "Install Android Studio (AVD) and/or Xcode (macOS)."
        )
    return {
        "installed": installed,
        "binary": binary,
        "java_home": java_home,
        "version": version,
        "devices": devices,
        "targets": targets,
        "device_count": len(devices),
        "startable_count": len(startable),
        "host": caps,
        "ready": ready,
        "message": message,
    }


def infer_platform(device_id: str, fallback: str = "android") -> str:
    did = (device_id or "").strip()
    if re.fullmatch(r"[0-9A-Fa-f-]{36}", did):
        return "ios"
    if did.startswith("emulator-") or ":" in did:
        return "android"
    return (fallback or "android").lower()


def resolve_app_id(app_id: str, platform: str, goal: str = "") -> str:
    if (app_id or "").strip():
        return app_id.strip()
    g = (goal or "").lower()
    plat = (platform or "android").lower()
    for key, mapping in _KNOWN_APP_IDS.items():
        if key in g:
            return mapping.get(plat) or mapping["android"]
    return mapping_default(plat)


def mapping_default(platform: str) -> str:
    return (
        "com.apple.Preferences"
        if platform == "ios"
        else "com.android.settings"
    )


def looks_like_maestro_yaml(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if re.search(r"(?m)^appId:\s*\S+", t) and "---" in t:
        return True
    if re.search(r"(?m)^\s*-\s*(launchApp|tapOn|assertVisible|openLink)\b", t):
        return True
    return False


def ensure_flow_yaml(yaml_text: str, app_id: str) -> str:
    text = (yaml_text or "").strip()
    if not text:
        aid = app_id or "com.android.settings"
        return f"appId: {aid}\nname: Generated mobile flow\n---\n- launchApp\n"
    if not re.search(r"(?m)^appId:\s*", text):
        aid = app_id or "com.android.settings"
        if "---" in text:
            return f"appId: {aid}\n---\n" + text.split("---", 1)[-1].lstrip()
        return f"appId: {aid}\nname: Generated mobile flow\n---\n{text}"
    return text


def ensure_stop_app(yaml_text: str) -> str:
    if re.search(r"(?m)^\s*-\s*stopApp\b", yaml_text or ""):
        return yaml_text
    return (yaml_text or "").rstrip() + "\n- stopApp\n"


_MAESTRO_SYSTEM_YAML = """You are a Maestro mobile test engineer.
Emit ONLY valid Maestro flow YAML (appId config above ---, commands below).
Rules:
1) Cover EVERY goal step — launch, navigate, assert, dismiss onboarding when needed.
2) Map goals to: launchApp, openLink, tapOn, inputText, pressKey, scroll,
   scrollUntilVisible, swipe, assertVisible, waitForAnimationToEnd, stopApp.
3) Prefer selectors from exploration results / view hierarchy when provided;
   else stable visible text.
4) When exploration results include a grounded plan, follow that plan closely.
5) iOS Settings: com.apple.Preferences. Android Settings: com.android.settings.
6) Mobile web (https://): openLink + Safari/Chrome appId. Never emit Playwright/Appium.
7) Wikipedia: org.wikipedia (Android) / org.wikimedia.wikipedia (iOS).
8) After launchApp, optionally dismiss Skip/Next/Continue/Allow/Not now.
9) End the flow with stopApp.
10) No markdown prose outside a ```yaml fence.
11) Do NOT use evalScript/runScript — YAML commands only for this project."""

_MAESTRO_SYSTEM_JS = """You are a Maestro mobile test engineer with JavaScript support enabled.
Emit a Maestro flow YAML and, when useful, companion JavaScript files.

Rules:
1) Primary artifact: valid Maestro YAML (appId above ---, commands below).
2) UI commands: launchApp, openLink, tapOn, inputText, pressKey, scroll,
   scrollUntilVisible, swipe, assertVisible, waitForAnimationToEnd, stopApp.
3) JavaScript (GraalJS / modern ES):
   - Use ${expression} for dynamic values in YAML fields.
   - Use evalScript for short inline logic (set output.*, compute values).
   - Use runScript: scripts/<name>.js for reusable helpers.
   - Prefer the global `output` object to share values across steps.
   - You may use console.log for debugging; no Node.js / filesystem APIs.
   - faker may be used for synthetic data when helpful.
4) Prefer selectors from exploration results / view hierarchy when provided;
   else stable visible text.
5) When exploration results include a grounded plan, follow that plan closely.
6) iOS Settings: com.apple.Preferences. Android Settings: com.android.settings.
7) Mobile web (https://): openLink + Safari/Chrome appId. Never emit Playwright/Appium.
8) Wikipedia: org.wikipedia (Android) / org.wikimedia.wikipedia (iOS).
9) After launchApp, optionally dismiss Skip/Next/Continue/Allow/Not now.
10) End the flow with stopApp.
11) Output format — use fenced blocks:
    ```yaml flow.yaml
    ...
    ```
    ```javascript scripts/helpers.js
    ...
    ```
    Only add .js files when the goal needs dynamic data, conditions, or HTTP helpers.
    Keep simple smoke flows YAML-only."""

def parse_flow_bundle(text: str, *, app_id: str) -> FlowBundle:
    """Parse LLM (or paste) text into YAML + optional JS scripts."""
    scripts: dict[str, str] = {}
    yaml_body = ""
    for name, body in extract_fenced_files(text or ""):
        lower = name.lower()
        if lower.endswith((".js", ".mjs")) or lower.endswith("javascript"):
            # Normalize to scripts/<file>.js when bare filename
            path = name
            if "/" not in path and "\\" not in path:
                path = f"scripts/{path}"
            # Strip leading // file: line if present
            lines = body.splitlines()
            if lines and re.match(r"^//\s*file:", lines[0], re.IGNORECASE):
                body = "\n".join(lines[1:]).strip()
            scripts[path] = body
        elif lower.endswith((".yaml", ".yml")) or looks_like_maestro_yaml(body):
            if not yaml_body:
                yaml_body = body
    if not yaml_body:
        yaml_body = extract_yaml_fence(text or "")
    yaml_out = ensure_stop_app(ensure_flow_yaml(yaml_body, app_id))
    # Rewrite runScript paths to scripts/… when we emitted helpers there
    yaml_out = _normalize_run_script_paths(yaml_out, scripts)
    return FlowBundle(flow_yaml=yaml_out, scripts=scripts)


def _normalize_run_script_paths(flow_yaml: str, scripts: dict[str, str]) -> str:
    if not scripts:
        return flow_yaml
    # Map basename → preferred relative path
    by_base = {Path(p).name: p for p in scripts}

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1).strip().strip("\"'")
        base = Path(raw).name
        if base in by_base:
            return f"- runScript: {by_base[base]}"
        if not raw.startswith("scripts/") and base.endswith(".js"):
            return f"- runScript: scripts/{base}"
        return match.group(0)

    return re.sub(
        r"(?m)^\s*-\s*runScript:\s*(\S+)\s*$",
        repl,
        flow_yaml,
    )


DEFAULT_HELPERS_JS = """\
// MobiFlow Maestro helpers (GraalJS sandbox — no Node.js APIs)
// Use via: - runScript: scripts/helpers.js
// Values set on `output` are available later as ${output.key}

function setOutput(key, value) {
  output[key] = value;
  return value;
}

function nowIso() {
  return new Date().toISOString();
}

// Example: setOutput('runId', 'run-' + Date.now());
"""


async def generate_flow_bundle(
    goal: str,
    *,
    app_id: str,
    platform: str,
    profile: ModelEntry,
    hierarchy: str = "",
    previous_yaml: str = "",
    previous_scripts: dict[str, str] | None = None,
    failure_log: str = "",
    exploration: str = "",
    allow_js: bool = True,
    progress: ProgressFn = None,
) -> FlowBundle:
    """NL (or pasted YAML) → Maestro FlowBundle (YAML + optional JS)."""
    goal = (goal or "").strip()
    if looks_like_maestro_yaml(goal):
        return parse_flow_bundle(goal, app_id=app_id)

    resolved = resolve_app_id(app_id, platform, goal)
    # Deterministic shortcuts (YAML-only — no JS needed) when no explore/repair context
    gl = goal.lower()
    if (
        not exploration.strip()
        and not previous_yaml
        and "settings" in gl
        and ("open" in gl or "launch" in gl)
    ):
        return FlowBundle(flow_yaml=_settings_flow(platform))
    if (
        not exploration.strip()
        and not previous_yaml
        and "wikipedia" in gl
        and ("open" in gl or "launch" in gl)
        and "search" not in gl
    ):
        return FlowBundle(flow_yaml=_wikipedia_open_flow(platform, resolved))

    if progress:
        progress(
            "Authoring Maestro YAML"
            + (" + JS" if allow_js else "")
            + (" from exploration" if exploration.strip() else "")
            + " with LLM…"
        )

    system = _MAESTRO_SYSTEM_JS if allow_js else _MAESTRO_SYSTEM_YAML
    llm_config = profile_to_llm_config(profile)
    user_parts = [
        f"Platform: {platform or 'android'}",
        f"App ID: {resolved}",
        f"JavaScript enabled: {str(allow_js).lower()}",
        f"Goal:\n{goal}",
    ]
    if exploration.strip():
        user_parts.append(exploration.strip()[:12000])
    if previous_yaml.strip():
        user_parts.append(
            f"Previous flow YAML to repair:\n```yaml\n{previous_yaml.strip()}\n```"
        )
    if previous_scripts:
        for name, body in previous_scripts.items():
            user_parts.append(
                f"Previous script `{name}`:\n```javascript {name}\n{body}\n```"
            )
    if failure_log.strip():
        user_parts.append(f"Failure log:\n{failure_log.strip()[:6000]}")
    if hierarchy.strip():
        user_parts.append(
            f"Current view hierarchy (truncated):\n{hierarchy.strip()[:8000]}"
        )
    if allow_js:
        user_parts.append(
            "Return ```yaml flow.yaml``` and optional ```javascript scripts/<name>.js```. "
            "End YAML with stopApp."
        )
    else:
        user_parts.append(
            "Return a complete Maestro flow in a ```yaml fence. End with stopApp."
        )

    text = await asyncio.to_thread(
        invoke_chat_text,
        system,
        "\n\n".join(user_parts),
        llm_config,
        max_tokens=4096,
        temperature=0.2,
        log_prefix="MobiFlow",
    )
    bundle = parse_flow_bundle(text or "", app_id=resolved)
    if not allow_js:
        # Strip JS if project disabled it
        bundle.scripts = {}
        # Remove runScript/evalScript lines if model ignored instructions
        cleaned = re.sub(
            r"(?m)^\s*-\s*(evalScript|runScript):.*(?:\n(?:\s{2,}.+)*)?",
            "",
            bundle.flow_yaml,
        )
        bundle.flow_yaml = ensure_stop_app(cleaned)
    return bundle


async def generate_flow_yaml(
    goal: str,
    *,
    app_id: str,
    platform: str,
    profile: ModelEntry,
    hierarchy: str = "",
    previous_yaml: str = "",
    failure_log: str = "",
    exploration: str = "",
    allow_js: bool = True,
    progress: ProgressFn = None,
) -> str:
    """NL → Maestro flow YAML (compat wrapper)."""
    bundle = await generate_flow_bundle(
        goal,
        app_id=app_id,
        platform=platform,
        profile=profile,
        hierarchy=hierarchy,
        previous_yaml=previous_yaml,
        failure_log=failure_log,
        exploration=exploration,
        allow_js=allow_js,
        progress=progress,
    )
    return bundle.flow_yaml


def _settings_flow(platform: str) -> str:
    aid = "com.apple.Preferences" if platform == "ios" else "com.android.settings"
    visible = "Settings|General|Wi-Fi|Network" if platform == "ios" else "Settings|Network|Apps"
    return (
        f"appId: {aid}\n"
        f"name: Open system Settings\n"
        f"---\n"
        f"- launchApp\n"
        f'- assertVisible: "{visible}"\n'
        f"- stopApp\n"
    )


def _wikipedia_open_flow(platform: str, app_id: str) -> str:
    aid = app_id or (
        "org.wikimedia.wikipedia" if platform == "ios" else "org.wikipedia"
    )
    return (
        f"appId: {aid}\n"
        f"name: Open Wikipedia\n"
        f"---\n"
        f"- launchApp\n"
        f"- tapOn:\n"
        f'    text: "Skip|Next|Continue|Get started|Allow|Not now"\n'
        f"    optional: true\n"
        f'- assertVisible: "Search|Explore|Wikipedia"\n'
        f"- stopApp\n"
    )


async def fetch_hierarchy(device_id: str | None = None) -> str:
    binary = resolve_maestro_binary()
    if not binary:
        return ""
    args = [binary, "hierarchy"]
    if device_id:
        args.extend(["--device", device_id])
    result = await _run_cmd(args, timeout=60.0)
    return (result.get("stdout") or "")[:12000]


def _maestro_test_args(
    binary: str,
    flow_path: Path,
    *,
    device_id: str | None = None,
    artifact_dir: Path | None = None,
) -> list[str]:
    args = [binary, "test", str(flow_path)]
    if device_id:
        args.extend(["--device", device_id])
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        debug_dir = artifact_dir / "maestro-debug"
        test_out = artifact_dir / "maestro-output"
        junit_path = artifact_dir / "maestro-junit.xml"
        debug_dir.mkdir(parents=True, exist_ok=True)
        test_out.mkdir(parents=True, exist_ok=True)
        args.extend(
            [
                "--debug-output",
                str(debug_dir),
                "--flatten-debug-output",
                "--test-output-dir",
                str(test_out),
                "--format",
                "JUNIT",
                "--output",
                str(junit_path),
            ]
        )
    return args


async def run_flow_yaml(
    flow_yaml: str,
    *,
    device_id: str | None = None,
    timeout_s: int = 180,
    scripts: dict[str, str] | None = None,
    work_dir: Path | None = None,
    progress: ProgressFn = None,
    device_config: Any = None,
    platform: str | None = None,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    """Run Maestro YAML locally or on a cloud device lab.

    When ``device_config.provider`` is ``browserstack`` or ``testmu``, uploads
    the flow (and app) and executes via that lab instead of local ``maestro test``.

    For local runs, ``artifact_dir`` enables Maestro ``--debug-output``,
    ``--test-output-dir``, and JUnit ``--format/--output``.
    """
    from mobiflow.cloud.base import is_cloud_provider

    if device_config is not None and is_cloud_provider(
        getattr(device_config, "provider", "local")
    ):
        from mobiflow.cloud.runner import request_from_device_config, run_on_cloud

        if progress:
            progress(
                f"Running on cloud provider={device_config.provider} "
                f"device={device_id or device_config.device_id or '(default)'}…"
            )
        req = request_from_device_config(
            device_config,
            flow_yaml=flow_yaml,
            scripts=scripts,
            platform=platform or getattr(device_config, "platform", "android"),
            device_id=device_id,
            timeout_s=max(
                timeout_s, int(getattr(device_config, "cloud_timeout_s", 1800) or 1800)
            ),
        )
        cloud_result = await run_on_cloud(req, progress=progress)
        out = cloud_result.as_run_dict()
        out["flow_yaml"] = flow_yaml
        out["scripts"] = scripts or {}
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "cloud-result.json").write_text(
                json.dumps(
                    {
                        "provider": out.get("provider"),
                        "build_id": out.get("build_id"),
                        "status": out.get("status"),
                        "dashboard_url": out.get("dashboard_url"),
                        "ok": out.get("ok"),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            out["artifact_dir"] = str(artifact_dir)
        return out

    binary = resolve_maestro_binary()
    if not binary:
        return {
            "ok": False,
            "error": "maestro_not_installed",
            "stdout": "",
            "stderr": "Maestro CLI not found",
            "returncode": -1,
        }

    def _write_bundle(root: Path) -> Path:
        flow_path = root / "flow.yaml"
        flow_path.write_text(flow_yaml, encoding="utf-8")
        for rel, body in (scripts or {}).items():
            sp = root / rel
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(body, encoding="utf-8")
        return flow_path

    def _finalize(result: dict[str, Any], root: Path) -> dict[str, Any]:
        result["flow_yaml"] = flow_yaml
        result["scripts"] = scripts or {}
        if artifact_dir is not None:
            result["artifact_dir"] = str(artifact_dir)
            junit = artifact_dir / "maestro-junit.xml"
            if junit.is_file():
                result["maestro_junit"] = str(junit)
            # Persist a copy of the flow used for this attempt
            try:
                (artifact_dir / "flow.yaml").write_text(flow_yaml, encoding="utf-8")
            except OSError:
                pass
            result["maestro_debug_dir"] = str(artifact_dir / "maestro-debug")
            result["maestro_output_dir"] = str(artifact_dir / "maestro-output")
        result["work_dir"] = str(root)
        return result

    if work_dir is not None:
        work_dir.mkdir(parents=True, exist_ok=True)
        flow_path = _write_bundle(work_dir)
        args = _maestro_test_args(
            binary, flow_path, device_id=device_id, artifact_dir=artifact_dir
        )
        if progress:
            progress(f"Running maestro test{' on ' + device_id if device_id else ''}…")
        result = await _run_cmd(args, timeout=float(timeout_s), cwd=str(work_dir))
        return _finalize(result, work_dir)

    # Prefer durable artifact_dir as work root when provided
    if artifact_dir is not None:
        root = Path(artifact_dir) / "bundle"
        root.mkdir(parents=True, exist_ok=True)
        flow_path = _write_bundle(root)
        args = _maestro_test_args(
            binary, flow_path, device_id=device_id, artifact_dir=artifact_dir
        )
        if progress:
            progress(f"Running maestro test{' on ' + device_id if device_id else ''}…")
        result = await _run_cmd(args, timeout=float(timeout_s), cwd=str(root))
        return _finalize(result, root)

    with tempfile.TemporaryDirectory(prefix="mobiflow-") as tmp:
        root = Path(tmp)
        flow_path = _write_bundle(root)
        args = _maestro_test_args(binary, flow_path, device_id=device_id)
        if progress:
            progress(f"Running maestro test{' on ' + device_id if device_id else ''}…")
        result = await _run_cmd(args, timeout=float(timeout_s), cwd=str(root))
        return _finalize(result, root)


async def run_mobile_task(
    goal: str,
    *,
    codegen_profile: ModelEntry,
    discovery_profile: ModelEntry | None = None,
    app_id: str = "",
    platform: str = "android",
    device_id: str | None = None,
    heal: int = 2,
    adaptive: bool = True,
    explore: bool = True,
    explore_steps: int = 5,
    timeout_s: int = 180,
    live: bool = True,
    allow_js: bool = True,
    auto_start_device: bool = True,
    progress: ProgressFn = None,
    device_config: Any = None,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    """Full agent loop: explore → author YAML(+JS) → run → optional heal."""
    from mobiflow.cloud.base import is_cloud_provider
    from mobiflow.devices import ensure_device
    from mobiflow.explore import ExplorationResult, explore_app, plan_only_explore

    logs: list[str] = []
    run_root = Path(artifact_dir) if artifact_dir else None
    if run_root is not None:
        run_root.mkdir(parents=True, exist_ok=True)
    discovery = discovery_profile or codegen_profile

    def _p(msg: str) -> None:
        logs.append(msg)
        if progress:
            progress(msg)

    cloud = bool(
        device_config is not None
        and is_cloud_provider(getattr(device_config, "provider", "local"))
    )
    provider = (
        getattr(device_config, "provider", "local") if device_config is not None else "local"
    )

    status = await get_status()
    if cloud:
        from mobiflow.cloud import cloud_readiness

        ready = cloud_readiness(device_config)
        _p(ready.get("message") or f"Cloud provider={provider}")
        # Cloud runs do not need local Maestro CLI / adb
        status = {
            **status,
            "ready": bool(ready.get("ready")),
            "cloud": ready,
            "message": ready.get("message") or status.get("message"),
        }
    else:
        _p(status.get("message") or "Checking Maestro…")

    selected = (device_id or "").strip()
    if cloud:
        selected = selected or (getattr(device_config, "device_id", None) or "")
        selected = (selected or "").strip()
        if not selected:
            from mobiflow.cloud.base import devices_from_config, normalize_provider

            selected = devices_from_config(
                None,
                platform=platform,
                provider=normalize_provider(provider),
            )[0]
            _p(f"Using default cloud device: {selected}")
    elif live:
        ensured = await ensure_device(
            platform_pref=platform,
            device_id=selected or None,
            auto_start=auto_start_device,
            timeout_s=max(90.0, float(timeout_s)),
            progress=_p,
        )
        if ensured.get("ok") and ensured.get("device"):
            selected = ensured["device"].get("id") or selected
            platform = ensured["device"].get("platform") or platform
            if ensured.get("started"):
                _p(f"Auto-started device {selected}")
        elif auto_start_device:
            _p(ensured.get("message") or "Could not ensure a device")
    else:
        # gen-only: still prefer an online id if present
        devices = list(status.get("devices") or [])
        if not selected and devices:
            plat = (platform or "").lower()
            match = next((d for d in devices if d.get("platform") == plat), None)
            selected = (match or devices[0]).get("id") or ""

    if selected and not cloud:
        platform = infer_platform(selected, platform)

    scripts: dict[str, str] = {}
    exploration = ExplorationResult(
        goal=goal,
        app_id=app_id,
        platform=platform,
        mode="skipped",
    )
    exploration_prompt = ""

    # Paste-to-run
    if looks_like_maestro_yaml(goal):
        bundle = parse_flow_bundle(goal, app_id=app_id)
        flow = bundle.flow_yaml
        scripts = bundle.scripts
        _p("Detected Maestro YAML — running as-is.")
    else:
        # --- Explore phase (discovery LLM) before codegen ---
        want_explore = bool(explore and discovery is not None)
        if want_explore and live and selected and not cloud and status.get("installed"):
            try:
                exploration = await explore_app(
                    goal,
                    app_id=app_id,
                    platform=platform,
                    device_id=selected,
                    profile=discovery,
                    max_steps=explore_steps,
                    step_timeout_s=min(90, max(30, timeout_s // 2)),
                    progress=_p,
                )
            except Exception as e:  # noqa: BLE001
                _p(f"Explore failed ({e}); falling back to hierarchy snapshot.")
                exploration = ExplorationResult(
                    goal=goal,
                    app_id=app_id,
                    platform=platform,
                    mode="skipped",
                    notes=[f"explore_error: {e}"],
                )
        elif want_explore:
            # Cloud / no device: plan-only exploration from the goal text
            try:
                exploration = await plan_only_explore(
                    goal=goal,
                    app_id=app_id,
                    platform=platform,
                    profile=discovery,
                    progress=_p,
                )
            except Exception as e:  # noqa: BLE001
                _p(f"Plan-only explore failed ({e}); continuing without it.")

        exploration_prompt = exploration.to_prompt_block()
        if run_root is not None and exploration.mode != "skipped":
            try:
                (run_root / "exploration.json").write_text(
                    json.dumps(exploration.to_dict(), indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass

        hierarchy = exploration.final_hierarchy or ""
        if (
            not hierarchy
            and live
            and adaptive
            and selected
            and status.get("installed")
            and not cloud
        ):
            _p("Fetching view hierarchy…")
            hierarchy = await fetch_hierarchy(selected)
        elif cloud and adaptive and not exploration_prompt:
            _p("Skipping local hierarchy (cloud provider) — heal uses failure logs only.")

        bundle = await generate_flow_bundle(
            goal,
            app_id=app_id,
            platform=platform,
            profile=codegen_profile,
            hierarchy=hierarchy,
            exploration=exploration_prompt,
            allow_js=allow_js,
            progress=_p,
        )
        flow = bundle.flow_yaml
        scripts = bundle.scripts

    if scripts:
        _p(f"Maestro bundle ready ({len(scripts)} JS file(s)).")
    else:
        _p("Maestro YAML ready.")
    result: dict[str, Any] = {
        "success": False,
        "flow_yaml": flow,
        "scripts": scripts,
        "device_id": selected or None,
        "platform": platform,
        "provider": provider,
        "logs": logs,
        "synthesis_only": False,
        "maestro_status": status,
        "exploration": exploration.to_dict() if exploration.mode != "skipped" else None,
    }

    can_run = False
    if live and selected:
        if cloud:
            can_run = bool((status.get("cloud") or {}).get("ready"))
        else:
            can_run = bool(status.get("installed"))

    if not live or not can_run:
        result["success"] = True
        result["synthesis_only"] = True
        if not live:
            result["summary"] = "Flow generated (--gen-only; skipped device run)."
        elif cloud:
            result["summary"] = (
                "Flow generated (cloud lab not ready — skipped run). "
                + str((status.get("cloud") or {}).get("message") or "")
            ).strip()
        else:
            result["summary"] = "Flow generated (no live device / Maestro — skipped run)."
        _p(result["summary"])
        return result

    attempt = 0
    last_run: dict[str, Any] = {}
    attempts_meta: list[dict[str, Any]] = []
    # Cloud heal is expensive; still honor heal but hierarchy is unavailable
    while attempt <= max(0, heal):
        attempt += 1
        _p(f"Device run attempt {attempt}/{max(1, heal + 1)}…")
        attempt_dir = None
        if run_root is not None:
            attempt_dir = run_root / "attempts" / f"{attempt:02d}"
            attempt_dir.mkdir(parents=True, exist_ok=True)
        last_run = await run_flow_yaml(
            flow,
            device_id=selected,
            timeout_s=timeout_s,
            scripts=scripts,
            progress=_p,
            device_config=device_config,
            platform=platform,
            artifact_dir=attempt_dir,
        )
        attempts_meta.append(
            {
                "attempt": attempt,
                "ok": bool(last_run.get("ok")),
                "artifact_dir": last_run.get("artifact_dir"),
                "error": last_run.get("error"),
                "build_id": last_run.get("build_id"),
                "dashboard_url": last_run.get("dashboard_url"),
            }
        )
        result["attempts"] = attempts_meta
        result["artifact_dir"] = str(run_root) if run_root else last_run.get("artifact_dir")
        if last_run.get("ok"):
            result["success"] = True
            where = f"cloud:{provider}" if cloud else "device"
            result["summary"] = f"Maestro flow passed on {where}."
            result["run"] = {
                k: last_run.get(k)
                for k in (
                    "returncode",
                    "stdout",
                    "stderr",
                    "provider",
                    "build_id",
                    "dashboard_url",
                    "status",
                    "artifact_dir",
                    "maestro_junit",
                    "maestro_debug_dir",
                    "maestro_output_dir",
                )
                if k in last_run
            }
            _p(result["summary"])
            if last_run.get("dashboard_url"):
                _p(f"Dashboard: {last_run['dashboard_url']}")
            return result

        failure = (last_run.get("stderr") or "") + "\n" + (last_run.get("stdout") or "")
        if attempt > heal:
            break
        _p("Flow failed — repairing with LLM…")
        hierarchy = ""
        if adaptive and not cloud:
            hierarchy = await fetch_hierarchy(selected)
        bundle = await generate_flow_bundle(
            goal,
            app_id=app_id,
            platform=platform,
            profile=codegen_profile,
            hierarchy=hierarchy,
            previous_yaml=flow,
            previous_scripts=scripts,
            failure_log=failure,
            exploration=exploration_prompt,
            allow_js=allow_js,
            progress=_p,
        )
        flow = bundle.flow_yaml
        scripts = bundle.scripts
        result["flow_yaml"] = flow
        result["scripts"] = scripts

    result["success"] = False
    result["summary"] = "Maestro flow failed after heal attempts."
    result["error"] = last_run.get("error") or "flow_failed"
    result["run"] = {
        k: last_run.get(k)
        for k in (
            "returncode",
            "stdout",
            "stderr",
            "provider",
            "build_id",
            "dashboard_url",
            "status",
            "artifact_dir",
            "maestro_junit",
            "maestro_debug_dir",
            "maestro_output_dir",
        )
        if k in last_run
    }
    _p(result["summary"])
    return result

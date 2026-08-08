"""TestMu AI (formerly LambdaTest) Maestro via HyperExecute."""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import yaml

from mobiflow.cloud.base import (
    CloudCredentials,
    CloudProvider,
    CloudRunRequest,
    CloudRunResult,
    resolve_credentials,
    write_suite_dir,
)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None] | None

UPLOAD_REAL = "https://manual-api.lambdatest.com/app/upload/realDevice"
UPLOAD_VIRTUAL = "https://manual-api.lambdatest.com/app/upload/virtualDevice"

_HYPEREXECUTE_URLS = {
    "Linux": "https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute",
    "Darwin": "https://downloads.lambdatest.com/hyperexecute/darwin/hyperexecute",
    "Windows": "https://downloads.lambdatest.com/hyperexecute/windows/hyperexecute.exe",
}


def _auth(creds: CloudCredentials) -> tuple[str, str]:
    return (creds.username, creds.access_key)


def hyperexecute_bin_dir() -> Path:
    return Path.home() / ".mobiflow" / "bin"


def resolve_hyperexecute_binary() -> str | None:
    which = shutil.which("hyperexecute")
    if which:
        return which
    name = "hyperexecute.exe" if platform.system() == "Windows" else "hyperexecute"
    candidate = hyperexecute_bin_dir() / name
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


async def ensure_hyperexecute(progress: ProgressFn = None) -> str:
    existing = resolve_hyperexecute_binary()
    if existing:
        return existing
    system = platform.system()
    url = _HYPEREXECUTE_URLS.get(system)
    if not url:
        raise RuntimeError(f"No HyperExecute CLI download for OS={system}")
    dest_dir = hyperexecute_bin_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = "hyperexecute.exe" if system == "Windows" else "hyperexecute"
    dest = dest_dir / name
    if progress:
        progress(f"Downloading HyperExecute CLI ({system})…")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=300.0)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(dest)


async def upload_app(
    client: httpx.AsyncClient,
    creds: CloudCredentials,
    app_path: Path,
    *,
    real_mobile: bool = True,
    name: str = "mobiflow-app",
) -> str:
    if not app_path.is_file():
        raise FileNotFoundError(f"App not found: {app_path}")
    endpoint = UPLOAD_REAL if real_mobile else UPLOAD_VIRTUAL
    files = {"appFile": (app_path.name, app_path.read_bytes())}
    data = {"name": name}
    resp = await client.post(
        endpoint, auth=_auth(creds), data=data, files=files, timeout=600.0
    )
    resp.raise_for_status()
    payload = resp.json()
    url = payload.get("app_url") or payload.get("appUrl") or payload.get("app_id")
    if not url:
        raise RuntimeError(f"TestMu app upload missing app_url: {payload}")
    url = str(url)
    if not url.startswith("lt://") and url.startswith("APP"):
        url = f"lt://{url}"
    return url


def render_hyperexecute_yaml(
    *,
    platform: str,
    devices: list[str],
    app_url: str = "",
    app_path: str = "",
    build_name: str,
    real_mobile: bool,
    flow_relpath: str,
    project_label: str = "MobiFlow",
) -> str:
    plat = (platform or "android").lower()
    runson = "ios" if plat == "ios" else "android"
    args: dict[str, Any] = {
        "devices": devices,
        "video": True,
        "deviceLog": True,
        "buildName": build_name or "mobiflow-maestro",
        "queueTimeout": 600,
        "isRealMobile": bool(real_mobile),
        "network": True,
        "platformName": plat,
        "disableReleaseDevice": True,
        "reservation": False,
    }
    if app_url:
        args["appId"] = app_url
    elif app_path:
        args["appPath"] = app_path

    doc: dict[str, Any] = {
        "version": "0.2",
        "autosplit": True,
        "concurrency": 1,
        "runson": runson,
        "dynamicAllocation": True,
        "runtime": [{"language": "java", "version": "21"}],
        "framework": {"name": "raw", "args": args},
        "env": {"MAESTRO": True, "MAESTRO_LOGS_DIR": "MaestroLogs"},
        "pre": [
            "curl -Ls 'https://get.maestro.mobile.dev' | bash",
            "export PATH=\"$PATH:$HOME/.maestro/bin\"",
            "maestro --version || true",
        ],
        "testDiscovery": {
            "command": f"echo {flow_relpath}",
            "mode": "static",
            "type": "raw",
        },
        "testRunnerCommand": (
            'export PATH="$PATH:$HOME/.maestro/bin"; '
            "maestro test $test --format junit"
        ),
        "frameworkStatusOnly": True,
        "report": True,
        "partialReports": [
            {"location": ".", "type": "xml", "frameworkName": "junit"}
        ],
        "jobLabel": ["MobiFlow", "Maestro", project_label, plat],
    }
    return yaml.safe_dump(doc, sort_keys=False)


async def run_testmu(
    request: CloudRunRequest,
    *,
    progress: ProgressFn = None,
    artifact_dir: Path | None = None,
) -> CloudRunResult:
    creds = resolve_credentials(
        CloudProvider.TESTMU,
        username_env=request.username_env,
        access_key_env=request.access_key_env,
    )
    devices = list(request.devices)
    if not devices:
        return CloudRunResult(
            ok=False,
            provider="testmu",
            error="no_devices",
            stderr="device.device_id (cloud device name) is required for TestMu",
        )

    app_url = (request.app_url or "").strip()
    app_path_rel = ""
    flow_name = request.flow_name or "flow.yaml"

    try:
        hyperexecute = await ensure_hyperexecute(progress=progress)
    except Exception as e:  # noqa: BLE001
        return CloudRunResult(
            ok=False,
            provider="testmu",
            error="hyperexecute_missing",
            stderr=str(e),
        )

    with tempfile.TemporaryDirectory(prefix="mobiflow-testmu-") as tmp:
        root = Path(tmp)
        suite_dir = root / "maestro-suite"
        write_suite_dir(
            suite_dir,
            request.flow_yaml,
            request.scripts,
            flow_name=flow_name,
        )
        flow_relpath = f"maestro-suite/{flow_name}"

        # Prefer uploaded app_url; else upload local app_path; else copy app into job
        async with httpx.AsyncClient() as client:
            if not app_url and request.app_path:
                src = Path(request.app_path)
                if progress:
                    progress(f"Uploading app to TestMu: {src}")
                try:
                    app_url = await upload_app(
                        client,
                        creds,
                        src,
                        real_mobile=request.real_mobile,
                    )
                    if progress:
                        progress(f"App uploaded → {app_url}")
                except Exception as e:  # noqa: BLE001
                    # Fall back to shipping the binary with the HyperExecute job
                    logger.warning("TestMu upload failed (%s); using appPath in job", e)
                    dest = suite_dir / src.name
                    dest.write_bytes(src.read_bytes())
                    app_path_rel = f"maestro-suite/{src.name}"

        if not app_url and not app_path_rel and not request.app_path:
            return CloudRunResult(
                ok=False,
                provider="testmu",
                error="app_missing",
                stderr=(
                    "Set device.app_path (.apk/.ipa) or device.app_url (lt://…) "
                    "for TestMu."
                ),
            )

        he_yaml = render_hyperexecute_yaml(
            platform=request.platform,
            devices=devices,
            app_url=app_url,
            app_path=app_path_rel,
            build_name=request.build_name or "mobiflow-maestro",
            real_mobile=request.real_mobile,
            flow_relpath=flow_relpath,
            project_label=request.project or "MobiFlow",
        )
        he_path = root / "hyperexecute.yaml"
        he_path.write_text(he_yaml, encoding="utf-8")
        if progress:
            progress("Starting TestMu HyperExecute Maestro job…")

        env = dict(os.environ)
        env["LT_USERNAME"] = creds.username
        env["LT_ACCESS_KEY"] = creds.access_key
        env.setdefault("TESTMU_USERNAME", creds.username)
        env.setdefault("TESTMU_ACCESS_KEY", creds.access_key)

        args = [
            hyperexecute,
            "--user",
            creds.username,
            "--key",
            creds.access_key,
            "--config",
            str(he_path),
            "--no-track",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(root),
                env=env,
            )
        except FileNotFoundError as e:
            return CloudRunResult(
                ok=False,
                provider="testmu",
                error="hyperexecute_not_found",
                stderr=str(e),
            )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=float(request.timeout_s)
            )
        except TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return CloudRunResult(
                ok=False,
                provider="testmu",
                error="timeout",
                stderr=f"HyperExecute timed out after {request.timeout_s}s",
            )

        stdout = (stdout_b or b"").decode("utf-8", errors="replace")
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")
        code = proc.returncode if proc.returncode is not None else -1
        ok = code == 0
        # Best-effort job / dashboard extraction
        build_id = ""
        dash = "https://hyperexecute.lambdatest.com/hyperexecute"
        for line in (stdout + "\n" + stderr).splitlines():
            if "hyperexecute.lambdatest.com" in line or "testmuai.com" in line:
                for token in line.split():
                    if token.startswith("http"):
                        dash = token.strip(".,)'\"")
                        break
            if "Job Id" in line or "job id" in line.lower():
                parts = line.replace(":", " ").split()
                for i, p in enumerate(parts):
                    if p.lower() in {"id", "job"} and i + 1 < len(parts):
                        build_id = parts[i + 1]
        if progress:
            progress(
                f"TestMu HyperExecute finished rc={code}"
                + (f" · {dash}" if dash else "")
            )
        media_urls: list[dict[str, str]] = []
        media_files: list[str] = []
        media_dir = ""
        video_url = ""
        if artifact_dir is not None:
            try:
                from mobiflow.cloud.media import pull_testmu_media

                media_dest = Path(artifact_dir) / "cloud"
                media_index = await pull_testmu_media(
                    stdout,
                    stderr,
                    media_dest,
                    creds=creds,
                    progress=progress,
                )
                media_urls = list(media_index.get("urls") or [])
                media_files = list(media_index.get("files") or [])
                media_dir = str(media_dest)
                for item in media_urls:
                    if item.get("kind") == "video":
                        video_url = item.get("url") or ""
                        break
            except Exception as exc:  # noqa: BLE001
                logger.warning("TestMu media pull failed: %s", exc)

        return CloudRunResult(
            ok=ok,
            provider="testmu",
            build_id=build_id,
            status="passed" if ok else "failed",
            dashboard_url=dash,
            app_url=app_url,
            stdout=stdout,
            stderr=stderr,
            error=None if ok else "hyperexecute_failed",
            raw={"returncode": code, "hyperexecute_yaml": he_yaml},
            media_urls=media_urls,
            media_files=media_files,
            media_dir=media_dir,
            video_url=video_url,
        )

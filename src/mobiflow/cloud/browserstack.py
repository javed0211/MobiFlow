"""BrowserStack App Automate Maestro REST client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from mobiflow.cloud.base import (
    CloudCredentials,
    CloudRunRequest,
    CloudRunResult,
    resolve_credentials,
    zip_maestro_suite,
)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None] | None

API_BASE = "https://api-cloud.browserstack.com/app-automate"
UPLOAD_APP = f"{API_BASE}/upload"
UPLOAD_SUITE = f"{API_BASE}/maestro/v2/test-suite"
BUILD_ANDROID = f"{API_BASE}/maestro/v2/android/build"
BUILD_IOS = f"{API_BASE}/maestro/v2/ios/build"
BUILD_STATUS = f"{API_BASE}/maestro/v2/builds/{{build_id}}"

_TERMINAL_OK = {"passed", "completed", "success"}
_TERMINAL_FAIL = {
    "failed",
    "error",
    "timeout",
    "timedout",
    "skipped",
    "stopped",
    "cancelled",
    "canceled",
}


def _auth(creds: CloudCredentials) -> tuple[str, str]:
    return (creds.username, creds.access_key)


def _dashboard_url(build_id: str) -> str:
    return f"https://app-automate.browserstack.com/dashboard/v2/builds/{build_id}"


async def upload_app(
    client: httpx.AsyncClient,
    creds: CloudCredentials,
    app_path: Path,
    *,
    custom_id: str = "mobiflow-app",
) -> str:
    if not app_path.is_file():
        raise FileNotFoundError(f"App not found: {app_path}")
    data = {"custom_id": custom_id}
    files = {"file": (app_path.name, app_path.read_bytes())}
    resp = await client.post(
        UPLOAD_APP, auth=_auth(creds), data=data, files=files, timeout=600.0
    )
    resp.raise_for_status()
    payload = resp.json()
    url = payload.get("app_url") or payload.get("appUrl")
    if not url:
        raise RuntimeError(f"BrowserStack app upload missing app_url: {payload}")
    return str(url)


async def upload_test_suite(
    client: httpx.AsyncClient,
    creds: CloudCredentials,
    zip_bytes: bytes,
    *,
    custom_id: str = "mobiflow-suite",
) -> str:
    files = {"file": ("maestro_tests.zip", zip_bytes, "application/zip")}
    data = {"custom_id": custom_id}
    resp = await client.post(
        UPLOAD_SUITE, auth=_auth(creds), data=data, files=files, timeout=300.0
    )
    resp.raise_for_status()
    payload = resp.json()
    url = (
        payload.get("test_suite_url")
        or payload.get("testSuiteUrl")
        or payload.get("test_url")
    )
    if not url:
        raise RuntimeError(f"BrowserStack suite upload missing test_suite_url: {payload}")
    return str(url)


async def start_build(
    client: httpx.AsyncClient,
    creds: CloudCredentials,
    *,
    platform: str,
    app_url: str,
    test_suite_url: str,
    devices: list[str],
    project: str,
    execute: list[str],
    build_name: str = "",
    local: bool = False,
) -> str:
    plat = (platform or "android").lower()
    endpoint = BUILD_IOS if plat == "ios" else BUILD_ANDROID
    body: dict[str, Any] = {
        "app": app_url,
        "testSuite": test_suite_url,
        "devices": devices,
        "project": project or "MobiFlow",
        "execute": execute,
        "deviceLogs": True,
        "debugscreenshots": True,
    }
    if build_name:
        body["customBuildName"] = build_name
    if local:
        body["local"] = "true"
    resp = await client.post(
        endpoint,
        auth=_auth(creds),
        headers={"Content-Type": "application/json"},
        content=json.dumps(body),
        timeout=120.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    build_id = payload.get("build_id") or payload.get("buildId") or payload.get("id")
    if not build_id:
        raise RuntimeError(f"BrowserStack build start missing build_id: {payload}")
    return str(build_id)


async def get_build_status(
    client: httpx.AsyncClient,
    creds: CloudCredentials,
    build_id: str,
) -> dict[str, Any]:
    resp = await client.get(
        BUILD_STATUS.format(build_id=build_id),
        auth=_auth(creds),
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


def _status_is_terminal(status: str) -> bool:
    s = (status or "").strip().lower()
    return s in _TERMINAL_OK or s in _TERMINAL_FAIL or s in {"done", "finished"}


def _status_ok(status: str) -> bool:
    return (status or "").strip().lower() in _TERMINAL_OK | {"done", "finished"}


async def poll_build(
    client: httpx.AsyncClient,
    creds: CloudCredentials,
    build_id: str,
    *,
    timeout_s: float,
    poll_interval_s: float,
    progress: ProgressFn = None,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    last: dict[str, Any] = {}
    while True:
        last = await get_build_status(client, creds, build_id)
        status = str(last.get("status") or "")
        if progress:
            progress(f"BrowserStack build {build_id[:12]}… status={status}")
        if _status_is_terminal(status):
            return last
        if loop.time() >= deadline:
            last["_mobiflow_error"] = "timeout"
            return last
        await asyncio.sleep(max(2.0, poll_interval_s))


async def run_browserstack(
    request: CloudRunRequest,
    *,
    progress: ProgressFn = None,
    artifact_dir: Path | None = None,
) -> CloudRunResult:
    creds = resolve_credentials(
        request.provider,
        username_env=request.username_env,
        access_key_env=request.access_key_env,
    )
    devices = list(request.devices)
    if not devices:
        return CloudRunResult(
            ok=False,
            provider="browserstack",
            error="no_devices",
            stderr="device.device_id (cloud device name) is required for BrowserStack",
        )

    app_url = (request.app_url or "").strip()
    flow_name = request.flow_name or "flow.yaml"

    async with httpx.AsyncClient() as client:
        if not app_url:
            if not request.app_path:
                return CloudRunResult(
                    ok=False,
                    provider="browserstack",
                    error="app_missing",
                    stderr=(
                        "Set device.app_path (.apk/.ipa) or device.app_url (bs://…) "
                        "for BrowserStack."
                    ),
                )
            if progress:
                progress(f"Uploading app to BrowserStack: {request.app_path}")
            app_url = await upload_app(client, creds, Path(request.app_path))
            if progress:
                progress(f"App uploaded → {app_url}")

        if progress:
            progress("Uploading Maestro test suite to BrowserStack…")
        zip_bytes = zip_maestro_suite(
            request.flow_yaml,
            request.scripts,
            flow_name=flow_name,
        )
        suite_url = await upload_test_suite(client, creds, zip_bytes)
        if progress:
            progress(f"Test suite uploaded → {suite_url}")

        if progress:
            progress(f"Starting BrowserStack Maestro build on {devices}…")
        build_id = await start_build(
            client,
            creds,
            platform=request.platform,
            app_url=app_url,
            test_suite_url=suite_url,
            devices=devices,
            project=request.project,
            execute=[flow_name],
            build_name=request.build_name,
            local=request.local,
        )
        dash = _dashboard_url(build_id)
        if progress:
            progress(f"Build started id={build_id} · {dash}")

        final = await poll_build(
            client,
            creds,
            build_id,
            timeout_s=float(request.timeout_s),
            poll_interval_s=request.poll_interval_s,
            progress=progress,
        )

    status = str(final.get("status") or "")
    ok = _status_ok(status) and not final.get("_mobiflow_error")
    err = None
    if final.get("_mobiflow_error") == "timeout":
        err = "timeout"
        ok = False
    elif not ok:
        err = f"build_{status or 'failed'}"

    summary = json.dumps(
        {
            "build_id": build_id,
            "status": status,
            "devices": final.get("devices"),
            "dashboard": dash,
        },
        indent=2,
    )
    media_urls: list[dict[str, str]] = []
    media_files: list[str] = []
    media_dir = ""
    video_url = ""
    if artifact_dir is not None and build_id:
        try:
            from mobiflow.cloud.media import pull_browserstack_media

            media_dest = Path(artifact_dir) / "cloud"
            media_index = await pull_browserstack_media(
                creds,
                build_id,
                final,
                media_dest,
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
            logger.warning("BrowserStack media pull failed: %s", exc)

    return CloudRunResult(
        ok=ok,
        provider="browserstack",
        build_id=build_id,
        status=status,
        dashboard_url=dash,
        app_url=app_url,
        test_suite_url=suite_url,
        stdout=summary,
        stderr="" if ok else summary,
        error=err,
        raw=final,
        media_urls=media_urls,
        media_files=media_files,
        media_dir=media_dir,
        video_url=video_url,
    )

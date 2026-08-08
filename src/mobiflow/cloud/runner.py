"""Dispatch Maestro runs to BrowserStack or TestMu."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from mobiflow.cloud.base import (
    CloudProvider,
    CloudRunRequest,
    CloudRunResult,
    devices_from_config,
    is_cloud_provider,
    normalize_provider,
    resolve_credentials,
)
from mobiflow.cloud.browserstack import run_browserstack
from mobiflow.cloud.testmu import resolve_hyperexecute_binary, run_testmu

ProgressFn = Callable[[str], None] | None


def cloud_readiness(device_cfg: Any) -> dict[str, Any]:
    """Report whether cloud credentials / tools are ready for device.provider."""
    provider_raw = getattr(device_cfg, "provider", "local") or "local"
    try:
        provider = normalize_provider(provider_raw)
    except ValueError as e:
        return {
            "provider": str(provider_raw),
            "cloud": False,
            "ready": False,
            "message": str(e),
        }
    if not is_cloud_provider(provider):
        return {
            "provider": "local",
            "cloud": False,
            "ready": True,
            "message": "Using local adb / simulators",
        }

    info: dict[str, Any] = {
        "provider": provider.value,
        "cloud": True,
        "ready": False,
        "app_path": getattr(device_cfg, "app_path", "") or "",
        "app_url": getattr(device_cfg, "app_url", "") or "",
        "device_id": getattr(device_cfg, "device_id", None),
        "real_mobile": bool(getattr(device_cfg, "real_mobile", True)),
    }
    try:
        creds = resolve_credentials(
            provider,
            username_env=getattr(device_cfg, "username_env", "") or "",
            access_key_env=getattr(device_cfg, "access_key_env", "") or "",
        )
        info["username_env"] = creds.username_env
        info["access_key_env"] = creds.access_key_env
        info["credentials"] = True
    except ValueError as e:
        info["credentials"] = False
        info["message"] = str(e)
        return info

    if provider == CloudProvider.TESTMU:
        he = resolve_hyperexecute_binary()
        info["hyperexecute"] = he or ""
        # CLI can be auto-downloaded on first run
        info["hyperexecute_installable"] = True

    has_app = bool(info["app_path"] or info["app_url"])
    if not has_app:
        info["message"] = "Set device.app_path or device.app_url for cloud runs"
        return info

    device_label = (info.get("device_id") or "").strip() or "(provider default)"
    info["ready"] = True
    info["message"] = f"{provider.value} credentials OK · device={device_label}"
    return info


def request_from_device_config(
    device_cfg: Any,
    *,
    flow_yaml: str,
    scripts: dict[str, str] | None = None,
    platform: str | None = None,
    device_id: str | None = None,
    timeout_s: int | None = None,
    flow_name: str = "flow.yaml",
) -> CloudRunRequest:
    provider = normalize_provider(getattr(device_cfg, "provider", "local"))
    plat = (platform or getattr(device_cfg, "platform", "android") or "android").lower()
    did = device_id if device_id is not None else getattr(device_cfg, "device_id", None)
    devices = devices_from_config(did, platform=plat, provider=provider)
    # Cloud runs can be long; default 30 min unless overridden
    t = timeout_s if timeout_s is not None else 1800
    run_timeout = getattr(device_cfg, "cloud_timeout_s", None)
    if run_timeout:
        t = int(run_timeout)
    return CloudRunRequest(
        provider=provider,
        platform=plat,
        flow_yaml=flow_yaml,
        scripts=dict(scripts or {}),
        devices=devices,
        app_path=(getattr(device_cfg, "app_path", "") or "").strip(),
        app_url=(getattr(device_cfg, "app_url", "") or "").strip(),
        project=(getattr(device_cfg, "cloud_project", "") or "MobiFlow").strip()
        or "MobiFlow",
        build_name=(getattr(device_cfg, "cloud_build_name", "") or "").strip(),
        real_mobile=bool(getattr(device_cfg, "real_mobile", True)),
        username_env=(getattr(device_cfg, "username_env", "") or "").strip(),
        access_key_env=(getattr(device_cfg, "access_key_env", "") or "").strip(),
        timeout_s=int(t),
        poll_interval_s=float(getattr(device_cfg, "poll_interval_s", 15.0) or 15.0),
        local=bool(getattr(device_cfg, "browserstack_local", False)),
        flow_name=flow_name,
    )


async def run_on_cloud(
    request: CloudRunRequest,
    *,
    progress: ProgressFn = None,
) -> CloudRunResult:
    if request.provider == CloudProvider.BROWSERSTACK:
        return await run_browserstack(request, progress=progress)
    if request.provider == CloudProvider.TESTMU:
        return await run_testmu(request, progress=progress)
    return CloudRunResult(
        ok=False,
        provider=str(request.provider),
        error="not_cloud",
        stderr=f"Provider {request.provider} is not a cloud lab",
    )


def env_present(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())

"""Shared types and helpers for cloud Maestro runners."""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CloudProvider(str, Enum):
    LOCAL = "local"
    BROWSERSTACK = "browserstack"
    TESTMU = "testmu"


_PROVIDER_ALIASES = {
    "local": CloudProvider.LOCAL,
    "none": CloudProvider.LOCAL,
    "": CloudProvider.LOCAL,
    "browserstack": CloudProvider.BROWSERSTACK,
    "bs": CloudProvider.BROWSERSTACK,
    "bstack": CloudProvider.BROWSERSTACK,
    "testmu": CloudProvider.TESTMU,
    "testmuai": CloudProvider.TESTMU,
    "testmu-ai": CloudProvider.TESTMU,
    "lambdatest": CloudProvider.TESTMU,
    "lt": CloudProvider.TESTMU,
}


def normalize_provider(value: str | None) -> CloudProvider:
    key = (value or "local").strip().lower().replace("_", "-")
    if key not in _PROVIDER_ALIASES:
        raise ValueError(
            f"Unknown device.provider {value!r}. "
            "Use: local | browserstack | testmu"
        )
    return _PROVIDER_ALIASES[key]


def is_cloud_provider(value: str | CloudProvider | None) -> bool:
    if isinstance(value, CloudProvider):
        return value in (CloudProvider.BROWSERSTACK, CloudProvider.TESTMU)
    try:
        return normalize_provider(value) in (
            CloudProvider.BROWSERSTACK,
            CloudProvider.TESTMU,
        )
    except ValueError:
        return False


@dataclass
class CloudCredentials:
    username: str
    access_key: str
    username_env: str
    access_key_env: str


def default_credential_env_names(provider: CloudProvider) -> tuple[str, str]:
    if provider == CloudProvider.BROWSERSTACK:
        return "BROWSERSTACK_USERNAME", "BROWSERSTACK_ACCESS_KEY"
    if provider == CloudProvider.TESTMU:
        # Prefer TestMu names; fall back to legacy LambdaTest names at resolve time.
        return "TESTMU_USERNAME", "TESTMU_ACCESS_KEY"
    return "", ""


def resolve_credentials(
    provider: CloudProvider,
    *,
    username_env: str = "",
    access_key_env: str = "",
) -> CloudCredentials:
    user_env, key_env = default_credential_env_names(provider)
    if (username_env or "").strip():
        user_env = username_env.strip()
    if (access_key_env or "").strip():
        key_env = access_key_env.strip()

    username = os.environ.get(user_env, "").strip()
    access_key = os.environ.get(key_env, "").strip()

    # TestMu rebrand: also accept LT_* when TESTMU_* unset
    if provider == CloudProvider.TESTMU:
        if not username:
            for alt in ("LT_USERNAME", "LAMBDATEST_USERNAME"):
                username = os.environ.get(alt, "").strip()
                if username:
                    user_env = alt
                    break
        if not access_key:
            for alt in ("LT_ACCESS_KEY", "LAMBDATEST_ACCESS_KEY"):
                access_key = os.environ.get(alt, "").strip()
                if access_key:
                    key_env = alt
                    break

    if not username or not access_key:
        raise ValueError(
            f"Cloud credentials missing for {provider.value}. "
            f"Export ${user_env} and ${key_env}"
            + (
                " (or LT_USERNAME / LT_ACCESS_KEY)."
                if provider == CloudProvider.TESTMU
                else "."
            )
        )
    return CloudCredentials(
        username=username,
        access_key=access_key,
        username_env=user_env,
        access_key_env=key_env,
    )


@dataclass
class CloudRunRequest:
    provider: CloudProvider
    platform: str  # android | ios
    flow_yaml: str
    scripts: dict[str, str] = field(default_factory=dict)
    devices: list[str] = field(default_factory=list)
    app_path: str = ""
    app_url: str = ""  # bs://… or lt://…
    project: str = "MobiFlow"
    build_name: str = ""
    real_mobile: bool = True
    username_env: str = ""
    access_key_env: str = ""
    timeout_s: int = 1800
    poll_interval_s: float = 15.0
    local: bool = False  # BrowserStack local testing flag
    flow_name: str = "flow.yaml"


@dataclass
class CloudRunResult:
    ok: bool
    provider: str
    build_id: str = ""
    status: str = ""
    dashboard_url: str = ""
    app_url: str = ""
    test_suite_url: str = ""
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def as_run_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "returncode": 0 if self.ok else 1,
            "stdout": self.stdout,
            "stderr": self.stderr or (self.error or ""),
            "error": None if self.ok else (self.error or "cloud_run_failed"),
            "provider": self.provider,
            "build_id": self.build_id,
            "status": self.status,
            "dashboard_url": self.dashboard_url,
            "app_url": self.app_url,
            "test_suite_url": self.test_suite_url,
            "raw": self.raw,
        }


def zip_maestro_suite(
    flow_yaml: str,
    scripts: dict[str, str] | None = None,
    *,
    flow_name: str = "flow.yaml",
    folder_name: str = "tests",
) -> bytes:
    """Zip Maestro flows for BrowserStack (parent folder required)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{folder_name}/{flow_name}", flow_yaml)
        for rel, body in (scripts or {}).items():
            # Keep scripts under the same parent folder
            clean = rel.replace("\\", "/").lstrip("/")
            zf.writestr(f"{folder_name}/{clean}", body)
    return buf.getvalue()


def write_suite_dir(
    root: Path,
    flow_yaml: str,
    scripts: dict[str, str] | None = None,
    *,
    flow_name: str = "flow.yaml",
) -> Path:
    """Write flow + scripts under root; return path to the flow file."""
    root.mkdir(parents=True, exist_ok=True)
    flow_path = root / flow_name
    flow_path.write_text(flow_yaml, encoding="utf-8")
    for rel, body in (scripts or {}).items():
        sp = root / rel
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(body, encoding="utf-8")
    return flow_path


def devices_from_config(
    device_id: str | None,
    *,
    platform: str,
    provider: CloudProvider,
) -> list[str]:
    """Resolve cloud device list from device_id (comma-separated OK)."""
    raw = (device_id or "").strip()
    if raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if parts:
            return parts
    # Sensible defaults for smoke / first-run
    if provider == CloudProvider.BROWSERSTACK:
        if (platform or "").lower() == "ios":
            return ["iPhone 15-17.0"]
        return ["Google Pixel 7-13.0"]
    # TestMu HyperExecute device strings
    if (platform or "").lower() == "ios":
        return ["iPhone 15"]
    return ["Pixel 6-14"]

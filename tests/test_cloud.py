"""Unit tests for BrowserStack / TestMu cloud helpers (mocked HTTP)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from mobiflow.cloud.base import (
    CloudProvider,
    CloudRunRequest,
    devices_from_config,
    is_cloud_provider,
    normalize_provider,
    resolve_credentials,
    zip_maestro_suite,
)
from mobiflow.cloud.runner import cloud_readiness, request_from_device_config
from mobiflow.cloud.testmu import render_hyperexecute_yaml
from mobiflow.config import DeviceConfig, MobiflowConfig


def test_normalize_provider_aliases():
    assert normalize_provider("bs") is CloudProvider.BROWSERSTACK
    assert normalize_provider("lambdatest") is CloudProvider.TESTMU
    assert normalize_provider("testmu") is CloudProvider.TESTMU
    assert normalize_provider("maestro") is CloudProvider.MAESTRO
    assert normalize_provider("local") is CloudProvider.LOCAL
    assert is_cloud_provider("browserstack")
    assert is_cloud_provider("maestro")
    assert not is_cloud_provider("local")


def test_device_config_provider_validation():
    d = DeviceConfig(provider="BrowserStack", platform="android")
    assert d.provider == "browserstack"
    assert d.is_cloud()
    with pytest.raises(ValidationError):
        DeviceConfig(provider="sauce")


def test_zip_maestro_suite_structure():
    raw = zip_maestro_suite(
        "appId: com.example\n---\n- launchApp\n",
        {"scripts/helpers.js": "output.x = 1;"},
        flow_name="flow.yaml",
    )
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = set(zf.namelist())
    assert "tests/flow.yaml" in names
    assert "tests/scripts/helpers.js" in names


def test_devices_from_config_defaults():
    assert devices_from_config(
        "Pixel 7-13.0, Pixel 8-14.0",
        platform="android",
        provider=CloudProvider.BROWSERSTACK,
    ) == ["Pixel 7-13.0", "Pixel 8-14.0"]
    assert "Pixel" in devices_from_config(
        None, platform="android", provider=CloudProvider.TESTMU
    )[0]


def test_resolve_credentials_browserstack(monkeypatch):
    monkeypatch.setenv("BROWSERSTACK_USERNAME", "user")
    monkeypatch.setenv("BROWSERSTACK_ACCESS_KEY", "key")
    creds = resolve_credentials(CloudProvider.BROWSERSTACK)
    assert creds.username == "user"
    assert creds.access_key == "key"


def test_resolve_credentials_testmu_lt_fallback(monkeypatch):
    monkeypatch.delenv("TESTMU_USERNAME", raising=False)
    monkeypatch.delenv("TESTMU_ACCESS_KEY", raising=False)
    monkeypatch.setenv("LT_USERNAME", "lt-user")
    monkeypatch.setenv("LT_ACCESS_KEY", "lt-key")
    creds = resolve_credentials(CloudProvider.TESTMU)
    assert creds.username == "lt-user"
    assert creds.access_key == "lt-key"
    assert creds.username_env == "LT_USERNAME"


def test_cloud_readiness_missing_creds(monkeypatch):
    for k in (
        "BROWSERSTACK_USERNAME",
        "BROWSERSTACK_ACCESS_KEY",
        "TESTMU_USERNAME",
        "TESTMU_ACCESS_KEY",
        "LT_USERNAME",
        "LT_ACCESS_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    cfg = DeviceConfig(
        provider="browserstack",
        app_path="app.apk",
        device_id="Google Pixel 7-13.0",
    )
    ready = cloud_readiness(cfg)
    assert ready["cloud"] is True
    assert ready["ready"] is False
    assert "credentials" in (ready.get("message") or "").lower() or ready.get(
        "credentials"
    ) is False


def test_cloud_readiness_ok(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BROWSERSTACK_USERNAME", "user")
    monkeypatch.setenv("BROWSERSTACK_ACCESS_KEY", "key")
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"fake")
    cfg = DeviceConfig(
        provider="browserstack",
        app_path=str(apk),
        device_id="Google Pixel 7-13.0",
    )
    ready = cloud_readiness(cfg)
    assert ready["ready"] is True


def test_render_hyperexecute_yaml_contains_maestro():
    text = render_hyperexecute_yaml(
        platform="android",
        devices=["Pixel 6-14"],
        app_url="lt://APP123",
        build_name="mobiflow",
        real_mobile=True,
        flow_relpath="maestro-suite/flow.yaml",
    )
    assert "maestro test" in text
    assert "lt://APP123" in text
    assert "Pixel 6-14" in text


def test_request_from_device_config():
    cfg = DeviceConfig(
        provider="testmu",
        platform="android",
        device_id="Pixel 6-14",
        app_url="lt://APP1",
        cloud_project="Demo",
        real_mobile=False,
    )
    req = request_from_device_config(
        cfg,
        flow_yaml="appId: x\n---\n- launchApp\n",
        scripts={},
    )
    assert req.provider is CloudProvider.TESTMU
    assert req.devices == ["Pixel 6-14"]
    assert req.app_url == "lt://APP1"
    assert req.real_mobile is False
    assert req.project == "Demo"


def test_run_browserstack_mocked(monkeypatch, tmp_path: Path):
    import asyncio

    from mobiflow.cloud import browserstack as bs

    monkeypatch.setenv("BROWSERSTACK_USERNAME", "user")
    monkeypatch.setenv("BROWSERSTACK_ACCESS_KEY", "key")
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"apk")

    mock_client = AsyncMock()
    # upload app
    app_resp = MagicMock()
    app_resp.raise_for_status = MagicMock()
    app_resp.json.return_value = {"app_url": "bs://apphash"}
    # upload suite
    suite_resp = MagicMock()
    suite_resp.raise_for_status = MagicMock()
    suite_resp.json.return_value = {"test_suite_url": "bs://suitehash"}
    # start build
    build_resp = MagicMock()
    build_resp.raise_for_status = MagicMock()
    build_resp.json.return_value = {"build_id": "build123", "message": "Success"}
    # poll status — passed
    status_resp = MagicMock()
    status_resp.raise_for_status = MagicMock()
    status_resp.json.return_value = {"status": "passed", "id": "build123"}

    mock_client.post = AsyncMock(side_effect=[app_resp, suite_resp, build_resp])
    mock_client.get = AsyncMock(return_value=status_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def _run():
        with patch.object(bs.httpx, "AsyncClient", return_value=mock_client):
            return await bs.run_browserstack(
                CloudRunRequest(
                    provider=CloudProvider.BROWSERSTACK,
                    platform="android",
                    flow_yaml="appId: com.example\n---\n- launchApp\n",
                    devices=["Google Pixel 7-13.0"],
                    app_path=str(apk),
                    project="MobiFlow",
                    timeout_s=60,
                    poll_interval_s=0.01,
                )
            )

    result = asyncio.run(_run())
    assert result.ok is True
    assert result.build_id == "build123"
    assert result.app_url == "bs://apphash"
    assert "browserstack.com" in result.dashboard_url


def test_config_warnings_cloud(monkeypatch):
    monkeypatch.delenv("BROWSERSTACK_USERNAME", raising=False)
    monkeypatch.delenv("BROWSERSTACK_ACCESS_KEY", raising=False)
    cfg = MobiflowConfig(
        device=DeviceConfig(
            provider="browserstack",
            app_path="app.apk",
            device_id="Google Pixel 7-13.0",
        )
    )
    from mobiflow.config import config_warnings

    warns = config_warnings(cfg)
    assert any("BROWSERSTACK" in w or "credentials" in w.lower() or "Cloud" in w for w in warns)

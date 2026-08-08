"""Tests for app install / clearState preflight helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mobiflow.config import RunConfig
from mobiflow.maestro.lifecycle import (
    build_preflight_flow_yaml,
    install_app_local,
    normalize_preflight,
    run_preflight,
)


def test_normalize_preflight():
    assert normalize_preflight("install, clear") == ["install", "clear"]
    assert normalize_preflight(["clearState", "INSTALL"]) == ["clear", "install"]
    assert normalize_preflight("none") == []
    assert RunConfig(preflight="clear").preflight == ["clear"]


def test_build_preflight_flow_yaml_android():
    yaml_text = build_preflight_flow_yaml("com.example.app", clear_state=True)
    assert "appId: com.example.app" in yaml_text
    assert "- clearState" in yaml_text
    assert "- stopApp" in yaml_text
    assert "clearKeychain" not in yaml_text


def test_build_preflight_flow_yaml_ios_keychain():
    yaml_text = build_preflight_flow_yaml(
        "org.example",
        clear_state=True,
        clear_keychain=True,
        platform="ios",
    )
    assert "- clearKeychain" in yaml_text


def test_install_app_missing_file(tmp_path: Path):
    result = asyncio.run(install_app_local(tmp_path / "missing.apk"))
    assert result["ok"] is False
    assert result["error"] == "app_not_found"


def test_install_app_adb_success(tmp_path: Path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"apk")

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return b"Success\n", b""

    async def fake_exec(*args, **kwargs):
        assert "install" in args
        assert str(apk) in args
        return FakeProc()

    with (
        patch("mobiflow.maestro.lifecycle.resolve_adb", return_value="/usr/bin/adb"),
        patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
    ):
        result = asyncio.run(
            install_app_local(apk, device_id="emulator-5554", platform="android")
        )
    assert result["ok"] is True
    assert result["error"] == ""


def test_run_preflight_clear_only():
    runner = AsyncMock(return_value={"ok": True})

    async def _run():
        return await run_preflight(
            app_id="com.android.settings",
            platform="android",
            device_id="emulator-5554",
            steps=["clear"],
            run_flow_yaml=runner,
        )

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert result["steps"] == ["clear"]
    runner.assert_awaited_once()
    flow = runner.await_args.args[0]
    assert "clearState" in flow

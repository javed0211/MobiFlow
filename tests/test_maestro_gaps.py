"""Tests for Maestro alignment gaps: tags, config, video discovery, provider."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mobiflow.cloud.base import CloudProvider, is_cloud_provider, normalize_provider
from mobiflow.config import DeviceConfig, RunConfig
from mobiflow.maestro import (
    _maestro_test_args,
    _run_cmd,
    android_serial_env,
    find_local_videos,
    maestro_global_args,
    prepare_exec_args,
)


def test_normalize_provider_maestro():
    assert normalize_provider("maestro") is CloudProvider.MAESTRO
    assert normalize_provider("maestro-cloud") is CloudProvider.MAESTRO
    assert is_cloud_provider("maestro")
    d = DeviceConfig(provider="maestro", platform="android")
    assert d.is_cloud()
    assert d.provider == "maestro"


def test_run_config_video_and_tags():
    r = RunConfig(
        video=False,
        include_tags="smoke,regression",
        exclude_tags=["wip"],
        maestro_config="/tmp/config.yaml",
    )
    assert r.video is False
    assert r.include_tags == ["smoke", "regression"]
    assert r.exclude_tags == ["wip"]
    assert r.maestro_config == "/tmp/config.yaml"


def test_maestro_test_args_tags_platform_config(tmp_path: Path):
    flow = tmp_path / "flow.yaml"
    flow.write_text("appId: com.example\n---\n- launchApp\n", encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("flows: []\n", encoding="utf-8")
    art = tmp_path / "art"

    args = _maestro_test_args(
        "maestro",
        flow,
        device_id="emulator-5554",
        artifact_dir=art,
        include_tags=["smoke", "android"],
        exclude_tags=["flaky"],
        maestro_config=cfg,
        platform="android",
    )
    joined = " ".join(args)
    assert args[:6] == [
        "maestro",
        "--device",
        "emulator-5554",
        "--platform",
        "android",
        "test",
    ]
    assert args.index("--device") < args.index("test")
    assert "--platform" in args and "android" in args
    assert "--include-tags=smoke,android" in args
    assert "--exclude-tags=flaky" in args
    assert "--config" in args and str(cfg) in args
    assert "--debug-output" in joined
    assert "--format" in args and "JUNIT" in args


def test_find_local_videos(tmp_path: Path):
    nested = tmp_path / "maestro-output" / "recordings"
    nested.mkdir(parents=True)
    mp4 = nested / "run.mp4"
    mp4.write_bytes(b"fake")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    found = find_local_videos(tmp_path)
    assert found == [mp4]
    assert find_local_videos(tmp_path / "missing") == []


def test_maestro_global_args_before_subcommand():
    args = maestro_global_args("maestro", device_id="emulator-5554", platform="android")
    args.extend(["record", "--local", "flow.yaml", "out.mp4"])
    assert args[:6] == [
        "maestro",
        "--device",
        "emulator-5554",
        "--platform",
        "android",
        "record",
    ]


def test_prepare_exec_args_quotes_ampersand_on_windows(monkeypatch):
    monkeypatch.setattr("mobiflow.maestro.os.name", "nt")
    raw = [
        r"C:\maestro\bin\maestro.cmd",
        "--device",
        "R58M123",
        "test",
        r"C:\Users\me\OneDrive - Capgemini\flow.yaml",
        "--env",
        "API_BASE=https://api.example.com/users?page=1&limit=10",
    ]
    wrapped = prepare_exec_args(raw)
    assert wrapped[1:4] == ["/d", "/S", "/C"]
    # Each Maestro argv stays its own token so cmd.exe cannot drop --device
    assert "--device" in wrapped
    assert "R58M123" in wrapped
    env = next(a for a in wrapped if "limit=10" in a)
    assert "^&limit=10" in env
    assert not env.startswith('"')
    flow = next(a for a in wrapped if "flow.yaml" in a)
    assert "OneDrive - Capgemini" in flow
    # Quotes must not be part of the path Maestro opens
    assert not flow.startswith('"')
    assert '"' not in flow


def test_prepare_exec_args_noop_on_posix():
    raw = ["maestro", "test", "flow.yaml", "--env", "API_BASE=https://x?a=1&limit=10"]
    assert prepare_exec_args(raw) == raw


def test_android_serial_env_pins_usb_and_emulator():
    assert android_serial_env("R58M123") == {"ANDROID_SERIAL": "R58M123"}
    assert android_serial_env("emulator-5554") == {"ANDROID_SERIAL": "emulator-5554"}
    assert android_serial_env("8B9754B2-AD59-476F-924E-E243FAA609EB") is None
    assert android_serial_env("") is None


def test_run_cmd_does_not_close_streamreader():
    """asyncio Process.stdout is a StreamReader — it has no close() (Windows crash)."""
    result = asyncio.run(
        _run_cmd([sys.executable, "-c", "import sys; sys.stdout.write('ok')"], timeout=20.0)
    )
    assert result["error"] != "executable_not_found"
    assert result["ok"] is True
    assert "ok" in (result.get("stdout") or "")

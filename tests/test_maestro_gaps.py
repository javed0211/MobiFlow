"""Tests for Maestro alignment gaps: tags, config, video discovery, provider."""

from __future__ import annotations

from pathlib import Path

from mobiflow.cloud.base import CloudProvider, is_cloud_provider, normalize_provider
from mobiflow.config import DeviceConfig, RunConfig
from mobiflow.maestro import _maestro_test_args, find_local_videos


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
    assert args[0:2] == ["maestro", "test"]
    assert "--device" in args and "emulator-5554" in args
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

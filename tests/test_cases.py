from pathlib import Path

import pytest

from mobiflow.cases import parse_case_text, resolve_run_options
from mobiflow.config import (
    DeviceConfig,
    LlmConfig,
    MobiflowConfig,
    ProjectConfig,
    RunConfig,
    StackConfig,
)
from mobiflow.maestro import ensure_flow_yaml, looks_like_maestro_yaml, resolve_app_id


def test_parse_intent_case():
    c = parse_case_text(
        """
appId: org.wikipedia
platform: android
task: Open Wikipedia and confirm Search
"""
    )
    assert c.app_id == "org.wikipedia"
    assert c.platform == "android"
    assert "Search" in c.task


def test_parse_multiple_tags_on_one_line():
    c = parse_case_text(
        """
@cloud @browserstack
appId: org.wikipedia
platform: android
task: Open Search
"""
    )
    assert c.tags == ["cloud", "browserstack"]
    assert c.has_tag("cloud")
    assert c.has_tag("browserstack")


def test_parse_guided_steps():
    c = parse_case_text(
        """
@smoke
appId: com.android.settings
platform: android

1. Launch Settings
2. Confirm Network is visible
"""
    )
    assert c.tags == ["smoke"]
    assert len(c.steps) == 2
    assert "Launch Settings" in c.explore_task()


def test_parse_run_knobs():
    c = parse_case_text(
        """
appId: org.wikipedia
platform: ios
codegen: false
retries: 2
heal: 1
explore: false
timeout: 240
task: |
  1. Open Wikipedia
  2. Confirm Search
"""
    )
    assert c.run.codegen is False
    assert c.run.retries == 2
    assert c.run.heal == 1
    assert c.run.explore is False
    assert c.run.timeout_s == 240
    assert len(c.guidance_steps()) == 2


def test_unknown_key_warns_strict_raises():
    soft = parse_case_text(
        """
appId: x
platform: android
retyr: 2
task: Open Settings
"""
    )
    assert soft.parse_warnings
    assert "retyr" in soft.parse_warnings[0]

    with pytest.raises(ValueError, match="retyr"):
        parse_case_text(
            """
strict: true
appId: x
platform: android
retyr: 2
task: Open Settings
"""
        )


def test_exclusive_modes_on_case():
    with pytest.raises(ValueError, match="exclusive"):
        parse_case_text(
            """
appId: x
platform: android
reuseFlow: true
incremental: true
task: Open Settings
"""
        )


def test_resolve_cli_over_case_over_config(tmp_path: Path):
    cfg = MobiflowConfig(
        project=ProjectConfig(path=str(tmp_path)),
        llm=LlmConfig(),
        stack=StackConfig(),
        device=DeviceConfig(),
        run=RunConfig(heal=3, retries=0, reuse_flow=False, explore=True),
    )
    case = parse_case_text(
        """
appId: x
platform: android
codegen: false
retries: 2
heal: 1
task: Open Settings
"""
    )
    # Case wins over config
    opts = resolve_run_options(case, cfg)
    assert opts.reuse_flow is True
    assert opts.retries == 2
    assert opts.heal == 1
    assert opts.sources["retries"] == "case"

    # CLI wins over case
    opts2 = resolve_run_options(case, cfg, reuse_flow=False, no_heal=True)
    assert opts2.reuse_flow is False
    assert opts2.heal == 0
    assert opts2.sources["reuse_flow"] == "cli"


def test_inline_comment_on_meta():
    c = parse_case_text(
        """
appId: org.wikipedia
platform: android
codegen: true   # freeze later
retries: 1      # flake
data: data/example.json  # relative
task: Open Search
"""
    )
    assert c.run.codegen is True
    assert c.run.retries == 1
    assert c.data_path == "data/example.json"


def test_maestro_yaml_helpers():
    assert looks_like_maestro_yaml("appId: x\n---\n- launchApp\n")
    y = ensure_flow_yaml("- launchApp\n", "org.wikipedia")
    assert y.startswith("appId: org.wikipedia")
    assert resolve_app_id("", "android", "open wikipedia") == "org.wikipedia"
    assert resolve_app_id("", "ios", "open wikipedia") == "org.wikimedia.wikipedia"
    assert resolve_app_id("", "android", "launch joplin notes") == "net.cozic.joplin"
    assert resolve_app_id("", "ios", "open Joplin") == "net.cozic.joplin"
    assert resolve_app_id("", "android", "open bitwarden vault") == "com.x8bit.bitwarden"
    assert resolve_app_id("", "ios", "bitwarden login") == "com.8bit.bitwarden"
    assert resolve_app_id("", "android", "open wdio native demo") == "com.wdiodemoapp"
    assert resolve_app_id("", "android", "launch proverbial") == "com.lambdatest.proverbial"
    assert resolve_app_id("", "ios", "open testmu sample") == "com.lambdatest.proverbial"
    assert resolve_app_id("", "android", "Open Go Grocery and sign in") == ""
    assert resolve_app_id("", "android", "Hit GET /v1/users then open the grocery app") == ""


def test_load_cloud_sample_cases():
    from mobiflow.cases import load_case

    root = Path(__file__).resolve().parents[1]
    bs = load_case(root / "cases" / "android_browserstack_smoke.txt")
    assert bs.provider == "browserstack"
    assert bs.app_path == "builds/browserstack.apk"
    assert bs.app_id == "org.wikipedia"
    assert bs.has_tag("cloud")

    tm = load_case(root / "cases" / "android_testmu_smoke.txt")
    assert tm.provider == "testmu"
    assert tm.app_path == "builds/testmu.apk"
    assert tm.app_id == "com.lambdatest.proverbial"
    assert tm.real_mobile is True
    assert tm.has_tag("proverbial")


def test_parse_cloud_case_device_overlay():
    from mobiflow.cases import overlay_device_config

    c = parse_case_text(
        """
@cloud @browserstack
appId: org.wikipedia
platform: android
provider: bs
device: Google Pixel 7-13.0
appPath: builds/browserstack.apk
appUrl: bs://abc
realMobile: true
task: Open Search
"""
    )
    assert c.provider == "browserstack"
    assert c.device_id == "Google Pixel 7-13.0"
    assert c.app_path == "builds/browserstack.apk"
    assert c.app_url == "bs://abc"
    assert c.real_mobile is True

    cfg_device = DeviceConfig(provider="local", platform="android")
    overlaid = overlay_device_config(cfg_device, c)
    assert overlaid.provider == "browserstack"
    assert overlaid.is_cloud()
    assert overlaid.device_id == "Google Pixel 7-13.0"
    assert overlaid.app_path == "builds/browserstack.apk"
    assert overlaid.app_url == "bs://abc"
    assert overlaid.real_mobile is True

    cli = overlay_device_config(cfg_device, c, device_id="Samsung Galaxy S23-13.0")
    assert cli.device_id == "Samsung Galaxy S23-13.0"


def test_parse_testmu_provider_alias():
    c = parse_case_text(
        """
appId: com.lambdatest.proverbial
platform: android
provider: lambdatest
appPath: builds/testmu.apk
task: Open Proverbial
"""
    )
    assert c.provider == "testmu"
    assert c.app_path == "builds/testmu.apk"


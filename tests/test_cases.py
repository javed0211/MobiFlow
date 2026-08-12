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

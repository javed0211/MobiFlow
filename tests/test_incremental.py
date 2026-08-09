"""Tests for WebQA-style incremental / extend-explore helpers."""

from __future__ import annotations

from pathlib import Path

from mobiflow.cases import parse_case_text
from mobiflow.incremental import (
    classify_guidance,
    format_gap_task,
    load_guidance,
    merge_flow_yaml,
    save_guidance,
    strip_trailing_stop_app,
)


def test_classify_append_unchanged_dirty():
    prior = ["Launch app", "Search for cats", "Open first result"]
    assert classify_guidance(prior, prior).mode == "unchanged"
    append = classify_guidance(prior, prior + ["Share the article"])
    assert append.mode == "append"
    assert append.common_prefix == 3
    assert append.new_guidance == ["Share the article"]
    dirty = classify_guidance(prior, ["Launch app", "Search for dogs", "Open first result"])
    assert dirty.mode == "dirty"
    assert dirty.common_prefix == 1
    assert classify_guidance([], prior).mode == "fresh"


def test_format_gap_task():
    gap = format_gap_task(
        title="Wikipedia complex search",
        new_steps=["Open the History tab", "Confirm the article appears"],
        start_index=4,
        app_id="org.wikimedia.wikipedia",
    )
    assert "ALREADY past" in gap
    assert "4. Open the History tab" in gap
    assert "5. Confirm the article appears" in gap
    assert "org.wikimedia.wikipedia" in gap


def test_strip_and_merge_flow_yaml():
    prior = """\
appId: org.wikipedia
---
- launchApp
- tapOn: Search
- stopApp
"""
    stripped = strip_trailing_stop_app(prior)
    assert "stopApp" not in stripped
    assert "tapOn: Search" in stripped

    # Full rewrite from LLM
    extended = """\
appId: org.wikipedia
---
- launchApp
- tapOn: Search
- tapOn: History
- stopApp
"""
    merged = merge_flow_yaml(prior, extended, app_id="org.wikipedia")
    assert "History" in merged
    assert merged.rstrip().endswith("stopApp") or "stopApp" in merged

    # Delta-style append
    delta = "- tapOn: Saved\n"
    merged2 = merge_flow_yaml(prior, delta, app_id="org.wikipedia")
    assert "tapOn: Search" in merged2
    assert "tapOn: Saved" in merged2
    assert "stopApp" in merged2


def test_guidance_roundtrip(tmp_path: Path):
    path = save_guidance(
        tmp_path,
        "wiki",
        ["A", "B"],
        flow_path="flows/wiki.yaml",
        mode="append",
    )
    assert path.is_file()
    assert load_guidance(tmp_path, "wiki") == ["A", "B"]
    assert load_guidance(tmp_path, "missing") == []


def test_case_guidance_steps_from_numbered_task():
    case = parse_case_text(
        """\
appId: org.wikimedia.wikipedia
platform: ios
task: |
  Wikipedia complex search

  1. Launch Wikipedia
  2. Dismiss onboarding if shown
  3. Search for Albert Einstein
  4. Open the first result
"""
    )
    steps = case.guidance_steps()
    assert len(steps) >= 4
    assert "Albert Einstein" in steps[2]

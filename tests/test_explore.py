"""Tests for explore-then-generate helpers."""

from __future__ import annotations

from mobiflow.explore import (
    ExplorationResult,
    ExploreAction,
    build_action_flow_yaml,
    extract_json_object,
    parse_explore_decision,
)


def test_extract_json_object_from_fence():
    text = """Here you go:
```json
{"status": "done", "plan_so_far": ["Open Settings"], "next_action": null}
```
"""
    data = extract_json_object(text)
    assert data["status"] == "done"
    assert data["plan_so_far"] == ["Open Settings"]


def test_parse_explore_decision_continue():
    raw = """
    {
      "status": "continue",
      "observation": "Onboarding visible",
      "screen": "onboarding",
      "plan_so_far": ["Launch app", "Dismiss Skip"],
      "selectors": [{"label": "Skip", "text": "Skip"}],
      "next_action": {"command": "tapOn", "text": "Skip", "optional": true},
      "notes": "Dismiss first"
    }
    """
    d = parse_explore_decision(raw)
    assert d["status"] == "continue"
    assert d["action"] is not None
    assert d["action"].command == "tapOn"
    assert d["action"].text == "Skip"
    assert d["action"].optional is True
    assert d["plan"][0] == "Launch app"


def test_parse_explore_decision_done_without_action():
    d = parse_explore_decision(
        '{"status":"done","observation":"Search visible","plan_so_far":["Open app","See Search"],'
        '"selectors":["Search"],"next_action":null}'
    )
    assert d["status"] == "done"
    assert d["action"] is None
    assert d["selectors"][0]["text"] == "Search"


def test_build_action_flow_yaml():
    yaml_text = build_action_flow_yaml(
        "com.android.settings",
        ExploreAction(command="tapOn", text="Network"),
    )
    assert "appId: com.android.settings" in yaml_text
    assert 'tapOn: "Network"' in yaml_text
    assert "stopApp" not in yaml_text


def test_exploration_to_prompt_block():
    result = ExplorationResult(
        goal="Open Network",
        app_id="com.android.settings",
        platform="android",
        plan=["Launch Settings", "Open Network"],
        selectors=[{"label": "Network", "text": "Network & internet"}],
        notes=["Use Network & internet label"],
        mode="device",
        completed=True,
    )
    block = result.to_prompt_block()
    assert "Grounded plan" in block
    assert "Network & internet" in block
    assert "Exploration results" in block


def test_optional_tap_action_lines():
    lines = ExploreAction(command="tap", text="Skip", optional=True).to_maestro_lines()
    assert lines[0] == "- tapOn:"
    assert "optional: true" in "\n".join(lines)

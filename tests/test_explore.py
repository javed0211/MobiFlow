"""Tests for explore-then-generate helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from mobiflow.explore import (
    ExplorationResult,
    ExploreAction,
    build_action_flow_yaml,
    explore_app,
    extract_json_object,
    parse_explore_decision,
)
from mobiflow.llm_catalog import ModelEntry


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


def _profile() -> ModelEntry:
    return ModelEntry(provider="openai", model="mock", label="mock")


def test_interactive_explore_accept_then_done():
    decisions = [
        {
            "status": "continue",
            "observation": "Home",
            "screen": "home",
            "plan": ["Launch", "Tap Network"],
            "selectors": [{"label": "Network", "text": "Network"}],
            "notes": "",
            "action": ExploreAction(command="tapOn", text="Network"),
        },
        {
            "status": "done",
            "observation": "Network screen",
            "screen": "network",
            "plan": ["Launch", "Tap Network", "Done"],
            "selectors": [],
            "notes": "",
            "action": None,
        },
    ]
    asks: list[dict] = []

    def ask(payload: dict) -> dict:
        asks.append(payload)
        if payload.get("kind") == "action_proposal":
            return {"choice": "accept"}
        return {"choice": "done"}

    async def _run():
        with (
            patch(
                "mobiflow.maestro.run_flow_yaml",
                new_callable=AsyncMock,
                return_value={"ok": True},
            ),
            patch(
                "mobiflow.maestro.fetch_hierarchy",
                new_callable=AsyncMock,
                return_value="<hierarchy/>",
            ),
            patch(
                "mobiflow.maestro.resolve_app_id",
                return_value="com.android.settings",
            ),
            patch(
                "mobiflow.explore.decide_explore_step",
                new_callable=AsyncMock,
                side_effect=decisions,
            ),
        ):
            return await explore_app(
                "Open Network",
                app_id="com.android.settings",
                platform="android",
                device_id="emulator-5554",
                profile=_profile(),
                max_steps=5,
                interactive=True,
                ask=ask,
            )

    result = asyncio.run(_run())
    assert result.mode == "interactive"
    assert result.completed is True
    assert len(asks) == 2
    assert asks[0]["kind"] == "action_proposal"
    assert asks[1]["kind"] == "done_proposal"
    assert any(s.action and s.action.text == "Network" for s in result.steps)


def test_interactive_explore_skip_and_quit():
    decision = {
        "status": "continue",
        "observation": "Dialog",
        "screen": "dialog",
        "plan": ["Dismiss"],
        "selectors": [],
        "notes": "",
        "action": ExploreAction(command="tapOn", text="Cancel"),
    }
    responses = iter(
        [
            {"choice": "skip"},
            {"choice": "quit"},
        ]
    )

    async def _run():
        with (
            patch(
                "mobiflow.maestro.run_flow_yaml",
                new_callable=AsyncMock,
                return_value={"ok": True},
            ),
            patch(
                "mobiflow.maestro.fetch_hierarchy",
                new_callable=AsyncMock,
                return_value="<hierarchy/>",
            ),
            patch(
                "mobiflow.maestro.resolve_app_id",
                return_value="com.android.settings",
            ),
            patch(
                "mobiflow.explore.decide_explore_step",
                new_callable=AsyncMock,
                return_value=decision,
            ),
        ):
            return await explore_app(
                "Dismiss dialog",
                app_id="com.android.settings",
                platform="android",
                device_id="emulator-5554",
                profile=_profile(),
                max_steps=5,
                interactive=True,
                ask=lambda _p: next(responses),
            )

    result = asyncio.run(_run())
    assert result.mode == "interactive"
    assert any("quit by operator" in n for n in result.notes)
    # First step skipped (no action executed), then quit on next proposal
    assert result.steps[0].action is None
    assert "skipped by operator" in result.steps[0].notes


def test_explore_and_studio_cli_registered():
    from mobiflow.cli import main

    names = {cmd.name for cmd in main.commands.values()}
    assert "explore" in names
    assert "studio" in names

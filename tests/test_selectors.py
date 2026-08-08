"""Tests for selector memory and expect asserts."""

from __future__ import annotations

from pathlib import Path

from mobiflow.selectors import (
    ensure_expect_asserts,
    load_selector_memory,
    memory_to_prompt_block,
    merge_selectors,
    save_selector_memory,
)


def test_selector_memory_roundtrip(tmp_path: Path):
    mem = merge_selectors(
        {"selectors": []},
        [{"label": "Search", "text": "Search"}],
        success=True,
    )
    path = save_selector_memory(tmp_path, "org.wikipedia", mem)
    assert path.is_file()
    loaded = load_selector_memory(tmp_path, "org.wikipedia")
    assert loaded["selectors"][0]["text"] == "Search"
    assert loaded["selectors"][0]["hits"] == 1
    block = memory_to_prompt_block(loaded)
    assert "Search" in block


def test_ensure_expect_asserts():
    yaml_text = "appId: x\n---\n- launchApp\n"
    out = ensure_expect_asserts(yaml_text, ["Search", "Home"])
    assert 'assertVisible: "Search"' in out
    assert 'assertVisible: "Home"' in out
    # idempotent
    out2 = ensure_expect_asserts(out, ["Search"])
    assert out2.count('assertVisible: "Search"') == 1

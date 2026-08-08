from mobiflow.cases import parse_case_text
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


def test_maestro_yaml_helpers():
    assert looks_like_maestro_yaml("appId: x\n---\n- launchApp\n")
    y = ensure_flow_yaml("- launchApp\n", "org.wikipedia")
    assert y.startswith("appId: org.wikipedia")
    assert resolve_app_id("", "android", "open wikipedia") == "org.wikipedia"

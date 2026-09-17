"""E2E API intent detection and Maestro hook injection."""

from __future__ import annotations

from mobiflow.cases import parse_case_text
from mobiflow.hooks import (
    apply_flow_hooks,
    compile_hook_steps,
    detect_api_intent,
    ensure_flow_env,
    parse_http_step,
)


def test_detect_api_intent():
    assert detect_api_intent("Call the API POST https://api.example.com/users")
    assert detect_api_intent("seed via API then open the app")
    assert not detect_api_intent("Open Wikipedia and confirm Search")


def test_parse_http_step():
    call = parse_http_step('POST https://api.example.com/users {"email":"a@b.c"}')
    assert call is not None
    assert call["method"] == "POST"
    assert "api.example.com" in call["url"]
    assert "email" in call["body"]
    assert parse_http_step("tapOn: Login") is None


def test_parse_case_hooks():
    c = parse_case_text(
        """
appId: com.example.app
platform: android
onFlowStart:
  - POST ${API_BASE}/users
after:
  - DELETE ${API_BASE}/users/1
task: Launch the app after the API creates a user
"""
    )
    assert c.on_flow_start == ["POST ${API_BASE}/users"]
    assert c.on_flow_complete == ["DELETE ${API_BASE}/users/1"]
    assert "onFlowStart" in c.explore_task()


def test_compile_and_apply_hooks():
    cmds, scripts = compile_hook_steps(
        ['POST https://api.example.com/users {"a":1}'],
        phase="onFlowStart",
    )
    assert any("runScript: scripts/_onFlowStart.js" in c for c in cmds)
    assert "scripts/_onFlowStart.js" in scripts
    assert "http.post" in scripts["scripts/_onFlowStart.js"]

    yaml_text, out = apply_flow_hooks(
        "appId: com.example.app\n---\n- launchApp\n- stopApp\n",
        {},
        start_steps=["POST https://api.example.com/seed"],
        complete_steps=["- runScript: scripts/teardown.js"],
    )
    assert "onFlowStart:" in yaml_text
    assert "onFlowComplete:" in yaml_text
    assert "scripts/_onFlowStart.js" in out
    assert "teardown.js" in yaml_text


def test_ensure_flow_env_writes_yaml_header():
    yaml_text = ensure_flow_env(
        "appId: com.example.app\n---\n- launchApp\n- inputText: ${LOGIN_EMAIL}\n- stopApp\n",
        {
            "API_BASE": "https://reqres.in",
            "LOGIN_EMAIL": "test@webdriver.io",
        },
    )
    assert "env:" in yaml_text
    assert "API_BASE: https://reqres.in" in yaml_text
    assert "LOGIN_EMAIL: test@webdriver.io" in yaml_text
    assert yaml_text.index("env:") < yaml_text.index("---")
    assert "${LOGIN_EMAIL}" in yaml_text


def test_ensure_flow_env_case_wins_over_existing():
    yaml_text = ensure_flow_env(
        "appId: x\nenv:\n  API_BASE: https://old.example\n  KEEP: leftover\n---\n- launchApp\n",
        {"API_BASE": "https://reqres.in"},
    )
    assert "API_BASE: https://reqres.in" in yaml_text
    assert "https://old.example" not in yaml_text
    assert "KEEP: leftover" in yaml_text


def test_ensure_flow_env_noop_when_empty():
    src = "appId: x\n---\n- launchApp\n"
    assert ensure_flow_env(src, None) == src
    assert ensure_flow_env(src, {}) == src

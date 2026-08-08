"""Tests for Maestro env injection and redaction."""

from __future__ import annotations

from mobiflow.secrets import maestro_env_args, merge_flow_env, redact_text


def test_merge_flow_env_resolves_process_names(monkeypatch):
    monkeypatch.setenv("MOBIFLOW_PASSWORD", "s3cret-value")
    merged = merge_flow_env({"USER": "demo", "PASSWORD": "MOBIFLOW_PASSWORD"})
    assert merged["USER"] == "demo"
    assert merged["PASSWORD"] == "s3cret-value"


def test_maestro_env_args_sorted():
    args = maestro_env_args({"B": "2", "A": "1"})
    assert args == ["--env", "A=1", "--env", "B=2"]


def test_redact_text_hides_secrets():
    text = "login password=s3cret-value ok"
    out = redact_text(text, {"PASSWORD": "s3cret-value"})
    assert "s3cret-value" not in out
    assert "***" in out

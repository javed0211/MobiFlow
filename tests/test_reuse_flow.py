"""Tests for reuse-flow path resolution and companion scripts."""

from __future__ import annotations

from pathlib import Path

from mobiflow.cases import parse_case_text
from mobiflow.config import MobiflowConfig, ProjectConfig, RunConfig, StackConfig
from mobiflow.pipeline import resolve_reuse_flow_path


def test_resolve_reuse_flow_from_case_meta(tmp_path: Path):
    flow = tmp_path / "flows" / "login.yaml"
    flow.parent.mkdir()
    flow.write_text("appId: x\n---\n- launchApp\n", encoding="utf-8")
    case = parse_case_text(
        "appId: x\nflow: flows/login.yaml\ntask: Login\n", name="login"
    )
    cfg = MobiflowConfig(
        project=ProjectConfig(mode="local", path=str(tmp_path)),
        stack=StackConfig(flow_dir="flows"),
        run=RunConfig(reuse_flow=False),
    )
    path = resolve_reuse_flow_path(case, cfg)
    assert path == flow.resolve()


def test_resolve_reuse_flow_default_name(tmp_path: Path):
    flow = tmp_path / "flows" / "settings.yaml"
    flow.parent.mkdir()
    flow.write_text("appId: x\n---\n- launchApp\n", encoding="utf-8")
    case = parse_case_text("appId: x\ntask: Open settings\n", name="settings")
    cfg = MobiflowConfig(
        project=ProjectConfig(mode="local", path=str(tmp_path)),
        stack=StackConfig(flow_dir="flows"),
        run=RunConfig(reuse_flow=True),
    )
    assert resolve_reuse_flow_path(case, cfg) == flow.resolve()
    assert resolve_reuse_flow_path(case, cfg, reuse_flow=False) is None

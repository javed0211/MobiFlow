"""Tests for suite discovery, aggregation, and reports."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from mobiflow.cases import discover_cases, parse_case_text
from mobiflow.config import MobiflowConfig, ProjectConfig, RunConfig, StackConfig
from mobiflow.reporting import ReportCase, write_suite_reports
from mobiflow.suite import run_suite


def test_parse_case_flow_clear_env_expect():
    c = parse_case_text(
        """
@smoke
@login
appId: com.example.app
platform: android
flow: flows/login.yaml
clearState: true
env: USER=demo
expect: Welcome
task: Log in and see home
"""
    )
    assert c.flow == "flows/login.yaml"
    assert c.clear_state is True
    assert c.env.get("USER") == "demo"
    assert "Welcome" in c.expect
    assert c.has_tag("smoke")
    assert c.has_tag("@login")


def test_discover_cases_filters_tags(tmp_path: Path):
    (tmp_path / "a.txt").write_text(
        "@smoke\nappId: x\ntask: Open A\n", encoding="utf-8"
    )
    (tmp_path / "b.txt").write_text(
        "@regression\nappId: x\ntask: Open B\n", encoding="utf-8"
    )
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "c.txt").write_text(
        "@smoke\nappId: x\ntask: Open C\n", encoding="utf-8"
    )
    all_cases = discover_cases(tmp_path)
    assert {c.name for c in all_cases} == {"a", "b", "c"}
    smoke = discover_cases(tmp_path, tags=["smoke"])
    assert {c.name for c in smoke} == {"a", "c"}


def test_write_suite_reports(tmp_path: Path):
    cases = [
        ReportCase(
            name="ok",
            success=True,
            summary="passed",
            platform="android",
            provider="local",
            duration_s=1.0,
        ),
        ReportCase(
            name="bad",
            success=False,
            summary="boom",
            error="fail",
            platform="android",
            provider="local",
            duration_s=2.0,
            stderr="stack",
        ),
    ]
    written = write_suite_reports(
        cases,
        tmp_path / "suite",
        formats=["junit", "html"],
        suite_name="smoke",
        started_at="2026-01-01T00:00:00Z",
        duration_s=3.0,
    )
    assert Path(written["junit"]).is_file()
    assert Path(written["html"]).is_file()
    root = ET.parse(written["junit"]).getroot()
    assert root.attrib["tests"] == "2"
    assert root.attrib["failures"] == "1"
    html = Path(written["html"]).read_text(encoding="utf-8")
    assert "smoke" in html
    assert "bad" in html
    assert "FAILED" in html


def test_run_suite_aggregates_and_fail_fast(tmp_path: Path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "a_pass.txt").write_text(
        "@smoke\nappId: x\ntask: Pass\n", encoding="utf-8"
    )
    (cases_dir / "b_fail.txt").write_text(
        "@smoke\nappId: x\ntask: Fail\n", encoding="utf-8"
    )
    (cases_dir / "c_skip.txt").write_text(
        "@smoke\nappId: x\ntask: Skip me\n", encoding="utf-8"
    )

    cfg = MobiflowConfig(
        project=ProjectConfig(mode="local", path=str(tmp_path)),
        stack=StackConfig(cases_dir="cases", flow_dir="flows"),
        run=RunConfig(
            reports=["junit", "html"],
            report_dir=".mobiflow/reports",
            fail_fast=True,
            save_artifacts=False,
        ),
    )

    calls: list[str] = []

    def fake_pipeline(case_file, config, **kwargs):
        name = Path(case_file).stem
        calls.append(name)
        ok = name != "b_fail"
        return {
            "success": ok,
            "summary": "ok" if ok else "failed",
            "error": "" if ok else "boom",
            "logs": [],
            "run": {},
            "flow_path": str(tmp_path / "flows" / f"{name}.yaml"),
            "artifact_dir": "",
            "screenshots": [],
        }

    with patch("mobiflow.suite.run_pipeline", side_effect=fake_pipeline):
        result = run_suite(
            cases_dir,
            cfg,
            tags=["smoke"],
            fail_fast=True,
            suite_name="unit",
        )

    assert calls == ["a_pass", "b_fail"]  # c_skip not run (fail_fast)
    assert "c_skip" not in calls
    assert result.failed == 1
    assert result.passed == 1
    assert result.success is False
    assert Path(result.reports["junit"]).is_file()
    assert (tmp_path / ".mobiflow" / "reports" / "suite.latest.json").is_file()


def test_suite_and_run_cli_registered():
    from mobiflow.cli import main

    names = {cmd.name for cmd in main.commands.values()}
    assert "suite" in names
    assert "run" in names

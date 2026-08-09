"""Tests for JUnit/HTML reporting helpers."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from mobiflow.config import MobiflowConfig, RunConfig
from mobiflow.reporting import (
    ReportCase,
    collect_screenshots,
    normalize_report_formats,
    write_junit_xml,
    write_run_reports,
)


def test_normalize_report_formats():
    assert normalize_report_formats("junit, html") == ["junit", "html"]
    assert normalize_report_formats(["JUNIT", "xml", "none"]) == ["junit"]
    assert normalize_report_formats("") == []
    assert normalize_report_formats(None) == []


def test_run_config_coerces_reports_string():
    cfg = RunConfig(reports="junit,html")
    assert cfg.reports == ["junit", "html"]
    cfg2 = RunConfig(reports=[])
    assert cfg2.reports == []


def test_write_junit_failure(tmp_path: Path):
    case = ReportCase(
        name="login",
        success=False,
        summary="assert failed",
        error="flow_failed",
        platform="android",
        provider="local",
        device_id="emulator-5554",
        duration_s=1.25,
        stderr="Element not found",
        logs=["step 1", "step 2"],
    )
    path = write_junit_xml(case, tmp_path / "junit.xml")
    root = ET.parse(path).getroot()
    assert root.attrib["failures"] == "1"
    tc = root.find("testcase")
    assert tc is not None
    assert tc.attrib["name"] == "login"
    assert tc.find("failure") is not None


def test_write_junit_skipped_synthesis(tmp_path: Path):
    case = ReportCase(
        name="gen",
        success=True,
        synthesis_only=True,
        summary="generated only",
        platform="ios",
        provider="local",
    )
    path = write_junit_xml(case, tmp_path / "junit.xml")
    root = ET.parse(path).getroot()
    tc = root.find("testcase")
    assert tc is not None
    assert tc.find("skipped") is not None


def test_write_html_and_index(tmp_path: Path):
    shots = tmp_path / "screenshots"
    shots.mkdir()
    img = shots / "fail.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    case = ReportCase(
        name="settings",
        success=True,
        summary="passed",
        provider="browserstack",
        platform="android",
        dashboard_url="https://example.com/dash",
        screenshot_paths=["../screenshots/fail.png"],
        artifact_dir=str(tmp_path),
    )
    report_dir = tmp_path / "report"
    written = write_run_reports(case, report_dir, formats=["junit", "html"])
    assert Path(written["junit"]).is_file()
    html = Path(written["html"]).read_text(encoding="utf-8")
    assert "window.__MOBIFLOW_REPORT__" in html
    assert "settings" in html
    pack = json.loads((report_dir / "pack.json").read_text(encoding="utf-8"))
    case0 = pack["cases"][0]
    assert case0["artifacts"]["provider"] == "browserstack"
    assert case0["artifacts"]["dashboard_url"] == "https://example.com/dash"
    assert "browserstack" in case0["tags"]
    assert Path(written["index"]).is_file()
    assert (report_dir / "report-simple.html").is_file()
    assert (report_dir / "pack.json").is_file()


def test_collect_screenshots(tmp_path: Path):
    (tmp_path / "a.png").write_bytes(b"x")
    nested = tmp_path / "takeScreenshot"
    nested.mkdir()
    (nested / "b.jpg").write_bytes(b"y")
    (tmp_path / "notes.txt").write_text("nope")
    found = collect_screenshots(tmp_path)
    assert len(found) == 2


def test_report_dir_path():
    cfg = MobiflowConfig(run=RunConfig(report_dir=".mobiflow/reports"))
    assert cfg.report_dir_path().name == "reports"

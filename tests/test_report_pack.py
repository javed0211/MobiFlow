"""Tests for rich ReportPack HTML generation."""

from __future__ import annotations

from pathlib import Path

from mobiflow.report import (
    build_pack,
    case_record_from_report_case,
    render_html,
    write_rich_reports,
)
from mobiflow.reporting import ReportCase


def test_render_html_injects_pack():
    case = ReportCase(
        name="demo",
        success=True,
        summary="ok",
        task="Open Settings",
        platform="ios",
        duration_s=1.5,
        logs=["ready", "passed"],
    )
    pack = build_pack([case_record_from_report_case(case)], title="MobiFlow Demo")
    html = render_html(pack)
    assert "window.__MOBIFLOW_REPORT__" in html
    assert "MobiFlow Demo" in html
    assert "demo" in html


def test_write_rich_reports(tmp_path: Path):
    case = ReportCase(
        name="wiki",
        success=False,
        summary="fail",
        error="boom",
        task="Search",
        platform="android",
        duration_s=3.0,
        stderr="Element not found",
        logs=["attempt 1"],
    )
    written = write_rich_reports([case], tmp_path, title="Pack")
    assert Path(written["html"]).is_file()
    assert Path(written["json"]).is_file()
    text = Path(written["html"]).read_text(encoding="utf-8")
    assert "__MOBIFLOW_REPORT__" in text
    assert (tmp_path / "report.html").is_file()

"""Run reporting: JUnit XML, HTML summary, artifact indexing."""

from __future__ import annotations

import html
import json
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.dom import minidom

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@dataclass
class ReportCase:
    name: str
    success: bool
    summary: str = ""
    error: str = ""
    task: str = ""
    platform: str = ""
    provider: str = "local"
    device_id: str = ""
    duration_s: float = 0.0
    flow_path: str = ""
    dashboard_url: str = ""
    build_id: str = ""
    stdout: str = ""
    stderr: str = ""
    logs: list[str] = field(default_factory=list)
    synthesis_only: bool = False
    screenshot_paths: list[str] = field(default_factory=list)
    artifact_dir: str = ""
    started_at: str = ""


def normalize_report_formats(value: Any) -> list[str]:
    """Accept list/tuple/comma-string; return lowercase unique formats."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [p.strip().lower() for p in value.replace(";", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(p).strip().lower() for p in value]
    else:
        items = [str(value).strip().lower()]
    out: list[str] = []
    for item in items:
        if not item or item in {"none", "off", "false", "0"}:
            continue
        if item in {"junit", "xml"}:
            fmt = "junit"
        elif item in {"html", "htm"}:
            fmt = "html"
        else:
            fmt = item
        if fmt not in out:
            out.append(fmt)
    return out


def collect_screenshots(root: Path, *, limit: int = 40) -> list[Path]:
    if not root.exists():
        return []
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            found.append(path)
            if len(found) >= limit:
                break
    return found


def index_artifacts(root: Path) -> dict[str, Any]:
    """Build a lightweight inventory of a run artifact directory."""
    if not root.exists():
        return {"dir": str(root), "files": [], "screenshots": []}
    files: list[str] = []
    screenshots: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        files.append(rel)
        if path.suffix.lower() in IMAGE_SUFFIXES:
            screenshots.append(rel)
    return {
        "dir": str(root),
        "files": files,
        "screenshots": screenshots,
        "file_count": len(files),
        "screenshot_count": len(screenshots),
    }


def copy_tree_if_present(src: Path, dest: Path) -> Path | None:
    if not src.exists():
        return None
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def write_junit_xml(case: ReportCase, path: Path) -> Path:
    """Write a single-testcase JUnit XML report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element(
        "testsuite",
        {
            "name": "MobiFlow",
            "tests": "1",
            "failures": "0" if case.success else "1",
            "errors": "0",
            "skipped": "1" if case.synthesis_only and case.success else "0",
            "time": f"{max(0.0, case.duration_s):.3f}",
            "timestamp": case.started_at
            or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    classname = f"{case.provider}.{case.platform or 'mobile'}".strip(".")
    testcase = ET.SubElement(
        suite,
        "testcase",
        {
            "name": case.name,
            "classname": classname or "mobiflow",
            "time": f"{max(0.0, case.duration_s):.3f}",
        },
    )
    props = ET.SubElement(testcase, "properties")
    for key, val in (
        ("platform", case.platform),
        ("provider", case.provider),
        ("device_id", case.device_id),
        ("dashboard_url", case.dashboard_url),
        ("build_id", case.build_id),
        ("flow_path", case.flow_path),
        ("artifact_dir", case.artifact_dir),
    ):
        if val:
            ET.SubElement(props, "property", {"name": key, "value": str(val)})

    system_out = "\n".join(case.logs)
    if case.stdout:
        system_out = (system_out + "\n" + case.stdout).strip()
    if system_out:
        ET.SubElement(testcase, "system-out").text = system_out[-20000:]
    if case.stderr:
        ET.SubElement(testcase, "system-err").text = case.stderr[-20000:]

    if case.synthesis_only and case.success:
        ET.SubElement(testcase, "skipped", {"message": case.summary or "synthesis only"})
    elif not case.success:
        msg = case.summary or case.error or "flow failed"
        fail = ET.SubElement(testcase, "failure", {"message": msg[:500]})
        fail.text = (case.stderr or case.stdout or case.error or msg)[-20000:]

    rough = ET.tostring(suite, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")
    # minidom adds XML declaration; write bytes
    path.write_bytes(pretty)
    return path


def write_html_report(case: ReportCase, path: Path) -> Path:
    """Write a self-contained HTML run summary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    status = "PASSED" if case.success else "FAILED"
    if case.synthesis_only:
        status = "GENERATED" if case.success else "FAILED"
    color = "#0a7a32" if case.success else "#b42318"
    if case.synthesis_only and case.success:
        color = "#175cd3"

    shots_html = ""
    for rel in case.screenshot_paths[:24]:
        safe = html.escape(rel)
        shots_html += (
            f'<figure class="shot"><img src="{safe}" alt="{safe}"/>'
            f"<figcaption>{safe}</figcaption></figure>\n"
        )
    if not shots_html:
        shots_html = "<p class='muted'>No screenshots captured for this run.</p>"

    def block(title: str, body: str) -> str:
        if not (body or "").strip():
            return ""
        return (
            f"<h2>{html.escape(title)}</h2>"
            f"<pre>{html.escape(body[-30000:])}</pre>"
        )

    meta_rows = "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in (
            ("Case", case.name),
            ("Status", status),
            ("Summary", case.summary or "-"),
            ("Provider", case.provider or "-"),
            ("Platform", case.platform or "-"),
            ("Device", case.device_id or "-"),
            ("Duration", f"{case.duration_s:.1f}s"),
            ("Started", case.started_at or "-"),
            ("Flow", case.flow_path or "-"),
            ("Build ID", case.build_id or "-"),
            ("Dashboard", case.dashboard_url or "-"),
            ("Artifacts", case.artifact_dir or "-"),
        )
        if v not in (None, "")
    )

    dash_link = ""
    if case.dashboard_url:
        url = html.escape(case.dashboard_url)
        dash_link = f'<p><a href="{url}">Open cloud dashboard</a></p>'

    progress_block = block("Progress log", "\n".join(case.logs))
    stdout_block = block("Stdout", case.stdout)
    stderr_block = block("Stderr", case.stderr)
    error_block = block("Error", case.error)
    safe_name = html.escape(case.name)
    safe_task = html.escape(case.task or "")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>MobiFlow — {safe_name} — {status}</title>
  <style>
    :root {{
      --bg: #f6f4ef;
      --ink: #1c1917;
      --card: #fffdf8;
      --line: #e7e0d5;
      --muted: #78716c;
      --accent: {color};
    }}
    body {{
      margin: 0; font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(1200px 500px at 10% -10%, #e8f0e4 0%, transparent 55%),
        radial-gradient(900px 400px at 100% 0%, #f0e6d8 0%, transparent 50%),
        var(--bg);
      color: var(--ink); line-height: 1.45;
    }}
    main {{ max-width: 960px; margin: 2rem auto; padding: 0 1.25rem 3rem; }}
    header {{
      background: var(--card); border: 1px solid var(--line);
      border-radius: 16px; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem;
    }}
    h1 {{ margin: 0 0 .35rem; font-size: 1.6rem; letter-spacing: -0.02em; }}
    .brand {{ font-size: .85rem; text-transform: uppercase; letter-spacing: .12em; color: var(--muted); }}
    .badge {{
      display: inline-block; margin-top: .5rem; padding: .25rem .7rem;
      border-radius: 999px; background: var(--accent); color: white;
      font-weight: 650; font-size: .85rem;
    }}
    section {{
      background: var(--card); border: 1px solid var(--line);
      border-radius: 16px; padding: 1.1rem 1.35rem; margin-bottom: 1rem;
    }}
    h2 {{ margin: 0 0 .75rem; font-size: 1.05rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; vertical-align: top; padding: .4rem 0; border-bottom: 1px solid var(--line); }}
    th {{ width: 8rem; color: var(--muted); font-weight: 600; }}
    pre {{
      white-space: pre-wrap; word-break: break-word; background: #1c1917; color: #f5f5f4;
      padding: .9rem 1rem; border-radius: 12px; overflow: auto; font-size: .82rem;
    }}
    .shots {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: .75rem; }}
    .shot {{ margin: 0; }}
    .shot img {{ width: 100%; border-radius: 10px; border: 1px solid var(--line); background: #fff; }}
    figcaption {{ font-size: .72rem; color: var(--muted); margin-top: .3rem; word-break: break-all; }}
    .muted {{ color: var(--muted); }}
    a {{ color: #0f4c81; }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="brand">MobiFlow report</div>
      <h1>{safe_name}</h1>
      <div class="badge">{status}</div>
      {dash_link}
    </header>
    <section>
      <h2>Run details</h2>
      <table>{meta_rows}</table>
      <p class="muted">{safe_task}</p>
    </section>
    <section>
      <h2>Screenshots</h2>
      <div class="shots">{shots_html}</div>
    </section>
    <section>
      {progress_block}
      {stdout_block}
      {stderr_block}
      {error_block}
    </section>
  </main>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")
    return path


def merge_maestro_junit(maestro_junit: Path, case: ReportCase, dest: Path) -> Path:
    """Prefer Maestro's JUnit when present; enrich classname/name if needed."""
    if not maestro_junit.is_file():
        return write_junit_xml(case, dest)
    try:
        tree = ET.parse(maestro_junit)
        root = tree.getroot()
        # Ensure at least one testcase has our case name property
        for tc in root.iter("testcase"):
            if not tc.get("name"):
                tc.set("name", case.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tree.write(dest, encoding="utf-8", xml_declaration=True)
        return dest
    except ET.ParseError:
        return write_junit_xml(case, dest)


def write_run_reports(
    case: ReportCase,
    report_dir: Path,
    *,
    formats: list[str],
    maestro_junit: Path | None = None,
) -> dict[str, str]:
    """Write configured reports; return map format → path."""
    formats = normalize_report_formats(formats)
    report_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    if "junit" in formats:
        junit_path = report_dir / "junit.xml"
        if maestro_junit and maestro_junit.is_file():
            merge_maestro_junit(maestro_junit, case, junit_path)
        else:
            write_junit_xml(case, junit_path)
        written["junit"] = str(junit_path)
    if "html" in formats:
        html_path = report_dir / "report.html"
        write_html_report(case, html_path)
        written["html"] = str(html_path)
    # Always write a machine-readable index alongside reports
    index = {
        "case": case.name,
        "success": case.success,
        "summary": case.summary,
        "provider": case.provider,
        "platform": case.platform,
        "device_id": case.device_id,
        "dashboard_url": case.dashboard_url,
        "build_id": case.build_id,
        "artifact_dir": case.artifact_dir,
        "screenshots": case.screenshot_paths,
        "reports": written,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    index_path = report_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    written["index"] = str(index_path)
    return written


_DURATION_RE = re.compile(r"(?i)(?:duration|elapsed)[^\d]*(\d+(?:\.\d+)?)\s*(s|ms)?")


def estimate_duration_s(stdout: str, stderr: str, fallback: float = 0.0) -> float:
    text = f"{stdout}\n{stderr}"
    for match in _DURATION_RE.finditer(text):
        val = float(match.group(1))
        unit = (match.group(2) or "s").lower()
        return val / 1000.0 if unit == "ms" else val
    return fallback

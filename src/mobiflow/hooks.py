"""Maestro E2E API calls + onFlowStart / onFlowComplete hooks.

Maestro has no YAML ``http:`` command. HTTP runs in GraalJS via built-in
``http.get/post/put/delete`` (and ``json()``), typically from ``runScript``.
Hooks belong in the flow config section (above ``---``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_API_INTENT_RE = re.compile(
    r"(?is)("
    r"\bapi\s*calls?\b|"
    r"\bcall(?:s|ing)?\s+(?:the\s+)?api\b|"
    r"\bhttp(?:s)?://|"
    r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+\S+|"
    r"\bgraphql\b|"
    r"\bwebhook\b|"
    r"\brest\s+(?:api|endpoint)\b|"
    r"\bonflowstart\b|"
    r"\bonflowcomplete\b|"
    r"\bseed\s+(?:via|using|with)\s+api\b|"
    r"\bteardown\s+(?:via|using|with)\s+api\b"
    r")"
)

_HTTP_STEP_RE = re.compile(
    r"^(?:http[.\s]+)?"
    r"(GET|POST|PUT|PATCH|DELETE)\s+"
    r"(\S+)"
    r"(?:\s+(\{.*\}))?\s*$",
    re.IGNORECASE | re.DOTALL,
)

API_CODEGEN_HINT = """
API / E2E requirement: the user asked for HTTP API calls in this mobile flow.
Use Maestro GraalJS (not Node fetch/axios):
  var response = http.get(url);
  var response = http.post(url, { headers: { Authorization: 'Bearer ' + TOKEN }, body: JSON.stringify({...}) });
  output.foo = json(response.body);
Put setup/teardown APIs in the YAML config section:
  onFlowStart:
    - runScript: scripts/setup.js
  onFlowComplete:
    - runScript: scripts/teardown.js
Mid-flow APIs are runScript steps between UI commands. Store results on output.*
and reference them later as ${output.key}. Secrets come from env (TOKEN, API_BASE).
""".strip()


def detect_api_intent(text: str) -> bool:
    """True when a case/goal mentions HTTP APIs, REST verbs, or flow hooks."""
    return bool(_API_INTENT_RE.search(text or ""))


def parse_http_step(step: str) -> dict[str, str] | None:
    """Parse ``POST https://api/x {\"a\":1}`` (or ``http.get url``) into parts."""
    raw = (step or "").strip()
    if raw.startswith("-"):
        raw = raw[1:].strip()
    m = _HTTP_STEP_RE.match(raw)
    if not m:
        return None
    return {
        "method": m.group(1).upper(),
        "url": m.group(2).strip().strip("\"'"),
        "body": (m.group(3) or "").strip(),
    }


def _http_js_line(call: dict[str, str], *, output_key: str) -> str:
    method = call["method"].lower()
    method = method if method in {"get", "post", "put", "delete", "patch"} else "get"
    url = call["url"].replace("\\", "\\\\").replace("'", "\\'")
    body = call.get("body") or ""
    if method in {"post", "put"} and body:
        opts = "{ headers: { 'Content-Type': 'application/json' }, body: " + body + " }"
        invoke = f"http.{method}('{url}', {opts})"
    elif method in {"post", "put"}:
        invoke = f"http.{method}('{url}', {{ headers: {{ 'Content-Type': 'application/json' }} }})"
    else:
        invoke = f"http.{method}('{url}')"
    return (
        f"var {output_key} = {invoke};\n"
        f"output.{output_key}Status = {output_key}.status;\n"
        f"try {{ output.{output_key}Json = json({output_key}.body); }} "
        f"catch (e) {{ output.{output_key}Body = {output_key}.body; }}"
    )


def compile_hook_steps(
    steps: list[str],
    *,
    phase: str,
) -> tuple[list[str], dict[str, str]]:
    """Turn case hook lines into Maestro YAML commands + optional JS scripts."""
    yaml_cmds: list[str] = []
    js_chunks: list[str] = []
    for i, step in enumerate(steps):
        raw = (step or "").strip()
        if not raw:
            continue
        call = parse_http_step(raw)
        if call:
            js_chunks.append(_http_js_line(call, output_key=f"{phase}{i}"))
            continue
        if not raw.startswith("-"):
            raw = f"- {raw}"
        yaml_cmds.append(raw)
    scripts: dict[str, str] = {}
    if js_chunks:
        rel = f"scripts/_{phase}.js"
        scripts[rel] = (
            f"// Auto-generated {phase} API hook (Maestro GraalJS http.*)\n"
            + "\n".join(js_chunks)
            + "\n"
        )
        yaml_cmds.insert(0, f"- runScript: {rel}")
    return yaml_cmds, scripts


def _command_to_obj(line: str) -> Any:
    raw = line.strip()
    if raw.startswith("-"):
        raw = raw[1:].strip()
    if not raw:
        return None
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


def _header_and_body(flow_yaml: str) -> tuple[str, str]:
    text = flow_yaml or ""
    if "\n---\n" in text:
        head, body = text.split("\n---\n", 1)
        return head, body
    if text.startswith("---\n"):
        return "", text[4:]
    return text, ""


def apply_flow_hooks(
    flow_yaml: str,
    scripts: dict[str, str] | None,
    *,
    start_steps: list[str] | None = None,
    complete_steps: list[str] | None = None,
) -> tuple[str, dict[str, str]]:
    """Merge case hooks into Maestro YAML config + companion scripts."""
    out_scripts = dict(scripts or {})
    start_yaml, start_js = compile_hook_steps(list(start_steps or []), phase="onFlowStart")
    complete_yaml, complete_js = compile_hook_steps(
        list(complete_steps or []), phase="onFlowComplete"
    )
    out_scripts.update(start_js)
    out_scripts.update(complete_js)
    if not start_yaml and not complete_yaml:
        return flow_yaml, out_scripts

    head, body = _header_and_body(flow_yaml)
    try:
        header = yaml.safe_load(head) if head.strip() else {}
    except yaml.YAMLError:
        header = {}
    if not isinstance(header, dict):
        header = {"appId": str(header)}

    def _merge(key: str, extra_lines: list[str]) -> None:
        extra = [_command_to_obj(x) for x in extra_lines]
        extra = [e for e in extra if e is not None]
        if not extra:
            return
        existing = header.get(key)
        if existing is None:
            header[key] = extra
            return
        if not isinstance(existing, list):
            existing = [existing]
        # Prepend case hooks; skip exact duplicates
        merged = list(extra)
        for item in existing:
            if item not in merged:
                merged.append(item)
        header[key] = merged

    _merge("onFlowStart", start_yaml)
    _merge("onFlowComplete", complete_yaml)

    ordered: dict[str, Any] = {}
    for key in (
        "appId",
        "name",
        "tags",
        "env",
        "onFlowStart",
        "onFlowComplete",
    ):
        if key in header:
            ordered[key] = header.pop(key)
    ordered.update(header)
    dumped = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True).rstrip()
    body_out = body if body else "- launchApp\n"
    if not body_out.startswith("\n") and not dumped.endswith("\n"):
        dumped += "\n"
    return f"{dumped}---\n{body_out.lstrip()}".rstrip() + "\n", out_scripts


def hooks_prompt_block(
    start_steps: list[str] | None,
    complete_steps: list[str] | None,
) -> str:
    lines: list[str] = []
    if start_steps:
        lines.append("onFlowStart (before UI):")
        lines.extend(f"  - {s.lstrip('- ').strip()}" for s in start_steps if s.strip())
    if complete_steps:
        lines.append("onFlowComplete (after UI, pass or fail):")
        lines.extend(f"  - {s.lstrip('- ').strip()}" for s in complete_steps if s.strip())
    return "\n".join(lines)


def write_hook_scripts(scripts: dict[str, str], flow_dir: Path) -> None:
    """Persist generated hook JS next to other Maestro scripts."""
    for rel, body in scripts.items():
        if not rel.startswith("scripts/_"):
            continue
        dest = flow_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")

"""First-party Maestro Cloud via `maestro cloud` CLI."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Callable

from mobiflow.cloud.base import (
    CloudProvider,
    CloudRunRequest,
    CloudRunResult,
    resolve_credentials,
)

ProgressFn = Callable[[str], None] | None


async def run_maestro_cloud(
    req: CloudRunRequest,
    *,
    progress: ProgressFn = None,
    artifact_dir: Path | None = None,
) -> CloudRunResult:
    """Upload app + flows with the official Maestro Cloud CLI."""
    from mobiflow.maestro import _run_cmd, resolve_maestro_binary

    binary = resolve_maestro_binary()
    if not binary:
        return CloudRunResult(
            ok=False,
            provider="maestro",
            status="error",
            error="maestro_not_installed",
            stdout="",
            stderr="Maestro CLI not found (needed for `maestro cloud`)",
        )

    try:
        creds = resolve_credentials(
            CloudProvider.MAESTRO,
            username_env=req.username_env,
            access_key_env=req.access_key_env,
        )
    except ValueError as e:
        return CloudRunResult(
            ok=False,
            provider="maestro",
            status="error",
            error="credentials_missing",
            stdout="",
            stderr=str(e),
        )

    api_key = creds.access_key
    app_file = (req.app_path or "").strip()
    app_binary_id = (req.app_url or "").strip() if not app_file else ""

    if not app_file and not app_binary_id:
        return CloudRunResult(
            ok=False,
            provider="maestro",
            status="error",
            error="app_missing",
            stdout="",
            stderr="Set device.app_path (.apk/.ipa) or device.app_url (app binary id)",
        )

    with tempfile.TemporaryDirectory(prefix="mobiflow-maestro-cloud-") as tmp:
        root = Path(tmp)
        flow_path = root / (req.flow_name or "flow.yaml")
        flow_path.write_text(req.flow_yaml, encoding="utf-8")
        for rel, body in (req.scripts or {}).items():
            sp = root / rel
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(body, encoding="utf-8")

        args = [
            binary,
            "cloud",
            "--api-key",
            api_key,
            "--flows",
            str(flow_path),
            "--format",
            "JUNIT",
            "--name",
            req.build_name or req.project or "MobiFlow",
        ]
        if app_file:
            args.extend(["--app-file", app_file])
        elif app_binary_id:
            args.extend(["--app-binary-id", app_binary_id])
        for did in req.devices or []:
            if did and ("-" in did or "_" in did):
                args.extend(["--device-model", did])
                break
        out_xml = root / "report.xml"
        args.extend(["--output", str(out_xml)])

        if progress:
            progress("Uploading to Maestro Cloud (`maestro cloud`)…")

        result = await _run_cmd(
            args, timeout=float(req.timeout_s or 1800), cwd=str(root)
        )
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        ok = bool(result.get("ok"))

        dashboard = ""
        for line in (stdout + "\n" + stderr).splitlines():
            m = re.search(r"https?://\S+", line)
            if m and "maestro" in m.group(0).lower():
                dashboard = m.group(0).rstrip(").,]")
                break

        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            if out_xml.is_file():
                (artifact_dir / "maestro-junit.xml").write_text(
                    out_xml.read_text(encoding="utf-8"), encoding="utf-8"
                )
            (artifact_dir / "maestro-cloud-stdout.txt").write_text(
                stdout, encoding="utf-8"
            )
            (artifact_dir / "maestro-cloud-stderr.txt").write_text(
                stderr, encoding="utf-8"
            )

        return CloudRunResult(
            ok=ok,
            provider="maestro",
            status="passed" if ok else "failed",
            error=None if ok else str(result.get("error") or "maestro_cloud_failed"),
            stdout=stdout,
            stderr=stderr,
            dashboard_url=dashboard,
            media_dir=str(artifact_dir) if artifact_dir else "",
        )

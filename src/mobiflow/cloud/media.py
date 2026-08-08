"""Download cloud-lab screenshots / video / logs into local run artifacts."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from mobiflow.cloud.base import CloudCredentials

logger = logging.getLogger(__name__)

_URL_KEYS = {
    "screenshots",
    "screenshot",
    "video",
    "video_url",
    "device_log",
    "device_logs",
    "devicelogs",
    "maestro_log",
    "maestro_logs",
    "maestrologs",
    "network_log",
    "network_logs",
    "instrumentation_log",
}


def collect_media_urls(payload: Any, *, limit: int = 40) -> list[dict[str, str]]:
    """Walk nested JSON and collect media URL entries ``{kind, url}``."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(kind: str, url: str) -> None:
        u = (url or "").strip()
        if not u.startswith("http"):
            return
        # Strip video time anchors for download
        clean = u.split("#", 1)[0]
        if clean in seen:
            return
        seen.add(clean)
        found.append({"kind": kind, "url": clean})

    def _walk(node: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(node, dict):
            for key, val in node.items():
                lk = str(key).lower()
                if lk in _URL_KEYS and isinstance(val, str):
                    kind = "screenshot" if "screenshot" in lk else (
                        "video" if "video" in lk else "log"
                    )
                    _add(kind, val)
                else:
                    _walk(val)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)
    return found[:limit]


def extract_session_ids(build_payload: dict[str, Any]) -> list[str]:
    """Pull session ids from a BrowserStack Maestro build status payload."""
    ids: list[str] = []
    sessions = build_payload.get("sessions") or []
    if isinstance(sessions, list):
        for sess in sessions:
            if isinstance(sess, dict):
                sid = sess.get("id") or sess.get("session_id") or sess.get("sessionId")
                if sid:
                    ids.append(str(sid))
            elif isinstance(sess, str):
                ids.append(sess)
    # Sometimes nested under devices
    devices = build_payload.get("devices") or []
    if isinstance(devices, list):
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            for sess in dev.get("sessions") or []:
                if isinstance(sess, dict):
                    sid = sess.get("id") or sess.get("session_id")
                    if sid:
                        ids.append(str(sid))
    # Deduplicate preserving order
    out: list[str] = []
    seen: set[str] = set()
    for sid in ids:
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def guess_filename(kind: str, url: str, index: int) -> str:
    path = urlparse(url).path.rstrip("/")
    leaf = Path(path).name or kind
    # BrowserStack often ends with bare "screenshot" / "video"
    if leaf in {"screenshot", "screenshots", "video", "devicelogs", "maestrologs"}:
        ext = {
            "screenshot": ".png",
            "video": ".mp4",
            "log": ".txt",
        }.get(kind, ".bin")
        return f"{index:02d}-{kind}{ext}"
    if "." not in leaf:
        ext = ".png" if kind == "screenshot" else (".mp4" if kind == "video" else ".txt")
        return f"{index:02d}-{leaf}{ext}"
    return f"{index:02d}-{leaf}"


async def download_media_files(
    client: httpx.AsyncClient,
    items: list[dict[str, str]],
    dest_dir: Path,
    *,
    auth: tuple[str, str] | None = None,
    limit: int = 24,
) -> list[str]:
    """Download media URLs into dest_dir; return relative filenames written."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for i, item in enumerate(items[:limit], start=1):
        url = item["url"]
        kind = item.get("kind") or "file"
        name = guess_filename(kind, url, i)
        path = dest_dir / name
        try:
            resp = await client.get(url, auth=auth, timeout=120.0, follow_redirects=True)
            if resp.status_code >= 400:
                logger.warning("Cloud media HTTP %s for %s", resp.status_code, url)
                continue
            ctype = (resp.headers.get("content-type") or "").lower()
            # If we guessed wrong extension for JSON error pages, skip
            if (
                "application/json" in ctype
                and kind in {"screenshot", "video"}
            ):
                logger.debug("Skipping JSON media body for %s", url)
                continue
            path.write_bytes(resp.content)
            written.append(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cloud media download failed %s: %s", url, exc)
    return written


async def fetch_browserstack_session(
    client: httpx.AsyncClient,
    creds: CloudCredentials,
    build_id: str,
    session_id: str,
) -> dict[str, Any]:
    url = (
        "https://api-cloud.browserstack.com/app-automate/maestro/v2/"
        f"builds/{build_id}/sessions/{session_id}"
    )
    resp = await client.get(url, auth=(creds.username, creds.access_key), timeout=60.0)
    resp.raise_for_status()
    return resp.json()


async def pull_browserstack_media(
    creds: CloudCredentials,
    build_id: str,
    build_payload: dict[str, Any],
    dest_dir: Path,
    *,
    progress: Any = None,
) -> dict[str, Any]:
    """Fetch session details + download screenshots/video/logs for a BS build."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    urls = collect_media_urls(build_payload)
    session_payloads: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for sid in extract_session_ids(build_payload):
            try:
                sess = await fetch_browserstack_session(client, creds, build_id, sid)
                session_payloads.append(sess)
                urls.extend(collect_media_urls(sess))
            except Exception as exc:  # noqa: BLE001
                logger.warning("BrowserStack session %s: %s", sid, exc)
        # Deduplicate urls
        dedup: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in urls:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            dedup.append(item)
        if progress and dedup:
            progress(f"Downloading {len(dedup)} cloud media file(s)…")
        written = await download_media_files(
            client,
            dedup,
            dest_dir,
            auth=(creds.username, creds.access_key),
        )
    # Persist URL index for reports even when download fails
    index = {
        "provider": "browserstack",
        "build_id": build_id,
        "urls": dedup,
        "files": written,
        "sessions": len(session_payloads),
    }
    (dest_dir / "media-index.json").write_text(
        __import__("json").dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return index


_HTTP_RE = re.compile(r"https?://[^\s\"'<>]+")


def extract_urls_from_text(text: str) -> list[dict[str, str]]:
    """Best-effort media URLs from HyperExecute CLI stdout/stderr."""
    out: list[dict[str, str]] = []
    for match in _HTTP_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,);'\"")
        lower = url.lower()
        if any(x in lower for x in ("screenshot", "video", ".png", ".mp4", "artifact")):
            kind = "video" if "video" in lower or lower.endswith(".mp4") else "screenshot"
            out.append({"kind": kind, "url": url.split("#", 1)[0]})
    return out


async def pull_testmu_media(
    stdout: str,
    stderr: str,
    dest_dir: Path,
    *,
    creds: CloudCredentials | None = None,
    progress: Any = None,
) -> dict[str, Any]:
    """Download any media URLs found in TestMu/HyperExecute output."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    urls = extract_urls_from_text(f"{stdout}\n{stderr}")
    written: list[str] = []
    if urls:
        if progress:
            progress(f"Downloading {len(urls)} TestMu media URL(s)…")
        auth = (creds.username, creds.access_key) if creds else None
        async with httpx.AsyncClient() as client:
            written = await download_media_files(client, urls, dest_dir, auth=auth)
    index = {
        "provider": "testmu",
        "urls": urls,
        "files": written,
        "note": (
            "HyperExecute media is best-effort from CLI output; "
            "open dashboard_url when empty."
            if not written
            else ""
        ),
    }
    (dest_dir / "media-index.json").write_text(
        __import__("json").dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return index

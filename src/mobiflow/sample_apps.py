"""Download and install FOSS sample apps (Wikipedia, Joplin) onto a connected device.

Binaries are **not** shipped in the npm/git package (too large). They download
into ``builds/`` on demand from official Wikimedia / GitHub releases.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

WIKIPEDIA_STABLE_INDEX = (
    "https://releases.wikimedia.org/mobile/android/wikipedia/stable/"
)
JOPLIN_RELEASES_API = (
    "https://api.github.com/repos/laurent22/joplin-android/releases?per_page=15"
)

_APK_RE = re.compile(
    r'href="(wikipedia-\d+-r-\d{4}-\d{2}-\d{2}\.apk)"',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SampleApp:
    name: str
    app_id_android: str
    app_id_ios: str
    label: str
    notes: str


CATALOG: dict[str, SampleApp] = {
    "wikipedia": SampleApp(
        name="wikipedia",
        app_id_android="org.wikipedia",
        app_id_ios="org.wikimedia.wikipedia",
        label="Wikipedia (Android APK from Wikimedia releases)",
        notes=(
            "Android: downloads stable APK. "
            "iOS Simulator: App Store IPA cannot be sideloaded — "
            "pass --app path/to/Wikipedia.app from a local Xcode build."
        ),
    ),
    "joplin": SampleApp(
        name="joplin",
        app_id_android="net.cozic.joplin",
        app_id_ios="net.cozic.joplin",
        label="Joplin notes (Android APK from GitHub releases)",
        notes=(
            "Android: downloads universal APK. "
            "iOS: pass --app path/to/Joplin.app from a local build."
        ),
    ),
}


def list_sample_apps() -> list[SampleApp]:
    return [CATALOG[k] for k in sorted(CATALOG)]


def get_sample_app(name: str) -> SampleApp:
    key = (name or "").strip().lower()
    if key not in CATALOG:
        known = ", ".join(sorted(CATALOG))
        raise ValueError(f"Unknown sample app {name!r}. Known: {known}")
    return CATALOG[key]


def default_builds_dir(repo: Path | None = None) -> Path:
    root = Path(repo).expanduser().resolve() if repo else Path.cwd()
    return root / "builds"


def _http_get(url: str, *, timeout: float = 60.0) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "MobiFlow/sample-apps",
            "Accept": "*/*",
        },
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed HTTPS URLs
        return resp.read()


def resolve_wikipedia_apk_url(html: str | None = None) -> str:
    """Pick the newest ``wikipedia-*-r-YYYY-MM-DD.apk`` from Wikimedia stable."""
    if html is None:
        html = _http_get(WIKIPEDIA_STABLE_INDEX, timeout=30.0).decode(
            "utf-8", errors="replace"
        )
    names = sorted(set(_APK_RE.findall(html)), reverse=True)
    if not names:
        names = sorted(
            set(
                re.findall(
                    r"(wikipedia-\d+-r-\d{4}-\d{2}-\d{2}\.apk)",
                    html,
                    flags=re.IGNORECASE,
                )
            ),
            reverse=True,
        )
    if not names:
        raise RuntimeError(
            f"No Wikipedia APK found at {WIKIPEDIA_STABLE_INDEX}"
        )
    return WIKIPEDIA_STABLE_INDEX.rstrip("/") + "/" + names[0]


def resolve_joplin_apk_url(payload: Any = None) -> str:
    """Latest non-prerelease Joplin Android APK from GitHub releases."""
    if payload is None:
        raw = _http_get(JOPLIN_RELEASES_API, timeout=30.0)
        payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected GitHub releases payload for Joplin")
    for rel in payload:
        if rel.get("prerelease"):
            continue
        for asset in rel.get("assets") or []:
            name = str(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            if name.endswith(".apk") and url:
                return url
    for rel in payload:
        for asset in rel.get("assets") or []:
            name = str(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            if name.endswith(".apk") and url:
                return url
    raise RuntimeError("No Joplin APK asset found on GitHub releases")


def resolve_download_url(name: str) -> str:
    app = get_sample_app(name)
    if app.name == "wikipedia":
        return resolve_wikipedia_apk_url()
    if app.name == "joplin":
        return resolve_joplin_apk_url()
    raise ValueError(f"No Android download URL for {app.name}")


def download_sample_apk(
    name: str,
    *,
    dest_dir: Path | None = None,
    force: bool = False,
    progress: Any = None,
) -> Path:
    """Download sample APK into ``builds/<name>.apk`` (cached unless ``force``)."""
    app = get_sample_app(name)
    out_dir = Path(dest_dir) if dest_dir else default_builds_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{app.name}.apk"
    if dest.is_file() and dest.stat().st_size > 1_000_000 and not force:
        if progress:
            progress(f"Using cached APK: {dest}")
        return dest

    url = resolve_download_url(app.name)
    if progress:
        progress(f"Downloading {app.label}…")
        progress(f"  {url}")
    try:
        data = _http_get(url, timeout=300.0)
    except (HTTPError, URLError, TimeoutError) as e:
        raise RuntimeError(f"Download failed for {app.name}: {e}") from e
    if len(data) < 100_000:
        raise RuntimeError(
            f"Downloaded file too small ({len(data)} bytes) — unexpected response"
        )
    tmp = dest.with_suffix(".apk.partial")
    tmp.write_bytes(data)
    tmp.replace(dest)
    if progress:
        progress(f"Saved {dest} ({len(data) // (1024 * 1024)} MB)")
    return dest


async def install_sample_app(
    name: str,
    *,
    platform: str = "android",
    device_id: str | None = None,
    apk_path: str | Path | None = None,
    app_path: str | Path | None = None,
    dest_dir: Path | None = None,
    download_only: bool = False,
    force_download: bool = False,
    progress: Any = None,
) -> dict[str, Any]:
    """Download (Android) and/or install a sample app onto a connected device."""
    from mobiflow.maestro.lifecycle import install_app_local

    app = get_sample_app(name)
    plat = (platform or "android").lower()
    result: dict[str, Any] = {
        "ok": False,
        "app": app.name,
        "platform": plat,
        "app_id": app.app_id_android if plat == "android" else app.app_id_ios,
    }

    package: Path | None = None
    if apk_path:
        package = Path(apk_path).expanduser().resolve()
    elif app_path:
        package = Path(app_path).expanduser().resolve()
    elif plat == "android":
        package = download_sample_apk(
            app.name,
            dest_dir=dest_dir,
            force=force_download,
            progress=progress,
        )
        result["apk_path"] = str(package)
    else:
        result["error"] = "ios_needs_app_bundle"
        result["message"] = (
            f"iOS: no store IPA sideload. Build {app.name} locally and pass "
            f"--app path/to/{app.name}.app (simctl install). {app.notes}"
        )
        return result

    if download_only:
        result["ok"] = True
        result["message"] = f"Downloaded to {package}"
        result["apk_path"] = str(package)
        return result

    if package is None:
        result["error"] = "no_package"
        result["message"] = "No APK/.app path to install"
        return result

    if progress:
        progress(f"Installing {app.name} on {device_id or 'default device'}…")
    installed = await install_app_local(
        package,
        device_id=device_id,
        platform=plat,
    )
    result.update(installed)
    if installed.get("ok"):
        result["message"] = (
            f"Installed {app.name} ({result['app_id']}) via {package}"
        )
    return result

"""Tests for cloud media URL harvesting / download helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from mobiflow.cloud.media import (
    collect_media_urls,
    download_media_files,
    extract_session_ids,
    extract_urls_from_text,
)


def test_collect_media_urls_and_sessions():
    payload = {
        "sessions": [{"id": "sess-1"}, {"id": "sess-2"}],
        "devices": [{"sessions": [{"id": "sess-1"}]}],
        "nested": {
            "screenshots": "https://example.com/shot.png",
            "video": "https://example.com/vid.mp4#t=0,10",
        },
    }
    assert extract_session_ids(payload) == ["sess-1", "sess-2"]
    urls = collect_media_urls(payload)
    kinds = {u["kind"] for u in urls}
    assert "screenshot" in kinds
    assert "video" in kinds
    assert all("#" not in u["url"] for u in urls)


def test_extract_urls_from_text():
    text = "see https://cdn.example.com/artifact/video.mp4 and https://x/screenshot/1"
    urls = extract_urls_from_text(text)
    assert any(u["kind"] == "video" for u in urls)


def test_download_media_files(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\x89PNG\r\n\x1a\nfake")

    transport = httpx.MockTransport(handler)

    async def _run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await download_media_files(
                client,
                [{"kind": "screenshot", "url": "https://example.com/screenshot"}],
                tmp_path / "cloud",
            )

    written = asyncio.run(_run())
    assert written
    assert (tmp_path / "cloud" / written[0]).is_file()

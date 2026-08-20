"""Tests for FOSS sample-app download URL resolution (no network)."""

from __future__ import annotations

import pytest

from mobiflow.sample_apps import (
    get_sample_app,
    list_sample_apps,
    resolve_joplin_apk_url,
    resolve_wikipedia_apk_url,
)


def test_catalog_has_wikipedia_and_joplin():
    names = {a.name for a in list_sample_apps()}
    assert "wikipedia" in names
    assert "joplin" in names
    wiki = get_sample_app("wikipedia")
    assert wiki.app_id_android == "org.wikipedia"
    assert wiki.app_id_ios == "org.wikimedia.wikipedia"


def test_unknown_sample_app():
    with pytest.raises(ValueError, match="Unknown sample app"):
        get_sample_app("booking")


def test_resolve_wikipedia_apk_url_from_html():
    html = """
    <a href="wikipedia-50590-r-2026-05-28.apk">old</a>
    <a href="wikipedia-50602-r-2026-08-19.apk">new</a>
    <a href="wikipedia-50601-r-2026-08-11.apk">mid</a>
    """
    url = resolve_wikipedia_apk_url(html)
    assert url.endswith("wikipedia-50602-r-2026-08-19.apk")
    assert url.startswith("https://releases.wikimedia.org/")


def test_resolve_joplin_apk_url_prefers_stable():
    payload = [
        {
            "prerelease": True,
            "assets": [
                {
                    "name": "joplin-v9.9.9.apk",
                    "browser_download_url": "https://example.com/pre.apk",
                }
            ],
        },
        {
            "prerelease": False,
            "assets": [
                {
                    "name": "joplin-v3.6.21.apk",
                    "browser_download_url": "https://example.com/stable.apk",
                }
            ],
        },
    ]
    assert resolve_joplin_apk_url(payload) == "https://example.com/stable.apk"

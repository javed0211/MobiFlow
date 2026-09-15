"""Tests for FOSS sample-app download URL resolution (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mobiflow.sample_apps import (
    BROWSERSTACK_ANDROID_APK,
    TESTMU_ANDROID_APK,
    get_sample_app,
    looks_like_package_path,
    list_sample_apps,
    platform_for_package,
    resolve_download_url,
    resolve_joplin_apk_url,
    resolve_wdio_apk_url,
    resolve_wikipedia_apk_url,
)


def test_catalog_has_wikipedia_and_joplin():
    names = {a.name for a in list_sample_apps()}
    assert "wikipedia" in names
    assert "joplin" in names
    assert "wdio" in names
    assert "browserstack" in names
    assert "testmu" in names
    wiki = get_sample_app("wikipedia")
    assert wiki.app_id_android == "org.wikipedia"
    assert wiki.app_id_ios == "org.wikimedia.wikipedia"
    demo = get_sample_app("native-demo")
    assert demo.name == "wdio"
    assert demo.app_id_android == "com.wdiodemoapp"
    bs = get_sample_app("bstack")
    assert bs.name == "browserstack"
    assert bs.app_id_android == "org.wikipedia"
    assert bs.android_url == BROWSERSTACK_ANDROID_APK
    tm = get_sample_app("proverbial")
    assert tm.name == "testmu"
    assert tm.app_id_android == "com.lambdatest.proverbial"
    assert tm.android_url == TESTMU_ANDROID_APK


def test_unknown_sample_app():
    with pytest.raises(ValueError, match="Unknown sample app"):
        get_sample_app("booking")


def test_looks_like_package_path(tmp_path):
    apk = tmp_path / "MyDemoApp.apk"
    apk.write_bytes(b"fake")
    assert looks_like_package_path(str(apk))
    assert looks_like_package_path("/tmp/foo.apk")
    assert not looks_like_package_path("Saucelab")
    assert platform_for_package(apk) == "android"
    assert platform_for_package(Path("demo.ipa")) == "ios"


def test_install_unknown_name_with_local_apk(tmp_path, monkeypatch):
    import asyncio

    from mobiflow.sample_apps import install_sample_app

    apk = tmp_path / "mda.apk"
    apk.write_bytes(b"fake-apk")

    async def fake_install(path, **kwargs):
        return {"ok": True, "message": f"Installed via adb {path}"}

    monkeypatch.setattr(
        "mobiflow.maestro.lifecycle.install_app_local", fake_install
    )
    result = asyncio.run(install_sample_app("Saucelab", apk_path=apk))
    assert result["ok"] is True
    assert "mda.apk" in result["message"]


def test_install_direct_apk_path(tmp_path, monkeypatch):
    import asyncio

    from mobiflow.sample_apps import install_sample_app

    apk = tmp_path / "local.apk"
    apk.write_bytes(b"fake-apk")

    async def fake_install(path, **kwargs):
        return {"ok": True, "message": "ok"}

    monkeypatch.setattr(
        "mobiflow.maestro.lifecycle.install_app_local", fake_install
    )
    result = asyncio.run(install_sample_app(str(apk)))
    assert result["ok"] is True


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


def test_resolve_wdio_apk_url_prefers_android_asset():
    payload = [
        {
            "prerelease": False,
            "assets": [
                {
                    "name": "ios.simulator.wdio.native.app.v2.2.0.zip",
                    "browser_download_url": "https://example.com/ios.zip",
                },
                {
                    "name": "android.wdio.native.app.v2.2.0.apk",
                    "browser_download_url": "https://example.com/wdio.apk",
                },
            ],
        }
    ]
    assert resolve_wdio_apk_url(payload) == "https://example.com/wdio.apk"


def test_cloud_sample_download_urls_are_static():
    assert resolve_download_url("browserstack") == BROWSERSTACK_ANDROID_APK
    assert resolve_download_url("testmu") == TESTMU_ANDROID_APK
    assert resolve_download_url("lambdatest") == TESTMU_ANDROID_APK

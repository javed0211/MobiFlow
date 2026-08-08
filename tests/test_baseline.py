"""Tests for PNG baseline compare."""

from __future__ import annotations

from pathlib import Path

from mobiflow.baseline import (
    _write_png_rgba,
    compare_case_screenshot,
    compare_images,
    update_baseline,
)


def _solid(path: Path, rgb: tuple[int, int, int], w: int = 8, h: int = 8) -> None:
    r, g, b = rgb
    rgba = bytes([r, g, b, 255] * (w * h))
    _write_png_rgba(path, w, h, rgba)


def test_compare_identical(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _solid(a, (10, 20, 30))
    _solid(b, (10, 20, 30))
    ok, ratio, _ = compare_images(a, b, diff_path=tmp_path / "d.png")
    assert ok is True
    assert ratio == 0.0


def test_compare_different(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _solid(a, (0, 0, 0))
    _solid(b, (255, 0, 0))
    ok, ratio, diff = compare_images(a, b, diff_path=tmp_path / "d.png", threshold=0.01)
    assert ok is False
    assert ratio > 0.5
    assert diff is not None and diff.is_file()


def test_update_and_compare_case(tmp_path: Path):
    img = tmp_path / "shot.png"
    _solid(img, (40, 50, 60))
    update_baseline("smoke", img, tmp_path)
    result = compare_case_screenshot("smoke", img, tmp_path)
    assert result.ok is True

"""Screenshot baseline compare for visual smoke checks."""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class BaselineResult:
    ok: bool
    case: str
    baseline: str = ""
    candidate: str = ""
    diff_path: str = ""
    mismatch_ratio: float = 0.0
    threshold: float = 0.02
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "case": self.case,
            "baseline": self.baseline,
            "candidate": self.candidate,
            "diff_path": self.diff_path,
            "mismatch_ratio": self.mismatch_ratio,
            "threshold": self.threshold,
            "message": self.message,
        }


def baseline_dir(artifacts_dir: Path, case_name: str) -> Path:
    return Path(artifacts_dir) / "baselines" / case_name


def _read_png_rgba(path: Path) -> tuple[int, int, bytes]:
    """Minimal PNG reader (8-bit RGBA/RGB/Gray). Returns width, height, RGBA bytes."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")
    pos = 8
    width = height = 0
    bit_depth = 8
    color_type = 2
    raw = b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        pos += 4
        ctype = data[pos : pos + 4]
        pos += 4
        chunk = data[pos : pos + length]
        pos += length
        pos += 4  # crc
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
        elif ctype == b"IDAT":
            raw += chunk
        elif ctype == b"IEND":
            break
    if not width or not height:
        raise ValueError(f"Invalid PNG header: {path}")
    if bit_depth != 8 or color_type not in (0, 2, 4, 6):
        raise ValueError(f"Unsupported PNG format in {path}")
    decompressed = zlib.decompress(raw)
    # Remove filter bytes (assume filter 0 for simplicity; handle None/sub roughly)
    stride = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    row_bytes = width * stride
    pixels = bytearray()
    offset = 0
    prev = bytearray(row_bytes)
    for _y in range(height):
        filter_type = decompressed[offset]
        offset += 1
        row = bytearray(decompressed[offset : offset + row_bytes])
        offset += row_bytes
        if filter_type == 1:  # Sub
            for i in range(row_bytes):
                left = row[i - stride] if i >= stride else 0
                row[i] = (row[i] + left) & 0xFF
        elif filter_type == 2:  # Up
            for i in range(row_bytes):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filter_type == 3:  # Average
            for i in range(row_bytes):
                left = row[i - stride] if i >= stride else 0
                row[i] = (row[i] + ((left + prev[i]) // 2)) & 0xFF
        elif filter_type == 4:  # Paeth
            for i in range(row_bytes):
                a = row[i - stride] if i >= stride else 0
                b = prev[i]
                c = prev[i - stride] if i >= stride else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF
        elif filter_type != 0:
            raise ValueError(f"Unsupported PNG filter {filter_type} in {path}")
        prev = row
        if color_type == 6:
            pixels.extend(row)
        elif color_type == 2:
            for i in range(0, len(row), 3):
                pixels.extend([row[i], row[i + 1], row[i + 2], 255])
        elif color_type == 0:
            for v in row:
                pixels.extend([v, v, v, 255])
        elif color_type == 4:
            for i in range(0, len(row), 2):
                pixels.extend([row[i], row[i], row[i], row[i + 1]])
    return width, height, bytes(pixels)


def _write_png_rgba(path: Path, width: int, height: int, rgba: bytes) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw.extend(rgba[y * stride : (y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def compare_images(
    baseline: Path,
    candidate: Path,
    *,
    diff_path: Path | None = None,
    threshold: float = 0.02,
    max_channel_delta: int = 12,
) -> tuple[bool, float, Path | None]:
    """Return (ok, mismatch_ratio, diff_path)."""
    bw, bh, bp = _read_png_rgba(baseline)
    cw, ch, cp = _read_png_rgba(candidate)
    if (bw, bh) != (cw, ch):
        # Treat size mismatch as total fail
        return False, 1.0, None
    total = bw * bh
    mismatches = 0
    diff = bytearray(len(bp))
    for i in range(0, len(bp), 4):
        dr = abs(bp[i] - cp[i])
        dg = abs(bp[i + 1] - cp[i + 1])
        db = abs(bp[i + 2] - cp[i + 2])
        if max(dr, dg, db) > max_channel_delta:
            mismatches += 1
            diff[i] = 255
            diff[i + 1] = 0
            diff[i + 2] = 0
            diff[i + 3] = 255
        else:
            # dim baseline
            diff[i] = bp[i] // 3
            diff[i + 1] = bp[i + 1] // 3
            diff[i + 2] = bp[i + 2] // 3
            diff[i + 3] = 255
    ratio = mismatches / max(1, total)
    out_diff = None
    if diff_path is not None:
        _write_png_rgba(diff_path, bw, bh, bytes(diff))
        out_diff = diff_path
    return ratio <= threshold, ratio, out_diff


def update_baseline(case_name: str, image: Path, artifacts_dir: Path) -> Path:
    dest = baseline_dir(artifacts_dir, case_name) / "baseline.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(image.read_bytes())
    meta = {
        "case": case_name,
        "source": str(image),
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (dest.parent / "baseline.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def compare_case_screenshot(
    case_name: str,
    candidate: Path,
    artifacts_dir: Path,
    *,
    threshold: float = 0.02,
) -> BaselineResult:
    base = baseline_dir(artifacts_dir, case_name) / "baseline.png"
    if not base.is_file():
        return BaselineResult(
            ok=False,
            case=case_name,
            candidate=str(candidate),
            threshold=threshold,
            message="No baseline — run `mobiflow baseline update <case> <png>`",
        )
    diff = baseline_dir(artifacts_dir, case_name) / "diff.png"
    ok, ratio, diff_out = compare_images(
        base, candidate, diff_path=diff, threshold=threshold
    )
    return BaselineResult(
        ok=ok,
        case=case_name,
        baseline=str(base),
        candidate=str(candidate),
        diff_path=str(diff_out or ""),
        mismatch_ratio=ratio,
        threshold=threshold,
        message="pass" if ok else f"mismatch {ratio:.3%} > {threshold:.3%}",
    )

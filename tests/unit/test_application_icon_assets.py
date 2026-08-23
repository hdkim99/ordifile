# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import struct
import subprocess
import sys
from pathlib import Path

from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "docs" / "assets" / "ordifile-icon.svg"
PNG_ROOT = ROOT / "packaging" / "standalone" / "assets" / "png"
ICO = ROOT / "packaging" / "standalone" / "assets" / "ordifile.ico"
ICNS = ROOT / "packaging" / "standalone" / "assets" / "Ordifile.icns"
RUNTIME_PNG = ROOT / "src" / "ordifile" / "desktop" / "assets" / "ordifile-icon-512.png"
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS_TYPES = {
    b"icp4",
    b"icp5",
    b"icp6",
    b"ic07",
    b"ic08",
    b"ic09",
    b"ic10",
    b"ic11",
    b"ic12",
    b"ic13",
    b"ic14",
}


def test_canonical_svg_is_self_contained_original_vector_artwork() -> None:
    text = SVG.read_text(encoding="utf-8")
    lowered = text.casefold()
    assert 'viewbox="0 0 1024 1024"' in lowered
    assert lowered.count("http://") == 1
    assert "http://www.w3.org/2000/svg" in lowered
    for prohibited in (
        "<script",
        "<image",
        "<text",
        "href=",
        "url(",
        "data:",
        "file:",
        "font-family",
    ):
        assert prohibited not in lowered
    assert "spdx-license-identifier: apache-2.0" in lowered


def test_png_derivatives_cover_every_required_size_and_small_sizes_are_legible() -> None:
    for size in PNG_SIZES:
        image = QImage(str(PNG_ROOT / f"ordifile-icon-{size}.png"))
        assert not image.isNull()
        assert (image.width(), image.height()) == (size, size)
        assert image.hasAlphaChannel()
    assert RUNTIME_PNG.read_bytes() == (PNG_ROOT / "ordifile-icon-512.png").read_bytes()

    for size in (16, 32):
        image = QImage(str(PNG_ROOT / f"ordifile-icon-{size}.png")).convertToFormat(
            QImage.Format.Format_RGBA8888
        )
        opaque = 0
        light = 0
        cyan = 0
        for y in range(size):
            for x in range(size):
                color = image.pixelColor(x, y)
                if color.alpha() > 220:
                    opaque += 1
                if color.red() > 180 and color.green() > 180 and color.blue() > 180:
                    light += 1
                if color.green() > 120 and color.blue() > 120 and color.red() < 100:
                    cyan += 1
        assert opaque >= size * size // 2
        assert light >= size
        assert cyan >= max(2, size // 2)


def test_windows_ico_contains_required_32_bit_png_representations() -> None:
    content = ICO.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", content)
    assert (reserved, kind, count) == (0, 1, len(ICO_SIZES))
    sizes: list[int] = []
    for index in range(count):
        width, height, colors, reserved_byte, planes, depth, length, offset = struct.unpack_from(
            "<BBBBHHII", content, 6 + 16 * index
        )
        decoded_width = width or 256
        decoded_height = height or 256
        sizes.append(decoded_width)
        assert decoded_width == decoded_height
        assert colors == reserved_byte == 0
        assert (planes, depth) == (1, 32)
        assert content[offset : offset + 8] == b"\x89PNG\r\n\x1a\n"
        assert offset + length <= len(content)
    assert tuple(sizes) == ICO_SIZES


def test_macos_icns_contains_standard_and_retina_png_representations() -> None:
    content = ICNS.read_bytes()
    assert content[:4] == b"icns"
    assert struct.unpack_from(">I", content, 4)[0] == len(content)
    offset = 8
    representations: set[bytes] = set()
    while offset < len(content):
        identifier = content[offset : offset + 4]
        length = struct.unpack_from(">I", content, offset + 4)[0]
        assert length > 8
        assert content[offset + 8 : offset + 16] == b"\x89PNG\r\n\x1a\n"
        representations.add(identifier)
        offset += length
    assert offset == len(content)
    assert representations == ICNS_TYPES


def test_generation_is_current_without_a_qt_platform_application() -> None:
    script = ROOT / "scripts" / "generate_app_icons.py"
    source = script.read_text(encoding="utf-8")
    assert "QGuiApplication" not in source
    assert "QApplication" not in source
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {"QT_PLUGIN_PATH", "QT_QPA_PLATFORM", "QT_QPA_PLATFORM_PLUGIN_PATH"}
    }
    completed = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

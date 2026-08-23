# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate deterministic Ordifile application-icon derivatives from the SVG master."""

from __future__ import annotations

import argparse
import struct
import tempfile
from collections.abc import Sequence
from pathlib import Path

PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS_REPRESENTATIONS = (
    (b"icp4", 16),
    (b"icp5", 32),
    (b"icp6", 64),
    (b"ic07", 128),
    (b"ic08", 256),
    (b"ic09", 512),
    (b"ic10", 1024),
    (b"ic11", 32),
    (b"ic12", 64),
    (b"ic13", 256),
    (b"ic14", 512),
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "docs" / "assets" / "ordifile-icon.svg"


def _relative_outputs(root: Path) -> tuple[Path, ...]:
    png_root = root / "packaging" / "standalone" / "assets" / "png"
    return (
        *(png_root / f"ordifile-icon-{size}.png" for size in PNG_SIZES),
        root / "packaging" / "standalone" / "assets" / "ordifile.ico",
        root / "packaging" / "standalone" / "assets" / "Ordifile.icns",
        root / "src" / "ordifile" / "desktop" / "assets" / "ordifile-icon-512.png",
        root / "docs" / "assets" / "ordifile-icon-1024.png",
    )


def _render_pngs(source: Path, png_root: Path) -> dict[int, bytes]:
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(source))
    if not renderer.isValid() or renderer.defaultSize().width() != 1024:
        raise ValueError("The canonical application icon SVG is invalid.")
    png_root.mkdir(parents=True, exist_ok=True)
    rendered: dict[int, bytes] = {}
    for size in PNG_SIZES:
        image = QImage(size, size, QImage.Format.Format_RGBA8888)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        destination = png_root / f"ordifile-icon-{size}.png"
        if not image.save(str(destination)):
            raise OSError(f"Could not write {destination.name}.")
        rendered[size] = destination.read_bytes()
    return rendered


def _write_ico(destination: Path, pngs: dict[int, bytes]) -> None:
    header_size = 6 + 16 * len(ICO_SIZES)
    offset = header_size
    entries: list[bytes] = []
    payloads: list[bytes] = []
    for size in ICO_SIZES:
        payload = pngs[size]
        encoded_size = 0 if size == 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                encoded_size,
                encoded_size,
                0,
                0,
                1,
                32,
                len(payload),
                offset,
            )
        )
        payloads.append(payload)
        offset += len(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        struct.pack("<HHH", 0, 1, len(ICO_SIZES)) + b"".join(entries) + b"".join(payloads)
    )


def _write_icns(destination: Path, pngs: dict[int, bytes]) -> None:
    chunks = tuple(
        identifier + struct.pack(">I", 8 + len(pngs[size])) + pngs[size]
        for identifier, size in ICNS_REPRESENTATIONS
    )
    payload = b"".join(chunks)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"icns" + struct.pack(">I", 8 + len(payload)) + payload)


def generate(source: Path, output_root: Path) -> tuple[Path, ...]:
    """Generate every committed derivative below ``output_root``."""
    png_root = output_root / "packaging" / "standalone" / "assets" / "png"
    pngs = _render_pngs(source, png_root)
    native_root = output_root / "packaging" / "standalone" / "assets"
    _write_ico(native_root / "ordifile.ico", pngs)
    _write_icns(native_root / "Ordifile.icns", pngs)
    runtime = output_root / "src" / "ordifile" / "desktop" / "assets" / "ordifile-icon-512.png"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(pngs[512])
    documentation = output_root / "docs" / "assets" / "ordifile-icon-1024.png"
    documentation.parent.mkdir(parents=True, exist_ok=True)
    documentation.write_bytes(pngs[1024])
    return _relative_outputs(output_root)


def _check(source: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="ordifile-app-icons-") as raw_temporary:
        temporary = Path(raw_temporary)
        generated = generate(source, temporary)
        mismatches = tuple(
            generated_path.relative_to(temporary).as_posix()
            for generated_path in generated
            if not (PROJECT_ROOT / generated_path.relative_to(temporary)).is_file()
            or generated_path.read_bytes()
            != (PROJECT_ROOT / generated_path.relative_to(temporary)).read_bytes()
        )
    if mismatches:
        raise ValueError("Generated application-icon assets differ: " + ", ".join(mismatches))


def main(argv: Sequence[str] | None = None) -> int:
    """Generate assets in place, or verify that committed derivatives are current."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    source = arguments.source.resolve(strict=True)
    if arguments.check:
        if arguments.output_root != PROJECT_ROOT:
            parser.error("--output-root cannot be combined with --check")
        _check(source)
    else:
        output_root = arguments.output_root.resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        generate(source, output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

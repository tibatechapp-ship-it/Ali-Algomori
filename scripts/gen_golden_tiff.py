#!/usr/bin/env python3
"""Generate the two golden TIFF reference files with zero dependencies.

- golden_dem_tile.tif      : 24x16, 8-bit grayscale, uncompressed, single strip,
                             georeferenced (ModelPixelScale + ModelTiepoint) at
                             a synthetic tile origin near Sana'a (43.9E, 15.2N).
- golden_dem_truncated.tif : the same bytes cut short -> validator must fail.

The generator writes the TIFF byte layout by hand (struct) so the reference
files do not depend on any imaging library. Re-run from repo root:
    python scripts/gen_golden_tiff.py
"""
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "tests" / "data"

W, H = 24, 16
PIXEL_SCALE = (0.001, 0.001, 0.0)            # ~0.001 deg per pixel
TIEPOINT = (0.0, 0.0, 0.0, 43.9, 15.2, 0.0)  # i,j,k -> x,y,z (Sana'a area)

TAG_IMAGE_WIDTH = 256
TAG_IMAGE_LENGTH = 257
TAG_BITS_PER_SAMPLE = 258
TAG_COMPRESSION = 259
TAG_PHOTOMETRIC = 262
TAG_STRIP_OFFSETS = 273
TAG_SAMPLES_PER_PIXEL = 277
TAG_ROWS_PER_STRIP = 278
TAG_STRIP_BYTE_COUNTS = 279
TAG_MODEL_PIXEL_SCALE = 33550
TAG_MODEL_TIEPOINT = 33922

REQUIRED_TAGS = (TAG_IMAGE_WIDTH, TAG_IMAGE_LENGTH, TAG_BITS_PER_SAMPLE,
                 TAG_COMPRESSION, TAG_PHOTOMETRIC, TAG_STRIP_OFFSETS,
                 TAG_SAMPLES_PER_PIXEL, TAG_ROWS_PER_STRIP, TAG_STRIP_BYTE_COUNTS)


def dem_values() -> bytes:
    """Deterministic synthetic elevation ramp (no randomness)."""
    out = bytearray()
    for row in range(H):
        for col in range(W):
            z = 2200 + row * 3 + col * 2
            out.append(z % 256)
    return bytes(out)


def build_tiff() -> bytes:
    entries = []   # (tag, type, count, payload or None)
    rationals = []  # (tag, values) too large for the 4-byte value field

    def short(tag, val):
        entries.append((tag, 3, 1, struct.pack("<HH", val, 0)))

    def long_(tag, val):
        entries.append((tag, 4, 1, struct.pack("<I", val)))

    def rational(tag, values):
        entries.append((tag, 5, len(values), None))
        rationals.append((tag, values))

    short(TAG_IMAGE_WIDTH, W)
    short(TAG_IMAGE_LENGTH, H)
    short(TAG_BITS_PER_SAMPLE, 8)
    short(TAG_COMPRESSION, 1)  # uncompressed
    short(TAG_PHOTOMETRIC, 1)  # BlackIsZero
    long_(TAG_STRIP_OFFSETS, 0)  # patched once layout is known
    short(TAG_SAMPLES_PER_PIXEL, 1)
    short(TAG_ROWS_PER_STRIP, H)
    long_(TAG_STRIP_BYTE_COUNTS, W * H)
    rational(TAG_MODEL_PIXEL_SCALE, PIXEL_SCALE)
    rational(TAG_MODEL_TIEPOINT, TIEPOINT)

    entries.sort(key=lambda e: e[0])
    ifd_offset = 8
    ifd_size = 2 + 12 * len(entries) + 4
    rat_offset = ifd_offset + ifd_size
    patch = {}
    rat_blob = b""
    for tag, values in rationals:
        patch[tag] = rat_offset + len(rat_blob)
        for f in values:  # each float becomes one RATIONAL pair (n/1e6)
            rat_blob += struct.pack("<II", int(round(f * 1_000_000)), 1_000_000)
    strip_offset = rat_offset + len(rat_blob)

    ifd = struct.pack("<H", len(entries))
    for tag, typ, count, payload in entries:
        if tag == TAG_STRIP_OFFSETS:
            payload = struct.pack("<I", strip_offset)
        elif tag in patch:
            payload = struct.pack("<I", patch[tag])
        ifd += struct.pack("<HHI", tag, typ, count) + payload
    ifd += struct.pack("<I", 0)  # next IFD = none

    blob = struct.pack("<2sHI", b"II", 42, ifd_offset) + ifd + rat_blob + dem_values()
    assert len(blob) == strip_offset + W * H, (len(blob), strip_offset + W * H)
    assert strip_offset == rat_offset + len(rat_blob)
    return blob, strip_offset


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    blob, strip_offset = build_tiff()
    good = OUT / "golden_dem_tile.tif"
    good.write_bytes(blob)
    bad = OUT / "golden_dem_truncated.tif"
    # keep header+IFD+rationals intact, cut inside the pixel strip -> the IFD
    # parses fine but the declared strip data overruns the file (TIFF_TRUNCATED)
    cut = strip_offset + 100
    bad.write_bytes(blob[:cut])
    print(f"wrote {good} ({good.stat().st_size} bytes)")
    print(f"wrote {bad} ({bad.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

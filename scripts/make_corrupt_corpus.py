#!/usr/bin/env python3
"""make_corrupt_corpus.py — توليد مجموعة الملفات التالفة الذهبية لاختبارات v0.5.0.

كل ملف تالف يمثل حالة رفض واحدة بمسار محدد، والاختبارات تثبت رمز الرفض
الدقيق لكل حالة (لا مجرد فشل عام). الملفات السليمة الذهبية القديمة تبقى كما
هي بلا أي تعديل — أي تغيير فيها يكسر اختبارات الاعتماد المرجعي.
"""
from pathlib import Path
import struct
import zipfile

D = Path(__file__).resolve().parent.parent / "tests" / "data"

# --- 1) LAS: قص بيانات ~A في منتصفها (تلف/عبث) → LAS_DATA_ROWS_MISMATCH (error)
src = (D / "golden_las_valid.las").read_text(encoding="utf-8").splitlines()
(D / "golden_las_truncated.las").write_text(
    "\n".join(src[:-2]) + "\n", encoding="utf-8")  # 4 rows instead of 6

# --- 2) LAS: بايت NUL داخل البيانات → LAS_CONTROL_CHARS (error)
nul_text = (D / "golden_las_valid.las").read_text(encoding="utf-8")
nul_text = nul_text.replace("101.000", "101.0\x000")
(D / "golden_las_nul.las").write_bytes(nul_text.encode("utf-8"))

# --- 3) GeoJSON: CRS مسقط معلن يتناقض مع محتوى WGS84 → CRS_GEOJSON_NON_WGS84
(D / "golden_geojson_crs_utm.json").write_text(
    '{"type": "FeatureCollection", '
    '"crs": {"type": "name", "properties": {"name": "EPSG:32638"}}, '
    '"features": [{"type": "Feature", "geometry": {"type": "Point", '
    '"coordinates": [44.20, 15.35]}, "properties": {"well": "sanaa-01"}}]}',
    encoding="utf-8")

# --- 4) CSV: CRS مسقط معلن (UTM) وأعمدة lat/lon بالدرجات → CRS_MISMATCH_PROJECTED_GEO
(D / "golden_csv_utm_degrees.csv").write_text(
    "well_name,lat,lon,depth_m\n"
    "sanaa-01,15.35,44.20,120.5\n"
    "sanaa-02,15.40,44.25,98.0\n",
    encoding="utf-8")

# --- 5) CSV: أعمدة easting/northing بقيم UTM حقيقية مع CRS جغرافي معلن → CRS_MISMATCH_GEO_PROJECTED
(D / "golden_csv_geo_utmvals.csv").write_text(
    "site,easting,northing\n"
    "sanaa-a,440512.0,1700342.0\n"
    "sanaa-b,441020.5,1701899.0\n",
    encoding="utf-8")

# --- 6) CSV: بايت NUL → CSV_CONTROL_CHARS
(D / "golden_csv_nul.csv").write_bytes(
    b"well_name,lat,lon\nsanaa-01,15.3\x00,44.2\n")

# --- 7) CSV: نفس المعرف ببيانات متضاربة → CSV_ID_CONFLICT
(D / "golden_csv_id_conflict.csv").write_text(
    "well_name,lat,lon,depth_m\n"
    "sanaa-01,15.35,44.20,120.5\n"
    "sanaa-02,15.40,44.25,98.0\n"
    "sanaa-01,15.35,44.21,120.9\n",  # نفس المعرف، قيم مختلفة
    encoding="utf-8")

# --- 8) CSV: أعمدة easting/northing UTM سليمة مع CRS مسقط معلن → CRS_DECLARED_OK
(D / "golden_csv_utm_valid.csv").write_text(
    "site,easting,northing\n"
    "sanaa-a,440512.0,1700342.0\n"
    "sanaa-b,441020.5,1701899.0\n",
    encoding="utf-8")

# --- 9) TIFF: بلاط ذهبي مع وسوم ميتاداتا (Software + Copyright) لإثبات الإزالة
def make_tiff(path: Path, extra_meta: bool) -> None:
    width, height = 4, 3
    pixels = bytes(range(width * height))  # 12 بايت صورة رمادية
    # (tag, typ, count, inline_value|None, out_of_line_value|None)
    tags = [
        (256, 4, 1, struct.pack("<I", width), None),
        (257, 4, 1, struct.pack("<I", height), None),
        (258, 3, 1, struct.pack("<H", 8), None),
        (259, 3, 1, struct.pack("<H", 1), None),
        (262, 3, 1, struct.pack("<H", 1), None),
        (273, 4, 1, None, None),                     # StripOffsets — يُرقّع
        (277, 3, 1, struct.pack("<H", 1), None),
        (278, 4, 1, struct.pack("<I", height), None),
        (279, 4, 1, struct.pack("<I", len(pixels)), None),
        (33550, 5, 3, None,
         struct.pack("<IIIIII", 1, 1, 1, 1, 1, 1)),          # PixelScale RATIONAL
        (33922, 5, 6, None,
         struct.pack("<IIIIIIIIIIII",
                     0, 1, 0, 1, 0, 1,
                     221, 5, 157, 10, 0, 1)),               # Tiepoint RATIONAL
    ]
    if extra_meta:
        tags.append((305, 2, 9, None, b"GeoTool 9.9"))      # Software
        tags.append((33432, 2, 12, None, b"(C) 2026 GEO"))  # Copyright
    tags.sort(key=lambda t: t[0])
    n = len(tags)
    ifd_off = 8
    body = bytearray()
    body += struct.pack("<H", n)
    out_of_line = bytearray()
    # القيم خارج السطر تُوزَّع أولًا لنثبّت مواضعها، ثم تُكتب السجلات
    ool_positions = {}
    ool_area_start = ifd_off + 2 + 12 * n + 4
    for tag, typ, count, inline, ool in tags:
        if ool is not None:
            ool_positions[tag] = ool_area_start + len(out_of_line)
            out_of_line += ool
            if len(out_of_line) % 2:
                out_of_line += b"\x00"
    for tag, typ, count, inline, ool in tags:
        if tag == 273:
            body += struct.pack("<HHI", tag, typ, count) + b"\x00" * 4
            continue
        if ool is not None:
            body += struct.pack("<HHI", tag, typ, count) + \
                struct.pack("<I", ool_positions[tag])
        else:
            body += struct.pack("<HHI", tag, typ, count) + \
                inline.ljust(4, b"\x00")
    body += struct.pack("<I", 0)  # لا IFD ثانية
    body += out_of_line
    strip_off = ool_area_start + len(out_of_line)
    body += pixels
    # رقّع StripOffsets: السجل داخل body بإزاحة (8 وحدات ملف مسبقة)
    idx_273 = [i for i, t in enumerate(tags) if t[0] == 273][0]
    pos_body = 2 + 12 * idx_273 + 8
    body[pos_body:pos_body + 4] = struct.pack("<I", strip_off)
    path.write_bytes(b"II" + struct.pack("<HI", 42, ifd_off) + bytes(body))

make_tiff(D / "golden_dem_with_meta.tif", extra_meta=True)

# --- 10) ZIP: قنبلة ضغط (نسبة تمدد 300x+) + مسار اجتياز داخل نفس الأرشيفين
def make_zip(path: Path, *, bomb: bool, traversal: bool) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if bomb:
            # 300KB أصفار → تمدد ~300x عند ضغط level 9
            zf.writestr("zeros.bin", b"\x00" * (300 * 1024), compresslevel=9)
        if traversal:
            zf.writestr("../escape.csv", "well,lat,lon\nx,15.3,44.2\n")
        if not bomb and not traversal:
            zf.writestr("wells.csv", "well_name,lat,lon\nsanaa-01,15.35,44.20\n")

make_zip(D / "golden_archive_bomb.zip", bomb=True, traversal=False)
make_zip(D / "golden_archive_traversal.zip", bomb=False, traversal=True)
make_zip(D / "golden_archive_ok.zip", bomb=False, traversal=False)

print("corpus files written to", D)
for p in sorted(D.iterdir()):
    if p.name.startswith("golden_") and p.suffix in (".las", ".json", ".csv", ".tif", ".zip"):
        print(f"  {p.name:38s} {p.stat().st_size:6d} bytes")

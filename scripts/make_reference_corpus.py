#!/usr/bin/env python3
"""make_reference_corpus.py — بناء مجموعة البيانات المرجعية v0.6.0.

هذه ليست مجموعة ملفات تالفة فقط: كل ملف هنا مرتبط بقيم متوقعة مجمّدة
(built ground truth) تُكتب في dataset_manifest.json، والمولّد نفسه يتحقق
أثناء البناء أن القرّاء الحقيقيين (lasio/tifffile/sqlite3+pyproj) يقرؤون
بالضبط ما بُني — فإذا خالف القارئ الثوابت، فشل البناء قبل أي اختبار.

القواعد:
- الملفات تُبنى حصراً بهذا السكربت ولا تُعدل يدوياً.
- القيم المتوقعة ثوابت صريحة في الأعلى، لا قيم مقروءة وقت البناء
  (القراءة وقت البناء للتأكيد فقط، ثم تُقارن بالثوابت).
- كل ملف تالف مرتبط برمز رفض دقيق (لا مجرد فشل عام).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
import sys
from datetime import date
from pathlib import Path

import tifffile

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

REF = REPO / "tests" / "data" / "reference"
REF.mkdir(parents=True, exist_ok=True)
for stale in REF.glob("*"):
    stale.unlink()  # إعادة البناء دائماً من الصفر: لا مخلفات قديمة

MANIFEST = {
    "schema": "geologia-reference-corpus/1",
    "generated": None,
    "doc": "كل ملف هنا مرتبط بقيم متوقعة مجمّدة؛ أي انحراف بين القراءة "
           "والمتوقع يفشل الاختبار المرجعي مباشرة",
    "files": {},
}

# --- ثوابت البناء (القيم المتوقعة المجمّدة) ---------------------------------
# GeoTIFF UTM 38N + MSL (نحو الرياض، هضبة ~400م)
DEM_UTM = {
    "name": "ref_dem_utm38n_msl.tif",
    "shape": (4, 4), "dtype": "float32",
    "scale": (25.0, 25.0, 1.0),
    "tiepoint": (0.0, 0.0, 0.0, 305000.0, 2740000.0, 380.0),
    "geokeys": [1, 1, 0, 6,
                1024, 0, 1, 1,      # GTModelType = projected
                1025, 0, 1, 1,      # GTRasterType = pixel is area
                3072, 0, 1, 32638,  # ProjectedCSType = UTM 38N
                4096, 0, 1, 5714,   # VerticalCSType = MSL height
                4097, 0, 1, 3,      # VerticalDatum = mean sea level
                4098, 0, 1, 9001],  # VerticalUnits = metre
    "values": [[380.0, 385.0, 390.0, 392.0],
               [386.0, 391.0, 395.0, 398.0],
               [392.0, 398.0, 401.0, 405.0],
               [397.0, 403.0, 408.0, 412.0]],
    "nodata": "-9999",
    "extent": {"minx": 305000.0, "miny": 2739900.0,
               "maxx": 305100.0, "maxy": 2740000.0},
    "crs_epsg": 32638,
}
# GeoTIFF جغرافي WGS84 بلا مرجع رأسي (ادعاء ارتفاع غير مثبت)
DEM_GEO = {
    "name": "ref_dem_geo_wgs84.tif",
    "shape": (4, 4), "dtype": "float32",
    "scale": (0.001, 0.001, 1.0),
    "tiepoint": (0.0, 0.0, 0.0, 46.5, 24.5, 0.0),
    "geokeys": [1, 1, 0, 3,
                1024, 0, 1, 2,
                1025, 0, 1, 1,
                2048, 0, 1, 4326],
    "values": [[10.0, 11.0, 12.0, 13.0],
               [11.0, 12.0, 13.0, 14.0],
               [12.0, 13.0, 14.0, 15.0],
               [13.0, 14.0, 15.0, 16.0]],
    "nodata": None,
    "crs_epsg": 4326,
}
#GeoTIFF مرجع رأسي برمز غير معروف → VERT_DATUM_UNKNOWN
DEM_VERT_UNKNOWN = {
    "name": "ref_dem_unknown_vertical.tif",
    "geokeys": [1, 1, 0, 6,
                1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, 32638,
                4096, 0, 1, 62000,  # رمز خارج الجدول المعروف (SHORT-safe)
                4097, 0, 1, 3, 4098, 0, 1, 9001],
}
# GeoTIFF وحدات رأسية بالأقدام → VERT_UNITS_NOT_METRE
DEM_VERT_FOOT = {
    "name": "ref_dem_foot_units.tif",
    "geokeys": [1, 1, 0, 6,
                1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, 32638,
                4096, 0, 1, 5714, 4097, 0, 1, 3, 4098, 0, 1, 9002],
}

WKT_32638 = None  # يُملأ من pyproj أدناه
# GeoPackage: 4 آبار حول نافذة DEM الرياض
GPKG_PTS = [(305000.0, 2740000.0), (305100.0, 2740000.0),
            (305000.0, 2740100.0), (305100.0, 2740100.0)]
GPKG_BBOX = {"minx": 305000.0, "miny": 2740000.0,
             "maxx": 305100.0, "maxy": 2740100.0}
GPKG_NAMES = ["well-a", "well-b", "well-c", "well-d"]

# LAS: سجل بئر مرجعي — عمودان قياس + عمق، 6 صفوف من 100 إلى 105م
LAS_HDR = """~Version Information
VERS.  2.0 :   CWLS LOG ASCII STANDARD VERSION 2.0
WRAP.  NO  :   One Line per Depth Step
~Well Information
WELL.  RIYDH-REF-01 :   Well Name
NULL.  -999.25 :   Null Value
STRT.  100.000 :   Start Depth (m)
STOP.  105.000 :   Stop Depth (m)
STEP.  1.0000 :   Step Depth (m)
~Curve Information
DEPT.m      :   Depth
RHOB.g/cm3  :   Bulk Density
NPHI.v/v    :   Neutron Porosity
~A
"""
LAS_ROWS = ["100.000   2.650   0.150", "101.000   2.640   0.152",
            "102.000   2.630   0.149", "103.000   2.645   0.151",
            "104.000   2.655   0.153", "105.000   2.660   0.154"]
LAS_ROWS_LIE = LAS_ROWS[:4]          # رأس يقول 6 وبيانات 4 → تلاعب
# قصّ في منتصف الصف الأخير المكتوب (سطر ناقص حرفياً)
LAS_PARTIAL_LAST = "104.000   2.655   0"


def build_tiff(spec: dict, path: Path) -> None:
    import numpy as np
    data = np.asarray(spec["values"], dtype=spec["dtype"])
    tags = [
        (33550, 12, 3, tuple(float(x) for x in spec["scale"]), True),
        (33922, 12, 6, tuple(float(x) for x in spec["tiepoint"]), True),
        (34735, 3, len(spec["geokeys"]), tuple(spec["geokeys"]), True),
    ]
    if spec.get("nodata"):
        tags.append((42113, 2, len(spec["nodata"]) + 1,
                     spec["nodata"] + "\x00", True))
    tifffile.imwrite(path, data, photometric="minisblack",
                     extratags=tags, byteorder="<")


def gpkg_geom_point(srs_id: int, x: float, y: float) -> bytes:
    """GeoPackageBinary header (envelope XY) + WKB point، little-endian."""
    header = (b"GP" + struct.pack("<BBi", 0, 0b00000010, srs_id)
              + struct.pack("<4d", x, x, y, y))
    wkb = struct.pack("<BI2d", 1, 1, x, y)
    return header + wkb


def build_gpkg(path: Path, *, app_id: int = 0x47504B47,
               drop_meta: bool = False, bad_geom_at: int | None = None,
               tamper_srs_at: int | None = None,
               lie_bbox: bool = False) -> None:
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA application_id = {app_id}")
    conn.execute("PRAGMA user_version = 10240")
    if not drop_meta:
        conn.execute("""CREATE TABLE gpkg_spatial_ref_sys (
            srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY,
            organization TEXT NOT NULL, organization_coordsys_id INTEGER,
            definition TEXT NOT NULL, description TEXT)""")
        conn.execute("""CREATE TABLE gpkg_contents (
            table_name TEXT PRIMARY KEY, data_type TEXT NOT NULL,
            identifier TEXT UNIQUE, description TEXT DEFAULT '',
            last_change DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
            srs_id INTEGER)""")
        conn.execute("""CREATE TABLE gpkg_geometry_columns (
            table_name TEXT NOT NULL, column_name TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
            z TINYINT NOT NULL, m TINYINT NOT NULL)""")
    conn.execute("""CREATE TABLE wells (
            fid INTEGER PRIMARY KEY AUTOINCREMENT, geom BLOB, name TEXT)""")
    if not drop_meta:
        conn.executemany(
            "INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)",
            [("Undefined cartesian SRS", -1, "NONE", -1, "undefined",
              "undefined cartesian coordinate reference system"),
             ("Undefined geographic SRS", 0, "NONE", 0, "undefined",
              "undefined geographic coordinate reference system"),
             ("WGS 84 geodetic", 4326, "EPSG", 4326, WKT_4326,
              "longitude/latitude coordinates in decimal degrees"),
             ("WGS 84 / UTM zone 38N", 32638, "EPSG", 32638, WKT_32638,
              "projected metre coordinates")])
        bbox = (0.0, 0.0, 10.0, 10.0) if lie_bbox else \
            (GPKG_BBOX["minx"], GPKG_BBOX["miny"],
             GPKG_BBOX["maxx"], GPKG_BBOX["maxy"])
        conn.execute(
            "INSERT INTO gpkg_contents (table_name, data_type, identifier,"
            " srs_id, min_x, min_y, max_x, max_y) VALUES"
            " ('wells','features','wells',32638,?,?,?,?)", bbox)
        conn.execute(
            "INSERT INTO gpkg_geometry_columns VALUES"
            " ('wells','geom','POINT',32638,0,0)")
    for i, ((x, y), nm) in enumerate(zip(GPKG_PTS, GPKG_NAMES)):
        srs = 32638
        if tamper_srs_at is not None and i == tamper_srs_at:
            srs = 4326  # تلاعب: ترويسة الهندسة تظهر إسناداً مختلفاً
        if bad_geom_at is not None and i == bad_geom_at:
            blob = b"\xde\xad\xbe\xef" + bytes(20)  # بلا سحر GP
        else:
            blob = gpkg_geom_point(srs, x, y)
        conn.execute("INSERT INTO wells (geom, name) VALUES (?,?)",
                     (sqlite3.Binary(blob), nm))
    conn.commit()
    conn.close()


def build_las(path: Path, *, rows: list[str], partial_last: bool = False,
              drop_units: bool = False) -> None:
    header = LAS_HDR
    if drop_units:
        header = header.replace("DEPT.m      :   Depth",
                                "DEPT.  :   Depth (unit forgotten)")
    lines = list(rows)
    if partial_last:
        lines.append(LAS_PARTIAL_LAST)
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


# --- بناء الملفات ------------------------------------------------------------
print("building corpus...")

import pyproj  # noqa: E402
WKT_32638 = pyproj.CRS("EPSG:32638").to_wkt(version="WKT1_GDAL")
WKT_4326 = pyproj.CRS("EPSG:4326").to_wkt(version="WKT1_GDAL")

build_tiff(DEM_UTM, REF / DEM_UTM["name"])
build_tiff(DEM_GEO, REF / DEM_GEO["name"])
build_tiff({**DEM_UTM, "name": DEM_VERT_UNKNOWN["name"],
            "geokeys": DEM_VERT_UNKNOWN["geokeys"]},
           REF / DEM_VERT_UNKNOWN["name"])
build_tiff({**DEM_UTM, "name": DEM_VERT_FOOT["name"],
            "geokeys": DEM_VERT_FOOT["geokeys"]},
           REF / DEM_VERT_FOOT["name"])
src_bytes = (REF / DEM_UTM["name"]).read_bytes()
(REF / "ref_dem_truncated.tif").write_bytes(src_bytes[:-60])

build_gpkg(REF / "ref_gpkg_wells.gpkg")
build_gpkg(REF / "ref_gpkg_bad_magic.gpkg", app_id=0)
build_gpkg(REF / "ref_gpkg_no_meta.gpkg", drop_meta=True)
build_gpkg(REF / "ref_gpkg_geom_bad.gpkg", bad_geom_at=2)
build_gpkg(REF / "ref_gpkg_srs_mismatch.gpkg", tamper_srs_at=1)
build_gpkg(REF / "ref_gpkg_bbox_lie.gpkg", lie_bbox=True)

build_las(REF / "ref_las_valid.las", rows=LAS_ROWS)
build_las(REF / "ref_las_rows_lie.las", rows=LAS_ROWS_LIE)
build_las(REF / "ref_las_no_units.las", rows=LAS_ROWS, drop_units=True)
build_las(REF / "ref_las_truncated.las", rows=LAS_ROWS[:4],
          partial_last=True)

# --- تأكيد ذاتي: القارئ الحقيقي يقرأ ما بنيناه بالضبط ------------------------
from geologia.data_layer.evidence import prove_file  # noqa: E402
from geologia.data_layer.readers import read_geotiff, read_geopackage, \
    read_las  # noqa: E402

def close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError("SELF-CHECK FAILED: " + msg)


def codes(rep) -> list[str]:
    return [f["code"] for f in rep["findings"]]


print("self-check against readers...")
r = read_geotiff(str(REF / DEM_UTM["name"]))
check(r["ok"] and r["data"]["crs_epsg"] == DEM_UTM["crs_epsg"], "utm crs")
check(r["data"]["shape"] == list(DEM_UTM["shape"]), "utm shape")
for k, v in DEM_UTM["extent"].items():
    check(close(r["data"]["extent"][k], v), f"utm extent {k}")
check("VERT_DATUM_OK" in codes({"findings": r["findings"]}), "utm vert ok")

r = read_geotiff(str(REF / DEM_GEO["name"]))
check(r["data"]["crs_epsg"] == 4326, "geo crs")
check("VERT_DATUM_MISSING" in codes({"findings": r["findings"]}),
      "geo vert missing")

r = read_geotiff(str(REF / DEM_VERT_UNKNOWN["name"]))
check("VERT_DATUM_UNKNOWN" in codes({"findings": r["findings"]}),
      "vert unknown")

r = read_geotiff(str(REF / DEM_VERT_FOOT["name"]))
check("VERT_UNITS_NOT_METRE" in codes({"findings": r["findings"]}),
      "vert foot")

r = read_geopackage(str(REF / "ref_gpkg_wells.gpkg"))
check(r["ok"] and r["data"]["features"]["wells"]["count"] == 4, "gpkg rows")
check(close(r["data"]["features"]["wells"]["bbox"]["maxx"],
            GPKG_BBOX["maxx"]), "gpkg bbox")
check("GPKG_CONTENTS_BBOX_VERIFIED" in
      [i["code"] for i in r["evidence"]["verified"]], "gpkg bbox verified")

r = read_geopackage(str(REF / "ref_gpkg_bad_magic.gpkg"))
check("GPKG_NOT_GPKG" in codes(r), "gpkg magic")
r = read_geopackage(str(REF / "ref_gpkg_no_meta.gpkg"))
check("GPKG_MISSING_META_TABLES" in codes(r), "gpkg meta")
r = read_geopackage(str(REF / "ref_gpkg_geom_bad.gpkg"))
check("GPKG_GEOM_MAGIC_INVALID" in codes(r), "gpkg geom magic")
r = read_geopackage(str(REF / "ref_gpkg_srs_mismatch.gpkg"))
check("GPKG_GEOM_SRS_MISMATCH" in codes(r), "gpkg srs mismatch")
r = read_geopackage(str(REF / "ref_gpkg_bbox_lie.gpkg"))
check("GPKG_CONTENTS_BBOX_MISMATCH" in codes(r), "gpkg bbox lie")

r = read_las(str(REF / "ref_las_valid.las"))
check(r["ok"] and r["data"]["rows"] == 6, "las rows")
check(r["data"]["curves"] == ["DEPT", "RHOB", "NPHI"], "las curves")
check(close(r["data"]["null"], -999.25), "las null")

r = read_las(str(REF / "ref_las_rows_lie.las"))
check("LAS_READER_ROWS_MISMATCH" in codes(r), "las rows lie")

r = read_las(str(REF / "ref_las_no_units.las"))
check("LAS_CURVE_UNIT_MISSING" in codes(r), "las units")

r = read_las(str(REF / "ref_las_truncated.las"))
check("LAS_READER_ROWS_MISMATCH" in codes(r), "las truncated rows")
print("self-check OK")

# --- تجميد القيم المتوقعة في manifest ----------------------------------------
def add(name: str, kind: str, status: str, codes_min: list[str],
        reader: dict | None = None, vertical: dict | None = None) -> None:
    p = REF / name
    data = p.read_bytes()
    MANIFEST["files"][name] = {
        "kind": kind, "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "expected": {"status": status, "codes_min": codes_min,
                     "reader": reader, "vertical": vertical}}

add(DEM_UTM["name"], "geotiff", "pass",
    ["TIFF_OK", "TIFF_GEO_TAGS", "VERT_DATUM_OK"],
    reader={"shape": list(DEM_UTM["shape"]), "dtype": DEM_UTM["dtype"],
            "crs_epsg": DEM_UTM["crs_epsg"], "extent": DEM_UTM["extent"]},
    vertical={"cs": 5714, "datum": 3, "units": 9001})
add(DEM_GEO["name"], "geotiff", "pass",
    ["TIFF_OK", "VERT_DATUM_MISSING"],
    reader={"shape": list(DEM_GEO["shape"]), "dtype": DEM_GEO["dtype"],
            "crs_epsg": 4326}, vertical=None)
add(DEM_VERT_UNKNOWN["name"], "geotiff", "pass",
    ["VERT_DATUM_UNKNOWN"],
    reader={"crs_epsg": 32638}, vertical={"cs": 99999, "datum": 3,
                                          "units": 9001})
add(DEM_VERT_FOOT["name"], "geotiff", "pass", ["VERT_UNITS_NOT_METRE"],
    reader={"crs_epsg": 32638}, vertical={"cs": 5714, "datum": 3,
                                          "units": 9002})
add("ref_dem_truncated.tif", "geotiff", "fail", ["TIFF_TRUNCATED"])

add("ref_gpkg_wells.gpkg", "gpkg", "pass",
    ["GPKG_FEATURE_COUNT_VERIFIED", "GPKG_SRS_ENGINE_VERIFIED",
     "GPKG_CONTENTS_BBOX_VERIFIED"],
    reader={"features": {"wells": {"count": 4}}, "srs_count": 4})
add("ref_gpkg_bad_magic.gpkg", "gpkg", "fail", ["GPKG_NOT_GPKG"])
add("ref_gpkg_no_meta.gpkg", "gpkg", "fail", ["GPKG_MISSING_META_TABLES"])
add("ref_gpkg_geom_bad.gpkg", "gpkg", "fail", ["GPKG_GEOM_MAGIC_INVALID"])
add("ref_gpkg_srs_mismatch.gpkg", "gpkg", "fail", ["GPKG_GEOM_SRS_MISMATCH"])
add("ref_gpkg_bbox_lie.gpkg", "gpkg", "fail", ["GPKG_CONTENTS_BBOX_MISMATCH"])

add("ref_las_valid.las", "las", "pass",
    ["LAS_OK", "LAS_READER_ROWS_VERIFIED", "LAS_READER_NULL_HONORED",
     "VERT_DEPTH_DATUM_UNDECLARED"],
    reader={"rows": 6, "curves": ["DEPT", "RHOB", "NPHI"], "null": -999.25})
add("ref_las_rows_lie.las", "las", "fail",
    ["LAS_DATA_ROWS_MISMATCH", "LAS_READER_ROWS_MISMATCH"])
add("ref_las_no_units.las", "las", "pass", ["LAS_CURVE_UNIT_MISSING"],
    reader={"rows": 6})
add("ref_las_truncated.las", "las", "fail",
    ["LAS_DATA_ROWS_MISMATCH", "LAS_READER_ROWS_MISMATCH"])

MANIFEST["generated"] = date.today().isoformat()
(REF / "dataset_manifest.json").write_text(
    json.dumps(MANIFEST, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8")
print(f"manifest written: {len(MANIFEST['files'])} files pinned")

# --- تحقق نهائي: prove_file يمر على كل ملف مع كل الرموز المتوقعة -------------
DTYPE = {"geotiff": "tiff", "gpkg": "gpkg", "las": "las"}
for nm, entry in MANIFEST["files"].items():
    rep = prove_file(str(REF / nm), dtype=DTYPE[entry["kind"]])
    st = rep["status"]
    got = set(codes(rep))
    ev = rep.get("evidence", {})
    got |= {i["code"] for lvl in ("read", "verified", "unverifiable")
            for i in ev.get(lvl, [])}
    if st != entry["expected"]["status"]:
        raise AssertionError(f"{nm}: status {st} != "
                             f"{entry['expected']['status']} (codes: {got})")
    for c in entry["expected"]["codes_min"]:
        if c not in got:
            raise AssertionError(f"{nm}: code {c} missing (codes: {got})")
print("manifest ground truth verified against the full pipeline")

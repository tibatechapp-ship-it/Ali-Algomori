# Phase 2 — Safe dataset intake

## Implemented
- Streaming raw-body upload with a hard 50 MiB cap.
- Allowlist: GeoJSON/JSON, GeoPackage, GeoTIFF, CSV, LAS.
- Generated storage IDs; user filenames are sanitized and never used as paths.
- SHA-256, size, format, CRS metadata, and creation timestamp.
- Structural-only GeoJSON validation and feature count.
- Dataset metadata endpoints. Stored source files are not exposed by a public path.
- GeoPackage, GeoTIFF, CSV, and LAS are stored but not interpreted.

## Verified display gate (0.19.0)

The map display is bound to the CRS gate — no drawing before verification:

- `GET /api/v1/datasets/{dataset_id}/display` refuses with classified 409s:
  `display.refusal.not_validated`, `display.refusal.validation_failed`,
  `display.refusal.integrity_mismatch` (stored bytes re-hashed at serve time
  against the upload-time SHA-256), and `display.refusal.vertical_or_3d_crs`.
- Success responses carry `truth_class: "verified_structural"` with an
  explicit note: structural verification and integrity never certify that
  coordinates are scientifically correct positions.
- Served coordinates are always EPSG:4326. Non-geographic declared CRS values
  are reprojected server-side via pyproj with the operation metadata attached;
  the actual engine is declared in `reprojection_engine` on every response.
- pyproj-free fallback: WGS 84 UTM zones (EPSG:326xx/327xx) invert through the
  frozen `utm_equations` module (Snyder 1987 series; golden control points in
  `data/utm_equation_points.json` with a pinned file fingerprint and a pyproj
  crosscheck). Other CRS values without pyproj answer 503 honestly instead of
  guessing.
- The web map view is a dependency-free SVG renderer (no CDN, no tile
  servers): adaptive graticule with honest axis labels, pointer pan, wheel
  zoom, double-click fit, and feature info built exclusively with
  `textContent`. It fetches the gated `/display` endpoint only and clears
  without drawing when the gate refuses.

## Upload protocol

```http
POST /api/v1/projects/{project_id}/datasets
Content-Type: application/octet-stream
X-Dataset-Name: Area study
X-Filename: area.geojson
X-CRS: EPSG:4326

<raw file bytes>
```

GeoJSON/JSON defaults to EPSG:4326 per RFC 7946 unless `X-CRS` is provided. Other formats may omit CRS, but are not eligible for spatial analysis until it is defined and validated.

## Endpoints
- `POST /api/v1/projects/{project_id}/datasets`
- `GET /api/v1/projects/{project_id}/datasets`
- `GET /api/v1/datasets/{dataset_id}`
- `GET /api/v1/datasets/{dataset_id}/display` (gated map payload, 0.19.0)

## Safety limits
- Maximum upload size: 50 MiB.
- No archive extraction.
- No execution of uploaded content.
- No GIS processing beyond validated, CRS-gated display (0.19.0).
- Upload is streamed to a temporary file and atomically moved to generated storage.
- Raw content paths are not returned by metadata APIs.

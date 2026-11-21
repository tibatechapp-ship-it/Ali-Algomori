# الملفات المرجعية الذهبية (مدخلات مرجعية + جسم أدلة الرفض)

هذه هي "المدخلات المرجعية" لاختبارات طبقة البيانات، والنتائج المتوقعة موثقة
مكسوبياً في الاختبارات نفسها (test_data_layer.py، test_validation_hardening.py،
test_reception.py) فأي تغيير في السلوك يكسر الاختبار قبل أن يصل لبيانات حقيقية.

ملفات الرفض التالفة تعاد ببنائها بأسلوب محدد الخطوات عبر
`scripts/make_corrupt_corpus.py` — لا تُعدل يدوياً.

## الملفات السليمة المرجعية (يجب أن تمر)

| الملف | النوع | النتيجة المتوقعة |
| ----- | ----- | ----------------- |
| golden_las_valid.las | LAS 2.0 سليم | status=pass، LAS_OK، 6 صفوف مطابقة، مدخل الاختبار المرجعي للمحرك المعتمد |
| golden.geojson | GeoJSON RFC7946 سليم | status=pass، GEOJSON_OK + ملاحظة لا CRS؛ ومع declared_crs=EPSG:4326: CRS_DECLARED_OK + CRS_AXIS_ORDER_NOTE |
| golden_wells.csv | جدول آبار سليم | status=pass، CSV_OK، CRS_NONE_DECLARED |
| golden_dem_tile.tif | بلاط DEM جغرافي قرب صنعاء | status=pass، TIFF_OK + TIFF_GEO_TAGS |
| golden_csv_utm_valid.csv | إحداثيات UTM متوافقة مع إعلان EPSG:32638 | status=pass مع declared_crs، CRS_DECLARED_OK |
| golden_archive_ok.zip | أرشيف نظيف | check_upload: needs_review + SEC_ARCHIVE_OK (الأعضاء لم تتحقق بعد) |

## جسم أدلة الرفض (كل حالة برمزها الدقيق — يجب أن تفشل)

| الملف | التلف | رمز الرفض الإلزامي |
| ----- | ----- | ------------------- |
| golden_las_no_version.las | LAS بلا ~V | LAS_NO_VERSION |
| golden_las_truncated.las | بيانات ~A مقصوصة (4 صفوف بدل 6) | LAS_DATA_ROWS_MISMATCH (error من 0.5.0) |
| golden_las_nul.las | بايت NUL داخل البيانات | LAS_CONTROL_CHARS |
| golden_geojson_bad_coords.json | إحداثيات خارج WGS84 | GEOJSON_BAD_COORDS |
| golden_geojson_crs_utm.json | CRS مسقط معلن فوق محتوى WGS84 | CRS_GEOJSON_NON_WGS84 |
| golden_wells_bad.csv | قيم ناقصة + lat خارج مدى + صف مكرر | CSV_LATLON_RANGE + تحذيرات |
| golden_csv_nul.csv | بايت NUL في جدول | CSV_CONTROL_CHARS |
| golden_csv_id_conflict.csv | نفس المعرف ببيانات متضاربة | CSV_ID_CONFLICT |
| golden_csv_utm_degrees.csv | CRS مسقط معلن وأعمدة درجات | CRS_MISMATCH_PROJECTED_GEO |
| golden_csv_geo_utmvals.csv | CRS جغرافي معلن وقيم بمقاييس UTM | CRS_MISMATCH_GEO_PROJECTED |
| golden_dem_truncated.tif | بلاط DEM مقتطع | TIFF_TRUNCATED |
| golden_dem_with_meta.tif | بلاط سليم + وسوم Software/Copyright | يمر؛ scan_tiff_metadata يعلن META_PRESENT، وstrip_tiff_auxiliary_tags يسقط الوسمين ويحفظ الجغرافيا |
| golden_archive_bomb.zip | مدخل يتمدد ~300x | SEC_ZIP_BOMB |
| golden_archive_traversal.zip | مدخل `../escape.csv` | SEC_PATH_TRAVERSAL |

## القاعدة

اختبار كل حالة يثبت **رمز الرفض الدقيق** — الفشل العام غير مقبول كعقد.
ونجاح CI لا يعني صحة النتائج الجيولوجية: الصحة العلمية اختصاص الاختبارات
المرجعية المثبتة خلف بوابة `certified` (ADR-0004/0005).

## المجموعة المرجعية المجمدة (v0.6.0 — `tests/data/reference/`)

ليست مجرد ملفات تالفة: كل ملف مرتبط بنتائج متوقعة مجمّدة في
`dataset_manifest.json` (بصمة sha256، الحجم، الحالة، الرموز الإلزامية،
حقول القارئ، التصنيف الرأسي)، ويُعاد إثباتها باختبار مرجعي معلمي.
تُبنى حصراً بـ`scripts/make_reference_corpus.py` (يتطلب lasio/tifffile/pyproj)
— والقيم المتوقعة ثوابت صريحة في المولّد، والقراءة وقت البناء للتأكيد فقط.
أي انحراف بايت في المجموعة يكشفه الـmanifest (`REF_HASH_MISMATCH`).

| الملف | البنية | النتيجة المجمّدة |
| ----- | ------ | ----------------- |
| ref_dem_utm38n_msl.tif | GeoTIFF مسقط UTM38N + MSL حقيقي | pass؛ امتداد مجمد، CRS 32638، VERT_DATUM_OK (5714/3/9001) |
| ref_dem_geo_wgs84.tif | جغرافي بلا مرجع رأسي | pass؛ VERT_DATUM_MISSING (ارتفاع غير مثبت) |
| ref_dem_unknown_vertical.tif | رمز رأسي خارج الجدول (62000) | pass؛ VERT_DATUM_UNKNOWN |
| ref_dem_foot_units.tif | وحدات رأسية بالأقدام (9002) | pass؛ VERT_UNITS_NOT_METRE |
| ref_dem_truncated.tif | قصّ 60 بايتاً | fail؛ TIFF_TRUNCATED |
| ref_gpkg_wells.gpkg | GeoPackage سليم، 4 آبار، srs 32638 | pass؛ عدّ ومغلفات وSRS تتحقق بمحرك pyproj |
| ref_gpkg_bad_magic.gpkg | application_id ليس GPKG | fail؛ GPKG_NOT_GPKG |
| ref_gpkg_no_meta.gpkg | بلا جداول الميتاداتا | fail؛ GPKG_MISSING_META_TABLES |
| ref_gpkg_geom_bad.gpkg | هندسة بلا سحر GP | fail؛ GPKG_GEOM_MAGIC_INVALID |
| ref_gpkg_srs_mismatch.gpkg | ترويسة هندسة srs مختلف | fail؛ GPKG_GEOM_SRS_MISMATCH |
| ref_gpkg_bbox_lie.gpkg | bbox معلن كاذب | fail؛ GPKG_CONTENTS_BBOX_MISMATCH |
| ref_las_valid.las | سجل آبار سليم 2.0 | pass؛ 6 صفوف، منحنيات ووحدات مجمدة، NULL مطبق |
| ref_las_rows_lie.las | رأس يقول 6 وبيانات 4 | fail؛ LAS_DATA_ROWS_MISMATCH + LAS_READER_ROWS_MISMATCH |
| ref_las_no_units.las | منحنى بلا وحدة | pass؛ LAS_CURVE_UNIT_MISSING |
| ref_las_truncated.las | قصّ في منتصف الصف الأخير | fail؛ mismatch على مستوى النص والقارئ معاً |

### المبدأ الثابت لهذه المجموعة

مجموعة المرجع تصدّق مسارات الكود وسلوك المدققين — لا صحة الجيولوجيا نفسها
(بند `REF_CORPUS_SCOPE` غير قابل للتأكيد ويظهر في كل تقرير مرجعي). ونقاط
التحكم المجمدة للتحويلات في `src/geologia/data/reference/transformations.json`
(الرياض/جدة/الدمام + دورة عكسية) هي الوحيدة المشحونة مع الحزمة، وخلاف
المحرك معها `XFORM_MISMATCH` خطأ صارم: المرجع لا يُعاير على المحرك.

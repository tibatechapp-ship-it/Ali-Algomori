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

# الملفات المرجعية الذهبية (مدخلات مرجعية)

هذه هي "المدخلات المرجعية" لاختبارات طبقة البيانات، والنتائج المتوقعة موثقة
مكسوبياً في الاختبارات نفسها (test_data_layer.py) فأي تغيير في السلوك يكسر
الاختبار قبل أن يصل لبيانات حقيقية.

| الملف | النوع | النتيجة المتوقعة |
| ----- | ----- | ----------------- |
| golden_las_valid.las | LAS 2.0 سليم | status=pass، LAS_OK، 6 صفوف مطابقة |
| golden_las_no_version.las | LAS بلا ~V | status=fail، LAS_NO_VERSION |
| golden.geojson | GeoJSON RFC7946 سليم | status=pass، GEOJSON_OK + ملاحظة لا CRS |
| golden_geojson_bad_coords.json | إحداثيات خارج WGS84 | status=fail، GEOJSON_BAD_COORDS |
| golden_wells.csv | جدول آبار سليم | status=pass، CSV_OK |
| golden_wells_bad.csv | قيم ناقصة + lat خارج مدى + صف مكرر | status=fail، CSV_LATLON_RANGE + تحذيرات |

# GEOLOGIA — جيولوجيا

**Geoscience Intelligence Platform** · منصة ذكاء جيولوجي مفتوحة المصدر — عربي / English
يقودها الوكيل الرئيسي **«المهندس الجمهوري»** (Chief Geoscience Agent).

> **الحالة الحالية: المرحلة 0.7.0 — حدود الاستقبال عبر HTTP + مراجعة علمية مستقلة للمراجع**
> لا يوجد أي محرك طرف ثالث مثبت أو مدمج بعد، واعتماده مرفوض في الكود حتى دورة حياة كاملة.
> ما يعمل الآن: نواة API + سجل محركات (عائلتان) + مخطّط حتمي (9 مجالات) + **طبقة معرفة
> استرجاعية بلا هلوسة** + **بوابة استقبال آمنة** (حدود حجم، تفتيش بايتات سحرية، أمان
> أرشيفات بلا استخراج، تعقيم أسماء بعلامات bidi) + **طبقة تحقق معلن-مقابل-ملاحظ**
> (بصمات + مدقق LAS/GeoJSON/CSV/TIFF/GPKG + فحص CRS والوحدات المعلنة ضد المحتوى الفعلي)
> + **نقطة رفع حية `/api/v1/uploads`**: جسم خام، سقف مزدوج، حجر صحي خام غير قابل للتعديل،
> سجل مصدر لكل حكم حتى الرفض ([ADR-0007](docs/adr/0007-http-upload-boundary.md))
> + **طبقة إثبات**: قرّاء حقيقيون (lasio/tifffile/sqlite3) + أدلة ثلاثية المستويات +
> سجل مصدر مضاد للتلاعب + **مرجع مجمّد مستقل عن المحرك** (معادلات EPSG:3857 المنشورة
> بلا pyproj + جدول رأسي مثبت على سجل EPSG)
> + **سجل مهام ببوابات إلزامية وعزل** + **مسار اعتماد `certified` بأول محرك علمي
> أول-الطرف (`porosity_density_v1`)** — وفق [معيار القبول الملزم](docs/ACCEPTANCE_STANDARD.md)
> و[ADR-0005](docs/adr/0005-file-reception-security.md):
> **نجاح CI ليس شهادة صحة النتائج الجيولوجية** — الأمان والصلاحية والصحة العلمية
> ثلاث شهادات منفصلة، وكل واحدة بدليلها.

## القواعد العلمية الملزمة

1. لا يختلق النظام نتائج، ولا يدّعي تشغيل محرك لم يعمل فعليًا.
2. الاحتمال ليس حقيقة: أي نسبة ثقة تحتاج نموذجًا معايرًا وبيانات مستقلة.
3. لا توصية بحفر بئر اعتمادًا على خريطة وحدها.
4. كل نتيجة قابلة للتتبع: البيانات، المحرك، الإصدار، المعلمات، المخرجات.
5. عزل المحركات: لا بيئة Python واحدة تجمع كل الاعتماديات.

## التشغيل السريع / Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q

# واجهة سطر الأوامر — بلا خادم:
geologia plan "حلل المياه الجوفية حول حوض صنعاء"
geologia domains
geologia engines --domain geophysics
geologia knowledge search "من بدأ علم الجيولوجيا في التاريخ؟"
geologia verify سجل_البئر.las --type las
geologia dataset add "سجل بئر" سجل_البئر.las --dtype las
geologia task create "مسامية بئر صنعاء" porosity_density_v1 ds-ab12cd34ef56 --param rho_ma_gcm3=2.65
geologia certify porosity_density_v1    # بوابة 3: مرجع مثبت + بصمة المدخل
geologia task go task-... inputs_validated && geologia task go task-... ready
geologia task execute task-...          # كشف العبث لحظة التنفيذ + تقرير الأدلة
geologia task report task-...           # المدخلات + الاستشهادات + ±1σ + حدود الصلاحية
geologia serve --port 8000
```

### Termux (أندرويد — بدون Rust)

```bash
pkg install -y python git gh
pip install "pydantic<2" "fastapi<0.128"   # نسخ نقية بايثون تعمل على أندرويد
pip install -e ".[dev]"
pytest -q
```

أداة الفحص Ruff اختيارية على الهاتف: `pkg install ruff` ثم `ruff check .`
( CI يشغّلها دائمًا على الخادم ).

## نقاط النهاية / Endpoints

| Method | Path | الوظيفة |
| ------ | ---- | ------- |
| GET | `/health` | حالة الخدمة + عدد المحركات المعتمدة فعلاً (ديناميكي) |
| GET | `/api/v1/engines` | سجل المحركات: 30 طرفاً ثالثاً + الأولى-الطرف (`?domain=` للفلترة) |
| GET | `/api/v1/engines/{id}` | بطاقة محرك واحدة |
| POST | `/api/v1/engines/{id}/certify` | **بوابة 3**: إعادة الاختبار المرجعي المثبت — 409 لرفض الطرف الثالث وعبث المرجع |
| GET | `/api/v1/domains` | المجالات التحليلية التسعة بعدد محركاتها ومدخلاتها |
| POST | `/api/v1/plans` | خطة تحليل حتمية؛ **422 مع قائمة المجالات المدعومة** إن لم يُعرف مجال |
| GET | `/api/v1/knowledge/stats` · `/catalog` | حجم المكتبة وكتالوجها بحالات ثقة مدخلاتها |
| POST | `/api/v1/knowledge/query` | **استرجاع فقط**: مقطع مخزن باستشهاده أو «ليس في المكتبة» |
| POST | `/api/v1/datasets` · `GET /api/v1/datasets` | تسجيل مجموعة بيانات حقيقية بهوية sha256 |
| POST | `/api/v1/datasets/{id}/validate` · `/verify-checksum` | تحقق صيغة (TIFF بنيوي) + تحقق بصمة ضد العبث |
| GET | `/api/v1/datasets/{id}/proof` | **إعادة إثبات حية**: ثلاثية أدلة جديدة من البايتات الحية + سجل مصدر جديد |
| GET | `/api/v1/uploads/policy` | عقد الاستقبال قبل إرسال بايت: السقف، الحاجات، الأحكام |
| POST | `/api/v1/uploads` | **بوابة الرفع الحية**: جسم خام + سقف مزدوج + حجر صحي + إثبات ثلاثي + provenance لكل حكم حتى الرفض |
| POST | `/api/v1/tasks` · `GET /api/v1/tasks` | سجل مهام بمواصفة عزل |
| POST | `/api/v1/tasks/{id}/transition` | انتقال محكوم بالبوابات؛ التنفيذ **409** قبل بوابة `certified` |
| POST | `/api/v1/tasks/{id}/execute` | تنفيذ المحرك المعتمد فقط + كشف عبث لحظة التنفيذ |
| GET | `/api/v1/tasks/{id}/report` | **بوابة 4**: تقرير الأدلة (مدخلات، استشهادات، ±1σ، حدود صلاحية) |

مثال:

```bash
curl -X POST localhost:8000/api/v1/plans -H "Content-Type: application/json" -d '{"request": "ادرس احتمالية المياه الجوفية حول هذه الإحداثيات"}'
curl -X POST localhost:8000/api/v1/plans -H "Content-Type: application/json" -d '{"request": "مرحبا"}'   # ← 422 unknown_domain، لا خطة مُصطنعة

curl -X POST "localhost:8000/api/v1/uploads?filename=well.las&declared_crs=local_depth" \
     -H "Content-Type: application/octet-stream" --data-binary @well.las   # ← حكم صادق: proven أو proven_with_unverified_claims أو 422 بالرموز
curl localhost:8000/api/v1/datasets/ds-ab12cd34ef56/proof               # ← إعادة إثبات حية من البايتات الحية
```

## البنية

```text
src/geologia/        # النواة: API + سجل المحركات (عائلتان) + المخطّط + التطبيع العربي + CLI
  engines/           # المحركات الأولى-الطرف: حتمية، بلا اعتماديات، قابلة للاعتماد
  knowledge/         # طبقة المعرفة: كتالوج بذرة + فهرس TF-IDF + استرجاع باستشهاد
  data_layer/        # بوابة استقبال آمنة + سجل بيانات + قرّاء حقيقيون (lasio/tifffile/sqlite3) + أدلة ثلاثية + سجل مصدر سلسلي + اعتماد + مهام
  data/reference/    # المراجع المثبتة بجبر نسبي دقيق (نتائج ذهبية ببصماتها)
docs/                # المعمارية، سياسة الدمج، معيار القبول، خارطة الطريق، ADR-0001..0006
tests/               # 250 اختباراً (منها 11 حية على uvicorn) + جسم أدلة الرفض + مجموعة مرجعية مجمّدة في tests/data/reference/
scripts/             # مولدات المراجع الذهبية + جسم الأدلة التالفة + مولّد المجموعة المرجعية (lasio/tifffile/pyproj)
.github/workflows/   # CI: فحص + اختبارات على مسارين (أحدث نسخ / مسار Termux)
```

## سجل التغييرات

راجع [CHANGELOG.md](CHANGELOG.md) — آخر إصدار 0.6.0 (2026-11-22).

## بخصوص «ذاكرة كل الكتب» — بصراحة

لا يُعلن هنا «تدريب نموذج على كل كتب الجيولوجيا» — ذلك ادعاء بلا أساس. ما بُني
هو بنية الذاكرة الصفرية هلوسة: كتالوج بذرة مصنّف بحالات ثقة (بما فيه الإرث العربي
والصيني)، و10 تلخيصات عربية أصلية، وقاعدة معرفة المحركات الثلاثين، وخط فهرسة
ملفات المستخدم (md/txt) — والجواب دائماً إما من مقطع مخزن باستشهاده أو «ليس في
المكتبة». النصوص الكاملة تُجلب بملفاتها ورخصها ثم تُفهرس ولا تُنسخ للمستودع.

## الوثائق

- [المعمارية](docs/ARCHITECTURE.md) · [سياسة دمج المحركات](docs/INTEGRATION_POLICY.md)
- [خارطة الطريق](docs/ROADMAP.md) · [حوكمة البيانات](docs/DATA_GOVERNANCE.md)
- [الأمان](SECURITY.md) · [معيار القبول الملزم](docs/ACCEPTANCE_STANDARD.md) · [ADR-0001](docs/adr/0001-chief-agent-isolated-engines.md) · [ADR-0002](docs/adr/0002-retrieval-only-knowledge.md) · [ADR-0003](docs/adr/0003-task-ledger-mandatory-gates.md) · [ADR-0004](docs/adr/0004-first-certified-engine.md)

## الترخيص

AGPL-3.0 للمنصة الأصلية. رخص المحركات الخارجية **تُراجع وتُوثّق قبل أي دمج أو توزيع**
(انظر سياسة الدمج). لا يُنسخ كود طرف ثالث داخل المستودع دون مراجعة شروطه.

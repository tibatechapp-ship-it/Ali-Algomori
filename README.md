# GEOLOGIA — جيولوجيا

**Geoscience Intelligence Platform** · منصة ذكاء جيولوجي مفتوحة المصدر — عربي / English
يقودها الوكيل الرئيسي **«المهندس الجمهوري»** (Chief Geoscience Agent).

> **الحالة الحالية: مرحلة التأسيس 0.2.0**
> لا يوجد أي محرك علمي مثبّت أو مدمج بعد. جميع بطاقات سجل المحركات بحالة `planned`
> ورخصها `unverified`. ما يعمل الآن: نواة API + سجل محركات للقراءة + مخطّط تحليل حتمي
> (9 مجالات، تطبيع عربي، قواعد أولوية) يُنتج **خططًا فقط** بلا أي نتائج محسوبة —
> ويرفض بأمانة أي طلب لا يطابق مجالاً بدل اختراع خطة GIS افتراضية.

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
| GET | `/health` | حالة الخدمة + عدد المحركات المدمجة (حاليًا 0) |
| GET | `/api/v1/engines` | سجل المحركات (فلترة اختيارية `?domain=`) |
| GET | `/api/v1/engines/{id}` | بطاقة محرك واحدة |
| GET | `/api/v1/domains` | المجالات التحليلية التسعة بعدد محركاتها ومدخلاتها |
| POST | `/api/v1/plans` | خطة تحليل حتمية؛ **422 مع قائمة المجالات المدعومة** إن لم يُعرف مجال |

مثال:

```bash
curl -X POST localhost:8000/api/v1/plans -H "Content-Type: application/json" -d '{"request": "ادرس احتمالية المياه الجوفية حول هذه الإحداثيات"}'
curl -X POST localhost:8000/api/v1/plans -H "Content-Type: application/json" -d '{"request": "مرحبا"}'   # ← 422 unknown_domain، لا خطة مُصطنعة
```

## البنية

```text
src/geologia/        # النواة: API + سجل المحركات + المخطّط + التطبيع العربي + CLI
docs/                # المعمارية، سياسة الدمج، خارطة الطريق، حوكمة البيانات، ADR
tests/               # اختبارات التطبيع والمخطّط وAPI وCLI (تشمل بوابة الصدق)
.github/workflows/   # CI: فحص + اختبارات على مسارين (أحدث نسخ / مسار Termux)
```

## سجل التغييرات

راجع [CHANGELOG.md](CHANGELOG.md) — آخر إصدار 0.2.0 (2026-11-21).

## الوثائق

- [المعمارية](docs/ARCHITECTURE.md) · [سياسة دمج المحركات](docs/INTEGRATION_POLICY.md)
- [خارطة الطريق](docs/ROADMAP.md) · [حوكمة البيانات](docs/DATA_GOVERNANCE.md)
- [الأمان](SECURITY.md) · [ADR-0001](docs/adr/0001-chief-agent-isolated-engines.md)

## الترخيص

AGPL-3.0 للمنصة الأصلية. رخص المحركات الخارجية **تُراجع وتُوثّق قبل أي دمج أو توزيع**
(انظر سياسة الدمج). لا يُنسخ كود طرف ثالث داخل المستودع دون مراجعة شروطه.

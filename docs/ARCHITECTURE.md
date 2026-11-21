# المعمارية — GEOLOGIA

## الطبقات

```text
واجهة عربية RTL / English LTR (لاحقًا: Next.js + MapLibre)
        |
المهندس الجمهوري — Chief Agent
(فهم الطلب، اختيار الأدوات، إدارة الوكلاء، التحقق، تقرير قابل للتتبع)
        |
وكلاء متخصصون = أدوار داخل نظام واحد (وليست 8 نماذج مستقلة):
GIS · المياه الجوفية · الجيوفيزياء · النمذجة 3D · الاستشعار · الجيوكيمياء · الزلازل
+ مراجع علمي مستقل
        |
Tool Registry → Adapters → محركات علمية معزولة
(QGIS · GemPy · MODFLOW 6 · ObsPy · SimPEG · OpenQuake · GRASS · PyGIMLi ...)
        |
مخرجات: خريطة · نموذج 3D · تقرير · بيانات ومصادر · حدود الثقة
```

## عقد المحرك الموحد

كل محرك يدمج عبر Adapter مستقل يلتزم بعقد ثابت (مثال):

```json
{
  "engine_id": "gempy",
  "engine_version": "pinned-version",
  "adapter_version": "0.1.0",
  "capabilities": ["geological_model_3d"],
  "input_schema": "versioned-schema",
  "output_schema": "versioned-schema",
  "license": "verified-license",
  "resource_limits": { "cpu": 4, "memory_mb": 8192, "timeout_seconds": 1800 },
  "health_check": "required",
  "provenance": "required"
}
```

المحرك لا يتصل مباشرة بالوكيل: الوكيل ← سجل الأدوات ← Adapter ← المحرك.
هذا يسمح بتحديث GemPy أو MODFLOW دون إعادة بناء المنصة.

## دورة حياة الطلب

1. استلام الطلب + منطقة الاهتمام (AOI) ونظام الإحداثيات.
2. جرد البيانات المتاحة وتحديد الناقص (إن نقصت بيانات كافية → إعلان ذلك صراحة).
3. بناء خطة تحليل (في مرحلة التأسيس: مخطّط حتمي عبر `/api/v1/plans`).
4. تنفيذ عبر سجل الأدوات ومحركات معزولة (مراحل لاحقة).
5. فحص المدخلات والمخرجات + تسجيل provenance كامل.
6. بوابة التحقق العلمي (7 أسئلة) + المراجع المستقل.
7. تقرير ثنائي اللغة مع حدود الثقة، أو رفض إصدار توصية.

## قرارات رئيسية

- وكيل رئيسي واحد + وكلاء كأدوار: راجع [ADR-0001](adr/0001-chief-agent-isolated-engines.md).
- لا خلط اعتماديات: كل محرك في بيئته (راجع سياسة الدمج).
- التقنية المستهدفة: FastAPI + Pydantic، وPostgreSQL/PostGIS لاحقًا،
  وQueue + Workers للمهام الطويلة، وCOG/GeoParquet للملفات الكبيرة.

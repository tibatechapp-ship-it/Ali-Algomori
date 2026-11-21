# NOTICE — إشعار رسمي / Official Notice

**GEOLOGIA — Geoscience Intelligence Platform · منصة الذكاء الجيولوجي**

---

## 1. Project status — حالة المشروع

**EN —** GEOLOGIA is **under active construction** (v0.8.1, foundation phase). The
architecture, data registries, and gates are real and tested (381 passing tests), but
the platform is **not yet a production system**: interfaces may change, knowledge
coverage is growing incrementally, and no geological result should be used for
operational decisions before it passes the project's certification pipeline.

**AR —** مشروع GEOLOGIA **قيد الإنشاء الفعلي** (الإصدار 0.8.1، مرحلة الأساس).
المعمارية وسجلات البيانات والبوابات حقيقية ومُختبرة (381 اختباراً ناجحاً)، لكن
المنصة **ليست نظام إنتاج بعد**: الواجهات قد تتغير، وتغطية المعرفة تتوسع تدريجياً،
ولا يُستخدم أي نتيجة جيولوجية لقرارات تشغيلية قبل أن تجتاز مسار الاعتماد الرسمي.

## 2. Support and adoption appeal — دعوة الدعم والتبني

**EN —** The project needs resources and partners to move faster: scientific reviewers
(9 specialist roles), licensed reference data, GIS/3D engineers, hosting and CI, and
academic or corporate adoption. If you or your institution can support, adopt, or
co-build GEOLOGIA, contact the technical team through the official channel published
in [SUPPORT.md](SUPPORT.md).

**AR —** يحتاج المشروع موارد وشركاء ليتقدم أسرع: مراجعين علميين (تسعة أدوار
تخصصية)، بيانات مرجعية مرخصة، مهندسي GIS و3D، استضافة وCI، وتبنياً أكاديمياً أو
مؤسسياً. من يرى نفسه قادراً على الدعم أو التبني — فرداً أو جهة — يتواصل مع الفريق
التقني عبر القناة الرسمية المعلنة في [SUPPORT.md](SUPPORT.md).

## 3. Rights and restrictions — الحقوق والقيود

**EN —** Copyright (c) 2026 GEOLOGIA Project. All rights reserved. Copying, cloning,
or commercializing the code — in whole or in substantial part — is **prohibited**
without a written license from the Project Owner. The full terms are in
[LICENSE.md](LICENSE.md); the Arabic text therein governs.

**AR —** حقوق الابتكار محفوظة بالكامل لصاحب المشروع © 2026. استنساخ الكود أو
تحويله تجارياً — كلياً أو جزءاً جوهرياً — **ممنوع** إلا بترخيص كتابي من المالك.
النص الكامل في [LICENSE.md](LICENSE.md) والنسخة العربية فيه هي الحاكمة.

## 4. Scientific integrity — نزاهة العلم

- نجاح CI أو الاختبارات ليس شهادة صحة النتائج الجيولوجية — الأمان والصلاحية
  والصحة العلمية ثلاث شهادات منفصلة، لكل واحدة دليلها.
- كل إجابة تحمل تصنيفها: موثق باستشهاده، أو استنتاج معلن المنطق ومصادر مبانيه،
  أو «غير قابل للتأكيد من المكتبة» — والصمت الأمين أفضل من الجواب الملفق.

## 5. Third-party acknowledgements — إسناد الاعتماديات

The project builds on the open scientific Python ecosystem; each dependency keeps its
own license and is used, not redistributed in modified form:
pydantic (MIT) · FastAPI (MIT) · uvicorn (BSD-3) · lasio (MIT) · tifffile (BSD-3) ·
pyproj (MIT) · numpy (BSD-3) · pytest (MIT). Geodetic registries reference EPSG codes
by their EPSG identifiers and NGA geoid models by their official distribution points;
no grid data is embedded (see `src/geologia/data/reference/`).

## 6. Trademarks — العلامات

«GEOLOGIA»، «Ali Algomori»، «المهندس الجمهوري» — أسماء وهوية محفوظة لصاحب المشروع.

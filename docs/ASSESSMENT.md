# التقييم الذاتي الصادق — GEOLOGIA (الخط التاريخي v0.8.1 — الخط الحالي v0.20.0)

**Honest self-assessment: what we built, what is strong, what is weak, and what
we are doing about it — measured, not vibes.**

> منهجية: جرد فعلي للمستودع (git + اختبارات + ملفات)، تشغيل خط الأساس كاملاً،
> ومسح عالمي موثق بمصادر ([المصفوفة التنافسية](benchmark/COMPETITIVE_MATRIX.md)).
> هذا الملف يتحدث بلغة الأرقام والأدلة، بنفس تصنيف الصدق الذي نُلزم به Ali:
> ما تحقق نقوله بدليله، وما لم يتحقق نقول إنه لم يتحقق.

## ملخص تنفيذي (English)

Historical baseline (v0.8.1): GEOLOGIA was a **381-test green foundation**
with a rare epistemic
discipline: three-layer evidence, tamper-evident provenance, honest-skip gates,
and refusal-by-default knowledge. Its unique market position is the combination
of an auditable evidence layer with Arabic-first bilingualism — unclaimed by any
surveyed platform. Its main weaknesses are external: no remote CI, no community,
no published artifacts, and a small knowledge corpus. That release directly fixes
the governance gap (LICENSE/NOTICE/SUPPORT), the interface gap (bilingual
corporate README), and the hygiene gap (stray tracked files), and sets the
measured roadmap for the rest.

Current baseline (v0.20.0): core **485 passing / 12 skipped** on the full
path, workspace **431 passing / 41 skipped** on the CI gate (**490/3**
locally with full extras), ruff clean on both layers. The GeoBench-style
external-alignment gap (ض8) is closed: frozen external facts, measured
internal numbers, and an honest comparability table — see
[EXTERNAL_ALIGNMENT_V1](benchmark/EXTERNAL_ALIGNMENT_V1.md). Phase 2
continues the honest way (0.19.0 → 0.20.0): the verified display gate
refuses unvalidated or byte-changed layers with classified 409s, the
offline SVG map draws only what that gate returns, the pyproj-free UTM
equation module carries the Termux path — and in 0.20.0 CRS detection from
actual content (magnitude class + RFC 7946 range + declared-vs-content
resolution with an explicit truth class) lands at the core intake gate,
while reference-matched spatial analysis runs in bounded analysis workers
with classified refusals, the display gate refuses implausible content
under a UTM declaration (`display.refusal.crs_content_mismatch`), a
dedicated `/crs-content-verify` endpoint returns the full envelope, and
the honest limit is carried on every verdict: a UTM zone NUMBER is not
falsifiable from (easting, northing) alone — the Sana'a 44.2°E lesson —
so confirming the label needs an independent geographic anchor (next
documented step). The second mirror is ACTIVE (ADR-0009 owner decision):
real sync + restore-verify from the mirror inside the same CI run, and
the community standards (bilingual issue/PR templates, dependabot,
branch protection, squash-only merges, Discussions) now match the
declared bar. The strengths and
weaknesses below were measured at the historical baseline and are kept as
the honest record — any claim that moved since carries its update inline.

---

## 1) نقاط القوة — وكيف نعززها

### ق1: انضباط إبستمولوجي نادر على مستوى الكود
- **الدليل:** تصنيف الصدق الثلاثي مُلزَم في الأدلة والاختبارات، بوابة هلوسة
  صفرية مقاسة في التدقيق الحتمي (T3)، وبوابة تخطٍّ صادقة في الاختبارات بدل
  فشل كاذب عند غياب مكتبات اختيارية.
- **التعزيز:** نُثبّت النمط في كل مساهمة جديدة — أي ميزة بلا بوابات قبول
  قابلة للاختبار لا تدخل (قاعدة قائمة في معيار القبول)، ونضيف لاحقاً تقرير
  صدق آلياً في مخرجات كل محرك.

### ق2: أمن استقبال بمستوى إنتاجي
- **الدليل:** حدود حجم، تفتيش بايتات سحرية، أمان أرشيفات بلا استخراج (قنابل
  الضغط والـ traversal في مجموعات الاختبارات الذهبية)، تعقيم أسماء bidi، حجر
  صحي خام غير قابل للتعديل — ADR-0005/0007.
- **التعزيز:** هذا أصلاً قوي بالفعل؛ سنفتحه للمراجعة الأمنية الخارجية عند
  أول راعٍ تقني (بند الدعم رقم 4).

### ق3: قابلية تدقيق حتمية
- **الدليل:** مجموعات ذهبية مجمّدة ببصمة (40+10+5)، سكربت تدقيق حتمي، مرجع
  مستقل عن المحرك (معادلات EPSG:3857 المنشورة بلا pyproj)، كشف عبث لحظة
  التنفيذ.
- **التعزيز:** نعرض «بصمة الصدق» كمنتج مستقل لاحقاً — شهادة قابلة للتحقق
  يمكن لجامعة أو شركة إعادة توليدها محلياً. **تحقق فعلاً في 0.17.0**
  ([ADR-0010](adr/0010-reproducible-attestation.md)): `geologia certify`
  يتحقق من سلسلة الأدلة كاملة ببصمة متطابقة عبر نظامين مستقلين.

### ق4: حوكمة قرارات كاملة
- **الدليل:** ثمانية ADRs من 0001 إلى 0008، كل قرار بأبداله المرفوضة
  وعواقبه، وقاعدة مالك ملزمة تُقفل النمذجة 3D خلف طبقة البيانات.
- **التعزيز:** الجديد في 0.8.1: رخصة وإشعار ودعم — كانت الحوكمة بلا غلاف
  قانوني، وهذا كان أكبر ثغرة نضج مؤسسي.

### ق5: خفة القدم ووصول حقيقي
- **الدليل:** المجموعة الكاملة خضراء على مسار Python نقي بلا Rust — تعمل على
  Termux (أندرويد). لا منصة عالمية من التي فحصناها تدعي هذا النوع من الوصول.
- **التعزيز:** نرفع هذا كشعار تموضع في الرؤية: «المنصة التي تعمل حيث تعمل
  الجامعات والطلاب فعلاً».

### ق6: عربية أولاً — ثنائية اللغة أصيلة
- **الدليل:** واجهة CLI والمخطط والمعرفة تعمل بالعربية والإنجليزية، ومصطلحات
  متعددة اللغات في T1، والواجهة الآن ثنائية بأسلوب مؤسسي.
- **التعزيز:** لا يوجد بديل عربي في المصفوفة التنافسية إطلاقاً — هذا تميز
  سوقي حقيقي نوسعه بمسار GEOLOGIA Academy التعليمي.

### ق7: قرارات معمارية صائبة توفر سنوات إعادة عمل
- **الدليل:** أدوار فوق نموذج لا نماذج مدربة (ADR-0008)، RAG قبل Fine-tuning،
  عزل المحركات، سجلات مراجع بلا شبكات مضمّنة — كلها تتجنب الفخاخ التي سقطت
  فيها مشاريع AI جيولوجي أخرى (هالوسة، تدريب بلا قياس، خلط محرك ونموذج).
- **التعزيز:** الالتزام الصارم — لا استثناء «لأغراض العرض» أبداً.

## 2) نقاط الضعف — وكيف عالجناها أو سنعالجها

| # | الضعف | الدليل | المعالجة | الحالة |
| - | ----- | ------ | -------- | ------ |
| ض1 | غلاف قانوني غائب رغم «الحقوق محفوظة» | لا LICENSE/NOTICE قبل 0.8.1 | LICENSE.md ثنائية حاكمة + NOTICE + قيد الرخص في الاختبارات | **عولج في 0.8.1** |
| ض2 | واجهة مستودع أحادية اللغة وبلا هوية مؤسسية | README عربي-ثقيل بلا إنجليزية كاملة | README ثنائي بأسلوب Google/OpenAI + شارات حالة | **عولج في 0.8.1** |
| ض3 | ملفات عرضية متتبعة في git (`tool-results/`) | التزام fdc0287 شارد | إزالة من التتبع + .gitignore | **عولج في 0.8.1** |
| ض4 | لا مستودع بعيد ولا CI عاملاً أمام الجمهور | لا remote ولا Actions | مستودع عام نشط `tibatechapp-ship-it/Ali-Algomori` + CI مزدوج المسار أخضر متواصل على GitHub Actions (النواة 431/12 + workspace على كل دفعة) | **عولج — CI عام أخضر متواصل** |
| ض5 | مجتمع ومساهمات خارجية: صفر | لا CONTRIBUTING ولا قنوات | `CONTRIBUTING.md` ثنائية اللغة جاهزة (0.9.0) بعدم القابل للتفاوض ومسار المقترحات؛ المستوى التالي: أول مساهم خارجي عبر مستويات الشراكة | الوثيقة عولجت في 0.9.0 — المجتمع لاحق |
| ض6 | حجم المعرفة صغير (بذرة) | seed_catalog + 10 digests | خطط اكتساب مرخص عبر شراكة البيانات (SUPPORT بند 2) — لا فيلقاً مجانياً | مخطط |
| ض7 | لا تصور بصري (خرائط/3D) | مقفل عمداً خلف المرحلة 1.5 | ليس عيباً بل انضباط؛ عند فتح المرحلة 2 نبدأ بخريطة تفاعلية مرتبطة ببوابة CRS | مؤجل مقصود |
| ض8 | القياس داخلي فقط | لا مشاركة خارجية في التقييم | **تقرير المحاذاة الخارجية GeoBench-style منشور** ([EXTERNAL_ALIGNMENT_V1](benchmark/EXTERNAL_ALIGNMENT_V1.md)): حقائق المعيار الخارجي مجمّدة ملفاً موثقاً بالبصمة، وأرقامنا الداخلية مقاسة بالتدقيق الحتمي، وعشر صفوف قابلية مقارنة تصنّف بصدق بما فيها صفّا الحجم وتنوع المصادر حيث يقود المعيار الخارجي | **عولج في 0.18.0** |

## 3) خط الأساس المقاس (2026-11-22)

- مجموعة الاختبارات: **431 ناجحاً / 12 تخطياً** على المسار الكامل
  (lasio/tifffile/pyproj/numpy/imagecodecs)، و**386 ناجحاً / 57 تخطياً** على
  المسار النقي — التخطي كله ببوابات صادقة مسمّاة السبب: مكتبات اختيارية أو
  شبكة (0.9.0).
- عدد ADRs: 8. بطاقات وكلاء: 9. أسئلة ذهبية مجمّدة: 40 + 10 سلبية + 5 مزيفة.
- سجلات مرجعية: `reference_sources.json` + `geoid_model_reference.json`
  (بوابات الشبكات المضمّنة داخل المستودع كلها `not_recorded` — لا شبكة
  داخل الشجرة، وهذا التصريح الصادق نفسه محمي بالاختبارات) + **سجل جديد في
  0.9.0**: `geoid_grid_registry.json` ببوابات ثماني مسجّلة فعلياً للشبكتين
  الرسميتين EGM96/EGM2008 (ملفاتها خارج المستودع مثبتة ببصماتها) +
  `geoid_golden_nodes.json` بـ25 عقدة ذهبية مجمّدة لكل شبكة.
- مخاطر مفتوحة واحدة معلنة: التزام الحزمة المجمّدة `v0.8.0.zip` داخل الشجرة —
  ننقل مخرجات الإصدار المستقبلية إلى خارج التتبع (`dist/` في .gitignore).

## 4) ما الذي لا نستطيع تأكيده (تصنيف الصدق ينطبق علينا أولاً)

- لا نستطيع تأكيد أي ادعاء أداء أو دقة لم تقس مجموعة مستقلة.
- لا نستطيع تأكيد أن أي منصة مغلفة في المصفوفة تفعل ما نفعل بالضبط — قياسنا
  لها من وثائقها العامة فقط (منهجية الـ teardown في المصفوفة).
- لا نستطيع تأكيد جاهزية التبني المؤسسي قبل وجود مستودع عام وCI أخضر.

---

## 5) تحديث الخط الأساس — v0.15.0 (2026-11-23)

تطوير رئيسي منذ القسم 3 أعلاه، بأرقام CI المقاسة لا الادعاءات:

- **Monorepo موحد:** النواة المحكومة وطبقة workspace تحت بوابة واحدة (v0.10.0)
  بعد سلسلة مزامنة دلتا مثبتة بالطريقة الموثقة (v0.12.0 → v0.14.0)، مع دمج
  مستمر لدلتا مستودع المصدر خلال ساعات دفعها.
- **CI عام أخضر متواصل:** النواة **431 ناجحاً / 12 تخطياً** على المسارين
  (latest + termux-compat)، وworkspace **366 ناجحاً / 37 تخطياً** على بوابة
  CI (`[dev,gis]`) — و425/3 محلياً بالكماليات الكاملة. ruff نظيف على الطبقتين.
- **ض4 أُغلق رسمياً:** المستودع العام نشط والـCI الأخضر متواصل على كل دفعة.
- **إصدار مكتبي ثلاثي الأنظمة** بأصول ثنائية وSHA256SUMS (workflow منشور).
- **إضافات 0.15.0:** نسخ احتياطي واستعادة منسّق عبر الطبقتين مع CLI وتوثيق؛
  تدقيق سلامة تخزين الرفع للقراءة فقط (يتامى + سلامة)؛ اختبارات تسابق انتقالات
  المهام والإلغاء المتزامن؛ ملفات كفاءات قابلة للتدقيق لوكلاء Ali؛ معيار توجيه
  مهارات متعدد اللغات بلا اتصال؛ مسارات عمل مناعية للمجالات؛ مهارة خفيفة
  لتحليل منسوب المياه الجوفية ضمن حدودها المعلنة.
- **المصفوفة التنافسية v2** ([benchmark/COMPETITIVE_MATRIX.md](benchmark/COMPETITIVE_MATRIX.md)):
  20 صفًا بعد تدقيق مصادر 2026-11-23 — تعليق IUGS لـDDE صار منشوراً محكّماً
  (Journal of Geoethics، DOI 10.4401/jgsg-119)، GemPy عند 2026.0.3، KoBold عند
  تقييم ~3 مليار دولار، OneGeology أُغلقت بعد 18 سنة (درس مؤسسي ثانٍ)، EGDI
  نحو «بنية معرفة»، JiuZhou مفتوح الأوزان (IJDE 2025)، واتجاه GraphRAG الإثباتي
  2026 يؤكد معمارية بصماتنا. و**خارطة التصدر والاستقلال** المنجزة:
  [benchmark/STRATEGIC_LEADERSHIP_PLAN.md](benchmark/STRATEGIC_LEADERSHIP_PLAN.md).
- **الفجوة الوحيدة الكبرى المتبقية:** ض5 — أول مساهم خارجي؛ علاجها مؤسسي
  (شراكات الجامعات) لا تقني.

---

## 6) تحديث الخط الأساس — v0.16.0 وv0.17.0 (2026-11-23)

تطويران رئيسيان بعد القسم 5، بأرقام CI المقاسة وأدلة التشغيل المثبّتة:

- **v0.16.0 — المرآة الثانية وأدلة التشغيل المثبّتة:** آلة مزامنة
  واستعادة مُختبَرة طرفاً إلى طرف ([ADR-0009](adr/0009-mirror-independence.md))
  — `scripts/mirror_sync.sh` يدفع الفرع الحاكم وكل الوسوم بلا قوة تجبرية
  إلى مضيف ثانٍ بسر `GEOLOGIA_MIRROR_REMOTE_URL` ويطابق كل بصمة، و
  `scripts/mirror_restore_verify.py` يستنسخ من المرآة نفسها ويُثبت تطابق
  التاريخ؛ بلا سر تخطٍّ صادق برمز 0. جدول «Pinned run evidence» في README
  (باللغتين) يربط كل ادعاء أرقام بتشغيل CI ملموس: [تشغيل CI
  45054712124](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45054712124)
  عند `1f270d7` — النواة 446/12 وworkspace 366/37 على البوابة.
- **v0.17.0 — الشهادة القابلة لإعادة التوليد:** الفجوة P1 الرابعة أُغلقت
  ([ADR-0010](adr/0010-reproducible-attestation.md)): `geologia certify`
  بلا معرّف محرك يعيد حساب 32 أصلاً إثباتياً معلناً + بصمتي المجموعة
  الذهبية الداخليتين إلى بصمة حاكمة مشتقة من المحتوى وحده، يتحقق منها
  مقابل مرجع مثبت داخل الشجرة — عبث أو حذف أو إضافة غير معلنة أو تعديل
  صامت للمرجع كلها تُكشف محلياً بلا اتصال، والبصمة متطابقة عبر نظامين
  مستقلين (بوابة القبول مُختبرة باختبار شجرتين). الفحوص التشغيلية
  استشارية مستثناة من البصمة تصريحاً، وكل مخرج يحمل تصنيف حقيقة موثق
  مع الحدّين الصادقين (كاشفة للعبث لا مانعة منه؛ سلامة هندسية لا صحة
  جيولوجية). النواة الآن **455/12** (9 اختبارات شهادة جديدة).
- **المتبقي المعلن:** ض5 (أول مساهم خارجي — مؤسسي)، ض8 (محاذاة خارجية
  GeoBench-style)، ض6 (اكتساب معرفة مرخص) — بوابات لا تواريخ.

---

## 7) تحديث الخط الأساس — v0.18.0 (2026-11-23)

الفجوة P0 الثانية أُغلقت بأدلة لا بتصريحات:

- **المحاذاة الخارجية GeoBench-style منشورة:**
  [EXTERNAL_ALIGNMENT_V1](benchmark/EXTERNAL_ALIGNMENT_V1.md) — حقائق GeoBench
  (أول معيار NLP لعلوم الأرض، من ورقة K2 arXiv:2306.05064v2) مجمّدة في
  [ملف موثق بالبصمة](../../src/geologia/data/evaluation/external_alignment_v1.json)
  بنفس نمط قفل المجموعة الذهبية: 183 سؤالاً موضوعياً من NPEE + 1,395 من
  AP Test + 939 تحليلياً (50 بتقييم بشري) — بمصادرها وتاريخ وصولها
  والاقتباس الحرفي حارساً لانحراف النقل، وبلا نسخ سؤال امتحاني واحد
  (`questions_copied: 0`).
- **أرقامنا الداخلية مقاسة لا مزعومة:** التدقيق الحتمي نفسه الذي تشغّله
  CI — 55 عنصراً (40 ذهبية: 27 تطويرياً + 13 محجوبة، 10 سلبية، 5 مراجع
  مزيفة)، بوابة الرفض الصادق **1.0 حاكمة**، ومعدل صلاحية الاستشهاد
  **1.0 مقاس**.
- **جدول قابلية المقارنة عشر الصفوف مصنّف بصدق:** 2 `comparable`،
  1 `partially_comparable`، 2 `not_comparable`، 3 `ours_unique`،
  و2 `external_leads` — حجم المعيار الخارجي أكبر 45.8× وتنوع مصادره أوسع:
  خسارة معلنة في الملف المجمّد نفسه لا مخفية في نثر دعائي (بوابة
  «النتيجة المعلنة حتى لو خسرنا صفوفاً» مُختبرة برمجياً).
- **بصمات التشغيل مثبتة بالاختبارات:** بصمة ملف الحقائق الخارجية
  `fbe39f7f7160031da757447e1807ae98818275936631aeb0a3932e62dbae52eb`،
  والبصمة الحاكمة لسلسلة الأدلة الآن فوق **33 أصلاً** (أصل المحاذاة
  أُعلن في الشهادة): `3c85ba9911cfa4b9302902becf700cee6ad37888f1fd5a3fef621a9234dd545e`.
- النواة الآن **465/12** (10 اختبارات محاذاة جديدة)، ruff نظيف،
  الإصدار 0.18.0 في الطبقتين.
- **المتبقي المعلن:** ض5 (أول مساهم خارجي — مؤسسي)، ض6 (اكتساب معرفة
  مرخص) — بوابات لا تواريخ.

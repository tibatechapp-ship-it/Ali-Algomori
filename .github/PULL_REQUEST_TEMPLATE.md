<!-- English / العربية -->

## What & why | ماذا ولماذا
<!-- One paragraph: the change and the need it serves. | فقرة واحدة: التغيير والحاجة التي يخدمها. -->

## Governing sequence | التسلسل الحاكم
- [ ] This change does not jump a roadmap gate | لا يقفز فوق بوابة من بوابات الخارطة
- [ ] The trusted data layer is respected (no 3D/MODFLOW ahead of it) | طبقة البيانات الموثوقة محفوظة
- [ ] Every output path touched still carries its truth classification | كل مخرج متأثر ما زال يحمل تصنيف الحقيقة

## Evidence | الدليل
- Tests added/updated locally: `N passed, M skipped` — CI numbers come from the run, not from here.
- الاختبارات محلياً؛ أرقام CI تأتي من التشغيل الفعلي لا من هذا النص.
- Ruff both layers clean | الفحص نظيف في الطبقتين: ☐
- If version/affects counts: CHANGELOG + README + ASSESSMENT aligned | التوثيق متوائم: ☐

## Attestation | الشهادة
- [ ] `python -m geologia certify` passes over the declared assets | سلسلة الشهادة سليمة

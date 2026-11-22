<div align="center">

# GEOLOGIA · الجيولوجيا

**Geoscience Intelligence Platform — evidence first, always.**
**منصة الذكاء الجيولوجي — الدليل أولاً، دائماً.**

**English** | [العربية](#arabic--العربية)

</div>

> [!IMPORTANT]
> **Under active construction.** GEOLOGIA is being built in the open and needs
> scientific reviewers, licensed data, engineers, and institutional partners.
> Rights are fully reserved — copying or commercial use requires a written
> license from the project owner. See [SUPPORT.md](SUPPORT.md) · [LICENSE.md](LICENSE.md)
>
> **قيد الإنشاء الفعلي.** المشروع يحتاج مراجعين علميين وبيانات مرخصة ومهندسين
> وشركاء مؤسسيين. حقوق الابتكار محفوظة — الاستنساخ والاستخدام التجاري ممنوعان
> إلا بترخيص كتابي من المالك.

[![CI](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/workflows/ci.yml/badge.svg)](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/workflows/ci.yml) ![version](https://img.shields.io/badge/version-0.17.0-3b6e4f) ![tests](https://img.shields.io/badge/tests-455_passing_%2F_12_skipped-2ea44f) ![workspace](https://img.shields.io/badge/workspace_tests-366_passing_%2F_37_skipped-8a5fb5) ![license](https://img.shields.io/badge/license-GEOLOGIA_Proprietary_1.0-d9534f) ![python](https://img.shields.io/badge/python-%E2%89%A53.10-3776ab) ![i18n](https://img.shields.io/badge/i18n-%D8%B9%D8%B1%D8%A8%D9%8A%20%2F%20English-blue)

---

## What is GEOLOGIA?

A geoscience intelligence platform led by a chief scientific agent — **Ali** —
orchestrating **nine specialist roles** (stratigraphy, tectonics, mineralogy,
petrology, geophysics, geochemistry, hydrogeology, GeoAI & GIS, scientific review).
It is designed to be a **knowledge and practice link**: the same platform serves
classrooms, research centers, and companies — from a student's first query to a
certified engine execution with a full evidence report.

Three principles make it unlike any other platform in its class:

1. **No fabricated results.** Every answer carries an explicit truth class:
   *documented with citation*, *inferential with declared reasoning and sources*,
   or *"cannot be confirmed from the library."* Honest silence beats fluent nonsense.
2. **CI success is not a certificate of geological truth.** Security, validity, and
   scientific correctness are three separate certifications — each with its own
   evidence, enforced in code.
3. **Retrieval-only knowledge.** No generation from thin air (ADR-0002): the
   knowledge layer cites or refuses, and third-party engines are refused at the
   code level until they pass a full certification lifecycle.

## What works today (v0.17.0)

| Capability | Status |
| --- | --- |
| API core + deterministic planner (9 domains) | Stable, tested |
| Secure intake gate — size caps, magic-byte inspection, archive safety without extraction, bidi-safe names | Stable ([ADR-0005](docs/adr/0005-file-reception-security.md)) |
| Live upload endpoint `/api/v1/uploads` with raw quarantine + tamper-evident provenance | Stable ([ADR-0007](docs/adr/0007-http-upload-boundary.md)) |
| Evidence layer — real readers (lasio/tifffile/sqlite3), declared-vs-observed CRS & units checks, frozen independent reference engine | Stable |
| First-party certified engine `porosity_density_v1` with gates + tamper detection at execution | Stable ([standard](docs/ACCEPTANCE_STANDARD.md)) |
| Official geodetic registries — EGM96 ↔ EPSG:5773, EGM2008 ↔ EPSG:3855 (PR #7 mirror, 8 acceptance gates recorded, no embedded grid) | Stable |
| Knowledge foundation — institutions, knowledge-unit schema v1, license×purpose matrix, multilingual terms | Stable (T1) |
| Frozen golden evaluation — 40 golden + 10 negative + 5 fake references, deterministic audit, 9 agent cards | Stable (T3) |
| Knowledge-source intake (T2.1) — every external source through the SAME gate, refusals logged like acceptances | Stable |
| PDF/HTML extraction → candidate knowledge units, short-quote doctrine (T2.2) | Stable |
| Six-stage deduplication line — evidence accumulates, never deletes; unit harmonization before matching (T2.3) | Stable |
| Knowledge graph v1 — typed entities, closed relation pairs, no edge without evidence (T2.4) | Stable |
| Official EGM96/EGM2008 grids ingested through the gate — 8 gates recorded, our-parser vs PROJ crosscheck Δ = 0 m, 25 frozen golden nodes per grid (T4.1) | Stable |
| Agent-level vertical refusal rule — coded 409 without a loaded AND verified grid; no approximate value, no silent MSL (T4.2) | Stable |
| Reproducible evidence-chain attestation — `geologia certify`: one content-derived chain fingerprint over 32 declared assets, verified against the committed reference, tamper-evident offline | Stable ([ADR-0010](docs/adr/0010-reproducible-attestation.md)) |
| Geospatial analysis, 3D modelling, MODFLOW | **Deliberately locked** behind the trusted-data phase ([ROADMAP](docs/ROADMAP.md)) |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q

geologia about                      # project status, support & rights notice
geologia plan "حلل المياه الجوفية حول حوض صنعاء"
geologia knowledge search "من بدأ علم الجيولوجيا في التاريخ؟"
geologia verify well_log.las --type las
geologia dataset add "صنعاء بئر-01" well_log.las --dtype las
geologia task create "porosity" porosity_density_v1 ds-ab12cd34ef56 --param rho_ma_gcm3=2.65
geologia vertical 15.35 44.2          # geoid undulation — 409 refusal without a verified grid
geologia certify                      # whole evidence-chain attestation (ADR-0010)
geologia serve --port 8000
```

<details>
<summary><strong>Termux (Android — no Rust toolchain required)</strong></summary>

```bash
pkg install -y python git
pip install "pydantic<2" "fastapi<0.128"   # pure-Python builds for Android
pip install -e ".[dev]"
pytest -q
```

The full test suite is green on the pure-Python path — a deliberate design choice
for regions with limited compute infrastructure.
</details>

## Documentation map

| Document | Content |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layered architecture & engine isolation |
| [docs/ACCEPTANCE_STANDARD.md](docs/ACCEPTANCE_STANDARD.md) | The binding acceptance standard (certification) |
| [docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md) | Data governance |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Gate-based roadmap (not calendar-based) |
| [docs/adr/](docs/adr/) | All decisions, ADR-0001 → ADR-0010 |
| [docs/ASSESSMENT.md](docs/ASSESSMENT.md) | Honest self-assessment: strengths, weaknesses, fixes |
| [docs/benchmark/COMPETITIVE_MATRIX.md](docs/benchmark/COMPETITIVE_MATRIX.md) | Global comparison vs 14 platforms (open & closed) |
| [docs/VISION.md](docs/VISION.md) | Nucleus for the Arab & Islamic world's universities, research centers, companies |
| [docs/EDUCATION.md](docs/EDUCATION.md) | GEOLOGIA Academy — practical learning track |
| [SUPPORT.md](SUPPORT.md) | Partnership tiers & contact |
| [NOTICE.md](NOTICE.md) · [LICENSE.md](LICENSE.md) | Official notice & proprietary license (Arabic governs) |

## The unified repository — two layers

As of v0.10.0 GEOLOGIA is one repository with two cooperating layers, each
installable independently:

| Layer | Path | What it is | Install |
| --- | --- | --- | --- |
| **Governed core** | `src/geologia` | Reception gate, evidence store, knowledge units & dedup line, knowledge graph, geoid gate, golden eval, audit | `pip install -e .` |
| **Workspace** | `workspace/` | Local FastAPI workspace: bilingual RTL/LTR UI, Ali deterministic agent (AR/EN/RU/ZH), DEM coverage & readiness with tamper-evident chains, PWA, desktop & Termux launchers | `pip install -e "./workspace[dev,gis]"` |

Reference suites: core **455 passing / 12 skipped**, workspace **366 passing /
37 skipped** (workspace CI gate installs the governed core). Both layers obey
the same doctrine — evidence first, coded refusals, honest skips — and CI
success remains an engineering certificate, never a scientific one. Since
v0.11.0 the two layers are bound at the ingestion door: every workspace
knowledge ingestion (CLI and core seeds) passes the governed core's reception
gate first — refused bytes are never indexed, and every verdict leaves a
hash-chained provenance trace. Graph-backed retrieval over the core's
knowledge units remains the declared next binding step. The former standalone
`geologia` repository remains as the workspace archive — this repository's
[LICENSE.md](LICENSE.md) governs everything here.

**Python & CI baseline (v0.17.0):** the governed core supports Python
≥3.10 — the CI matrix runs a `latest` path and a `termux-compat` path on
pydantic<2 without compiled dependencies; the workspace layer requires
Python ≥3.12 (its `pyproject.toml` pins exact ranges). The root
`.github/workflows/ci.yml` is the single integration gate of this
repository: core tests, workspace tests and ruff on both layers — a
change counts as accepted only when that gate is green on the tagged
commit. Every test-count claim in this README is tied to that tagged
baseline; older numbers found anywhere else are historical, not current.

### Pinned run evidence

Every CI/test claim above is tied to a concrete run of the CI gate, not to
an assertion:

| Baseline | Claim | Evidence (pinned run) |
| --- | --- | --- |
| v0.15.1 | core 438/12 · workspace 366/37 green on the CI gate · tri-platform desktop assets | [CI run 45052350042](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45052350042) · [Desktop Release run 45052349833](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45052349833) at commit `b9504ea` |
| v0.16.0 | core 446/12 · workspace 366/37 on the CI gate · mirror workflow honest-skip verified | [CI run 45054712124](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45054712124) · [Mirror sync run 45054712138](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45054712138) at commit `1f270d7` |
| v0.17.0 | core 455/12 · workspace 366/37 on the CI gate · evidence-chain attestation shipped (ADR-0010) | [CI run 45057872188](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45057872188) · [Mirror sync run 45057872124](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45057872124) at commit `bb55c92` |

### Second-mirror independence (ADR-0009)

The repository, CI and releases live on GitHub alone — a single-host failure
point, and the closure of OneGeology after 18 years is the recent
institutional lesson. v0.16.0 ships the machinery, not just the intent:
`scripts/mirror_sync.sh` pushes the governing branch and all tags
fast-forward-only to a second host configured via the
`GEOLOGIA_MIRROR_REMOTE_URL` repository secret, then matches every reported
hash, and `scripts/mirror_restore_verify.py` clones **from the mirror** and
proves the restored history is hash-identical before running a smoke suite.
The `.github/workflows/mirror.yml` job skips cleanly with a notice until the
owner provisions the mirror account — an honest skip, not a fake green. The
whole chain is tested offline end-to-end in
[tests/test_mirror_independence.py](tests/test_mirror_independence.py),
including a deleted tag and a diverged mirror branch being caught. Tag
signing (PGP) activates the day a release key is provisioned; today's tags
are annotated and unsigned, and the sync script reports that count honestly
on every run.

### Reproducible attestation (ADR-0010)

The honesty fingerprint is now a product: `geologia certify` (no engine id)
recomputes the whole evidence chain — 32 declared assets plus the frozen
golden-eval internal fingerprints — into one content-derived chain
fingerprint and verifies it against
[data/attestation/attestation_reference_v1.json](src/geologia/data/attestation/attestation_reference_v1.json),
committed to the tree. Tampering with any asset, deleting or adding an
undeclared asset, breaking the golden internal fingerprints, or silently
editing the reference breaks the command and the tests — offline, with no
network and no trust assumptions. What is inside the hash is content only
(no clock, no paths, no runtime results), so two independent systems on the
same repo state produce the identical fingerprint — the acceptance gate,
tested directly. Runtime re-certification of the first-party engine runs as
an advisory, explicitly excluded from the hash with an honest named skip.
The attestation is tamper-evident, not tamper-proof, and certifies
engineering integrity — never geological truth.

## Where GEOLOGIA stands globally

We benchmarked ourselves against the open-source leaders (GemPy v3, LoopStructural),
the AI geoscience platforms (GeoGPT/DDE, K2 + GeoBench), the data standards (OSDU),
and the closed leaders (Leapfrog Geo, Petrel/DELFI, GeoModeller) — see the
[competitive matrix](docs/benchmark/COMPETITIVE_MATRIX.md). Our differentiator is
not another modelling engine; it is an **auditable evidence layer with honest
refusal, bilingual by design (Arabic-first)** — a gap none of the surveyed
platforms fills today.

## License & contact

Copyright (c) 2026 GEOLOGIA Project — **all rights reserved**. Academic, research,
and educational use is permitted with attribution; cloning and commercial use are
prohibited without a written license from the project owner
([LICENSE.md](LICENSE.md)).

**Contact / التواصل:** [aigeologia@gmail.com](mailto:aigeologia@gmail.com) — the
official contact channel approved for GEOLOGIA (adoption memo, 2026-11-22).
Licensing requests: [LICENSE.md](LICENSE.md) · Support: [SUPPORT.md](SUPPORT.md)

---

<a id="arabic--العربية"></a>

## العربية

**منصة ذكاء جيوعلمي يقودها وكيل علمي رئيسي — «Ali» — فوق تسعة أدوار تخصصية
(طبقات، تكتونيات، معادن، صخور، جيوفيزياء، كيمياء جيولوجية، مياه جوفية،
GeoAI وGIS، مراجعة علمية). صُممت لتكون رابطاً معرفياً وعملياً في آن واحد:
نفس المنصة تخدم قاعة الدرس ومركز الأبحاث وشركة التعدين — من أول سؤال للطالب
إلى تنفيذ محرك معتمد بتقرير أدلة كامل.**

### القواعد العلمية الملزمة

1. لا يختلق النظام نتائج، ولا يدّعي تشغيل محرك لم يعمل فعلياً — كل إجابة
   تحمل تصنيف الصدق المعلن: موثق باستشهاده، أو استنتاجي بمنطق معلن، أو
   «غير قابل للتأكيد من المكتبة».
2. الاحتمال ليس حقيقة: أي نسبة ثقة تحتاج نموذجاً معايراً وبيانات مستقلة.
3. لا توصية بحفر بئر اعتماداً على خريطة وحدها.
4. كل نتيجة قابلة للتتبع: البيانات، المحرك، الإصدار، المعلمات، المخرجات.
5. عزل المحركات: لا بيئة Python واحدة تجمع كل الاعتماديات، ونجاح CI ليس
   شهادة صحة النتائج الجيولوجية.

### ما يعمل الآن (v0.17.0)

- نواة API + مخطط حتمي لتسعة مجالات، وبوابة استقبال آمنة (حدود حجم، تفتيش
  بايتات سحرية، أمان أرشيفات بلا استخراج، تعقيم أسماء بعلامات bidi)، ونقطة
  رفع حية `/api/v1/uploads` بحجر صحي خام وسجل مصدر مضاد للتلاعب —
  [ADR-0007](docs/adr/0007-http-upload-boundary.md).
- طبقة إثبات: قرّاء حقيقيون، فحص CRS والوحدات المعلنة مقابل المحتوى الفعلي،
  ومرجع مجمّد مستقل عن المحرك، وأول محرك علمي أول-الطرف معتمد
  (`porosity_density_v1`) وفق [معيار القبول الملزم](docs/ACCEPTANCE_STANDARD.md).
- سجلات مرجعية جيوديسية رسمية: EGM96 ↔ EPSG:5773 وEGM2008 ↔ EPSG:3855
  (مرآة PR #7، بوابات القبول الثماني مسجّلة، بلا شبكة مضمّنة).
- أساس المعرفة T1 والاختبارات الذهبية T3: 40 سؤالاً ذهبياً + 10 سلبية +
  5 مراجع مزيفة، بسكربت تدقيق حتمي وبطاقات للوكلاء التسعة.
- **مدخل المعرفة T2 (0.9.0)**: كل مصدر خارجي عبر البوابة نفسها، استخراج
  PDF/HTML إلى وحدات مرشحة باقتباس قصير حرفي، خط جِدّة سداسي يجمع الأدلة
  ولا يحذف، وشبكة معرفة v1 بلا حافة بلا إثبات.
- **البوابة الجيويدية T4 (0.9.0)**: الشبكتان الرسميتان EGM96 وEGM2008
  جرّدتا عبر البوابة نفسها والبوابات الثماني مسجلة، والتحقق المستقل
  (محللنا مقابل PROJ على نفس البايتات) بتطابق صفر متر، وقاعدة رفض رأسي
  مرمزة 409 — `geologia vertical LAT LON`.
- **الشهادة القابلة لإعادة التوليد (0.17.0، [ADR-0010](docs/adr/0010-reproducible-attestation.md))**: `geologia certify` بلا معرّف محرك يتحقق من سلسلة الأدلة كاملة — بصمة حاكمة مشتقة من المحتوى وحده لـ 32 أصلاً إثباتياً معلناً + بصمتي المجموعة الذهبية الداخليتين، مقابل مرجع مثبت داخل الشجرة؛ عبث أو حذف أو إضافة غير معلنة تُكشف بلا اتصال، والبصمة متطابقة عبر نظامين مستقلين.
- النمذجة ثلاثية الأبعاد والمياه الجوفية **مقفلة عمداً** خلف اكتمال طبقة
  البيانات الموثوقة — انضباط مقصود لا قصور ([خارطة الطريق](docs/ROADMAP.md)).

### التشغيل السريع

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q

geologia about                    # حالة المشروع ودعوة الدعم والحقوق
geologia plan "حلل المياه الجوفية حول حوض صنعاء"
geologia knowledge search "من بدأ علم الجيولوجيا في التاريخ؟"
geologia verify سجل_البئر.las --type las
geologia certify                      # شهادة سلامة سلسلة الأدلة كاملة (ADR-0010)
geologia serve --port 8000
```

يدعم **Termux (أندرويد)** كاملاً بمسار Python نقي — قرار تصميمي للمناطق
محدودة البنية التحتية للحوسبة.

### المستندات

المعمارية والتوثيق الكامل في الجدول أعلاه، وكل القرارات موثقة في
[docs/adr/](docs/adr/) من ADR-0001 إلى ADR-0010، والتقييم الذاتي الصادق في
[docs/ASSESSMENT.md](docs/ASSESSMENT.md)، والموقع التنافسي العالمي في
[docs/benchmark/COMPETITIVE_MATRIX.md](docs/benchmark/COMPETITIVE_MATRIX.md)،
ورؤية التبني الإقليمي في [docs/VISION.md](docs/VISION.md)، والمسار التعليمي
العملي في [docs/EDUCATION.md](docs/EDUCATION.md).

### المستودع الموحد — طبقتان

منذ v0.10.0 صار GEOLOGIA مستودعاً واحداً بطبقتين متعاونتين، كلٌّ منهما
قابلة للتثبيت باستقلال:

| الطبقة | المسار | ما هي | التثبيت |
| --- | --- | --- | --- |
| **النواة الحاكمة** | `src/geologia` | بوابة الاستقبال، مخزن الأدلة، وحدات المعرفة وخط الجِدّة، شبكة المعرفة، بوابة الجيود، الاختبارات الذهبية | `pip install -e .` |
| **مساحة العمل** | `workspace/` | مساحة FastAPI المحلية: واجهة ثنائية اللغة RTL/LTR، وكيل Ali الحتمي (عربي/إنجليزي/روسي/صيني)، تغطية وجاهزية DEM بسلاسل مقاومة للتلاعب، PWA، مشغّلات سطح المكتب وTermux | `pip install -e "./workspace[dev,gis]"` |

المجموعتان المرجعيتان: النواة **455 ناجحاً / 12 تخطياً**، مساحة العمل
**366 ناجحاً / 37 تخطياً** (بوابة CI لمساحة العمل تثبت النواة الحاكمة أولاً). الطبقتان تخضعان للعقيدة نفسها — الدليل أولاً،
رفض مرمز، تخطٍّ صادق — ونجاح CI يبقى شهادة هندسية لا علمية أبداً. ومنذ v0.11.0 ارتبطت الطبقتان عند باب الاستيعاب: كل استيعاب معرفة في مساحة العمل (CLI والبذور) يمر أولاً عبر بوابة الاستقبال في النواة الحاكمة — البايتات المرفوضة لا تُفهرس أبداً، وكل حكم يترك أثراً في سجل المصدر المضاد للتلاعب. الاسترجاع المدعوم بشبكة المعرفة على وحدات النواة يبقى خطوة الربط المعلنة التالية. مستودع `geologia` السابق يبقى أرشيفاً
لتاريخ مساحة العمل — و[رخصة هذا المستودع](LICENSE.md) تحكم كل ما هنا.

**خط أساس Python وCI (v0.17.0):** النواة الحاكمة تدعم Python ≥3.10 —
مصفوفة CI تشغّل مسار `latest` ومسار `termux-compat` على pydantic<2 بلا
اعتماديات مترجمة، ومساحة العمل تتطلب Python ≥3.12 (تثبّت نطاقاتها في
pyproject الخاص بها). الملف الجذري `.github/workflows/ci.yml` هو بوابة
التكامل الوحيدة لهذا المستودع: اختبارات النواة واختبارات مساحة العمل
وruff على الطبقتين — ولا يُعد التغيير مقبولاً إلا بأخضر البوابة على
commit الوسم. كل رقم اختبارات في هذا الملف مرتبط بذلك الخط الموسوم،
وكل رقم أقدم في أي ملف آخر يُقرأ تاريخياً لا كخط أساس حالي.

### أدلة التشغيل المثبّتة

كل ادعاء CI/اختبارات أعلاه مرتبط بتشغيل ملموس للبوابة لا بمجرّد تصريح:

| الخط الأساسي | الادعاء | الدليل (تشغيل مثبّت) |
| --- | --- | --- |
| v0.15.1 | النواة 438/12 · مساحة العمل 366/37 خضراء على بوابة CI · أصول مكتبي ثلاثية الأنظمة | [تشغيل CI 45052350042](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45052350042) · [تشغيل الإصدار المكتبي 45052349833](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45052349833) عند commit `b9504ea` |
| v0.16.0 | النواة 446/12 · مساحة العمل 366/37 على بوابة CI · تحقق تخطي المرآة الصادق | [تشغيل CI 45054712124](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45054712124) · [تشغيل مزامنة المرآة 45054712138](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45054712138) عند commit `1f270d7` |
| v0.17.0 | النواة 455/12 · مساحة العمل 366/37 على بوابة CI · شهادة سلسلة الأدلة صارت منتجاً (ADR-0010) | [تشغيل CI 45057872188](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45057872188) · [تشغيل مزامنة المرآة 45057872124](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/runs/45057872124) عند commit `bb55c92` |

### استقلال المرآة الثانية (ADR-0009)

المستودع وCI والإصدارات كلها على GitHub وحده — نقطة فشل واحدة، وإغلاق
OneGeology بعد 18 عاماً هو الدرس المؤسسي المعاصر. v0.16.0 تُسلّم الآلة لا
النية فقط: `scripts/mirror_sync.sh` يدفع الفرع الحاكم وكل الوسوم بلا قوة
تجبرية إلى مضيف ثانٍ يُضبَط بسر `GEOLOGIA_MIRROR_REMOTE_URL`، ويطابق كل
بصمة تُعلنها المرآة، ثم يستنسخ `scripts/mirror_restore_verify.py`
**من المرآة نفسها** ويُثبت أن التاريخ المستعاد مطابق بالبصمات قبل تشغيل
اختبار دخان. مهمة `.github/workflows/mirror.yml` تتخطى نفسها بنظافة
بإشعار صريح إلى أن يوفّر المالك حساب المرآة — تخطٍّ صادق لا أخضر مزيّف.
والسلسلة كلها مُختبَرة بلا اتصال طرفاً إلى طرف في
[tests/test_mirror_independence.py](tests/test_mirror_independence.py)
بما يشمل كشف وسم محذوف وفرع مُنحرف على المرآة. توقيع الوسوم بPGP يُفعَّل
يوم توفير مفتاح الإصدار؛ وسوم اليوم موسومة تعليقياً بلا توقيع، والسكربت
يعلن ذلك العدد بصدق في كل تشغيل.

### الشهادة القابلة لإعادة التوليد (ADR-0010)

بصمة الصدق صارت منتجاً: `geologia certify` بلا معرّف محرك يعيد حساب
سلسلة الأدلة كاملة — 32 أصلاً إثباتياً معلناً مع بصمتي المجموعة الذهبية
المجمّدة الداخليتين — إلى بصمة حاكمة مشتقة من المحتوى وحده، ويتحقق منها
مقابل [المرجع المثبت داخل الشجرة](src/geologia/data/attestation/attestation_reference_v1.json).
عبثٌ بأي أصل، أو حذفُ أصلاً أو إضافةُ غير معلن، أو كسرٌ للبصمات الذهبية
الداخلية، أو تعديلٌ صامت للمرجع — يكسر الأمر والاختبارات بلا اتصال ولا
افتراض ثقة. ما داخل البصمة محتوى فقط (لا ساعة ولا مسارات ولا نتائج
تشغيل)، فنظامان مستقلان على حالة المستودع نفسها يولّدان البصمة نفسها —
بوابة القبول مُختبرة مباشرة. إعادة اعتماد المحرك الأول-الطرف تُشغَّل
استشارياً ومستثناة من البصمة تصريحاً بتخطٍّ صادق مسمّى. الشهادة كاشفةٌ
للعبث لا مانعةٌ منه، وتوثّق سلامة هندسية — لا صحة جيولوجية أبداً.

### الدعم والتبني والحقوق

المشروع قيد الإنشاء ويحتاج موارد ودعماً: مراجعين علميين، بيانات مرخصة،
مهندسين، جامعات ومراكز أبحاث تتبناه، ورعاة تقنيين — من يرى نفسه قادراً على
الدعم أو التبني يتواصل مع الفريق التقني عبر
[SUPPORT.md](SUPPORT.md).
حقوق الابتكار محفوظة بالكامل، وممنوع استنساخ الكود أو تحويله تجارياً إلا
بترخيص كتابي من صاحب المشروع ([LICENSE.md](LICENSE.md) — النص العربي حاكم).

**التواصل:** [aigeologia@gmail.com](mailto:aigeologia@gmail.com) — البريد الرسمي
المعتمد لمشروع GEOLOGIA (مذكرة الاعتماد، 2026-11-22). طلبات الترخيص عبر
[LICENSE.md](LICENSE.md) والدعم عبر [SUPPORT.md](SUPPORT.md).

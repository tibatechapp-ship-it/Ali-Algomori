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

[![CI](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/workflows/ci.yml/badge.svg)](https://github.com/tibatechapp-ship-it/Ali-Algomori/actions/workflows/ci.yml) ![version](https://img.shields.io/badge/version-0.13.1-3b6e4f) ![tests](https://img.shields.io/badge/tests-431_passing_%2F_12_skipped-2ea44f) ![workspace](https://img.shields.io/badge/workspace_tests-322_passing_%2F_41_skipped-8a5fb5) ![license](https://img.shields.io/badge/license-GEOLOGIA_Proprietary_1.0-d9534f) ![python](https://img.shields.io/badge/python-%E2%89%A53.10-3776ab) ![i18n](https://img.shields.io/badge/i18n-%D8%B9%D8%B1%D8%A8%D9%8A%20%2F%20English-blue)

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

## What works today (v0.8.1)

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
| [docs/adr/](docs/adr/) | All decisions, ADR-0001 → ADR-0008 |
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

Reference suites: core **431 passing / 12 skipped**, workspace **291 passing /
40 skipped** (workspace CI gate installs the governed core). Both layers obey
the same doctrine — evidence first, coded refusals, honest skips — and CI
success remains an engineering certificate, never a scientific one. Since
v0.11.0 the two layers are bound at the ingestion door: every workspace
knowledge ingestion (CLI and core seeds) passes the governed core's reception
gate first — refused bytes are never indexed, and every verdict leaves a
hash-chained provenance trace. Graph-backed retrieval over the core's
knowledge units remains the declared next binding step. The former standalone
`geologia` repository remains as the workspace archive — this repository's
[LICENSE.md](LICENSE.md) governs everything here.

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

### ما يعمل الآن (v0.8.1)

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
geologia serve --port 8000
```

يدعم **Termux (أندرويد)** كاملاً بمسار Python نقي — قرار تصميمي للمناطق
محدودة البنية التحتية للحوسبة.

### المستندات

المعمارية والتوثيق الكامل في الجدول أعلاه، وكل القرارات موثقة في
[docs/adr/](docs/adr/) من ADR-0001 إلى ADR-0008، والتقييم الذاتي الصادق في
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

المجموعتان المرجعيتان: النواة **431 ناجحاً / 12 تخطياً**، مساحة العمل
**291 ناجحاً / 40 تخطياً** (بوابة CI لمساحة العمل تثبت النواة الحاكمة أولاً). الطبقتان تخضعان للعقيدة نفسها — الدليل أولاً،
رفض مرمز، تخطٍّ صادق — ونجاح CI يبقى شهادة هندسية لا علمية أبداً. ومنذ v0.11.0 ارتبطت الطبقتان عند باب الاستيعاب: كل استيعاب معرفة في مساحة العمل (CLI والبذور) يمر أولاً عبر بوابة الاستقبال في النواة الحاكمة — البايتات المرفوضة لا تُفهرس أبداً، وكل حكم يترك أثراً في سجل المصدر المضاد للتلاعب. الاسترجاع المدعوم بشبكة المعرفة على وحدات النواة يبقى خطوة الربط المعلنة التالية. مستودع `geologia` السابق يبقى أرشيفاً
لتاريخ مساحة العمل — و[رخصة هذا المستودع](LICENSE.md) تحكم كل ما هنا.

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

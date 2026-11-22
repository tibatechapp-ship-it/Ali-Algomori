# Contributing — المساهمة في GEOLOGIA

**GEOLOGIA grows by gates, not by promises. If you want to contribute, these
rules are not bureaucracy — they are the reason the platform can be trusted.**

**GEOLOGIA تكبر بالبوابات لا بالوعود. من أراد المساهمة، فهذه القواعد ليست
بيروقراطية — بل هي سبب إمكان تصديق هذه المنصة أصلاً.**

---

## 1. Read first — اقرأ أولاً

- [LICENSE.md](LICENSE.md) — by opening a contribution you grant the project
  owner the permanent right to use, modify, and relicense it (License §6).
  بقبول مساهمتك تمنح صاحب المشروع حق الاستخدام والتعديل وإعادة الترخيص دائماً.
- [docs/ACCEPTANCE_STANDARD.md](docs/ACCEPTANCE_STANDARD.md) — the binding
  acceptance standard. معيار القبول الملزم.
- [docs/adr/](docs/adr/) — every architectural decision lives here; propose
  changes through a new ADR, not by rewriting old ones. القرارات عبر ADR
  جديد لا بإعادة كتابة القديم.

## 2. The non-negotiables — غير القابل للتفاوض

1. **No second door.** Every byte — data, source, grid, upload — enters
   through the same reception gate. A "trusted site" exception is a bug, not
   a feature. لا مسار خاص لأي بايت مهما كان مصدره.
2. **Every verdict leaves a trace.** Refusals go to the provenance log like
   acceptances. A refusal without a trace is a shrug. كل حكم — حتى الرفض —
   يوثق في سجل المصدر.
3. **Every feature ships with tests and refusal codes.** A gate that cannot
   be tested does not exist. Any capability claim needs a deterministic
   measurement. ميزة بلا اختبار وبوابة رفض مرمزة ليست ميزة.
4. **Honest skips, never fake passes.** Missing optional dependencies produce
   `pytest.mark.skipif(..., reason=...)` with a named reason — on the pure
   Python path (Termux) included. تخطٍّ صادق باسم السبب، ولا نجاح مزيف
   أبداً على المسار النقي.
5. **CI success is not geological truth.** Security, validity, and scientific
   correctness are three separate certificates. لا تخلط الشهادات الثلاث.

## 3. Dev setup — بيئة التطوير

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,geo]"     # full path (lasio/tifffile/pyproj/numpy)
pytest -q                       # expect: all passed, skips only with named reasons
ruff check .

# pure path (Termux parity) — must also be green:
pip uninstall -y lasio tifffile pyproj imagecodecs numpy
pytest -q
pip install -e ".[dev,geo]"     # restore
```

## 4. What we need most (see SUPPORT.md) — الأكثر احتياجاً

Scientific reviewers for the nine roles, licensed reference data, GIS/3D
engineering, hosting/CI, and university partners. المراجعون العلميون
للأدوار التسعة، البيانات المرخصة، هندسة GIS، الاستضافة، والجامعات الشريكة.

## 5. How to propose — كيف تقترح

Open a change proposal describing: the gap it fills (like the gap numbering
in the approved plan), the frozen data file it adds (if any), the schema it
touches, and the coded refusal it introduces. Proposals without refusal
codes return with one question: **what does your feature refuse, and where
is that refusal tested?** كل مقترح يصف الفجوة التي يملؤها والرفض المرمز
الذي يضيفه — والمقترح بلا رفض مرمز يعود بسؤال واحد: ماذا يرفض ميزتك
وأين يُختبر ذلك الرفض؟

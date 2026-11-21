# Project status banner: construction phase, support appeal, and rights notice.
# Bilingual by design (AR first) — surfaced via `geologia about` and the API root.
import sys
from geologia import __version__

PROJECT = "GEOLOGIA"
STATUS = "construction"  # honest phase marker: not production

_SUPPORT_AR = (
    "GEOLOGIA قيد الإنشاء الفعلي — ونحتاج موارد ودعماً: مراجعين علميين، "
    "بيانات مرخصة، مهندسين، وتبنياً من جامعات ومراكز أبحاث وشركات. "
    "من يرى نفسه قادراً على الدعم أو التبني يتواصل مع الفريق التقني عبر "
    "قناة التواصل الرسمية المعلنة في المستودع (SUPPORT.md)."
)
_SUPPORT_EN = (
    "GEOLOGIA is under active construction — it needs resources and support: "
    "scientific reviewers, licensed data, engineers, and adoption by "
    "universities, research centers, and companies. If you can support or "
    "adopt the project, contact the technical team via the official channel "
    "published in the repository (SUPPORT.md)."
)
_RIGHTS_AR = (
    "حقوق الابتكار محفوظة بالكامل لصاحب المشروع © 2026 GEOLOGIA — "
    "ممنوع استنساخ الكود أو تحويله تجارياً إلا بترخيص كتابي من المالك "
    "(LICENSE.md — النص العربي حاكم)."
)
_RIGHTS_EN = (
    "All innovation rights reserved by the project owner (c) 2026 GEOLOGIA — "
    "copying or commercializing the code requires a written license from the "
    "owner (LICENSE.md — Arabic text governs)."
)
_STATUS_AR = f"حالة المشروع: قيد الإنشاء (الإصدار {__version__}) — ليس نظام إنتاج بعد، وكل نتيجة تحمل تصنيف صدقها المعلن."
_STATUS_EN = (
    f"Project status: under construction (version {__version__}) — not a "
    "production system; every result carries its declared truth class."
)


def banner(lang: str = "both") -> str:
    """Return the project notice banner ('ar', 'en', or 'both')."""
    lang = (lang or "both").lower()
    header = f"[{PROJECT} {__version__}]"
    if lang == "ar":
        parts = [header, _STATUS_AR, _SUPPORT_AR, _RIGHTS_AR]
    elif lang == "en":
        parts = [header, _STATUS_EN, _SUPPORT_EN, _RIGHTS_EN]
    else:
        parts = [header, _STATUS_AR, _STATUS_EN, "", _SUPPORT_AR, _SUPPORT_EN,
                 "", _RIGHTS_AR, _RIGHTS_EN]
    return "\n".join(parts)


if __name__ == "__main__":
    print(banner(sys.argv[1] if len(sys.argv) > 1 else "both"))

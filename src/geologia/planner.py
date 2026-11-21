# Deterministic analysis planner v2 (foundation phase).
# Produces PLANS ONLY: no engine is executed and no scientific result is
# computed here.
#
# Design rules enforced by this module:
# 1. Candidate engines are DERIVED from the engine registry, so the planner
#    can never advertise an engine outside its registry domain.
# 2. Every intent domain must exist in the registry (validated at import).
# 3. Matching is done on normalized Arabic/Latin text (see normalize.py).
# 4. When no domain matches, the planner raises UnknownDomainError instead of
#    fabricating a GIS plan — the honest-gate rule: never invent a plan.
# 5. Specific intents win over generic keyword collisions (PRECEDENCE_RULES):
#    e.g. "LAS well log" is well_logs, not hydrology via the word "well".
from typing import Dict, List, Optional, Set

from geologia.normalize import normalize_text
from geologia.registry import ENGINES

# ---------------------------------------------------------------------------
# Analysis intents: 9 user-facing domains.
# The registry's "agent_reference" and "engineering" domains are reference /
# integration domains, deliberately excluded from user analysis intents.
# ---------------------------------------------------------------------------
INTENTS: List[Dict] = [
    {
        "domain": "well_logs",
        "required_inputs": ["las_files", "well_header_metadata"],
        "keywords": [
            "las", "well log", "well logs", "petrophys", "porosity",
            "permeability", "gamma ray", "سجل البئر", "سجل الآبار",
            "سجلات الآبار", "سجلات البئر", "قطع الآبار", "قطع البئر",
            "المسامية", "النفاذية", "الشعاع الغامي",
        ],
    },
    {
        "domain": "hydrology",
        "required_inputs": ["well_logs", "water_levels_timeseries",
                            "recharge_estimate", "dem", "geology_map"],
        "keywords": [
            "مياه", "جوفية", "جوفي", "بئر", "آبار", "ضخ", "خزان جوفي",
            "نزول المنسوب", "ارتوازي", "aquifer", "groundwater", "hydro",
            "well", "pumping", "recharge", "water level", "modflow",
        ],
    },
    {
        "domain": "geology3d",
        "required_inputs": ["geology_map", "structural_orientations",
                            "contacts", "dem"],
        "keywords": [
            "ثلاثي", "قطاع", "بنية", "طيات", "فوالق", "طباقي",
            "نمذجة جيولوجية", "3d", "cross-section", "cross section",
            "structural", "geological model", "stratigraph",
        ],
    },
    {
        "domain": "seismology",
        "required_inputs": ["waveforms_or_catalog", "station_metadata"],
        "keywords": [
            "زلزال", "زلازل", "زلزالي", "هزات", "سيزمي", "موجات",
            "الخطر الزلزالي", "seismic", "earthquake", "waveform",
            "seismolog", "seismic hazard",
        ],
    },
    {
        "domain": "geophysics",
        "required_inputs": ["geophysical_survey_data", "survey_geometry",
                            "topography", "crs_definition"],
        "keywords": [
            "جيوفيزي", "كهرومغناطيسي", "مقاومة نوعية", "تصوير كهربائي",
            "جاذبية", "ثقالي", "مغناطيسي", "انعكاسي", "انكساري",
            "عكس جيوفيزيائي", "ert", "tomograph", "inversion", "resistivity",
            "magnetic", "gravity", "geophysic", "seismic reflection",
            "seismic refraction",
        ],
    },
    {
        "domain": "geochemistry",
        "required_inputs": ["geochemistry_samples", "sample_locations",
                            "qc_report"],
        "keywords": [
            "جيوكيمي", "عناصر", "عينات", "تحليل عنصري", "geochem",
            "samples", "rock classification",
        ],
    },
    {
        "domain": "exploration",
        "required_inputs": ["geochemistry_samples", "geophysics_surveys",
                            "geology_map"],
        "keywords": [
            "تنقيب", "استكشاف", "ذهب", "معدن", "معدنية", "قابلية",
            "prospectivity", "mineral", "exploration", "gold",
        ],
    },
    {
        "domain": "remote_sensing",
        "required_inputs": ["drone_images_or_satellite_scenes",
                            "ground_control_points"],
        "keywords": [
            "درون", "استشعار", "قمر صناعي", "فوتوغرامتري", "تصوير جوي",
            "drone", "satellite", "remote sensing", "photogrammetry",
            "orthophoto",
        ],
    },
    {
        "domain": "gis",
        "required_inputs": ["aoi_boundary", "data_layers", "crs_definition"],
        "keywords": [
            "خريطة", "طبقات", "مكاني", "أساس", "صفائح", "تكتون",
            "gis", "map", "layers", "spatial", "shapefile", "geotiff",
            "tectonic", "plate",
        ],
    },
]

# ---------------------------------------------------------------------------
# Precedence rules: when a "strong" intent matches, a "weak" intent matched
# ONLY through its generic keywords is suppressed. Generic sets are stored
# in normalized form (they are compared against normalized matched keywords).
# ---------------------------------------------------------------------------
PRECEDENCE_RULES: List[Dict] = [
    {
        "strong": "well_logs",
        "weak": "hydrology",
        "weak_generics": {normalize_text(k) for k in ("well", "بئر", "آبار")},
    },
    {
        "strong": "geophysics",
        "weak": "seismology",
        "weak_generics": {normalize_text(k) for k in ("seismic", "سيزمي", "زلزال", "زلازل")},
    },
]

GATES_AR = [
    "هل البيانات كافية؟",
    "هل نظام الإحداثيات والوحدات صحيحان؟",
    "هل المحرك المناسب استُخدم؟",
    "هل توجد أخطاء أو تحذيرات؟",
    "هل النتيجة قابلة لإعادة الإنتاج؟",
    "هل مستوى عدم اليقين واضح؟",
    "هل وافق المراجع العلمي المستقل؟",
]

GATES_EN = [
    "Is the data sufficient?",
    "Are CRS and units correct?",
    "Was the right engine used?",
    "Are there errors or warnings?",
    "Is the result reproducible?",
    "Is uncertainty explicit?",
    "Did the independent scientific reviewer approve?",
]

DISCLAIMER_AR = (
    "هذه خطة تحليل فقط ولم تُحسب أي نتيجة علمية بعد. "
    "لا يوصي النظام بحفر بئر أو تأكيد مورد اعتمادًا على خريطة وحدها، "
    "وأي نسبة ثقة مستقبلية تتطلب نموذجًا معايرًا وبيانات مستقلة."
)

DISCLAIMER_EN = (
    "This is an analysis plan only; no scientific result has been computed. "
    "The system never recommends drilling or confirms a resource from a map alone, "
    "and any future confidence score requires a calibrated model and independent data."
)

UNKNOWN_AR = (
    "لم يتعرّف المخطّط على مجال علمي في الطلب، ولن يُصنع خطة GIS افتراضية. "
    "أعد صياغة الطلب بذكر أحد المجالات المدعومة أو أحد محركاتها."
)

UNKNOWN_EN = (
    "The planner did not recognise a scientific domain in the request, and no "
    "default GIS plan will be fabricated. Rephrase the request naming one of "
    "the supported domains or one of their engines."
)


class UnknownDomainError(ValueError):
    """Raised when no analysis domain matches the request.

    Honesty gate: the old behaviour silently produced a GIS plan for any
    input (e.g. "مرحبا"). Fabricating a plan is dishonest; refusing with a
    clear message is the correct foundation-phase behaviour."""

    def __init__(self, request_text: str, language: str = "ar") -> None:
        self.request_text = request_text
        self.language = language
        self.supported_domains: List[str] = list(SUPPORTED_DOMAINS)
        self.message = UNKNOWN_AR if language == "ar" else UNKNOWN_EN
        super().__init__(self.message)


def _prepare_intents() -> List[Dict]:
    """Bind each intent to its registry engines and precompute normalized
    keywords. Fails fast if an intent domain is missing from the registry."""
    engines_by_domain: Dict[str, List[str]] = {}
    for card in ENGINES:
        engines_by_domain.setdefault(card["domain"], []).append(card["engine_id"])
    prepared = []
    for index, intent in enumerate(INTENTS):
        domain = intent["domain"]
        if domain not in engines_by_domain:
            raise RuntimeError(
                f"planner intent domain {domain!r} is missing from the engine registry"
            )
        prepared.append({
            "index": index,
            "domain": domain,
            "required_inputs": list(intent["required_inputs"]),
            "keywords": list(intent["keywords"]),
            "norm_keywords": [normalize_text(k) for k in intent["keywords"]],
            "candidate_engines": sorted(engines_by_domain[domain]),
        })
    return prepared


PREPARED_INTENTS = _prepare_intents()
SUPPORTED_DOMAINS: List[str] = [p["domain"] for p in PREPARED_INTENTS]


def match_domains(text: str) -> List[Dict]:
    """Score every intent against the normalized text and apply precedence
    rules. Returns matches sorted by score desc, then by intent order."""
    norm = normalize_text(text)
    matches: List[Dict] = []
    for prepared in PREPARED_INTENTS:
        hits_norm = [nk for nk in prepared["norm_keywords"] if nk in norm]
        if not hits_norm:
            continue
        # Report the original (human-readable) keywords, compare in normalized space.
        hits = [
            prepared["keywords"][prepared["norm_keywords"].index(nk)]
            for nk in hits_norm
        ]
        matches.append({
            "index": prepared["index"],
            "domain": prepared["domain"],
            "matched_keywords": hits,            # original keywords (reporting)
            "matched_keywords_norm": hits_norm,  # canonical forms (rule comparisons)
            "score": len(hits_norm),
        })
    by_domain = {m["domain"]: m for m in matches}
    for rule in PRECEDENCE_RULES:
        weak = by_domain.get(rule["weak"])
        strong = by_domain.get(rule["strong"])
        if weak and strong and set(weak["matched_keywords_norm"]) <= rule["weak_generics"]:
            matches.remove(weak)
            del by_domain[rule["weak"]]
    matches.sort(key=lambda m: (-m["score"], m["index"]))
    return matches


def list_planner_domains() -> List[Dict]:
    """Supported analysis domains with registry-derived engine counts."""
    return [
        {
            "domain": p["domain"],
            "engine_count": len(p["candidate_engines"]),
            "candidate_engines": p["candidate_engines"],
            "required_inputs": p["required_inputs"],
        }
        for p in PREPARED_INTENTS
    ]


def build_plan(request: str, language: str = "ar",
               bbox: Optional[List[float]] = None) -> Dict:
    matches = match_domains(request)
    if not matches:
        raise UnknownDomainError(request, language)
    steps = []
    required: Set[str] = set()
    engines_by_domain = {p["domain"]: p for p in PREPARED_INTENTS}
    for m in matches:
        p = engines_by_domain[m["domain"]]
        steps.append({
            "domain": p["domain"],
            "candidate_engines": p["candidate_engines"],
            "required_inputs": p["required_inputs"],
            "matched_keywords": m["matched_keywords"],
            "engine_status": "planned",
        })
        required.update(p["required_inputs"])
    return {
        "plan_only": True,
        "no_results_computed": True,
        "planner_version": 2,
        "language": language,
        "aoi_bbox": bbox,
        "matched_domains": [s["domain"] for s in steps],
        "steps": steps,
        "required_inputs": sorted(required),
        "scientific_gates": GATES_AR if language == "ar" else GATES_EN,
        "disclaimer": DISCLAIMER_AR if language == "ar" else DISCLAIMER_EN,
    }

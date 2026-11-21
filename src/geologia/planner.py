# Deterministic analysis planner (foundation phase).
# Produces PLANS ONLY: no engine is executed and no scientific result is computed here.
from typing import Dict, List, Optional

INTENTS = [
    {
        "domain": "hydrology",
        "candidate_engines": ["modflow6", "pastas"],
        "required_inputs": ["well_logs", "water_levels_timeseries", "recharge_estimate",
                            "dem", "geology_map"],
        "keywords": ["مياه", "جوفية", "بئر", "آبار", "ضخ", "groundwater", "aquifer",
                     "well", "pumping"],
    },
    {
        "domain": "geology3d",
        "candidate_engines": ["gempy", "map2loop", "loopstructural"],
        "required_inputs": ["geology_map", "structural_orientations", "contacts",
                            "dem"],
        "keywords": ["ثلاثي", "قطاع", "بنية", "طيات", "فوالق", "3d", "cross-section",
                     "structural", "geological model"],
    },
    {
        "domain": "seismology",
        "candidate_engines": ["obspy", "openquake"],
        "required_inputs": ["waveforms_or_catalog", "station_metadata"],
        "keywords": ["زلزال", "زلازل", "موجات", "seismic", "earthquake", "waveform"],
    },
    {
        "domain": "exploration",
        "candidate_engines": ["eis-toolkit", "geopytool"],
        "required_inputs": ["geochemistry_samples", "geophysics_surveys", "geology_map"],
        "keywords": ["ذهب", "معدن", "تنقيب", "استكشاف", "gold", "mineral", "exploration"],
    },
    {
        "domain": "geochemistry",
        "candidate_engines": ["geochemistry-pi", "geopytool"],
        "required_inputs": ["geochemistry_samples", "sample_locations", "qc_report"],
        "keywords": ["جيوكيمي", "عناصر", "عينات", "geochem", "samples"],
    },
    {
        "domain": "remote_sensing",
        "candidate_engines": ["opendronemap"],
        "required_inputs": ["drone_images_or_satellite_scenes", "ground_control_points"],
        "keywords": ["درون", "استشعار", "قمر صناعي", "drone", "satellite", "remote sensing"],
    },
    {
        "domain": "gis",
        "candidate_engines": ["geopandas", "rasterio", "qgis"],
        "required_inputs": ["aoi_boundary", "data_layers", "crs_definition"],
        "keywords": ["خريطة", "طبقات", "gis", "map", "layers"],
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


def build_plan(request: str, language: str = "ar",
               bbox: Optional[List[float]] = None) -> Dict:
    text = request.lower()
    matched = [i for i in INTENTS if any(k in text for k in i["keywords"])]
    if not matched:
        matched = [i for i in INTENTS if i["domain"] == "gis"]
    steps = []
    required = set()
    for intent in matched:
        steps.append({
            "domain": intent["domain"],
            "candidate_engines": intent["candidate_engines"],
            "required_inputs": intent["required_inputs"],
            "engine_status": "planned",
        })
        required.update(intent["required_inputs"])
    return {
        "plan_only": True,
        "no_results_computed": True,
        "language": language,
        "aoi_bbox": bbox,
        "matched_domains": [s["domain"] for s in steps],
        "steps": steps,
        "required_inputs": sorted(required),
        "scientific_gates": GATES_AR if language == "ar" else GATES_EN,
        "disclaimer": DISCLAIMER_AR if language == "ar" else DISCLAIMER_EN,
    }

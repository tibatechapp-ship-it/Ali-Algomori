"""Auditable competency profiles for Ali Algomori specialist agents.

Profiles specify planning and validation requirements; they do not claim
neural training, scientific mastery, or engine execution.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

SKILL_SCHEMA_VERSION = "1.0.0"

_DOMAIN = {
    "well_logs": {
        "role": "well_log_specialist",
        "competencies": [
            "las_header_and_curve_inventory",
            "mnemonic_and_unit_review",
            "curve_quality_flags",
        ],
        "inputs": ["las_files", "well_header_metadata"],
        "outputs": ["curve_inventory", "quality_flags"],
        "checks": ["LAS format", "depth monotonicity", "units and null values"],
        "limit": "No petrophysical estimate without calibrated interpretation and required logs.",
    },
    "hydrology": {
        "role": "groundwater_specialist",
        "competencies": [
            "conceptual_model_decomposition",
            "water_level_timeseries_qc",
            "boundary_condition_inventory",
        ],
        "inputs": [
            "well_logs", "water_levels_timeseries", "recharge_estimate",
            "dem", "geology_map",
        ],
        "outputs": [
            "conceptual_model", "data_gap_register", "model_setup_specification",
        ],
        "checks": [
            "time and vertical datum", "units and pumping metadata",
            "boundary conditions",
        ],
        "limit": "No sustainable yield or drilling recommendation from incomplete observations.",
    },
    "geology3d": {
        "role": "geology3d_specialist",
        "competencies": [
            "geological_surface_inventory",
            "structural_orientation_qc",
            "contact_and_fault_constraints",
        ],
        "inputs": ["geology_map", "structural_orientations", "contacts", "dem"],
        "outputs": [
            "constraint_inventory", "model_readiness_report", "model_specification",
        ],
        "checks": ["CRS", "orientation convention", "constraint provenance"],
        "limit": "No 3D model claim until a registered engine executes and validates.",
    },
    "seismology": {
        "role": "seismology_specialist",
        "competencies": [
            "catalog_and_waveform_inventory",
            "station_metadata_qc",
            "time_system_review",
        ],
        "inputs": ["waveforms_or_catalog", "station_metadata"],
        "outputs": ["catalog_qc_report", "station_inventory", "analysis_readiness"],
        "checks": [
            "UTC/time-window consistency", "sampling and response metadata",
            "event provenance",
        ],
        "limit": "No hazard or event forecast claim from routing.",
    },
    "geophysics": {
        "role": "geophysics_specialist",
        "competencies": [
            "survey_geometry_review", "instrument_and_unit_qc", "inversion_readiness",
        ],
        "inputs": [
            "geophysical_survey_data", "survey_geometry", "topography",
            "crs_definition",
        ],
        "outputs": [
            "survey_qc_report", "geometry_checklist", "inversion_specification",
        ],
        "checks": [
            "sensor geometry", "units and sign conventions", "topography and CRS",
        ],
        "limit": "No inversion or interpretation without data and engine execution.",
    },
    "geochemistry": {
        "role": "geochemistry_specialist",
        "competencies": [
            "sample_and_assay_inventory",
            "detection_limit_handling",
            "quality_control_review",
        ],
        "inputs": ["geochemistry_samples", "sample_locations", "qc_report"],
        "outputs": ["sample_qc_report", "element_inventory", "analysis_readiness"],
        "checks": [
            "units and detection limits", "standards/blanks/duplicates",
            "sample provenance",
        ],
        "limit": "No grade or resource claim without QC and documented method.",
    },
    "exploration": {
        "role": "mineral_exploration_specialist",
        "competencies": [
            "evidence_layer_inventory", "targeting_criteria_definition",
            "multi_layer_readiness",
        ],
        "inputs": ["geochemistry_samples", "geophysics_surveys", "geology_map"],
        "outputs": ["evidence_matrix", "data_gap_register", "targeting_workflow_spec"],
        "checks": [
            "independent evidence layers", "spatial alignment",
            "bias and uncertainty",
        ],
        "limit": "No discovery or drilling target is confirmed by a planned workflow.",
    },
    "remote_sensing": {
        "role": "remote_sensing_specialist",
        "competencies": [
            "imagery_metadata_review", "ground_control_point_qc",
            "processing_chain_planning",
        ],
        "inputs": ["imagery", "ground_control_points"],
        "outputs": [
            "imagery_inventory", "control_point_qc", "processing_specification",
        ],
        "checks": [
            "sensor/acquisition metadata", "GCP CRS", "resolution and coverage",
        ],
        "limit": "No orthomosaic, DEM, or classification claim without validation.",
    },
    "gis": {
        "role": "gis_specialist",
        "competencies": [
            "vector_raster_inventory", "crs_and_unit_review",
            "spatial_integrity_review",
        ],
        "inputs": ["aoi_boundary", "data_layers", "crs_definition"],
        "outputs": ["layer_inventory", "spatial_qc_report", "workflow_specification"],
        "checks": [
            "CRS authority and axis order", "geometry validity", "extent and units",
        ],
        "limit": "Valid file structure is not proof of geospatial or scientific correctness.",
    },
}

_CROSS = {
    "data_integrity": [
        "content_hash_verification", "source_and_version_tracking",
    ],
    "crs_units": ["crs_identification", "unit_consistency_review"],
    "reproducibility": ["parameter_capture", "software_version_recording"],
    "uncertainty": ["uncertainty_source_inventory", "limitations_reporting"],
    "scientific_review": ["claim_evidence_linking", "independent_review_checklist"],
}

DOMAIN_SKILLS = {
    domain: {
        "specialist_role": item["role"],
        "competencies": item["competencies"],
        "required_inputs": item["inputs"],
        "outputs": item["outputs"],
        "verification": item["checks"],
        "safety_limits": [item["limit"]],
    }
    for domain, item in _DOMAIN.items()
}
CROSS_DOMAIN_SKILLS = _CROSS


def get_domain_skill_profile(domain: str) -> dict[str, Any]:
    """Return a defensive copy of the competency contract for one domain."""
    if domain not in DOMAIN_SKILLS:
        raise ValueError(f"unsupported skill domain: {domain}")
    return {
        "schema_version": SKILL_SCHEMA_VERSION,
        "domain": domain,
        "role_id": DOMAIN_SKILLS[domain]["specialist_role"],
        "competency_status": "planning_and_validation_specification_only",
        "model_training_claim": False,
        "engine_execution_claim": False,
        **deepcopy(DOMAIN_SKILLS[domain]),
    }


def assess_skill_readiness(
    domains: list[str], available_inputs: set[str] | None = None
) -> dict[str, Any]:
    """Report required competencies and input gaps without inferring mastery."""
    profiles = [get_domain_skill_profile(domain) for domain in domains]
    required = sorted({
        name for profile in profiles for name in profile["required_inputs"]
    })
    if available_inputs is None:
        status, present, missing = "not_assessed", None, None
    else:
        present = sorted(set(available_inputs) & set(required))
        missing = sorted(set(required) - set(available_inputs))
        status = "ready_for_validation" if not missing else "missing_required_inputs"
    return {
        "schema_version": SKILL_SCHEMA_VERSION,
        "readiness_status": status,
        "required_inputs": required,
        "available_required_inputs": present,
        "missing_required_inputs": missing,
        "domain_profiles": profiles,
        "cross_domain_skills": list(_CROSS),
        "training_status": "no_neural_training_performed",
        "scientific_execution_status": "not_executed",
        "mastery_status": "not_certified",
    }

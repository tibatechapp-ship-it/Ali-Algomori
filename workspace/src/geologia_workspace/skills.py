"""Auditable competency profiles for Ali Algomori's specialist agents.

Profiles specify planning and validation requirements; they do not claim
neural training, scientific mastery, or engine execution.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any

SKILL_SCHEMA_VERSION = "1.0.0"

# Each domain names observable work products and domain-specific QA gates.
_DOMAIN = {
 "well_logs": ("well_log_specialist", ["las_header_and_curve_inventory","mnemonic_and_unit_review","curve_quality_flags"], ["las_files","well_header_metadata"], ["curve_inventory","quality_flags"], ["LAS format","depth monotonicity","units and null values"], "No petrophysical estimate without calibrated interpretation and required logs."),
 "hydrology": ("groundwater_specialist", ["conceptual_model_decomposition","water_level_timeseries_qc","boundary_condition_inventory"], ["well_logs","water_levels_timeseries","recharge_estimate","dem","geology_map"], ["conceptual_model","data_gap_register","model_setup_specification"], ["time and vertical datum","units and pumping metadata","boundary conditions"], "No sustainable yield or drilling recommendation from incomplete observations."),
 "geology3d": ("geology3d_specialist", ["geological_surface_inventory","structural_orientation_qc","contact_and_fault_constraints"], ["geology_map","structural_orientations","contacts","dem"], ["constraint_inventory","model_readiness_report","model_specification"], ["CRS","orientation convention","constraint provenance"], "No 3D model claim until a registered engine executes and validates."),
 "seismology": ("seismology_specialist", ["catalog_and_waveform_inventory","station_metadata_qc","time_system_review"], ["waveforms_or_catalog","station_metadata"], ["catalog_qc_report","station_inventory","analysis_readiness"], ["UTC/time-window consistency","sampling and response metadata","event provenance"], "No hazard or event forecast claim from routing."),
 "geophysics": ("geophysics_specialist", ["survey_geometry_review","instrument_and_unit_qc","inversion_readiness"], ["geophysical_survey_data","survey_geometry","topography","crs_definition"], ["survey_qc_report","geometry_checklist","inversion_specification"], ["sensor geometry","units and sign conventions","topography and CRS"], "No inversion or subsurface interpretation without data and engine execution."),
 "geochemistry": ("geochemistry_specialist", ["sample_and_assay_inventory","detection_limit_handling","quality_control_review"], ["geochemistry_samples","sample_locations","qc_report"], ["sample_qc_report","element_inventory","analysis_readiness"], ["units and detection limits","standards/blanks/duplicates","sample provenance"], "No grade or resource claim without QC and documented method."),
 "exploration": ("mineral_exploration_specialist", ["evidence_layer_inventory","targeting_criteria_definition","multi_layer_readiness"], ["geochemistry_samples","geophysics_surveys","geology_map"], ["evidence_matrix","data_gap_register","targeting_workflow_spec"], ["independent evidence layers","spatial alignment","bias and uncertainty"], "No discovery or drilling target is confirmed by a planned workflow."),
 "remote_sensing": ("remote_sensing_specialist", ["imagery_metadata_review","ground_control_point_qc","processing_chain_planning"], ["imagery","ground_control_points"], ["imagery_inventory","control_point_qc","processing_specification"], ["sensor/acquisition metadata","GCP CRS","resolution and coverage"], "No orthomosaic, DEM, or classification claim without processing and validation."),
 "gis": ("gis_specialist", ["vector_raster_inventory","crs_and_unit_review","spatial_integrity_review"], ["aoi_boundary","data_layers","crs_definition"], ["layer_inventory","spatial_qc_report","workflow_specification"], ["CRS authority and axis order","geometry validity","extent and units"], "Valid file structure is not proof of geospatial or scientific correctness."),
}
_CROSS = {
 "data_integrity": ["content_hash_verification","source_and_version_tracking"],
 "crs_units": ["crs_identification","unit_consistency_review"],
 "reproducibility": ["parameter_capture","software_version_recording"],
 "uncertainty": ["uncertainty_source_inventory","limitations_reporting"],
 "scientific_review": ["claim_evidence_linking","independent_review_checklist"],
}

DOMAIN_SKILLS = {
 domain: {
  "specialist_role": values[0], "competencies": values[1],
  "required_inputs": values[2], "outputs": values[3],
  "verification": values[4], "safety_limits": [values[5]],
 }
 for domain, values in _DOMAIN.items()
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
    required = sorted({name for profile in profiles for name in profile["required_inputs"]})
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

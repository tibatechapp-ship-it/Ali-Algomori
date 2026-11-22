"""Versioned domain workflow playbooks for Ali's local specialist agents."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

WORKFLOW_SCHEMA_VERSION = "1.0.0"

# Step tuples: (id, objective, required inputs, acceptance checks, artifact).
# Templates guide task decomposition; they never claim to run the named method.
_TEMPLATES = {
    "well_logs": [
        (
            "inventory",
            "Inventory LAS files and curve headers",
            (
            "las_files",
        ),
            (
            "LAS parse succeeds",
            "curve mnemonics listed",
        ),
            "curve_inventory",
        ),
        (
            "curve_qc",
            "Review depth, null values, units, and curve quality",
            (
            "las_files",
            "well_header_metadata",
        ),
            (
            "depth ordering checked",
            "units and nulls documented",
        ),
            "curve_quality_report",
        ),
        (
            "method_design",
            "Specify petrophysical workflow only where inputs support it",
            (
            "well_header_metadata",
        ),
            (
            "calibration and required curves identified",
        ),
            "petrophysical_method_spec",
        ),
        (
            "verification",
            "Record checks, assumptions, and review needs",
            (
            "curve_quality_report",
        ),
            (
            "limitations and provenance recorded",
        ),
            "well_log_review_report",
        ),
    ],
    "hydrology": [
        (
            "conceptual_model",
            "Define aquifer layers, boundaries, and conceptual model",
            (
            "geology_map",
            "dem",
        ),
            (
            "boundary assumptions explicit",
        ),
            "hydrogeological_conceptual_model",
        ),
        (
            "timeseries_qc",
            "Check water levels, pumping history, and temporal coverage",
            (
            "water_levels_timeseries",
            "well_logs",
        ),
            (
            "time and vertical datum checked",
        ),
            "water_level_qc_report",
        ),
        (
            "model_design",
            "Specify recharge, boundary conditions, and model setup",
            (
            "recharge_estimate",
            "geology_map",
        ),
            (
            "parameters and units documented",
        ),
            "groundwater_model_spec",
        ),
        (
            "validation_plan",
            "Specify calibration, validation, and uncertainty checks",
            (
            "water_levels_timeseries",
        ),
            (
            "independent validation period identified",
        ),
            "groundwater_validation_plan",
        ),
    ],
    "geology3d": [
        (
            "constraint_inventory",
            "Inventory geological maps, contacts, and surfaces",
            (
            "geology_map",
            "contacts",
        ),
            (
            "source and scale recorded",
        ),
            "geological_constraint_inventory",
        ),
        (
            "structural_qc",
            "Review orientation conventions and structural measurements",
            (
            "structural_orientations",
        ),
            (
            "azimuth/dip convention and CRS checked",
        ),
            "structural_data_qc",
        ),
        (
            "model_design",
            "Specify surfaces, topology, and model boundaries",
            (
            "dem",
            "geology_map",
        ),
            (
            "constraints and assumptions traceable",
        ),
            "3d_model_specification",
        ),
        (
            "model_review",
            "Define geometric and independent geological checks",
            (
            "contacts",
            "structural_orientations",
        ),
            (
            "topology and uncertainty review planned",
        ),
            "3d_model_validation_plan",
        ),
    ],
    "seismology": [
        (
            "data_inventory",
            "Inventory event catalogues, waveforms, and stations",
            (
            "waveforms_or_catalog",
        ),
            (
            "event and waveform coverage recorded",
        ),
            "seismic_data_inventory",
        ),
        (
            "station_qc",
            "Check station coordinates, response, and sampling",
            (
            "station_metadata",
        ),
            (
            "time and instrument metadata checked",
        ),
            "station_metadata_qc",
        ),
        (
            "analysis_design",
            "Specify event or waveform analysis and method limits",
            (
            "waveforms_or_catalog",
            "station_metadata",
        ),
            (
            "method assumptions explicit",
        ),
            "seismic_analysis_spec",
        ),
        (
            "uncertainty_review",
            "Define uncertainty, provenance, and review requirements",
            (
            "waveforms_or_catalog",
        ),
            (
            "uncertainty disclosed; no forecast claim",
        ),
            "seismic_review_plan",
        ),
    ],
    "geophysics": [
        (
            "survey_inventory",
            "Inventory survey data, instruments, and geometry",
            (
            "geophysical_survey_data",
            "survey_geometry",
        ),
            (
            "survey coverage and instrument metadata recorded",
        ),
            "survey_inventory",
        ),
        (
            "geometry_qc",
            "Check sensor geometry, topography, CRS, and units",
            (
            "survey_geometry",
            "topography",
            "crs_definition",
        ),
            (
            "geometry and units pass documented checks",
        ),
            "survey_geometry_qc",
        ),
        (
            "method_design",
            "Specify forward or inversion method and parameters",
            (
            "geophysical_survey_data",
        ),
            (
            "method and regularization assumptions recorded",
        ),
            "geophysical_method_spec",
        ),
        (
            "fit_review",
            "Define residual, sensitivity, and independent review checks",
            (
            "geophysical_survey_data",
        ),
            (
            "fit criteria and limitations explicit",
        ),
            "geophysical_validation_plan",
        ),
    ],
    "geochemistry": [
        (
            "sample_inventory",
            "Inventory assays, sample IDs, and analytical methods",
            (
            "geochemistry_samples",
        ),
            (
            "sample identity and units preserved",
        ),
            "geochemical_sample_inventory",
        ),
        (
            "qa_qc",
            "Review blanks, standards, duplicates, and detection limits",
            (
            "qc_report",
        ),
            (
            "QA/QC acceptance criteria recorded",
        ),
            "geochemical_qa_qc_report",
        ),
        (
            "analysis_design",
            "Specify transformations and statistical analysis",
            (
            "geochemistry_samples",
        ),
            (
            "censored values and assumptions handled",
        ),
            "geochemical_analysis_spec",
        ),
        (
            "spatial_review",
            "Define spatial checks and evidence-backed interpretation",
            (
            "sample_locations",
        ),
            (
            "coordinate provenance and uncertainty recorded",
        ),
            "geochemical_spatial_review",
        ),
    ],
    "exploration": [
        (
            "evidence_inventory",
            "Inventory geology, geochemistry, and geophysics evidence",
            (
            "geology_map",
            "geochemistry_samples",
            "geophysics_surveys",
        ),
            (
            "each layer has provenance and quality",
        ),
            "exploration_evidence_matrix",
        ),
        (
            "spatial_alignment",
            "Check CRS, extent, resolution, and sample bias",
            (
            "geology_map",
        ),
            (
            "layers align; coverage gaps reported",
        ),
            "exploration_spatial_qc",
        ),
        (
            "targeting_design",
            "Specify criteria and evidence combination method",
            (
            "geochemistry_samples",
            "geophysics_surveys",
        ),
            (
            "weights and assumptions documented",
        ),
            "prospectivity_workflow_spec",
        ),
        (
            "validation_plan",
            "Define independent validation and uncertainty review",
            (
            "geology_map",
        ),
            (
            "no target declared without validation",
        ),
            "exploration_validation_plan",
        ),
    ],
    "remote_sensing": [
        (
            "imagery_inventory",
            "Inventory imagery, sensor, acquisition, and coverage",
            (
            "imagery",
        ),
            (
            "metadata and image coverage recorded",
        ),
            "imagery_inventory",
        ),
        (
            "control_point_qc",
            "Check ground control points and coordinate reference",
            (
            "ground_control_points",
        ),
            (
            "GCP CRS and residual checks specified",
        ),
            "gcp_quality_report",
        ),
        (
            "processing_design",
            "Specify photogrammetry or image processing stages",
            (
            "imagery",
            "ground_control_points",
        ),
            (
            "settings and versions recorded",
        ),
            "remote_sensing_workflow_spec",
        ),
        (
            "accuracy_review",
            "Define independent accuracy and artifact validation",
            (
            "ground_control_points",
        ),
            (
            "independent checkpoints separated from GCPs",
        ),
            "remote_sensing_validation_plan",
        ),
    ],
    "gis": [
        (
            "layer_inventory",
            "Inventory AOI, vector, raster, and attribute layers",
            (
            "aoi_boundary",
            "data_layers",
        ),
            (
            "formats and coverage recorded",
        ),
            "gis_layer_inventory",
        ),
        (
            "spatial_qc",
            "Check CRS, units, geometry validity, and extents",
            (
            "crs_definition",
            "data_layers",
        ),
            (
            "axis order and geometry errors reported",
        ),
            "gis_spatial_qc_report",
        ),
        (
            "analysis_design",
            "Specify overlay, spatial query, or cartographic workflow",
            (
            "aoi_boundary",
            "data_layers",
        ),
            (
            "operations and parameters reproducible",
        ),
            "gis_workflow_spec",
        ),
        (
            "map_review",
            "Define output integrity, provenance, and map review",
            (
            "data_layers",
        ),
            (
            "legend, scale, CRS, and sources documented",
        ),
            "gis_output_review_plan",
        ),
    ],
}



def get_domain_workflow(domain: str) -> dict[str, Any]:
    """Return a safe copy of a domain workflow with non-executed step states."""
    if domain not in _TEMPLATES:
        raise ValueError(f"unsupported workflow domain: {domain}")
    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "domain": domain,
        "workflow_status": "planned_not_executed",
        "steps": [
            {
                "step_id": step_id,
                "objective": objective,
                "required_inputs": list(inputs),
                "acceptance_checks": list(checks),
                "expected_artifact": artifact,
                "status": "not_started",
                "execution": "not_started",
            }
            for step_id, objective, inputs, checks, artifact in _TEMPLATES[domain]
        ],
    }


def supported_workflow_domains() -> list[str]:
    return sorted(_TEMPLATES)

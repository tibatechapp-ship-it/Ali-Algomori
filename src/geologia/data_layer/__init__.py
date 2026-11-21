# GEOLOGIA data layer: trusted dataset registry + task ledger with gates.
from geologia.data_layer.records import (
    get_dataset,
    list_datasets,
    register_dataset,
    validate_dataset,
    verify_checksum,
)
from geologia.data_layer.tasks import (
    TaskGateError,
    create_task,
    get_task,
    list_tasks,
    transition,
)
from geologia.data_layer.reception import (
    check_upload,
    sanitize_filename,
    scan_archive,
    scan_tiff_metadata,
    sniff_content,
    strip_tiff_auxiliary_tags,
)
from geologia.data_layer.validators import validate_file
from geologia.data_layer.evidence import (
    compile_evidence,
    ev_read,
    ev_unverifiable,
    ev_verified,
    prove_file,
)
from geologia.data_layer.readers import (
    capabilities,
    parse_geokeys,
    read_geopackage,
    read_geotiff,
    read_las,
)
from geologia.data_layer.provenance import (
    ProvenanceLog,
    default_log_path,
    ref_file,
    tool_versions,
)
from geologia.data_layer.reference import (
    load_transformations,
    transformations_fingerprint,
    verify_reference_dir,
    verify_transformations,
)
from geologia.data_layer.vertical import (
    classify_vertical_geokeys,
    vertical_findings,
)
from geologia.data_layer.uploads import ingest_bytes, ingest_stream
from geologia.data_layer.transforms_math import (
    pseudo_mercator,
    inverse_pseudo_mercator,
    verify_frozen_equation_points,
)

__all__ = [
    "register_dataset", "list_datasets", "get_dataset", "validate_dataset",
    "verify_checksum", "validate_file", "create_task", "list_tasks",
    "get_task", "transition", "TaskGateError",
    "check_upload", "sanitize_filename", "scan_archive",
    "scan_tiff_metadata", "sniff_content", "strip_tiff_auxiliary_tags",
    # v0.6.0: proof layer — what was read, what was verified, what cannot
    # be confirmed; real readers; provenance; frozen references.
    "compile_evidence", "ev_read", "ev_verified", "ev_unverifiable",
    "prove_file", "capabilities", "parse_geokeys", "read_las",
    "read_geotiff", "read_geopackage", "ProvenanceLog", "tool_versions",
    "ref_file", "default_log_path", "load_transformations",
    "verify_transformations", "verify_reference_dir",
    "transformations_fingerprint", "classify_vertical_geokeys",
    "vertical_findings",
    # v0.7.0: HTTP upload ingestion (library-level, no HTTP concepts) +
    # engine-independent EPSG:3857 verification from published equations.
    "ingest_bytes", "ingest_stream", "pseudo_mercator",
    "inverse_pseudo_mercator", "verify_frozen_equation_points",
]

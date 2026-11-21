# First-party scientific engines.
#
# EXECUTORS is the only dispatch table from engine_id to a run function.
# An engine may appear here ONLY if it is:
#   - first-party (this repository, stdlib-only, deterministic),
#   - covered by a pinned reference test (src/geologia/data/reference/),
#   - therefore certifiable via geologia.data_layer.certification.certify_engine.
# Third-party tools (GemPy, MODFLOW 6, ...) are NOT here and cannot be certified
# until they pass the sandboxed -> integrated -> certified lifecycle per the
# integration policy. This is the structural lock demanded by the owner.
from geologia.engines.porosity_density import run_porosity_density

EXECUTORS = {
    "porosity_density_v1": run_porosity_density,
}


def get_executor(engine_id: str):
    return EXECUTORS.get(engine_id)

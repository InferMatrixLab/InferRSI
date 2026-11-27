"""Compose the frozen B projection only when H invokes fresh evidence capture."""

from copy import deepcopy

from ...harness.api import PublicError
from ..storage.archive import read_prepared
from ..storage.artifact_reader import ArtifactReader
from .evidence_capture import EvidenceCapture


class PreparedCapture:
    """Trusted host adapter; constructing it performs no task or artifact reads."""

    def __init__(self, storage_config: dict):
        self._storage = deepcopy(storage_config)

    def capture(self, phase, facts, *, artifacts):
        # H never invokes this callback for registered replay/conflict/in-progress.
        from ...benchmark.proofs import ProofError, ProofProjector

        prepared = read_prepared(self._storage, facts["prepared_ref"])
        reader = ArtifactReader(self._storage)
        with reader.open(prepared["protocol"]) as stream:
            protocol = stream.read()
        try:
            projector = ProofProjector(prepared, protocol)
            # B's supported P1 validator fixes the single-output recipe. Apps
            # takes role names from that validated metadata, not task names.
            adapter = EvidenceCapture(
                projector.project,
                candidate_role=prepared["candidate_contract"]["input_role"],
                report_role=prepared["recipe"]["outputs"][0]["role"],
            )
            return adapter.capture(phase, facts, artifacts=artifacts)
        except ProofError as error:
            raise PublicError(error.code, stage="evidence_capture", message=str(error)) from error

from __future__ import annotations

from collections import deque


class FakeRepository:
    def __init__(self):
        self.artifacts = {}
        self.files = []
        self.edges = []
        self.releases = {}
        self.release_members = []
        self.gates = []
        self.gate_evaluations = {}
        self.waivers = []
        self.promotion_decisions = []
        self.approval_items = []
        self.audits = []
        self.runs = {}
        self.stage_runs = {}

    def get_artifact(self, artifact_id):
        return self.artifacts.get(artifact_id)

    def get_artifact_by_manifest_hash(self, sha256):
        return next(
            (x for x in self.artifacts.values() if x.manifest_sha256 == sha256), None
        )

    def list_artifact_ids(self):
        return set(self.artifacts)

    def add_artifact(self, record):
        self.artifacts[record.id] = record

    def add_artifact_file(self, record):
        self.files.append(record)

    def add_lineage_edge(self, edge):
        if any(
            x.parent_artifact_id == edge.parent_artifact_id
            and x.child_artifact_id == edge.child_artifact_id
            and x.relationship_type == edge.relationship_type
            for x in self.edges
        ):
            return
        self.edges.append(edge)

    def _walk(self, artifact_id, forward):
        result = set()
        queue = deque([artifact_id])
        while queue:
            current = queue.popleft()
            for edge in self.edges:
                source = edge.parent_artifact_id if forward else edge.child_artifact_id
                target = edge.child_artifact_id if forward else edge.parent_artifact_id
                if source == current and target not in result:
                    result.add(target)
                    queue.append(target)
        result.discard(artifact_id)
        return result

    def descendants(self, artifact_id):
        return self._walk(artifact_id, True)

    def ancestors(self, artifact_id):
        return self._walk(artifact_id, False)

    def get_release(self, release_id):
        return self.releases.get(release_id)

    def add_release(self, record):
        self.releases[record.id] = record

    def add_release_artifact(self, record):
        self.release_members.append(record)

    def release_artifact_ids(self, release_id):
        return {
            x.artifact_id for x in self.release_members if x.release_id == release_id
        }

    def blocking_gates(self, scope_type, scope_id):
        return [
            x
            for x in self.gates
            if x.scope_type == scope_type and x.scope_id == scope_id and x.blocking
        ]

    def get_gate_result(self, gate_id, scope_type, scope_id):
        return next(
            (
                x
                for x in self.gates
                if x.gate_id == gate_id
                and x.scope_type == scope_type
                and x.scope_id == scope_id
            ),
            None,
        )

    def get_gate_result_by_id(self, gate_result_id):
        return next((x for x in self.gates if x.id == gate_result_id), None)

    def add_gate_result(self, record):
        self.gates.append(record)

    def get_gate_evaluation(self, evaluation_id):
        return self.gate_evaluations.get(evaluation_id)

    def get_gate_evaluation_by_key(self, key):
        return next(
            (x for x in self.gate_evaluations.values() if x.evaluation_key == key),
            None,
        )

    def list_gate_evaluations(self, gate_id, scope_type, scope_id):
        return [
            x
            for x in self.gate_evaluations.values()
            if x.gate_id == gate_id
            and x.scope_type == scope_type
            and x.scope_id == scope_id
        ]

    def add_gate_evaluation(self, record):
        self.gate_evaluations[record.id] = record

    def get_gate_waiver(self, waiver_id):
        return next((x for x in self.waivers if x.id == waiver_id), None)

    def get_gate_waiver_by_request_key(self, key):
        return next((x for x in self.waivers if x.request_key == key), None)

    def active_gate_waiver(self, gate_result_id, evaluation_id):
        return next(
            (
                x
                for x in reversed(self.waivers)
                if x.gate_result_id == gate_result_id
                and x.evaluation_id == evaluation_id
                and x.status == "ACTIVE"
            ),
            None,
        )

    def list_gate_waivers(self, *, scope_type=None, scope_id=None):
        return [
            x
            for x in self.waivers
            if (scope_type is None or x.scope_type == scope_type)
            and (scope_id is None or x.scope_id == scope_id)
        ]

    def add_gate_waiver(self, record):
        self.waivers.append(record)

    def get_promotion_decision(self, decision_id):
        return next((x for x in self.promotion_decisions if x.id == decision_id), None)

    def get_promotion_decision_by_key(self, key):
        return next(
            (x for x in self.promotion_decisions if x.idempotency_key == key), None
        )

    def list_promotion_decisions(self, *, target_type=None, target_id=None):
        return [
            x
            for x in self.promotion_decisions
            if (target_type is None or x.target_type == target_type)
            and (target_id is None or x.target_id == target_id)
        ]

    def add_promotion_decision(self, record):
        self.promotion_decisions.append(record)

    def approvals(self, target_type, target_id):
        return [
            x
            for x in self.approval_items
            if x.target_type == target_type and x.target_id == target_id
        ]

    def get_approval(self, approval_id):
        return next((x for x in self.approval_items if x.id == approval_id), None)

    def get_approval_by_request_key(self, request_key):
        return next(
            (x for x in self.approval_items if x.request_key == request_key), None
        )

    def list_approvals(self, *, status=None, pipeline_run_id=None):
        return [
            x
            for x in self.approval_items
            if (status is None or x.status == status)
            and (pipeline_run_id is None or x.pipeline_run_id == pipeline_run_id)
        ]

    def add_approval(self, record):
        self.approval_items.append(record)

    def get_pipeline_run(self, run_id):
        return self.runs.get(run_id)

    def get_stage_run(self, stage_run_id):
        return self.stage_runs.get(stage_run_id)

    def artifacts_for_stage_run(self, stage_run_id):
        return {
            x.id
            for x in self.artifacts.values()
            if x.producer_stage_run_id == stage_run_id
        }

    def succeeded_stage_runs_without_artifacts(self):
        return {
            x.id
            for x in self.stage_runs.values()
            if x.status == "SUCCEEDED" and not self.artifacts_for_stage_run(x.id)
        }

    def add_audit_event(self, record):
        self.audits.append(record)

    def flush(self):
        pass

"""Frozen D023/P1 preparations over a Benchmark-owned task and byte capability.

The host configures the frozen task and a role-keyed read-only resource opener.
PrepareRequest cannot supply task rules, worker code or a filesystem authority.
Preparation neither executes the worker nor persists a preparation or its bytes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import closing
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import PurePosixPath

from ..contracts.json_v1 import CanonicalError
from ..contracts.json_v1 import decode as canonical_decode
from ..contracts.json_v1 import encode as canonical_encode

_REQUEST = set("schema_version task operation validation_scope input_pins task_parameters "
               "comparison_conditions expected_candidate budget_policy_refs".split())
_PROTOCOL = set("schema_version task grader operation validation_scope candidate_contract "
                "worker_recipe input_requirements claim_definitions metric_definitions "
                "required_evidence task_parameters baseline reference quality_reference "
                "sampling feedback_visibility budget_policy_refs resources display_notes".split())
_PREPARED = set("schema_version prepared_id task grader operation validation_scope protocol "
                "protocol_digest candidate_contract expected_candidate required_evidence "
                "recipe resources created_at display_notes".split())
_COPIES = ("task", "grader", "operation", "validation_scope", "candidate_contract",
           "required_evidence")
_RESOURCE = {"role", "artifact", "format_schema", "required_for"}
_ARTIFACT = {"location", "sha256", "size_bytes", "media_type"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,255}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_DECIMAL = re.compile(r"(?:0|-?[1-9][0-9]*|-?(?:0|[1-9][0-9]*)\.[0-9]*[1-9])\Z")
_CANDIDATE = {
    "kind": "text", "input_role": "candidate",
    "format_schema": {"name": "utf8-text", "revision": "1"},
    "identity_rule": {"name": "captured-sha256", "revision": "1"},
    "entrypoint": None, "required_paths": [], "allowed_content": {},
    "modification_receipt_required": False,
}


class PreparationError(ValueError):
    """A Benchmark-owned rejection, with the portable PublicError wire form."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def to_json(self) -> dict:
        return {
            "code": self.code, "stage": "prepare", "attempt_id": None, "started": None,
            "latest_record_ref": None, "partial_record": None, "retained_refs": [],
            "field_errors": [], "message": str(self),
        }


def _require(condition, message: str, code: str = "InvalidRequest") -> None:
    if not condition:
        raise PreparationError(code, message)


def _object(value, fields) -> None:
    _require(isinstance(value, dict) and value.keys() == fields, "Unexpected object fields.")


def _id(value) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _definition(value) -> None:
    _object(value, {"name", "revision"})
    _require(all(_id(item) for item in value.values()), "Invalid definition reference.")


def _artifact(value) -> None:
    _object(value, _ARTIFACT)
    location = value["location"]
    _require(isinstance(location, str) and bool(location) and "\\" not in location
             and ":" not in location and not location.startswith("/")
             and all(part not in ("", ".", "..") for part in location.split("/"))
             and str(PurePosixPath(location)) == location, "Invalid logical artifact location.")
    _require(isinstance(value["sha256"], str) and _SHA.fullmatch(value["sha256"]) is not None
             and type(value["size_bytes"]) is int and value["size_bytes"] >= 0
             and isinstance(value["media_type"], str) and bool(value["media_type"]),
             "Invalid artifact metadata.")


def _resource(value) -> None:
    _object(value, _RESOURCE)
    _require(_id(value["role"]), "Invalid resource role.")
    _artifact(value["artifact"])
    _definition(value["format_schema"])
    uses = value["required_for"]
    _require(isinstance(uses, list) and bool(uses)
             and all(isinstance(use, str) for use in uses)
             and len(uses) == len(set(uses)) and set(uses) <= {"prepare", "execute", "assess"},
             "Invalid resource use.")


def _closure(protocol: dict) -> list[dict]:
    _require(isinstance(protocol["resources"], list), "Expected protocol resources.")
    values = list(protocol["resources"])
    values += [protocol[key] for key in ("baseline", "reference", "quality_reference")
               if protocol[key] is not None]
    for value in values:
        _resource(value)
    roles = [value["role"] for value in values]
    _require(len(roles) == len(set(roles)), "Resource roles must be unique across the closure.")
    return sorted(values, key=lambda value: value["role"])


def _project_resource(value: dict) -> dict:
    _resource(value)
    return {**value, "artifact": {key: item for key, item in value["artifact"].items()
                                 if key != "location"}}


def protocol_digest(protocol: dict) -> str:
    """Project declared ArtifactRefs only; ref-shaped Parameters stay semantic."""
    _object(protocol, _PROTOCOL)
    value = deepcopy(protocol)
    value.pop("display_notes")
    value["resources"] = [_project_resource(item) for item in value["resources"]]
    for key in ("baseline", "reference", "quality_reference"):
        if value[key] is not None:
            value[key] = _project_resource(value[key])
    return "sha256:" + sha256(canonical_encode(value)).hexdigest()


def prepared_id(prepared: dict) -> str:
    """Compute identity independently of outer locators, clock and display notes."""
    _object(prepared, _PREPARED)
    value = deepcopy(prepared)
    for key in ("prepared_id", "created_at", "display_notes"):
        value.pop(key)
    _artifact(value["protocol"])
    value["protocol"].pop("location")
    value["resources"] = [_project_resource(item) for item in value["resources"]]
    return "sha256:" + sha256(canonical_encode(value)).hexdigest()


def _parameters(value) -> None:
    _object(value, {"decimal_fixture", "label"})
    _require(isinstance(value["decimal_fixture"], str)
             and _DECIMAL.fullmatch(value["decimal_fixture"]) is not None
             and isinstance(value["label"], str), "Invalid P1 task parameters.")


def _candidate(value) -> None:
    _require(canonical_encode(value) == canonical_encode(_CANDIDATE),
             "Unsupported P1 candidate contract.", "UnsupportedRuleVersion")


def _recipe(recipe) -> None:
    _object(recipe, set("recipe_revision runtime_role entrypoint_kind entrypoint "
                        "entrypoint_revision code_sha256 args input_roles outputs "
                        "required_capabilities".split()))
    fixed = {"recipe_revision": "1", "runtime_role": "local-python",
             "entrypoint_kind": "python_module", "entrypoint": "fixture_worker",
             "entrypoint_revision": "1"}
    _require(all(recipe[key] == value for key, value in fixed.items()),
             "Unsupported frozen P1 worker revision.", "UnsupportedRuleVersion")
    _require(isinstance(recipe["code_sha256"], str)
             and _SHA.fullmatch(recipe["code_sha256"]) is not None,
             "Invalid frozen worker digest.")
    for key in ("args", "input_roles", "required_capabilities"):
        _require(isinstance(recipe[key], list)
                 and all(isinstance(item, str) and item for item in recipe[key]),
                 "Invalid worker arguments or roles.")
    _require(recipe["input_roles"] == ["candidate"]
             and recipe["args"] == ["{input:candidate}", "{output:grader}"]
             and recipe["required_capabilities"] == ["local-process-tree"],
             "Unsupported P1 worker recipe.", "UnsupportedRuleVersion")
    _require(recipe["outputs"] == [{
        "role": "grader", "path": "outputs/grader.json", "media_type": "application/json",
        "format_schema": {"name": "fixture-grader", "revision": "1"}, "required": True,
    }] and type(recipe["outputs"][0]["required"]) is bool,
        "Unsupported P1 worker output.", "UnsupportedRuleVersion")


def _requirements(requirements) -> None:
    _require(isinstance(requirements, list) and len(requirements) == 4,
             "Expected the P1 evidence requirements.")
    expected = {
        "format": ("F", "preparing", {"harness_capture"}),
        "grader": ("C", "finalizing", {"task_worker"}),
        "samples": ("M", "running", {"harness_capture", "task_worker"}),
        "cleanup": ("M", "finalizing", {"harness_capture"}),
    }
    for item in requirements:
        _object(item, set("check_id checker_revision allowed_producer_kinds subject phase "
                          "artifact_schema matching_rule_revision allowed_control_domains "
                          "for_claims".split()))
        key = item["check_id"]
        _require(isinstance(key, str) and key in expected, "Unsupported P1 check.",
                 "UnsupportedRuleVersion")
        claim, phase, producers = expected.pop(key)
        kinds, domains = item["allowed_producer_kinds"], item["allowed_control_domains"]
        _require(isinstance(kinds, list) and all(_id(kind) for kind in kinds)
                 and len(kinds) == len(set(kinds)) and set(kinds) == producers
                 and isinstance(domains, list) and bool(domains)
                 and all(_id(domain) for domain in domains)
                 and len(domains) == len(set(domains))
                 and item["checker_revision"] == item["matching_rule_revision"] == "1"
                 and item["subject"] == "candidate" and item["phase"] == phase
                 and item["for_claims"] == [claim]
                 and item["artifact_schema"] == {"name": key + "-proof", "revision": "1"},
                 "Unsupported frozen P1 evidence rule.", "UnsupportedRuleVersion")


def _protocol(protocol: dict) -> None:
    canonical_encode(protocol)
    _object(protocol, _PROTOCOL)
    _require(type(protocol["schema_version"]) is int and protocol["schema_version"] == 1,
             "Unsupported protocol version.", "UnsupportedSchema")
    _require(protocol["task"] == {"name": "p1-fixture", "revision": "1"}
             and protocol["grader"] == {"name": "p1-rules", "revision": "1"},
             "Only the accepted P1 task and grader revision are supported.",
             "UnsupportedRuleVersion")
    _require(protocol["operation"] == "evaluate" and protocol["validation_scope"] == "p1",
             "Unsupported task operation or scope.", "UnsupportedOperation")
    _parameters(protocol["task_parameters"])
    _closure(protocol)
    _candidate(protocol["candidate_contract"])
    _recipe(protocol["worker_recipe"])
    _requirements(protocol["required_evidence"])
    _require(protocol["input_requirements"] == {"candidate_role": "candidate"}
             and protocol["metric_definitions"] == []
             and protocol["sampling"] == {"order": ["AB", "BA"], "repetitions": 2}
             and type(protocol["sampling"]["repetitions"]) is int
             and protocol["feedback_visibility"] == ["format"]
             and isinstance(protocol["display_notes"], str),
             "Unsupported P1 protocol conditions.", "UnsupportedRuleVersion")
    claims = protocol["claim_definitions"]
    _require(isinstance(claims, list) and len(claims) == 3, "Expected the P1 claim registry.")
    expected = {"F": ["format"], "C": ["grader"], "M": ["samples", "cleanup"]}
    for claim in claims:
        _object(claim, {"claim_id", "validation_scope", "decision_rule", "required_checks",
                        "requires_completed_measurement", "requires_cleanup_confirmed"})
        key = claim["claim_id"]
        _require(isinstance(key, str) and key in expected
                 and claim["decision_rule"] == {"name": "p1-" + key, "revision": "1"}
                 and claim["validation_scope"] == "p1"
                 and claim["required_checks"] == expected.pop(key)
                 and type(claim["requires_completed_measurement"]) is bool
                 and type(claim["requires_cleanup_confirmed"]) is bool
                 and claim["requires_completed_measurement"] == (key == "M")
                 and claim["requires_cleanup_confirmed"] == (key == "M"),
                 "Unsupported frozen P1 claim rule.", "UnsupportedRuleVersion")
    _require(isinstance(protocol["budget_policy_refs"], list), "Expected budget references.")
    for ref in protocol["budget_policy_refs"]:
        _definition(ref)


def _expectation(candidate, contract: dict) -> None:
    if candidate is None:
        return
    _object(candidate, {"candidate_id", "sha256", "format_schema"})
    _require(_id(candidate["candidate_id"]) and isinstance(candidate["sha256"], str)
             and _SHA.fullmatch(candidate["sha256"]) is not None,
             "Invalid expected candidate.")
    _definition(candidate["format_schema"])
    _require(candidate["format_schema"] == contract["format_schema"],
             "Expected candidate format differs from the frozen contract.")


def _prepared(prepared: dict) -> None:
    canonical_encode(prepared)
    _object(prepared, _PREPARED)
    _require(type(prepared["schema_version"]) is int and prepared["schema_version"] == 1,
             "Unsupported prepared version.", "UnsupportedSchema")
    _artifact(prepared["protocol"])
    _candidate(prepared["candidate_contract"])
    _recipe(prepared["recipe"])
    _requirements(prepared["required_evidence"])
    _require(prepared["task"] == {"name": "p1-fixture", "revision": "1"}
             and prepared["grader"] == {"name": "p1-rules", "revision": "1"}
             and prepared["operation"] == "evaluate" and prepared["validation_scope"] == "p1",
             "Unsupported prepared task revision or scope.", "UnsupportedRuleVersion")
    _require(isinstance(prepared["display_notes"], str)
             and isinstance(prepared["protocol_digest"], str)
             and re.fullmatch(r"sha256:[a-f0-9]{64}", prepared["protocol_digest"]) is not None,
             "Invalid preparation metadata.")
    timestamp = prepared["created_at"]
    if timestamp is not None:
        _require(isinstance(timestamp, str)
                 and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z",
                                  timestamp) is not None,
                 "Invalid preparation timestamp.")
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            raise PreparationError("InvalidRequest", "Invalid preparation timestamp.") from None
    _require(isinstance(prepared["resources"], list), "Expected prepared resources.")
    for resource in prepared["resources"]:
        _resource(resource)
    roles = [resource["role"] for resource in prepared["resources"]]
    _require(roles == sorted(set(roles)), "Prepared closure must be sorted by unique role.")
    _expectation(prepared["expected_candidate"], prepared["candidate_contract"])
    _require(prepared["prepared_id"] == prepared_id(prepared),
             "Prepared identity does not match its content.", "IdentityMismatch")


def encode(prepared: dict) -> bytes:
    """Pure prepared encoding, including its self-identity check."""
    _prepared(prepared)
    return canonical_encode(prepared)


def decode(data: bytes) -> dict:
    """Decode canonical prepared bytes without resolving or opening any artifact."""
    value = canonical_decode(data)
    _require(canonical_encode(value) == data, "Prepared bytes are not canonical.")
    _prepared(value)
    return value


def validate_prepared(prepared: dict, protocol_bytes: bytes) -> None:
    """Pure validation of the full prepared/protocol identity and closure binding."""
    _prepared(prepared)
    protocol = canonical_decode(protocol_bytes)
    _require(canonical_encode(protocol) == protocol_bytes, "Protocol bytes are not canonical.")
    _protocol(protocol)
    ref = prepared["protocol"]
    _require(ref["sha256"] == sha256(protocol_bytes).hexdigest()
             and ref["size_bytes"] == len(protocol_bytes)
             and ref["media_type"] == "application/json"
             and prepared["protocol_digest"] == protocol_digest(protocol)
             and all(prepared[key] == protocol[key] for key in _COPIES)
             and prepared["recipe"] == protocol["worker_recipe"]
             and [_project_resource(item) for item in prepared["resources"]]
             == [_project_resource(item) for item in _closure(protocol)],
             "Prepared object disagrees with its frozen protocol.", "IdentityMismatch")


def _verify_resource(source, ref: dict) -> None:
    if source is None:
        raise FileNotFoundError("A required resource is unavailable.")
    expected_size = ref["size_bytes"]
    digest = sha256()
    if isinstance(source, bytes):
        size = len(source)
        if size == expected_size:
            digest.update(source)
    else:
        size = 0
        with closing(source):
            while True:
                chunk = source.read(min(1024 * 1024, expected_size - size + 1))
                if not isinstance(chunk, bytes):
                    raise TypeError("A host resource capability must return binary bytes.")
                size += len(chunk)
                if not chunk or size > expected_size:
                    break
                digest.update(chunk)
    _require(size == expected_size and digest.hexdigest() == ref["sha256"],
             "Resource bytes disagree with their fixed metadata.", "ArtifactIntegrityError")


class PreparationService:
    """The supported P1 prepare port bound to frozen rules and read capabilities.

    ``worker_role`` identifies the retained code bytes for recipe.code_sha256.
    Preparation closes every stream it opens for verification. After prepare,
    the consumer of the returned resource reader owns each stream it opens.
    The returned closure reopens resources: deletion fails at the Apps archive
    boundary and changed bytes are independently rejected by Apps' verifier.
    """

    def __init__(self, protocol: dict, *, resources: Callable, worker_role: str):
        _protocol(protocol)
        _require(callable(resources) and _id(worker_role), "Invalid resource capability.")
        closure = {item["role"]: item for item in _closure(protocol)}
        _require(worker_role in closure and closure[worker_role]["artifact"]["sha256"]
                 == protocol["worker_recipe"]["code_sha256"],
                 "The worker recipe must bind retained code bytes.", "IdentityMismatch")
        self._frozen = canonical_encode(protocol)
        self._resources = resources

    def prepare(self, request: dict) -> tuple | dict:
        """Return the prepared object, frozen protocol bytes and read-only closure."""
        try:
            canonical_encode(request)
        except CanonicalError:
            return PreparationError("InvalidRequest", "Malformed prepare request.").to_json()
        try:
            return self._prepare(request)
        except PreparationError as error:
            return error.to_json()

    def _prepare(self, request: dict) -> tuple:
        _object(request, _REQUEST)
        _require(type(request["schema_version"]) is int and request["schema_version"] == 1,
                 "Unsupported request version.", "UnsupportedSchema")
        protocol = canonical_decode(self._frozen)
        _require(request["task"] == protocol["task"], "Unsupported task revision.",
                 "UnsupportedRuleVersion")
        _require(request["operation"] == protocol["operation"]
                 and request["validation_scope"] == protocol["validation_scope"],
                 "Unsupported operation or scope.", "UnsupportedOperation")
        _parameters(request["task_parameters"])
        _require(request["comparison_conditions"] == {},
                 "The first P1 task uses the configured frozen comparison conditions.")
        _expectation(request["expected_candidate"], protocol["candidate_contract"])
        protocol["task_parameters"] = deepcopy(request["task_parameters"])
        protocol["budget_policy_refs"] = deepcopy(request["budget_policy_refs"])
        direct = {item["role"]: item for item in protocol["resources"]}
        all_roles = {item["role"]: item for item in _closure(protocol)}
        _require(isinstance(request["input_pins"], list), "Expected resource pins.")
        seen = set()
        for pin in request["input_pins"]:
            _resource(pin)
            role = pin["role"]
            _require(role not in seen, "Duplicate input role.")
            seen.add(role)
            if role in all_roles:
                _require(role in direct
                         and _project_resource(pin) == _project_resource(direct[role]),
                         "Input pin conflicts with a frozen task resource.", "IdentityMismatch")
            direct[role] = deepcopy(pin)
        protocol["resources"] = [direct[role] for role in sorted(direct)]
        _protocol(protocol)
        closure = _closure(protocol)
        for resource in closure:
            try:
                _verify_resource(self._resources(resource["role"]), resource["artifact"])
            except (KeyError, OSError):
                raise PreparationError("ArtifactUnavailable", "A required resource is unavailable.")
        data = canonical_encode(protocol)
        prepared = {
            "schema_version": 1, "prepared_id": "", **{key: deepcopy(protocol[key])
                                                       for key in _COPIES},
            "protocol": {"location": "benchmark/protocol.json", "sha256": sha256(data).hexdigest(),
                         "size_bytes": len(data), "media_type": "application/json"},
            "protocol_digest": protocol_digest(protocol),
            "recipe": deepcopy(protocol["worker_recipe"]),
            "expected_candidate": deepcopy(request["expected_candidate"]),
            "resources": deepcopy(closure), "created_at": None, "display_notes": "",
        }
        prepared["prepared_id"] = prepared_id(prepared)
        validate_prepared(prepared, data)
        roles = frozenset(resource["role"] for resource in closure)

        def read_resource(role):
            if role not in roles:
                raise KeyError(role)
            return self._resources(role)

        return prepared, data, read_resource

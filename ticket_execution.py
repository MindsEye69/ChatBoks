"""Validated, versioned ticket input for isolated ChatBoks executions.

The signed ecosystem envelope establishes where a request came from.  This
module establishes whether its task material is sufficiently bounded for
ChatBoks to queue and show to a local operator.  It deliberately does not
grant capabilities or interpret context references as paths to open.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


TICKET_EXECUTION_SCHEMA = "chatboks.ticket-execution/v1"
_MAX_OBJECTIVE_CHARS = 10_000
_MAX_ITEMS = 32
_MAX_ITEM_CHARS = 1_000
_MAX_CONTEXT_REFERENCES = 64
_MAX_CONTEXT_REFERENCE_CHARS = 512
_MAX_IDEMPOTENCY_KEY_CHARS = 128
_CAPABILITY_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")


class TicketExecutionValidationError(ValueError):
    """A structured ticket cannot safely be queued for execution."""


@dataclass(frozen=True)
class TicketExecution:
    """Normalized, untrusted work material supplied with an execution request."""

    objective: str
    constraints: tuple[str, ...]
    context_references: tuple[str, ...]
    requested_capabilities: tuple[str, ...]
    approval_policy: str
    verification_criteria: tuple[str, ...]
    budget: dict[str, int]
    idempotency_key: str

    def idempotency_digest(self, *, ticket_id: str, capability_id: str) -> str:
        """Fingerprint logical work while excluding request/proof transport fields."""
        canonical = json.dumps(
            {
                "ticketId": ticket_id,
                "capabilityId": capability_id,
                "objective": self.objective,
                "constraints": self.constraints,
                "contextReferences": self.context_references,
                "requestedCapabilities": self.requested_capabilities,
                "approvalPolicy": self.approval_policy,
                "verificationCriteria": self.verification_criteria,
                "budget": self.budget,
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def render_task_material(self) -> str:
        """Render declared scope as untrusted task material for the configured agent."""
        lines = [
            "[TICKET OBJECTIVE]",
            self.objective,
            "[CONSTRAINTS]",
            *(f"- {item}" for item in self.constraints),
            "[CONTEXT REFERENCES]",
            *(f"- {item}" for item in self.context_references),
            "[REQUESTED CAPABILITIES — DECLARATION ONLY]",
            *(f"- {item}" for item in self.requested_capabilities),
            "[VERIFICATION CRITERIA]",
            *(f"- {item}" for item in self.verification_criteria),
            "[REQUESTED BUDGET — DECLARATION ONLY]",
            *(f"- {name}: {value}" for name, value in sorted(self.budget.items())),
        ]
        return "\n".join(lines)

    def local_summary(self) -> str:
        return self.objective.replace("\n", " ").strip()


def parse_ticket_execution(request: Mapping[str, Any]) -> TicketExecution | None:
    """Parse the optional structured ticket payload; ``None`` means legacy input.

    The existing signed execution-request envelope remains at its Foundation
    version.  ``input.ticketExecution.schema`` versions the ChatBoks-specific
    payload independently so a paired client can migrate without a shared
    database or a DasDashboard dependency.
    """
    request_input = request.get("input")
    if not isinstance(request_input, Mapping) or "ticketExecution" not in request_input:
        return None
    if set(request_input) != {"ticketExecution"}:
        raise TicketExecutionValidationError(
            "Structured ticket input may contain only ticketExecution."
        )
    payload = request_input["ticketExecution"]
    if not isinstance(payload, Mapping):
        raise TicketExecutionValidationError("ticketExecution must be an object.")
    required = {
        "schema",
        "objective",
        "constraints",
        "contextReferences",
        "requestedCapabilities",
        "approvalPolicy",
        "verificationCriteria",
        "budget",
        "idempotencyKey",
    }
    if set(payload) != required:
        missing = sorted(required - set(payload))
        unknown = sorted(set(payload) - required)
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unknown:
            details.append(f"unknown {', '.join(unknown)}")
        raise TicketExecutionValidationError(
            "ticketExecution fields are invalid" + (f": {'; '.join(details)}." if details else ".")
        )
    if payload["schema"] != TICKET_EXECUTION_SCHEMA:
        raise TicketExecutionValidationError(
            f"ticketExecution.schema must be {TICKET_EXECUTION_SCHEMA}."
        )
    objective = _bounded_text(payload["objective"], "objective", _MAX_OBJECTIVE_CHARS)
    if objective.lstrip().startswith("/"):
        raise TicketExecutionValidationError("Ticket objective cannot invoke a ChatBoks command.")
    constraints = _bounded_text_list(payload["constraints"], "constraints", _MAX_ITEMS, _MAX_ITEM_CHARS)
    context_references = _bounded_text_list(
        payload["contextReferences"],
        "contextReferences",
        _MAX_CONTEXT_REFERENCES,
        _MAX_CONTEXT_REFERENCE_CHARS,
    )
    requested_capabilities = _capabilities(payload["requestedCapabilities"])
    approval_policy = payload["approvalPolicy"]
    if approval_policy != "local_operator_required":
        raise TicketExecutionValidationError(
            "ticketExecution.approvalPolicy must be local_operator_required."
        )
    verification_criteria = _bounded_text_list(
        payload["verificationCriteria"], "verificationCriteria", _MAX_ITEMS, _MAX_ITEM_CHARS
    )
    budget = _budget(payload["budget"])
    idempotency_key = _bounded_text(
        payload["idempotencyKey"], "idempotencyKey", _MAX_IDEMPOTENCY_KEY_CHARS
    )
    return TicketExecution(
        objective=objective,
        constraints=constraints,
        context_references=context_references,
        requested_capabilities=requested_capabilities,
        approval_policy=approval_policy,
        verification_criteria=verification_criteria,
        budget=budget,
        idempotency_key=idempotency_key,
    )


def _bounded_text(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise TicketExecutionValidationError(f"ticketExecution.{name} must be a string.")
    value = value.strip()
    if not value or len(value) > maximum:
        raise TicketExecutionValidationError(
            f"ticketExecution.{name} must contain between 1 and {maximum} characters."
        )
    return value


def _bounded_text_list(value: Any, name: str, maximum_items: int, maximum_chars: int) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TicketExecutionValidationError(f"ticketExecution.{name} must be an array.")
    if not value or len(value) > maximum_items:
        raise TicketExecutionValidationError(
            f"ticketExecution.{name} must contain between 1 and {maximum_items} items."
        )
    return tuple(_bounded_text(item, f"{name} item", maximum_chars) for item in value)


def _capabilities(value: Any) -> tuple[str, ...]:
    capabilities = _bounded_text_list(value, "requestedCapabilities", _MAX_ITEMS, 128)
    if not all(_CAPABILITY_PATTERN.fullmatch(capability) for capability in capabilities):
        raise TicketExecutionValidationError(
            "ticketExecution.requestedCapabilities must contain capability IDs."
        )
    if len(set(capabilities)) != len(capabilities):
        raise TicketExecutionValidationError("ticketExecution.requestedCapabilities cannot contain duplicates.")
    return capabilities


def _budget(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != {"maxSteps", "maxRuntimeSeconds"}:
        raise TicketExecutionValidationError(
            "ticketExecution.budget requires only maxSteps and maxRuntimeSeconds."
        )
    max_steps = value["maxSteps"]
    max_runtime_seconds = value["maxRuntimeSeconds"]
    if (
        isinstance(max_steps, bool)
        or not isinstance(max_steps, int)
        or not 1 <= max_steps <= 100
    ):
        raise TicketExecutionValidationError("ticketExecution.budget.maxSteps must be between 1 and 100.")
    if (
        isinstance(max_runtime_seconds, bool)
        or not isinstance(max_runtime_seconds, int)
        or not 1 <= max_runtime_seconds <= 86_400
    ):
        raise TicketExecutionValidationError(
            "ticketExecution.budget.maxRuntimeSeconds must be between 1 and 86400."
        )
    return {"maxSteps": max_steps, "maxRuntimeSeconds": max_runtime_seconds}

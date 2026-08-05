"""Local capability definitions for provenance-verified integration work.

The paired-client proof establishes provenance, not authority.  This module is
the ChatBoks-owned allowlist between a verified request and local approval.
Capability definitions are deliberately local so ChatBoks remains usable
without DasDashboard or a shared service.
"""

from __future__ import annotations

from dataclasses import dataclass

from ticket_execution import TicketExecution


@dataclass(frozen=True)
class IntegrationCapability:
    capability_id: str
    risk: str
    reversibility: str
    requires_local_approval: bool
    input_description: str


class IntegrationCapabilityError(ValueError):
    """A request names a capability ChatBoks cannot authorize."""


_CAPABILITIES = {
    "execution.lifecycle": IntegrationCapability(
        capability_id="execution.lifecycle",
        risk="high",
        reversibility="unknown",
        requires_local_approval=True,
        input_description="legacy input.prompt or chatboks.ticket-execution/v1",
    )
}


def get_integration_capability(capability_id: str) -> IntegrationCapability:
    """Resolve one locally supported capability without accepting wildcards."""
    capability = _CAPABILITIES.get(capability_id)
    if capability is None:
        raise IntegrationCapabilityError(
            f"ChatBoks does not support integration capability {capability_id!r}."
        )
    return capability


def validate_capability_scope(
    capability_id: str, ticket_execution: TicketExecution | None
) -> IntegrationCapability:
    """Require structured tickets to declare exactly the capability to be run.

    A ticket cannot accumulate unused or future privileges.  Additional
    capabilities will need their own executable adapters and approval scopes
    before they can be added to this allowlist.
    """
    capability = get_integration_capability(capability_id)
    if ticket_execution is not None and ticket_execution.requested_capabilities != (capability_id,):
        raise IntegrationCapabilityError(
            "ticketExecution.requestedCapabilities must contain exactly the requested capabilityId."
        )
    return capability

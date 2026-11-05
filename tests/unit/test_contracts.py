import pytest
from pydantic import ValidationError

from agent.handoffs import ApprovalDecision
from agent.marketplace_port import ProposalWrite
from agent.mcp_client import tools_for_role
from mcp_servers.workspace.tools import SlotRequest


def test_write_defaults_to_preview_and_requires_idempotency_key():
    with pytest.raises(ValidationError):
        ProposalWrite(job_id="job", text="draft", bid_amount=30)
    request = ProposalWrite(job_id="job", text="draft", bid_amount=30, idempotency_key="job-12345")
    assert request.dry_run is True


@pytest.mark.parametrize("payload", [{"action": "reject"}, {"action": "edit"}])
def test_approval_requires_rejection_reason_or_edit(payload):
    with pytest.raises(ValidationError):
        ApprovalDecision.model_validate(payload)


def test_calendar_requires_timezone_and_ordered_range():
    with pytest.raises(ValidationError):
        SlotRequest(start="2026-11-04T10:00:00", end="2026-11-04T11:00:00")


def test_unknown_roles_cannot_receive_tools():
    with pytest.raises(KeyError):
        tools_for_role("untrusted", [])

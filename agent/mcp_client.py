"""Construct clients with explicit credentials; never hand every agent all available tools."""

from datetime import timedelta

from langchain_mcp_adapters.client import MultiServerMCPClient

TOOL_ALLOWLISTS = {
    "scout": {"search_jobs", "get_job"},
    "analyst": set(),
    "risk": {"get_client_history"},
    "matcher": {"search_evidence", "get_case_study", "list_skills"},
    "pricing": {"get_client_history", "get_connects_balance", "get_pricing_statistics"},
    "writer": {"search_evidence", "get_case_study"},
    "critic": {"search_evidence", "get_case_study"},
    "compliance": set(),
    "liaison": {"list_messages", "free_calendar_slots"},
    "approved_executor": {
        "create_proposal_draft",
        "submit_proposal",
        "send_message",
        "create_interview_hold",
        "create_email_draft",
    },
}


def build_client(connections: dict) -> MultiServerMCPClient:
    bounded = {}
    for name, connection in connections.items():
        options = dict(connection)
        options["session_kwargs"] = {
            "read_timeout_seconds": timedelta(seconds=45),
            **options.get("session_kwargs", {}),
        }
        bounded[name] = options
    return MultiServerMCPClient(bounded)


def tools_for_role(role: str, tools: list):
    allowed = TOOL_ALLOWLISTS[role]  # Unknown roles must not receive a default tool set.
    return [tool for tool in tools if tool.name in allowed]

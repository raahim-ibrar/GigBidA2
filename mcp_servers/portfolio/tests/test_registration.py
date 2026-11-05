import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.portfolio.server import mcp


@pytest.mark.asyncio
async def test_portfolio_registration_through_in_memory_mcp_client():
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.list_tools()
        assert {tool.name for tool in result.tools} == {
            "search_evidence",
            "get_case_study",
            "list_skills",
        }
        templates = await client.list_resource_templates()
        assert {item.uriTemplate for item in templates.resourceTemplates} == {
            "portfolio://case/{id}",
            "portfolio://proposal/{id}",
        }
        prompts = await client.list_prompts()
        assert "answer_screening_question" in {item.name for item in prompts.prompts}

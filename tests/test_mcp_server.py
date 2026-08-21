import pytest
from mcp import Client

from app.mcp.server import mcp


@pytest.mark.anyio
async def test_mcp_get_base_rate() -> None:
    async with Client(mcp) as client:
        result = await client.list_tools()

        tool_names = [tool.name for tool in result.tools]

        assert "get_base_rate" in tool_names

        tool_result = await client.call_tool(
            "get_base_rate",
            {
                "start_date": "20260818",
                "end_date": "20260821",
            },
        )

        assert tool_result.is_error is False
        assert tool_result.structured_content is not None

        points = tool_result.structured_content["result"]

        assert len(points) == 4
        assert points[-1]["time"] == "20260821"
        assert points[-1]["value"] == 2.75
        assert points[-1]["unit"] == "연%"
        assert points[-1]["statistic_code"] == "722Y001"
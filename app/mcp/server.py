from mcp.server import MCPServer

from app.config import settings
from app.mcp.ecos_tools import EcosTools
from app.services.ecos import EcosService

mcp = MCPServer("personal-investment-agent")

ecos_service = EcosService(api_key=settings.ecos_api_key)
ecos_tools = EcosTools(service=ecos_service)


@mcp.tool()
async def get_base_rate(
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Get the Bank of Korea base rate for the requested date range."""
    points = await ecos_tools.get_base_rate(
        start_date=start_date,
        end_date=end_date,
    )

    return [point.model_dump() for point in points]


if __name__ == "__main__":
    mcp.run()
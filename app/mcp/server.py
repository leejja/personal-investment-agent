from mcp.server import MCPServer

from app.config import settings
from app.mcp.ecos_tools import EcosTools
from app.mcp.kiwoom_tools import KiwoomTools
from app.mcp.opendart_tools import (
    CompanyFinancials,
    KeyFinancials,
    OpenDartTools,
)
from app.models.portfolio import PortfolioContext
from app.services.ecos import EcosService
from app.services.kiwoom import (
    KiwoomAccountBalance,
    KiwoomService,
    KiwoomStockInfo,
)
from app.services.opendart import OpenDartService
from app.services.portfolio_adapter import PortfolioAdapter

mcp = MCPServer("personal-investment-agent")

ecos_service = EcosService(api_key=settings.ecos_api_key)
ecos_tools = EcosTools(service=ecos_service)

opendart_service = OpenDartService(api_key=settings.opendart_api_key)
opendart_tools = OpenDartTools(service=opendart_service)

kiwoom_service = KiwoomService(
    app_key=settings.kiwoom_app_key,
    secret_key=settings.kiwoom_secret_key,
)
kiwoom_tools = KiwoomTools(service=kiwoom_service)


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


@mcp.tool()
async def get_company_financials(
    stock_code: str,
    business_year: str,
    report_code: str = "11011",
) -> CompanyFinancials:
    """Get financial accounts for a Korean listed company."""
    return await opendart_tools.get_company_financials(
        stock_code=stock_code,
        business_year=business_year,
        report_code=report_code,
    )


@mcp.tool()
async def get_key_financials(
    stock_code: str,
    business_year: str,
    report_code: str = "11011",
) -> KeyFinancials:
    """Get normalized key financial metrics for a Korean listed company."""
    return await opendart_tools.get_key_financials(
        stock_code=stock_code,
        business_year=business_year,
        report_code=report_code,
    )


@mcp.tool()
async def get_stock_info(
    stock_code: str,
) -> KiwoomStockInfo:
    """Get normalized stock information from Kiwoom."""
    return await kiwoom_tools.get_stock_info(
        stock_code=stock_code,
    )


@mcp.tool()
async def get_account_balance(
    query_type: str = "1",
    exchange_type: str = "KRX",
) -> KiwoomAccountBalance:
    """Get normalized Kiwoom account balance and positions."""
    return await kiwoom_tools.get_account_balance(
        query_type=query_type,
        exchange_type=exchange_type,
    )


@mcp.tool()
async def get_portfolio_context(
    query_type: str = "1",
    exchange_type: str = "KRX",
) -> PortfolioContext:
    """Get the current portfolio in the project's common portfolio model."""
    balance = await kiwoom_tools.get_account_balance(
        query_type=query_type,
        exchange_type=exchange_type,
    )

    return PortfolioAdapter.from_kiwoom_balance(balance)


if __name__ == "__main__":
    mcp.run()
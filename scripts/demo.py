import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import settings
from app.mcp.ecos_tools import EcosTools
from app.mcp.opendart_tools import OpenDartTools
from app.services.ecos import EcosService
from app.services.opendart import OpenDartService


async def main() -> None:
    # --------------------------------------------------
    # ECOS
    # --------------------------------------------------
    ecos_service = EcosService(api_key=settings.ecos_api_key)
    ecos_tools = EcosTools(service=ecos_service)

    today = datetime.now(ZoneInfo("Asia/Seoul"))
    start_date = (today - timedelta(days=7)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")

    base_rates = await ecos_tools.get_base_rate(
        start_date=start_date,
        end_date=end_date,
    )

    print("=== Bank of Korea Base Rate ===")

    for point in base_rates:
        print(
            f"{point.time} | "
            f"{point.item_name1} | "
            f"{point.value} {point.unit}"
        )

    # --------------------------------------------------
    # OpenDART
    # --------------------------------------------------
    opendart_service = OpenDartService(
        api_key=settings.opendart_api_key,
    )
    opendart_tools = OpenDartTools(service=opendart_service)

    financials = await opendart_tools.get_key_financials(
        stock_code="005930",
        business_year="2025",
    )

    print("\n=== Samsung Electronics Key Financials ===")
    print(f"stock_code       : {financials.stock_code}")
    print(f"corp_code        : {financials.corp_code}")
    print(f"business_year    : {financials.business_year}")
    print(f"fs_div           : {financials.fs_div}")
    print(f"revenue          : {financials.revenue:,}")
    print(f"operating_profit : {financials.operating_profit:,}")
    print(f"net_income       : {financials.net_income:,}")
    print(f"total_assets     : {financials.total_assets:,}")
    print(f"total_liabilities: {financials.total_liabilities:,}")
    print(f"total_equity     : {financials.total_equity:,}")


if __name__ == "__main__":
    asyncio.run(main())
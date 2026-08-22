from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from mcp import Client

from app.mcp.server import mcp


@pytest.mark.anyio
async def test_mcp_get_base_rate() -> None:
    async with Client(mcp) as client:
        # 1. MCP Tool discovery
        tools = await client.list_tools()

        tool_names = [tool.name for tool in tools.tools]
        assert "get_base_rate" in tool_names

        # 2. 오늘 날짜(KST)를 조회 종료일로 사용
        start_date = "20260818"
        end_date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")

        # 3. MCP Tool 호출
        result = await client.call_tool(
            "get_base_rate",
            {
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        # 4. MCP 호출 결과 검증
        assert result.is_error is False
        assert result.structured_content is not None

        rows = result.structured_content["result"]

        assert len(rows) > 0

        # 5. ECOS에서 실제 반환된 데이터 출력
        print("\n=== ECOS MCP Response ===")
        print(f"조회 요청 기간: {start_date} ~ {end_date}")

        for row in rows:
            print(
                f"{row['time']} | "
                f"{row['item_name1']} | "
                f"{row['value']} {row['unit']}"
            )

        # 6. ECOS가 실제 반환한 가장 최신 데이터 출력
        latest = rows[-1]

        print("\n=== Latest Available Data ===")
        print(
            f"{latest['time']} | "
            f"{latest['item_name1']} | "
            f"{latest['value']} {latest['unit']}"
        )

@pytest.mark.anyio
async def test_mcp_get_company_financials() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

        tool_names = [tool.name for tool in tools.tools]
        assert "get_company_financials" in tool_names

        result = await client.call_tool(
            "get_company_financials",
            {
                "stock_code": "005930",
                "business_year": "2025",
                "report_code": "11011",
            },
        )

        assert result.is_error is False
        assert result.structured_content is not None

        financials = result.structured_content

        assert financials["stock_code"] == "005930"
        assert financials["corp_code"] == "00126380"
        assert financials["business_year"] == "2025"
        assert financials["report_code"] == "11011"

        accounts = financials["accounts"]

        assert len(accounts) > 0

        print("\n=== OpenDART MCP Response ===")
        print(f"stock_code: {financials['stock_code']}")
        print(f"corp_code : {financials['corp_code']}")
        print(f"account_count: {len(accounts)}")

        for account in accounts:
            if (
                account["fs_div"] == "CFS"
                and account["account_name"]
                in {
                    "매출액",
                    "영업이익",
                    "자산총계",
                    "부채총계",
                    "자본총계",
                }
            ):
                print(
                    f"{account['fs_div']} | "
                    f"{account['statement_div']} | "
                    f"{account['account_name']} | "
                    f"{account['current_term_amount']}"
                )

@pytest.mark.anyio
async def test_mcp_get_key_financials() -> None:
    async with Client(mcp) as client:
        # 1. MCP Tool discovery
        tools = await client.list_tools()

        tool_names = [tool.name for tool in tools.tools]
        assert "get_key_financials" in tool_names

        # 2. MCP Tool 호출
        result = await client.call_tool(
            "get_key_financials",
            {
                "stock_code": "005930",
                "business_year": "2025",
                "report_code": "11011",
            },
        )

        # 3. MCP 호출 결과 검증
        assert result.is_error is False
        assert result.structured_content is not None

        financials = result.structured_content

        assert financials["stock_code"] == "005930"
        assert financials["corp_code"] == "00126380"
        assert financials["business_year"] == "2025"
        assert financials["report_code"] == "11011"
        assert financials["fs_div"] == "CFS"

        assert financials["revenue"] is not None
        assert financials["operating_profit"] is not None
        assert financials["net_income"] is not None
        assert financials["total_assets"] is not None
        assert financials["total_liabilities"] is not None
        assert financials["total_equity"] is not None

        # 4. 실제 OpenDART 주요 재무정보 출력
        print("\n=== OpenDART Key Financials MCP Response ===")
        print(f"stock_code       : {financials['stock_code']}")
        print(f"corp_code        : {financials['corp_code']}")
        print(f"fs_div           : {financials['fs_div']}")
        print(f"revenue          : {financials['revenue']}")
        print(f"operating_profit : {financials['operating_profit']}")
        print(f"net_income       : {financials['net_income']}")
        print(f"total_assets     : {financials['total_assets']}")
        print(f"total_liabilities: {financials['total_liabilities']}")
        print(f"total_equity     : {financials['total_equity']}")
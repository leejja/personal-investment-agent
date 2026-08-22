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

@pytest.mark.anyio
async def test_mcp_get_stock_info() -> None:
    async with Client(mcp) as client:
        # 1. MCP Tool discovery
        tools = await client.list_tools()

        tool_names = [tool.name for tool in tools.tools]
        assert "get_stock_info" in tool_names

        # 2. MCP Tool 호출
        result = await client.call_tool(
            "get_stock_info",
            {
                "stock_code": "005930",
            },
        )

        # 3. MCP 호출 결과 검증
        assert result.is_error is False
        assert result.structured_content is not None

        stock_info = result.structured_content

        assert stock_info["stock_code"] == "005930"
        assert stock_info["stock_name"] == "삼성전자"
        assert stock_info["current_price"] > 0

        # 4. 실제 Kiwoom 데이터 출력
        print("\n=== Kiwoom Stock Info MCP Response ===")
        print(f"stock_code     : {stock_info['stock_code']}")
        print(f"stock_name     : {stock_info['stock_name']}")
        print(f"current_price  : {stock_info['current_price']}")
        print(f"change         : {stock_info['change']}")
        print(f"change_rate    : {stock_info['change_rate']}")
        print(f"trading_volume : {stock_info['trading_volume']}")
        print(f"PER            : {stock_info['per']}")
        print(f"PBR            : {stock_info['pbr']}")
        print(f"ROE            : {stock_info['roe']}")
        print(f"EPS            : {stock_info['eps']}")
        print(f"BPS            : {stock_info['bps']}")
        print(f"250d_high      : {stock_info['high_250d']}")
        print(f"250d_low       : {stock_info['low_250d']}")

@pytest.mark.anyio
async def test_mcp_get_account_balance() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

        tool_names = [tool.name for tool in tools.tools]
        assert "get_account_balance" in tool_names

        result = await client.call_tool(
            "get_account_balance",
            {
                "query_type": "1",
                "exchange_type": "KRX",
            },
        )

        assert result.is_error is False
        assert result.structured_content is not None

        balance = result.structured_content

        assert balance["total_purchase_amount"] >= 0
        assert balance["total_evaluation_amount"] >= 0
        assert isinstance(balance["positions"], list)

        print("\n=== Kiwoom Account Balance MCP Response ===")
        print(
            f"total_purchase_amount  : "
            f"{balance['total_purchase_amount']:,}"
        )
        print(
            f"total_evaluation_amount: "
            f"{balance['total_evaluation_amount']:,}"
        )
        print(
            f"total_profit_loss      : "
            f"{balance['total_profit_loss']:,}"
        )
        print(
            f"total_return_rate      : "
            f"{balance['total_return_rate']}"
        )
        print(
            f"position_count         : "
            f"{len(balance['positions'])}"
        )

        print("\n=== Positions ===")

        for position in balance["positions"]:
            print(
                f"{position['stock_code']} | "
                f"{position['stock_name']} | "
                f"qty={position['quantity']} | "
                f"avg={position['average_price']:,} | "
                f"current={position['current_price']:,} | "
                f"return={position['return_rate']}% | "
                f"weight={position['portfolio_weight']}%"
            )
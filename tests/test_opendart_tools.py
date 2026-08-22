from unittest.mock import AsyncMock

import pytest

from app.mcp.opendart_tools import OpenDartTools
from app.services.opendart import OpenDartFinancialAccount, OpenDartService


@pytest.mark.anyio
async def test_get_company_financials() -> None:
    service = OpenDartService(api_key="test-key")

    service.resolve_corp_code = AsyncMock(return_value="00126380")
    service.get_financial_accounts = AsyncMock(
        return_value=[
            OpenDartFinancialAccount(
                rcept_no="20260316001009",
                bsns_year="2025",
                stock_code="005930",
                reprt_code="11011",
                account_name="매출액",
                fs_div="CFS",
                fs_name="연결재무제표",
                statement_div="IS",
                statement_name="손익계산서",
                current_term_name="제57기",
                current_term_date="2025.01.01 ~ 2025.12.31",
                current_term_amount=333605938000000,
                previous_term_name="제56기",
                previous_term_date="2024.01.01 ~ 2024.12.31",
                previous_term_amount=300870903000000,
                currency="KRW",
            )
        ]
    )

    tools = OpenDartTools(service)

    result = await tools.get_company_financials(
        stock_code="005930",
        business_year="2025",
    )

    assert result.stock_code == "005930"
    assert result.corp_code == "00126380"
    assert result.business_year == "2025"
    assert result.report_code == "11011"

    assert len(result.accounts) == 1
    assert result.accounts[0].account_name == "매출액"
    assert result.accounts[0].current_term_amount == 333605938000000

    service.resolve_corp_code.assert_awaited_once_with("005930")

    service.get_financial_accounts.assert_awaited_once_with(
        corp_code="00126380",
        business_year="2025",
        report_code="11011",
    )


@pytest.mark.anyio
async def test_get_company_financials_custom_report_code() -> None:
    service = OpenDartService(api_key="test-key")

    service.resolve_corp_code = AsyncMock(return_value="00126380")
    service.get_financial_accounts = AsyncMock(return_value=[])

    tools = OpenDartTools(service)

    result = await tools.get_company_financials(
        stock_code="005930",
        business_year="2025",
        report_code="11014",
    )

    assert result.report_code == "11014"

    service.get_financial_accounts.assert_awaited_once_with(
        corp_code="00126380",
        business_year="2025",
        report_code="11014",
    )

@pytest.mark.anyio
async def test_get_key_financials_prefers_cfs() -> None:
    service = OpenDartService(api_key="test-key")

    service.resolve_corp_code = AsyncMock(return_value="00126380")
    service.get_financial_accounts = AsyncMock(
        return_value=[
            OpenDartFinancialAccount(
                rcept_no="1",
                bsns_year="2025",
                stock_code="005930",
                reprt_code="11011",
                account_name="매출액",
                fs_div="CFS",
                fs_name="연결재무제표",
                statement_div="IS",
                statement_name="손익계산서",
                current_term_name="제57기",
                current_term_date="2025",
                current_term_amount=300,
                previous_term_name="제56기",
                previous_term_date="2024",
                previous_term_amount=280,
                currency="KRW",
            ),
            OpenDartFinancialAccount(
                rcept_no="2",
                bsns_year="2025",
                stock_code="005930",
                reprt_code="11011",
                account_name="영업이익",
                fs_div="CFS",
                fs_name="연결재무제표",
                statement_div="IS",
                statement_name="손익계산서",
                current_term_name="제57기",
                current_term_date="2025",
                current_term_amount=40,
                previous_term_name="제56기",
                previous_term_date="2024",
                previous_term_amount=30,
                currency="KRW",
            ),
            OpenDartFinancialAccount(
                rcept_no="3",
                bsns_year="2025",
                stock_code="005930",
                reprt_code="11011",
                account_name="당기순이익(손실)",
                fs_div="CFS",
                fs_name="연결재무제표",
                statement_div="IS",
                statement_name="손익계산서",
                current_term_name="제57기",
                current_term_date="2025",
                current_term_amount=35,
                previous_term_name="제56기",
                previous_term_date="2024",
                previous_term_amount=25,
                currency="KRW",
            ),
            OpenDartFinancialAccount(
                rcept_no="4",
                bsns_year="2025",
                stock_code="005930",
                reprt_code="11011",
                account_name="자산총계",
                fs_div="CFS",
                fs_name="연결재무제표",
                statement_div="BS",
                statement_name="재무상태표",
                current_term_name="제57기",
                current_term_date="2025",
                current_term_amount=500,
                previous_term_name="제56기",
                previous_term_date="2024",
                previous_term_amount=450,
                currency="KRW",
            ),
            OpenDartFinancialAccount(
                rcept_no="5",
                bsns_year="2025",
                stock_code="005930",
                reprt_code="11011",
                account_name="부채총계",
                fs_div="CFS",
                fs_name="연결재무제표",
                statement_div="BS",
                statement_name="재무상태표",
                current_term_name="제57기",
                current_term_date="2025",
                current_term_amount=120,
                previous_term_name="제56기",
                previous_term_date="2024",
                previous_term_amount=110,
                currency="KRW",
            ),
            OpenDartFinancialAccount(
                rcept_no="6",
                bsns_year="2025",
                stock_code="005930",
                reprt_code="11011",
                account_name="자본총계",
                fs_div="CFS",
                fs_name="연결재무제표",
                statement_div="BS",
                statement_name="재무상태표",
                current_term_name="제57기",
                current_term_date="2025",
                current_term_amount=380,
                previous_term_name="제56기",
                previous_term_date="2024",
                previous_term_amount=340,
                currency="KRW",
            ),
            OpenDartFinancialAccount(
                rcept_no="7",
                bsns_year="2025",
                stock_code="005930",
                reprt_code="11011",
                account_name="매출액",
                fs_div="OFS",
                fs_name="재무제표",
                statement_div="IS",
                statement_name="손익계산서",
                current_term_name="제57기",
                current_term_date="2025",
                current_term_amount=200,
                previous_term_name="제56기",
                previous_term_date="2024",
                previous_term_amount=190,
                currency="KRW",
            ),
        ]
    )

    tools = OpenDartTools(service)

    result = await tools.get_key_financials(
        stock_code="005930",
        business_year="2025",
    )

    assert result.fs_div == "CFS"
    assert result.revenue == 300
    assert result.operating_profit == 40
    assert result.net_income == 35
    assert result.total_assets == 500
    assert result.total_liabilities == 120
    assert result.total_equity == 380


@pytest.mark.anyio
async def test_get_key_financials_falls_back_to_ofs() -> None:
    service = OpenDartService(api_key="test-key")

    service.resolve_corp_code = AsyncMock(return_value="00126380")
    service.get_financial_accounts = AsyncMock(
        return_value=[
            OpenDartFinancialAccount(
                rcept_no="1",
                bsns_year="2025",
                stock_code="005930",
                reprt_code="11011",
                account_name="매출액",
                fs_div="OFS",
                fs_name="재무제표",
                statement_div="IS",
                statement_name="손익계산서",
                current_term_name="제57기",
                current_term_date="2025",
                current_term_amount=200,
                previous_term_name="제56기",
                previous_term_date="2024",
                previous_term_amount=180,
                currency="KRW",
            )
        ]
    )

    tools = OpenDartTools(service)

    result = await tools.get_key_financials(
        stock_code="005930",
        business_year="2025",
    )

    assert result.fs_div == "OFS"
    assert result.revenue == 200
    assert result.operating_profit is None
    assert result.net_income is None
    assert result.total_assets is None
    assert result.total_liabilities is None
    assert result.total_equity is None
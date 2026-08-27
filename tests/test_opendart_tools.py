from unittest.mock import AsyncMock

import pytest

from app.mcp.opendart_tools import OpenDartTools, _year_label_for_term
from app.services.opendart import (
    OpenDartCorporation,
    OpenDartFinancialAccount,
    OpenDartService,
)


def _corporation(**overrides: object) -> OpenDartCorporation:
    defaults: dict[object, object] = {
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "corp_eng_name": "SAMSUNG ELECTRONICS CO,.LTD",
        "stock_code": "005930",
        "modify_date": "20260101",
    }
    defaults.update(overrides)
    return OpenDartCorporation(**defaults)


def _account(**overrides: object) -> OpenDartFinancialAccount:
    defaults: dict[object, object] = {
        "rcept_no": "1",
        "bsns_year": "2025",
        "stock_code": "005930",
        "reprt_code": "11011",
        "account_name": "매출액",
        "fs_div": "CFS",
        "fs_name": "연결재무제표",
        "statement_div": "IS",
        "statement_name": "손익계산서",
        "current_term_name": "제57기",
        "current_term_date": "2025.01.01 ~ 2025.12.31",
        "current_term_amount": 300,
        "previous_term_name": "제56기",
        "previous_term_date": "2024.01.01 ~ 2024.12.31",
        "previous_term_amount": 280,
        "before_previous_term_name": "제55기",
        "before_previous_term_date": "2023.01.01 ~ 2023.12.31",
        "before_previous_term_amount": 250,
        "currency": "KRW",
    }
    defaults.update(overrides)
    return OpenDartFinancialAccount(**defaults)


@pytest.mark.anyio
async def test_find_stock_code_by_name_returns_exact_match() -> None:
    service = OpenDartService(api_key="test-key")
    service.get_corporations = AsyncMock(
        return_value=[
            _corporation(),
            _corporation(
                corp_code="00164742",
                corp_name="SK하이닉스",
                stock_code="000660",
            ),
        ]
    )

    tools = OpenDartTools(service)

    assert await tools.find_stock_code_by_name("삼성전자") == "005930"


@pytest.mark.anyio
async def test_find_stock_code_by_name_returns_none_when_no_match() -> None:
    service = OpenDartService(api_key="test-key")
    service.get_corporations = AsyncMock(return_value=[_corporation()])

    tools = OpenDartTools(service)

    assert await tools.find_stock_code_by_name("존재하지않는회사") is None


@pytest.mark.anyio
async def test_find_stock_code_by_name_returns_none_when_ambiguous() -> None:
    # 회사명이 정확히 같은 항목이 둘 이상이면(비상장 계열사 포함 등) 추측하지
    # 않고 None을 반환한다.
    service = OpenDartService(api_key="test-key")
    service.get_corporations = AsyncMock(
        return_value=[
            _corporation(corp_code="A"),
            _corporation(corp_code="B"),
        ]
    )

    tools = OpenDartTools(service)

    assert await tools.find_stock_code_by_name("삼성전자") is None


@pytest.mark.anyio
async def test_find_stock_code_by_name_ignores_entries_without_stock_code() -> None:
    # 비상장 법인은 stock_code가 None이므로 매칭 대상에서 제외된다.
    service = OpenDartService(api_key="test-key")
    service.get_corporations = AsyncMock(
        return_value=[_corporation(stock_code=None)]
    )

    tools = OpenDartTools(service)

    assert await tools.find_stock_code_by_name("삼성전자") is None


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


def test_year_label_for_term() -> None:
    assert _year_label_for_term("2025", "current") == "2025"
    assert _year_label_for_term("2025", "previous") == "2024"
    assert _year_label_for_term("2025", "before_previous") == "2023"


@pytest.mark.anyio
async def test_get_key_financials_history_returns_three_years_for_annual_report() -> (
    None
):
    service = OpenDartService(api_key="test-key")

    service.resolve_corp_code = AsyncMock(return_value="00126380")
    service.get_financial_accounts = AsyncMock(
        return_value=[
            _account(account_name="매출액"),
            _account(
                account_name="영업이익",
                current_term_amount=40,
                previous_term_amount=30,
                before_previous_term_amount=20,
            ),
            _account(
                account_name="당기순이익(손실)",
                current_term_amount=35,
                previous_term_amount=25,
                before_previous_term_amount=15,
            ),
        ]
    )

    tools = OpenDartTools(service)

    history = await tools.get_key_financials_history(
        stock_code="005930",
        business_year="2025",
        report_code="11011",
    )

    assert len(history) == 3

    current, previous, before_previous = history

    assert current.business_year == "2025"
    assert current.revenue == 300
    assert current.operating_profit == 40
    assert current.net_income == 35

    assert previous.business_year == "2024"
    assert previous.revenue == 280
    assert previous.operating_profit == 30
    assert previous.net_income == 25

    assert before_previous.business_year == "2023"
    assert before_previous.revenue == 250
    assert before_previous.operating_profit == 20
    assert before_previous.net_income == 15

    # OpenDART API는 회사당 한 번만 호출된다(추가 API 호출 없음).
    service.get_financial_accounts.assert_awaited_once()


@pytest.mark.anyio
async def test_get_key_financials_history_only_current_for_non_annual_report() -> (
    None
):
    # 분기/반기 보고서는 전기/전전기를 추세로 섞지 않는다 — 당기 1건만
    # 반환한다.
    service = OpenDartService(api_key="test-key")

    service.resolve_corp_code = AsyncMock(return_value="00126380")
    service.get_financial_accounts = AsyncMock(
        return_value=[_account(reprt_code="11012")]
    )

    tools = OpenDartTools(service)

    history = await tools.get_key_financials_history(
        stock_code="005930",
        business_year="2025",
        report_code="11012",
    )

    assert len(history) == 1
    assert history[0].business_year == "2025"


@pytest.mark.anyio
async def test_get_key_financials_history_omits_years_with_no_data() -> None:
    # 상장 이력이 짧은 회사 등은 bfefrmtrm(전전기) 컬럼 자체가 없을 수
    # 있다. 이 경우 해당 연도는 결과에서 생략된다(당기는 항상 포함).
    service = OpenDartService(api_key="test-key")

    service.resolve_corp_code = AsyncMock(return_value="00126380")
    service.get_financial_accounts = AsyncMock(
        return_value=[
            _account(
                before_previous_term_amount=None,
            )
        ]
    )

    tools = OpenDartTools(service)

    history = await tools.get_key_financials_history(
        stock_code="005930",
        business_year="2025",
        report_code="11011",
    )

    assert len(history) == 2
    assert [kf.business_year for kf in history] == ["2025", "2024"]


@pytest.mark.anyio
async def test_get_key_financials_history_always_includes_current_even_if_empty() -> (
    None
):
    # 당기는 값이 전부 None이더라도(재무 계정이 아직 확인되지 않은 경우 등)
    # get_key_financials()와 동일하게 항상 포함되어야 한다.
    service = OpenDartService(api_key="test-key")

    service.resolve_corp_code = AsyncMock(return_value="00126380")
    service.get_financial_accounts = AsyncMock(return_value=[])

    tools = OpenDartTools(service)

    history = await tools.get_key_financials_history(
        stock_code="005930",
        business_year="2025",
        report_code="11011",
    )

    assert len(history) == 1
    assert history[0].business_year == "2025"
    assert history[0].revenue is None
import os
from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest
from dotenv import load_dotenv

from app.services.opendart import OpenDartService


def build_corp_code_zip() -> bytes:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<result>
    <list>
        <corp_code>00126380</corp_code>
        <corp_name>삼성전자</corp_name>
        <corp_eng_name>SAMSUNG ELECTRONICS CO.,LTD</corp_eng_name>
        <stock_code>005930</stock_code>
        <modify_date>20260821</modify_date>
    </list>
    <list>
        <corp_code>99999999</corp_code>
        <corp_name>비상장회사</corp_name>
        <corp_eng_name></corp_eng_name>
        <stock_code></stock_code>
        <modify_date>20260821</modify_date>
    </list>
</result>
"""

    buffer = BytesIO()

    with ZipFile(buffer, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)

    return buffer.getvalue()


def test_parse_corporation_zip() -> None:
    service = OpenDartService(api_key="test-key")

    corporations = service._parse_corporation_zip(build_corp_code_zip())

    assert len(corporations) == 2

    samsung = corporations[0]

    assert samsung.corp_code == "00126380"
    assert samsung.corp_name == "삼성전자"
    assert samsung.corp_eng_name == "SAMSUNG ELECTRONICS CO.,LTD"
    assert samsung.stock_code == "005930"
    assert samsung.modify_date == "20260821"

    unlisted = corporations[1]

    assert unlisted.corp_eng_name is None
    assert unlisted.stock_code is None


def test_parse_empty_archive() -> None:
    buffer = BytesIO()

    with ZipFile(buffer, "w"):
        pass

    service = OpenDartService(api_key="test-key")

    with pytest.raises(
        ValueError,
        match="Empty OpenDART corporation archive",
    ):
        service._parse_corporation_zip(buffer.getvalue())

@pytest.mark.anyio
async def test_get_corporations(monkeypatch: pytest.MonkeyPatch) -> None:
    zip_content = build_corp_code_zip()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/corpCode.xml"
        assert request.url.params["crtfc_key"] == "test-key"

        return httpx.Response(
            200,
            content=zip_content,
            request=request,
        )

    transport = httpx.MockTransport(handler)

    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    service = OpenDartService(api_key="test-key")

    corporations = await service.get_corporations()

    assert len(corporations) == 2
    assert corporations[0].corp_name == "삼성전자"
    assert corporations[0].stock_code == "005930"

@pytest.mark.anyio
async def test_resolve_corp_code(monkeypatch: pytest.MonkeyPatch) -> None:
    service = OpenDartService(api_key="test-key")

    async def mock_get_corporations():
        return service._parse_corporation_zip(build_corp_code_zip())

    monkeypatch.setattr(service, "get_corporations", mock_get_corporations)

    corp_code = await service.resolve_corp_code("005930")

    assert corp_code == "00126380"


@pytest.mark.anyio
async def test_resolve_corp_code_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OpenDartService(api_key="test-key")

    async def mock_get_corporations():
        return service._parse_corporation_zip(build_corp_code_zip())

    monkeypatch.setattr(service, "get_corporations", mock_get_corporations)

    with pytest.raises(
        ValueError,
        match="OpenDART corporation not found: 000000",
    ):
        await service.resolve_corp_code("000000")





@pytest.mark.anyio
async def test_real_resolve_corp_code() -> None:
    load_dotenv()

    api_key = os.environ["OPENDART_API_KEY"]

    service = OpenDartService(api_key=api_key)

    corp_code = await service.resolve_corp_code("005930")

    print("\n=== OpenDART Corporation Resolution ===")
    print("stock_code: 005930")
    print(f"corp_code : {corp_code}")

    assert corp_code == "00126380"

@pytest.mark.anyio
async def test_get_financial_accounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/fnlttSinglAcnt.json"
        assert request.url.params["crtfc_key"] == "test-key"
        assert request.url.params["corp_code"] == "00126380"
        assert request.url.params["bsns_year"] == "2025"
        assert request.url.params["reprt_code"] == "11011"

        return httpx.Response(
            200,
            json={
                "status": "000",
                "message": "정상",
                "list": [
                    {
                        "rcept_no": "20260316001009",
                        "bsns_year": "2025",
                        "stock_code": "005930",
                        "reprt_code": "11011",
                        "account_nm": "매출액",
                        "fs_div": "CFS",
                        "fs_nm": "연결재무제표",
                        "sj_div": "IS",
                        "sj_nm": "손익계산서",
                        "thstrm_nm": "제57기",
                        "thstrm_dt": "2025.01.01 ~ 2025.12.31",
                        "thstrm_amount": "300,000,000,000,000",
                        "frmtrm_nm": "제56기",
                        "frmtrm_dt": "2024.01.01 ~ 2024.12.31",
                        "frmtrm_amount": "280,000,000,000,000",
                        "currency": "KRW",
                    }
                ],
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    service = OpenDartService(api_key="test-key")

    accounts = await service.get_financial_accounts(
        corp_code="00126380",
        business_year="2025",
        report_code="11011",
    )

    assert len(accounts) == 1

    account = accounts[0]

    assert account.stock_code == "005930"
    assert account.account_name == "매출액"
    assert account.fs_div == "CFS"
    assert account.current_term_amount == 300000000000000
    assert account.previous_term_amount == 280000000000000
    assert account.currency == "KRW"


@pytest.mark.anyio
async def test_get_financial_accounts_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "013",
                "message": "조회된 데이타가 없습니다.",
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    service = OpenDartService(api_key="test-key")

    with pytest.raises(
        ValueError,
        match="OpenDART API error",
    ):
        await service.get_financial_accounts(
            corp_code="00126380",
            business_year="2025",
            report_code="11011",
        )


def test_parse_amount() -> None:
    assert OpenDartService._parse_amount("123,456") == 123456
    assert OpenDartService._parse_amount(" 123,456 ") == 123456
    assert OpenDartService._parse_amount("") is None
    assert OpenDartService._parse_amount("   ") is None
    assert OpenDartService._parse_amount(None) is None

@pytest.mark.anyio
async def test_real_get_financial_accounts() -> None:
    load_dotenv()

    api_key = os.environ["OPENDART_API_KEY"]

    service = OpenDartService(api_key=api_key)

    corp_code = await service.resolve_corp_code("005930")

    accounts = await service.get_financial_accounts(
        corp_code=corp_code,
        business_year="2025",
        report_code="11011",
    )

    print("\n=== OpenDART Samsung Financial Accounts ===")
    print(f"corp_code: {corp_code}")
    print(f"account_count: {len(accounts)}")

    for account in accounts:
        if account.account_name in {
            "매출액",
            "영업이익",
            "당기순이익",
            "자산총계",
            "부채총계",
            "자본총계",
        }:
            print(
                f"{account.fs_div} | "
                f"{account.statement_div} | "
                f"{account.account_name} | "
                f"{account.current_term_amount}"
            )

    assert accounts
    assert any(account.stock_code == "005930" for account in accounts)
import os
from unittest.mock import AsyncMock

import httpx
import pytest
from dotenv import load_dotenv

from app.services.kiwoom import KiwoomApiResponse, KiwoomService


@pytest.mark.anyio
async def test_issue_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.kiwoom.com/oauth2/token"

        body = request.content.decode()

        assert '"grant_type":"client_credentials"' in body
        assert '"appkey":"test-app-key"' in body
        assert '"secretkey":"test-secret-key"' in body

        return httpx.Response(
            200,
            json={
                "expires_dt": "20260823180000",
                "token_type": "bearer",
                "token": "test-access-token",
                "return_code": 0,
                "return_msg": "정상처리되었습니다.",
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    service = KiwoomService(
        app_key="test-app-key",
        secret_key="test-secret-key",
    )

    token = await service.issue_access_token()

    assert token.expires_dt == "20260823180000"
    assert token.token_type == "bearer"
    assert token.token == "test-access-token"


@pytest.mark.anyio
async def test_issue_access_token_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "return_code": 1,
                "return_msg": "인증 실패",
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    service = KiwoomService(
        app_key="test-app-key",
        secret_key="test-secret-key",
    )

    with pytest.raises(
        ValueError,
        match="Kiwoom API error",
    ):
        await service.issue_access_token()


@pytest.mark.anyio
async def test_issue_access_token_unexpected_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "return_code": 0,
                "return_msg": "정상",
                "token": 1234,
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    service = KiwoomService(
        app_key="test-app-key",
        secret_key="test-secret-key",
    )

    with pytest.raises(
        TypeError,
        match="Unexpected Kiwoom token response",
    ):
        await service.issue_access_token()

@pytest.mark.anyio
async def test_real_issue_access_token() -> None:
    load_dotenv()

    app_key = os.environ["KIWOOM_APP_KEY"]
    secret_key = os.environ["KIWOOM_SECRET_KEY"]

    service = KiwoomService(
        app_key=app_key,
        secret_key=secret_key,
    )

    token = await service.issue_access_token()

    print("\n=== Kiwoom Access Token ===")
    print(f"token_type : {token.token_type}")
    print(f"expires_dt : {token.expires_dt}")
    print(f"token      : {token.token[:12]}...")

    assert token.token
    assert token.token_type
    assert token.expires_dt

@pytest.mark.anyio
async def test_request_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.kiwoom.com/test-endpoint"
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["api-id"] == "test-api"
        assert request.headers["content-type"] == "application/json;charset=UTF-8"

        body = request.content.decode()

        assert '"stk_cd":"005930"' in body

        return httpx.Response(
            200,
            json={
                "stk_cd": "005930",
                "stk_nm": "삼성전자",
                "return_code": 0,
                "return_msg": "정상처리되었습니다.",
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    service = KiwoomService(
        app_key="test-app-key",
        secret_key="test-secret-key",
    )

    result = await service.request(
        access_token="test-token",
        api_id="test-api",
        endpoint="/test-endpoint",
        payload={
            "stk_cd": "005930",
        },
    )

    assert result.data["stk_cd"] == "005930"
    assert result.data["stk_nm"] == "삼성전자"


@pytest.mark.anyio
async def test_request_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "return_code": 1,
                "return_msg": "요청 실패",
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    service = KiwoomService(
        app_key="test-app-key",
        secret_key="test-secret-key",
    )

    with pytest.raises(
        ValueError,
        match="Kiwoom API error",
    ):
        await service.request(
            access_token="test-token",
            api_id="test-api",
            endpoint="/test-endpoint",
            payload={
                "stk_cd": "005930",
            },
        )

@pytest.mark.anyio
async def test_get_stock_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = KiwoomService(
        app_key="test-app-key",
        secret_key="test-secret-key",
    )

    service.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "stk_cd": "005930",
                "stk_nm": "삼성전자",
                "cur_prc": "+281500",
                "pred_pre": "+10500",
                "flu_rt": "+3.87",
                "trde_qty": "27746471",
                "per": "42.89",
                "pbr": "4.40",
                "roe": "10.9",
                "eps": "6564",
                "bps": "63976",
                "250hgst": "+374500",
                "250lwst": "-67500",
                "return_code": 0,
                "return_msg": "정상적으로 처리되었습니다.",
            }
        )
    )

    result = await service.get_stock_info(
        access_token="test-token",
        stock_code="005930",
    )

    assert result.stock_code == "005930"
    assert result.stock_name == "삼성전자"

    assert result.current_price == 281500
    assert result.change == 10500
    assert result.change_rate == 3.87
    assert result.trading_volume == 27746471

    assert result.per == 42.89
    assert result.pbr == 4.40
    assert result.roe == 10.9
    assert result.eps == 6564
    assert result.bps == 63976

    assert result.high_250d == 374500
    assert result.low_250d == 67500

    service.request.assert_awaited_once_with(
        access_token="test-token",
        api_id="ka10001",
        endpoint="/api/dostk/stkinfo",
        payload={
            "stk_cd": "005930",
        },
    )

@pytest.mark.anyio
async def test_real_get_stock_info() -> None:
    load_dotenv()

    service = KiwoomService(
        app_key=os.environ["KIWOOM_APP_KEY"],
        secret_key=os.environ["KIWOOM_SECRET_KEY"],
    )

    token = await service.issue_access_token()

    stock_info = await service.get_stock_info(
        access_token=token.token,
        stock_code="005930",
    )

    print("\n=== Kiwoom Samsung Stock Info ===")
    print(f"stock_code     : {stock_info.stock_code}")
    print(f"stock_name     : {stock_info.stock_name}")
    print(f"current_price  : {stock_info.current_price}")
    print(f"change         : {stock_info.change}")
    print(f"change_rate    : {stock_info.change_rate}")
    print(f"trading_volume : {stock_info.trading_volume}")
    print(f"PER            : {stock_info.per}")
    print(f"PBR            : {stock_info.pbr}")
    print(f"ROE            : {stock_info.roe}")
    print(f"EPS            : {stock_info.eps}")
    print(f"BPS            : {stock_info.bps}")
    print(f"250d_high      : {stock_info.high_250d}")
    print(f"250d_low       : {stock_info.low_250d}")

    assert stock_info.stock_code == "005930"
    assert stock_info.stock_name == "삼성전자"
    assert stock_info.current_price != 0
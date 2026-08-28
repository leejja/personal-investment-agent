import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest
from dotenv import load_dotenv

from app.services.kiwoom import (
    THEME_CATALOG_CACHE_TTL,
    KiwoomAccessToken,
    KiwoomApiResponse,
    KiwoomService,
)


def _access_token(
    *,
    expires_dt: str = "20991231235959",
    token: str = "test-access-token",
) -> KiwoomAccessToken:
    return KiwoomAccessToken(
        expires_dt=expires_dt,
        token_type="Bearer",
        token=token,
    )


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
async def test_get_access_token_issues_once_on_first_call() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")
    service.issue_access_token = AsyncMock(return_value=_access_token())

    token = await service.get_access_token()

    assert token.token == "test-access-token"
    service.issue_access_token.assert_awaited_once()


@pytest.mark.anyio
async def test_get_access_token_reuses_cached_token() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")
    service.issue_access_token = AsyncMock(return_value=_access_token())

    first = await service.get_access_token()
    second = await service.get_access_token()

    assert first == second
    service.issue_access_token.assert_awaited_once()


@pytest.mark.anyio
async def test_get_access_token_reissues_when_expired() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")
    # 이미 만료된(과거) expires_dt로 캐시를 미리 채워둔다 — "now"를
    # monkeypatch하지 않아도 확실히 만료로 판정된다.
    service._cached_token = _access_token(
        expires_dt="20200101000000", token="stale-token"
    )
    service.issue_access_token = AsyncMock(
        return_value=_access_token(token="fresh-token")
    )

    token = await service.get_access_token()

    assert token.token == "fresh-token"
    service.issue_access_token.assert_awaited_once()


@pytest.mark.anyio
async def test_get_access_token_force_refresh_bypasses_valid_cache() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")
    service._cached_token = _access_token(token="cached-token")
    service.issue_access_token = AsyncMock(
        return_value=_access_token(token="forced-token")
    )

    token = await service.get_access_token(force_refresh=True)

    assert token.token == "forced-token"
    service.issue_access_token.assert_awaited_once()


@pytest.mark.anyio
async def test_get_access_token_concurrent_calls_issue_once() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    async def slow_issue() -> KiwoomAccessToken:
        # 여러 coroutine이 캐시가 비어 있는 상태에서 겹치도록 인위적으로
        # 지연시킨다 — 지연이 없으면 첫 호출이 너무 빨리 끝나 경쟁 상황
        # 자체가 재현되지 않는다.
        await asyncio.sleep(0.01)
        return _access_token()

    service.issue_access_token = AsyncMock(side_effect=slow_issue)

    results = await asyncio.gather(*[service.get_access_token() for _ in range(5)])

    assert all(result.token == "test-access-token" for result in results)
    service.issue_access_token.assert_awaited_once()


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


@pytest.mark.anyio
async def test_get_stock_list_parses_fields() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    service.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "list": [
                    {
                        "code": "000020",
                        "name": "동화약품",
                        "listCount": "0000000027931470",
                        "auditInfo": "정상",
                        "regDay": "19760324",
                        "lastPrice": "00005180",
                        "state": "증거금40%|담보대출|신용가능",
                        "marketCode": "0",
                        "marketName": "거래소",
                        "upName": "제약",
                        "upSizeName": "소형주",
                        "companyClassName": "",
                        "orderWarning": "0",
                        "nxtEnable": "N",
                        "kind": "A",
                    }
                ],
                "return_code": 0,
                "return_msg": "정상적으로 처리되었습니다",
            },
            cont_yn="N",
            next_key=None,
        )
    )

    result = await service.get_stock_list(access_token="test-token", market_code="0")

    assert len(result) == 1
    item = result[0]
    assert item.symbol == "000020"
    assert item.name == "동화약품"
    assert item.market_name == "거래소"
    assert item.sector_name == "제약"
    assert item.size_name == "소형주"
    assert item.listed_shares == 27931470
    assert item.last_price == 5180
    assert item.audit_info == "정상"
    assert item.order_warning == "0"

    service.request.assert_awaited_once_with(
        access_token="test-token",
        api_id="ka10099",
        endpoint="/api/dostk/stkinfo",
        payload={"mrkt_tp": "0"},
    )


@pytest.mark.anyio
async def test_get_stock_list_with_continuation() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    def _row(code: str) -> dict:
        return {
            "code": code,
            "name": f"종목{code}",
            "listCount": "1000",
            "auditInfo": "정상",
            "lastPrice": "1000",
            "marketName": "거래소",
            "upName": "제약",
            "upSizeName": "소형주",
            "orderWarning": "0",
        }

    service.request = AsyncMock(
        side_effect=[
            KiwoomApiResponse(
                data={"list": [_row("000001")], "return_code": 0, "return_msg": "정상"},
                cont_yn="Y",
                next_key="next-key-1",
            ),
            KiwoomApiResponse(
                data={"list": [_row("000002")], "return_code": 0, "return_msg": "정상"},
                cont_yn="N",
                next_key=None,
            ),
        ]
    )

    result = await service.get_stock_list(access_token="test-token", market_code="0")

    assert [item.symbol for item in result] == ["000001", "000002"]
    assert service.request.await_count == 2


@pytest.mark.anyio
async def test_real_get_stock_list_kospi() -> None:
    load_dotenv()

    service = KiwoomService(
        app_key=os.environ["KIWOOM_APP_KEY"],
        secret_key=os.environ["KIWOOM_SECRET_KEY"],
    )

    token = await service.issue_access_token()

    result = await service.get_stock_list(access_token=token.token, market_code="0")

    print("\n=== Kiwoom KOSPI Stock List ===")
    print(f"count: {len(result)}")
    if result:
        first = result[0]
        print(f"first: {first.symbol} {first.name} sector={first.sector_name} "
              f"size={first.size_name} listed_shares={first.listed_shares}")

    assert len(result) > 0
    assert all(item.symbol for item in result)
    assert all(item.name for item in result)


@pytest.mark.anyio
async def test_get_account_balance_with_continuation() -> None:
    service = KiwoomService(
        app_key="test-app-key",
        secret_key="test-secret-key",
    )

    service.request = AsyncMock(
        side_effect=[
            KiwoomApiResponse(
                data={
                    "tot_pur_amt": "1000000",
                    "tot_evlt_amt": "1200000",
                    "tot_evlt_pl": "200000",
                    "tot_prft_rt": "20.0",
                    "prsm_dpst_aset_amt": "1500000",
                    "tot_loan_amt": "0",
                    "tot_crd_loan_amt": "0",
                    "tot_crd_ls_amt": "0",
                    "acnt_evlt_remn_indv_tot": [
                        {
                            "stk_cd": "005930",
                            "stk_nm": "삼성전자",
                            "evltv_prft": "100000",
                            "prft_rt": "10.0",
                            "pur_pric": "250000",
                            "pred_close_pric": "271000",
                            "rmnd_qty": "4",
                            "trde_able_qty": "4",
                            "cur_prc": "+281500",
                            "pred_buyq": "0",
                            "pred_sellq": "0",
                            "tdy_buyq": "0",
                            "tdy_sellq": "0",
                            "pur_amt": "1000000",
                            "pur_cmsn": "0",
                            "evlt_amt": "1126000",
                            "sell_cmsn": "0",
                            "tax": "0",
                            "sum_cmsn": "0",
                            "poss_rt": "75.0",
                            "crd_tp": "00",
                            "crd_tp_nm": "",
                            "crd_loan_dt": "",
                        }
                    ],
                    "return_code": 0,
                    "return_msg": "정상",
                },
                cont_yn="Y",
                next_key="next-key-1",
            ),
            KiwoomApiResponse(
                data={
                    "acnt_evlt_remn_indv_tot": [
                        {
                            "stk_cd": "000660",
                            "stk_nm": "SK하이닉스",
                            "evltv_prft": "100000",
                            "prft_rt": "25.0",
                            "pur_pric": "200000",
                            "pred_close_pric": "250000",
                            "rmnd_qty": "2",
                            "trde_able_qty": "2",
                            "cur_prc": "+250000",
                            "pred_buyq": "0",
                            "pred_sellq": "0",
                            "tdy_buyq": "0",
                            "tdy_sellq": "0",
                            "pur_amt": "400000",
                            "pur_cmsn": "0",
                            "evlt_amt": "500000",
                            "sell_cmsn": "0",
                            "tax": "0",
                            "sum_cmsn": "0",
                            "poss_rt": "25.0",
                            "crd_tp": "00",
                            "crd_tp_nm": "",
                            "crd_loan_dt": "",
                        }
                    ],
                    "return_code": 0,
                    "return_msg": "정상",
                },
                cont_yn="N",
                next_key=None,
            ),
        ]
    )

    result = await service.get_account_balance(
        access_token="test-token",
        query_type="1",
        exchange_type="KRX",
    )

    assert result.total_purchase_amount == 1000000
    assert result.total_evaluation_amount == 1200000
    assert result.total_profit_loss == 200000
    assert result.total_return_rate == 20.0
    assert result.estimated_asset_amount == 1500000

    assert len(result.positions) == 2

    samsung = result.positions[0]

    assert samsung.stock_code == "005930"
    assert samsung.stock_name == "삼성전자"
    assert samsung.quantity == 4
    assert samsung.tradable_quantity == 4
    assert samsung.average_price == 250000
    assert samsung.current_price == 281500
    assert samsung.purchase_amount == 1000000
    assert samsung.evaluation_amount == 1126000
    assert samsung.profit_loss == 100000
    assert samsung.return_rate == 10.0
    assert samsung.portfolio_weight == 75.0

    hynix = result.positions[1]

    assert hynix.stock_code == "000660"
    assert hynix.stock_name == "SK하이닉스"
    assert hynix.current_price == 250000

    assert service.request.await_count == 2

    first_call = service.request.await_args_list[0]
    second_call = service.request.await_args_list[1]

    assert first_call.kwargs == {
        "access_token": "test-token",
        "api_id": "kt00018",
        "endpoint": "/api/dostk/acnt",
        "payload": {
            "qry_tp": "1",
            "dmst_stex_tp": "KRX",
        },
    }

    assert second_call.kwargs == {
        "access_token": "test-token",
        "api_id": "kt00018",
        "endpoint": "/api/dostk/acnt",
        "payload": {
            "qry_tp": "1",
            "dmst_stex_tp": "KRX",
        },
        "cont_yn": "Y",
        "next_key": "next-key-1",
    }


@pytest.mark.anyio
async def test_get_account_balance_strips_market_prefix_from_stock_code() -> None:
    # 실제 Kiwoom 계좌평가잔고(kt00018) 응답의 stk_cd는 시장 구분
    # 접두문자가 붙은 채로 내려온다(예: "A005930"). 다른 Kiwoom API
    # (get_stock_info 등)는 접두문자 없는 순수 종목코드를 기대하므로
    # Service 계층에서 정규화해야 한다.
    service = KiwoomService(
        app_key="test-app-key",
        secret_key="test-secret-key",
    )

    service.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "tot_pur_amt": "1000000",
                "tot_evlt_amt": "1200000",
                "tot_evlt_pl": "200000",
                "tot_prft_rt": "20.0",
                "prsm_dpst_aset_amt": "1500000",
                "tot_loan_amt": "0",
                "tot_crd_loan_amt": "0",
                "tot_crd_ls_amt": "0",
                "acnt_evlt_remn_indv_tot": [
                    {
                        "stk_cd": "A005930",
                        "stk_nm": "삼성전자",
                        "evltv_prft": "100000",
                        "prft_rt": "10.0",
                        "pur_pric": "250000",
                        "rmnd_qty": "4",
                        "trde_able_qty": "4",
                        "cur_prc": "+281500",
                        "pur_amt": "1000000",
                        "evlt_amt": "1126000",
                        "poss_rt": "75.0",
                    }
                ],
                "return_code": 0,
                "return_msg": "정상",
            },
            cont_yn="N",
            next_key=None,
        )
    )

    result = await service.get_account_balance(
        access_token="test-token",
        query_type="1",
        exchange_type="KRX",
    )

    assert result.positions[0].stock_code == "005930"


@pytest.mark.anyio
async def test_real_get_account_balance() -> None:
    load_dotenv()

    service = KiwoomService(
        app_key=os.environ["KIWOOM_APP_KEY"],
        secret_key=os.environ["KIWOOM_SECRET_KEY"],
    )

    token = await service.issue_access_token()

    balance = await service.get_account_balance(
        access_token=token.token,
        query_type="1",
        exchange_type="KRX",
    )

    print("\n=== Kiwoom Account Balance ===")
    print(f"total_purchase_amount  : {balance.total_purchase_amount:,}")
    print(f"total_evaluation_amount: {balance.total_evaluation_amount:,}")
    print(f"total_profit_loss      : {balance.total_profit_loss:,}")
    print(f"total_return_rate      : {balance.total_return_rate}")
    print(f"position_count         : {len(balance.positions)}")

    print("\n=== Positions ===")

    for position in balance.positions:
        print(
            f"{position.stock_code} | "
            f"{position.stock_name} | "
            f"qty={position.quantity} | "
            f"avg={position.average_price:,} | "
            f"current={position.current_price:,} | "
            f"return={position.return_rate}% | "
            f"weight={position.portfolio_weight}%"
        )

    assert balance.total_purchase_amount >= 0
    assert balance.total_evaluation_amount >= 0
    assert isinstance(balance.positions, list)


# ============================== UX-01: Theme catalog/membership ==============================

_KST = ZoneInfo("Asia/Seoul")


def _theme_group_row(code: str, name: str, stk_num: str = "3") -> dict:
    return {
        "thema_grp_cd": code,
        "thema_nm": name,
        "stk_num": stk_num,
        "flu_sig": "1",
        "flu_rt": "+1.23",
        "rising_stk_num": "1",
        "fall_stk_num": "0",
        "dt_prft_rt": "+5.0",
        "main_stk": "삼성전자, SK하이닉스",
    }


def _theme_stock_row(code: str, name: str) -> dict:
    return {
        "stk_cd": code,
        "stk_nm": name,
        "cur_prc": "+100000",
        "flu_sig": "1",
        "pred_pre": "+1000",
        "flu_rt": "+1.0",
        "acc_trde_qty": "1000",
        "sel_bid": "100100",
        "sel_req": "10",
        "buy_bid": "99900",
        "buy_req": "10",
        "dt_prft_rt_n": "+5.0",
    }


@pytest.mark.anyio
async def test_get_theme_groups_parses_fields() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    service.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "thema_grp": [_theme_group_row("550", "반도체_생산", "3")],
                "return_code": 0,
                "return_msg": "정상",
            },
            cont_yn="N",
            next_key=None,
        )
    )

    result = await service.get_theme_groups(access_token="test-token")

    assert len(result) == 1
    assert result[0].theme_code == "550"
    assert result[0].theme_name == "반도체_생산"
    assert result[0].stock_count == 3

    service.request.assert_awaited_once_with(
        access_token="test-token",
        api_id="ka90001",
        endpoint="/api/dostk/thme",
        payload={
            "qry_tp": "0",
            "date_tp": "10",
            "flu_pl_amt_tp": "1",
            "stex_tp": "1",
            "stk_cd": "",
            "thema_nm": "",
        },
    )


@pytest.mark.anyio
async def test_get_theme_groups_with_continuation() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    service.request = AsyncMock(
        side_effect=[
            KiwoomApiResponse(
                data={
                    "thema_grp": [_theme_group_row("550", "반도체_생산")],
                    "return_code": 0,
                    "return_msg": "정상",
                },
                cont_yn="Y",
                next_key="next-key-1",
            ),
            KiwoomApiResponse(
                data={
                    "thema_grp": [_theme_group_row("551", "반도체_설계(fabless)")],
                    "return_code": 0,
                    "return_msg": "정상",
                },
                cont_yn="N",
                next_key=None,
            ),
        ]
    )

    result = await service.get_theme_groups(access_token="test-token")

    assert [group.theme_code for group in result] == ["550", "551"]
    assert service.request.await_count == 2


@pytest.mark.anyio
async def test_get_theme_groups_cache_hit_does_not_refetch() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    service.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "thema_grp": [_theme_group_row("550", "반도체_생산")],
                "return_code": 0,
                "return_msg": "정상",
            },
            cont_yn="N",
            next_key=None,
        )
    )

    first = await service.get_theme_groups(access_token="test-token")
    second = await service.get_theme_groups(access_token="test-token")

    assert first == second
    service.request.assert_awaited_once()


@pytest.mark.anyio
async def test_get_theme_groups_cache_expires_after_ttl() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    # 이미 THEME_CATALOG_CACHE_TTL보다 오래된 캐시를 미리 채워둔다 —
    # "now"를 monkeypatch하지 않아도 확실히 만료로 판정된다(access token
    # 만료 테스트와 동일한 관례).
    service._theme_catalog_cache = []
    service._theme_catalog_cached_at = datetime.now(_KST) - THEME_CATALOG_CACHE_TTL - timedelta(
        seconds=1
    )

    service.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "thema_grp": [_theme_group_row("550", "반도체_생산")],
                "return_code": 0,
                "return_msg": "정상",
            },
            cont_yn="N",
            next_key=None,
        )
    )

    result = await service.get_theme_groups(access_token="test-token")

    assert len(result) == 1
    service.request.assert_awaited_once()


@pytest.mark.anyio
async def test_get_theme_groups_within_ttl_does_not_refetch() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    service._theme_catalog_cache = [
        service._parse_theme_groups([_theme_group_row("550", "반도체_생산")])[0]
    ]
    service._theme_catalog_cached_at = datetime.now(_KST) - (
        THEME_CATALOG_CACHE_TTL - timedelta(minutes=1)
    )

    service.request = AsyncMock()

    result = await service.get_theme_groups(access_token="test-token")

    assert [group.theme_code for group in result] == ["550"]
    service.request.assert_not_awaited()


@pytest.mark.anyio
async def test_get_theme_groups_force_refresh_bypasses_valid_cache() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    service._theme_catalog_cache = [
        service._parse_theme_groups([_theme_group_row("550", "반도체_생산")])[0]
    ]
    service._theme_catalog_cached_at = datetime.now(_KST)

    service.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "thema_grp": [_theme_group_row("999", "새테마")],
                "return_code": 0,
                "return_msg": "정상",
            },
            cont_yn="N",
            next_key=None,
        )
    )

    result = await service.get_theme_groups(access_token="test-token", force_refresh=True)

    assert [group.theme_code for group in result] == ["999"]
    service.request.assert_awaited_once()


@pytest.mark.anyio
async def test_theme_catalog_cache_is_instance_level() -> None:
    # 두 KiwoomService 인스턴스는 독립된 캐시를 가진다 — 전역/singleton
    # 캐시가 아니다(access token 캐시와 동일한 설계 원칙).
    service_a = KiwoomService(app_key="a", secret_key="a")
    service_b = KiwoomService(app_key="b", secret_key="b")

    service_a.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "thema_grp": [_theme_group_row("550", "반도체_생산")],
                "return_code": 0,
                "return_msg": "정상",
            },
            cont_yn="N",
            next_key=None,
        )
    )
    service_b.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "thema_grp": [_theme_group_row("140", "2차전지_완제품")],
                "return_code": 0,
                "return_msg": "정상",
            },
            cont_yn="N",
            next_key=None,
        )
    )

    result_a = await service_a.get_theme_groups(access_token="token-a")
    result_b = await service_b.get_theme_groups(access_token="token-b")

    assert [group.theme_code for group in result_a] == ["550"]
    assert [group.theme_code for group in result_b] == ["140"]


@pytest.mark.anyio
async def test_get_theme_stocks_parses_fields() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    service.request = AsyncMock(
        return_value=KiwoomApiResponse(
            data={
                "thema_comp_stk": [_theme_stock_row("005930", "삼성전자")],
                "flu_rt": "+1.0",
                "dt_prft_rt": "+5.0",
                "return_code": 0,
                "return_msg": "정상",
            },
            cont_yn="N",
            next_key=None,
        )
    )

    result = await service.get_theme_stocks(access_token="test-token", theme_code="550")

    assert len(result) == 1
    assert result[0].stock_code == "005930"
    assert result[0].stock_name == "삼성전자"

    service.request.assert_awaited_once_with(
        access_token="test-token",
        api_id="ka90002",
        endpoint="/api/dostk/thme",
        payload={"thema_grp_cd": "550", "stex_tp": "1", "date_tp": "2"},
    )


@pytest.mark.anyio
async def test_get_theme_stocks_with_continuation() -> None:
    service = KiwoomService(app_key="test-app-key", secret_key="test-secret-key")

    service.request = AsyncMock(
        side_effect=[
            KiwoomApiResponse(
                data={
                    "thema_comp_stk": [_theme_stock_row("005930", "삼성전자")],
                    "return_code": 0,
                    "return_msg": "정상",
                },
                cont_yn="Y",
                next_key="next-key-1",
            ),
            KiwoomApiResponse(
                data={
                    "thema_comp_stk": [_theme_stock_row("000660", "SK하이닉스")],
                    "return_code": 0,
                    "return_msg": "정상",
                },
                cont_yn="N",
                next_key=None,
            ),
        ]
    )

    result = await service.get_theme_stocks(access_token="test-token", theme_code="550")

    assert [stock.stock_code for stock in result] == ["005930", "000660"]
    assert service.request.await_count == 2


@pytest.mark.anyio
async def test_real_get_theme_groups() -> None:
    load_dotenv()

    service = KiwoomService(
        app_key=os.environ["KIWOOM_APP_KEY"],
        secret_key=os.environ["KIWOOM_SECRET_KEY"],
    )

    token = await service.issue_access_token()

    result = await service.get_theme_groups(access_token=token.token)

    print("\n=== Kiwoom Theme Groups (ka90001) ===")
    print(f"count: {len(result)}")
    if result:
        first = result[0]
        print(f"first: {first.theme_code} {first.theme_name} stock_count={first.stock_count}")

    assert len(result) > 0
    assert all(group.theme_code for group in result)
    assert all(group.theme_name for group in result)

    # 캐시가 실제로 재사용되는지도 함께 확인한다 — 두 번째 호출은 새
    # HTTP 요청 없이 동일한 결과를 즉시 반환해야 한다.
    cached_result = await service.get_theme_groups(access_token=token.token)
    assert cached_result == result


@pytest.mark.anyio
async def test_real_get_theme_stocks() -> None:
    load_dotenv()

    service = KiwoomService(
        app_key=os.environ["KIWOOM_APP_KEY"],
        secret_key=os.environ["KIWOOM_SECRET_KEY"],
    )

    token = await service.issue_access_token()

    groups = await service.get_theme_groups(access_token=token.token)
    semiconductor_production = next(
        group for group in groups if group.theme_name == "반도체_생산"
    )

    result = await service.get_theme_stocks(
        access_token=token.token, theme_code=semiconductor_production.theme_code
    )

    print("\n=== Kiwoom Theme Stocks (ka90002) — 반도체_생산 ===")
    for stock in result:
        print(f"{stock.stock_code} {stock.stock_name}")

    assert len(result) > 0
    assert any(stock.stock_code == "005930" for stock in result)
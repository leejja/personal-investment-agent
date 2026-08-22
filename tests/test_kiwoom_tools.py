from unittest.mock import AsyncMock

import pytest

from app.mcp.kiwoom_tools import KiwoomTools
from app.services.kiwoom import (
    KiwoomAccessToken,
    KiwoomService,
    KiwoomStockInfo,
)


@pytest.mark.anyio
async def test_get_stock_info() -> None:
    service = KiwoomService(
        app_key="test-app-key",
        secret_key="test-secret-key",
    )

    service.issue_access_token = AsyncMock(
        return_value=KiwoomAccessToken(
            expires_dt="20260823180000",
            token_type="bearer",
            token="test-access-token",
        )
    )

    service.get_stock_info = AsyncMock(
        return_value=KiwoomStockInfo(
            stock_code="005930",
            stock_name="삼성전자",
            current_price=281500,
            change=10500,
            change_rate=3.87,
            trading_volume=27746471,
            per=42.89,
            pbr=4.4,
            roe=10.9,
            eps=6564,
            bps=63976,
            high_250d=374500,
            low_250d=67500,
        )
    )

    tools = KiwoomTools(service=service)

    result = await tools.get_stock_info(
        stock_code="005930",
    )

    assert result.stock_code == "005930"
    assert result.stock_name == "삼성전자"
    assert result.current_price == 281500
    assert result.change == 10500
    assert result.change_rate == 3.87
    assert result.trading_volume == 27746471

    assert result.per == 42.89
    assert result.pbr == 4.4
    assert result.roe == 10.9
    assert result.eps == 6564
    assert result.bps == 63976

    assert result.high_250d == 374500
    assert result.low_250d == 67500

    service.issue_access_token.assert_awaited_once_with()

    service.get_stock_info.assert_awaited_once_with(
        access_token="test-access-token",
        stock_code="005930",
    )
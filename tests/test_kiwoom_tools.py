from unittest.mock import AsyncMock

import pytest

from app.mcp.kiwoom_tools import KiwoomTools
from app.services.kiwoom import (
    KiwoomAccessToken,
    KiwoomAccountBalance,
    KiwoomAccountPosition,
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

@pytest.mark.anyio
async def test_get_account_balance() -> None:
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

    service.get_account_balance = AsyncMock(
        return_value=KiwoomAccountBalance(
            total_purchase_amount=1000000,
            total_evaluation_amount=1200000,
            total_profit_loss=200000,
            total_return_rate=20.0,
            estimated_asset_amount=1500000,
            total_loan_amount=0,
            total_credit_loan_amount=0,
            total_credit_short_amount=0,
            positions=[
                KiwoomAccountPosition(
                    stock_code="005930",
                    stock_name="삼성전자",
                    quantity=4,
                    tradable_quantity=4,
                    average_price=250000,
                    current_price=281500,
                    purchase_amount=1000000,
                    evaluation_amount=1126000,
                    profit_loss=126000,
                    return_rate=12.6,
                    portfolio_weight=75.0,
                )
            ],
        )
    )

    tools = KiwoomTools(service=service)

    result = await tools.get_account_balance()

    assert result.total_purchase_amount == 1000000
    assert result.total_evaluation_amount == 1200000
    assert result.total_profit_loss == 200000
    assert result.total_return_rate == 20.0
    assert len(result.positions) == 1

    position = result.positions[0]

    assert position.stock_code == "005930"
    assert position.stock_name == "삼성전자"
    assert position.quantity == 4
    assert position.average_price == 250000
    assert position.current_price == 281500
    assert position.portfolio_weight == 75.0

    service.issue_access_token.assert_awaited_once_with()

    service.get_account_balance.assert_awaited_once_with(
        access_token="test-access-token",
        query_type="1",
        exchange_type="KRX",
    )
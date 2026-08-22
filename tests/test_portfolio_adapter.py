import pytest

from app.config import settings
from app.services.kiwoom import (
    KiwoomAccountBalance,
    KiwoomAccountPosition,
    KiwoomService,
)
from app.services.portfolio_adapter import PortfolioAdapter


def test_from_kiwoom_position() -> None:
    position = KiwoomAccountPosition(
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

    result = PortfolioAdapter.from_kiwoom_position(position)

    assert result.symbol == "005930"
    assert result.name == "삼성전자"
    assert result.quantity == 4
    assert result.average_price == 250000.0
    assert result.current_price == 281500.0
    assert result.market_value == 1126000.0
    assert result.profit_loss == 126000.0
    assert result.profit_loss_pct == 12.6
    assert result.weight == 0.75


def test_from_kiwoom_balance() -> None:
    balance = KiwoomAccountBalance(
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

    result = PortfolioAdapter.from_kiwoom_balance(balance)

    assert result.total_value == 1200000.0
    assert result.cash == 0.0
    assert len(result.positions) == 1

    position = result.positions[0]

    assert position.symbol == "005930"
    assert position.name == "삼성전자"
    assert position.weight == 0.75


@pytest.mark.anyio
async def test_real_kiwoom_balance_to_portfolio_context() -> None:
    service = KiwoomService(
        app_key=settings.kiwoom_app_key,
        secret_key=settings.kiwoom_secret_key,
    )

    token = await service.issue_access_token()

    balance = await service.get_account_balance(
        access_token=token.token,
        query_type="1",
        exchange_type="KRX",
    )

    portfolio = PortfolioAdapter.from_kiwoom_balance(balance)

    print("\n=== PortfolioContext from Kiwoom ===")
    print(f"total_value   : {portfolio.total_value:,.0f}")
    print(f"cash          : {portfolio.cash:,.0f}")
    print(f"position_count: {len(portfolio.positions)}")

    print("\n=== Portfolio Positions ===")

    for position in portfolio.positions:
        print(
            f"{position.symbol} | "
            f"{position.name} | "
            f"qty={position.quantity} | "
            f"avg={position.average_price:,.0f} | "
            f"current={position.current_price:,.0f} | "
            f"value={position.market_value:,.0f} | "
            f"return={position.profit_loss_pct}% | "
            f"weight={position.weight:.4f}"
        )

    assert portfolio.total_value >= 0
    assert portfolio.cash == 0.0
    assert isinstance(portfolio.positions, list)

    for position in portfolio.positions:
        assert 0 <= position.weight <= 1
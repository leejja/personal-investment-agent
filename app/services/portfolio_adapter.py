from app.models.portfolio import PortfolioContext, PortfolioPosition
from app.services.kiwoom import KiwoomAccountBalance, KiwoomAccountPosition


class PortfolioAdapter:
    @staticmethod
    def from_kiwoom_position(
        position: KiwoomAccountPosition,
    ) -> PortfolioPosition:
        return PortfolioPosition(
            symbol=position.stock_code,
            name=position.stock_name,
            quantity=position.quantity,
            average_price=float(position.average_price),
            current_price=float(position.current_price),
            market_value=float(position.evaluation_amount),
            profit_loss=float(position.profit_loss),
            profit_loss_pct=position.return_rate,
            weight=position.portfolio_weight / 100.0,
        )

    @classmethod
    def from_kiwoom_balance(
        cls,
        balance: KiwoomAccountBalance,
    ) -> PortfolioContext:
        positions = [
            cls.from_kiwoom_position(position)
            for position in balance.positions
        ]

        return PortfolioContext(
            total_value=float(balance.total_evaluation_amount),
            cash=0.0,
            positions=positions,
        )
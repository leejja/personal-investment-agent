from enum import Enum

from pydantic import BaseModel, Field

from app.models.market import MarketAnalysis
from app.models.portfolio import PortfolioContext
from app.models.stock import StockAnalysis
from app.models.strategy import StrategyResult


class Intent(str, Enum):
    MARKET_ONLY = "market_only"
    STOCK_RESEARCH = "stock_research"
    PORTFOLIO_STRATEGY = "portfolio_strategy"


class SupervisorResult(BaseModel):
    intent: Intent
    resolved_symbols: list[str] = Field(default_factory=list)

    market_analysis: MarketAnalysis | None = None
    stock_analyses: list[StockAnalysis] = Field(default_factory=list)
    portfolio_context: PortfolioContext | None = None
    strategy_result: StrategyResult | None = None

    # 개별 종목 Stock Research 실패 등, 요청 전체를 실패시키지는 않지만
    # 사용자에게 투명하게 알려야 하는 부분 실패 기록("005930: ...").
    skipped: list[str] = Field(default_factory=list)

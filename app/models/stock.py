from enum import Enum

from pydantic import BaseModel, Field

from app.models.common import AnalysisConfidence, Evidence, RiskLevel


class ScenarioType(str, Enum):
    BULL = "bull"
    BASE = "base"
    BEAR = "bear"


class StockPriceSnapshot(BaseModel):
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price: float
    change_pct: float | None = None
    volume: int | None = None


class FinancialSnapshot(BaseModel):
    revenue: float | None = None
    operating_profit: float | None = None
    net_income: float | None = None

    per: float | None = None
    pbr: float | None = None
    roe: float | None = None


class StockScenario(BaseModel):
    scenario: ScenarioType
    thesis: str = Field(min_length=1)
    target_price: float | None = None
    probability: float | None = Field(default=None, ge=0, le=1)


class StockAnalysis(BaseModel):
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)

    price: StockPriceSnapshot | None = None
    financials: FinancialSnapshot | None = None

    investment_thesis: str = Field(min_length=1)

    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    scenarios: list[StockScenario] = Field(default_factory=list)

    risk_level: RiskLevel
    confidence: AnalysisConfidence

    evidence: list[Evidence] = Field(default_factory=list)

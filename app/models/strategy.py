from enum import Enum

from pydantic import BaseModel, Field

from app.models.common import AnalysisConfidence, Evidence, RiskLevel


class InvestmentAction(str, Enum):
    BUY = "buy"
    ADD = "add"
    HOLD = "hold"
    REDUCE = "reduce"
    SELL = "sell"
    AVOID = "avoid"


class PositionRecommendation(BaseModel):
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)

    action: InvestmentAction

    current_weight: float | None = Field(default=None, ge=0, le=1)
    target_weight: float | None = Field(default=None, ge=0, le=1)

    rationale: str = Field(min_length=1)
    conditions: list[str] = Field(default_factory=list)


class StrategyResult(BaseModel):
    summary: str = Field(min_length=1)

    recommendations: list[PositionRecommendation] = Field(
        default_factory=list
    )

    portfolio_risk: RiskLevel
    confidence: AnalysisConfidence

    evidence: list[Evidence] = Field(default_factory=list)

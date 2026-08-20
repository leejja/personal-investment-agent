from enum import Enum

from pydantic import BaseModel, Field

from app.models.common import AnalysisConfidence, Evidence, RiskLevel


class MarketRegime(str, Enum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"


class MarketIndicator(BaseModel):
    name: str = Field(min_length=1)
    value: float
    unit: str | None = None
    change: float | None = None
    description: str | None = None


class MarketAnalysis(BaseModel):
    regime: MarketRegime
    risk_level: RiskLevel
    summary: str = Field(min_length=1)
    indicators: list[MarketIndicator] = Field(default_factory=list)
    confidence: AnalysisConfidence
    evidence: list[Evidence] = Field(default_factory=list)

from pydantic import BaseModel, Field

from app.models.common import AnalysisConfidence, RiskLevel
from app.models.discovery import Candidate
from app.models.market import MarketRegime
from app.models.strategy import InvestmentAction
from app.models.supervisor import Intent

# 이 파일의 모델들은 SupervisorResult(app/models/supervisor.py)의 순수
# 파생(read-only projection)이다. 여기 있는 어떤 필드도 새 투자 판단을
# 담지 않는다 — 예: target_weight/target_price 같이 "만들면 안 되는" 값은
# 아예 필드로 선언하지 않는다(실수로도 채울 수 없게). 조립은
# app/api/presentation.py의 순수 함수(build_presentation)만 담당하며, 이
# 파일이나 그 조립 함수 모두 LLM/외부 API를 호출하지 않는다.


class MarketSummary(BaseModel):
    regime: MarketRegime
    risk_level: RiskLevel
    summary: str
    confidence: AnalysisConfidence


class StockSummary(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    investment_thesis: str
    risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    confidence: AnalysisConfidence


class DiscoverySummary(BaseModel):
    candidate_count: int
    # Candidate 자체가 이미 최소 구조(symbol/name/market/sector/
    # matched_filters, 점수 없음)라 별도 요약 모델을 새로 만들지 않고
    # 그대로 재사용한다.
    candidates: list[Candidate] = Field(default_factory=list)


class RecommendationSummary(BaseModel):
    symbol: str
    name: str
    action: InvestmentAction
    current_weight: float | None = None
    rationale: str
    conditions: list[str] = Field(default_factory=list)


class PortfolioSummary(BaseModel):
    portfolio_risk: RiskLevel
    confidence: AnalysisConfidence
    summary: str
    recommendation_count: int
    recommendations: list[RecommendationSummary] = Field(default_factory=list)


class PresentationResult(BaseModel):
    intent: Intent
    headline: str | None = None

    market: MarketSummary | None = None
    stocks: list[StockSummary] = Field(default_factory=list)
    discovery: DiscoverySummary | None = None
    portfolio: PortfolioSummary | None = None

    skipped: list[str] = Field(default_factory=list)

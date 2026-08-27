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

    high_250d: float | None = None
    low_250d: float | None = None


class FinancialSnapshot(BaseModel):
    # 과거 연도 스냅샷(StockAnalysis.financial_history)에서는 채워지지
    # 않는다 — 그 해의 사업보고서가 어느 회계연도인지 표시하는 용도.
    business_year: str | None = None

    revenue: float | None = None
    operating_profit: float | None = None
    net_income: float | None = None

    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None

    # PER/PBR/ROE는 Kiwoom이 제공하는 "현재 시점" valuation 스냅샷에서만
    # 채워진다(StockAnalysis.financials). OpenDART는 과거 재무제표만
    # 제공하고 과거 시점의 시가총액/주가를 함께 주지 않으므로, 과거 연도의
    # PER/PBR/ROE는 계산 근거가 없다 — financial_history의 각 항목에서는
    # 항상 None으로 둔다(과거 valuation 지표를 추정/생성하지 않는다).
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
    # 최근 3개 사업연도 재무 추세(오래된 연도 → 최신 연도 순). 사업보고서
    # (report_code=11011) 기준으로만 채워지며, 데이터가 2개 연도 미만이면
    # 추세라 부를 근거가 없으므로 빈 리스트로 둔다.
    financial_history: list[FinancialSnapshot] = Field(default_factory=list)

    investment_thesis: str = Field(min_length=1)

    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    scenarios: list[StockScenario] = Field(default_factory=list)

    risk_level: RiskLevel
    confidence: AnalysisConfidence

    evidence: list[Evidence] = Field(default_factory=list)

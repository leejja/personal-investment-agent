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


# ============================== RE-01: Financial Features ==============================
#
# 아래 모델들은 Stock Research Agent가 이미 deterministic하게 계산하고
# 있던 값(app/agents/stock_research/analysis.py)을 machine-readable
# 구조로 노출하기 위한 것이다 — 새로운 계산식이나 새로운 투자 판단을
# 담지 않는다. 같은 값이 기존 Evidence(DeterministicFact.description)
# 텍스트와 동일한 계산 한 번에서 나온다(single source of truth,
# 2026-08-28 RE-01 dev-log 참고). PER/PBR/ROE는 여기 포함하지 않는다 —
# Kiwoom 현재 시점 스냅샷(FinancialSnapshot)이라는 기존 경계를 유지한다.


class FinancialTransition(str, Enum):
    """`_classify_yoy()`(app/agents/stock_research/analysis.py)가 실제로
    구분하는 손익 부호 전환/적자 규모 변화 케이스만 담는다 — 새 의미를
    추가하지 않는다."""

    LOSS_TO_PROFIT = "loss_to_profit"
    PROFIT_TO_LOSS = "profit_to_loss"
    LOSS_WIDENING = "loss_widening"
    LOSS_NARROWING = "loss_narrowing"
    LOSS_UNCHANGED = "loss_unchanged"


class FinancialTrendDirection(str, Enum):
    """`_classify_direction()`이 실제로 구분하는 2가지 단조 방향만 담는다.
    비단조/데이터 부족 등 방향을 판단하지 않는 경우는 이 값 대신
    `FinancialTrendEntry` 자체를 만들지 않는다(MIXED/FLAT 등 새 의미를
    추가하지 않는다)."""

    INCREASING = "increasing"
    DECREASING = "decreasing"


class FinancialMetric(str, Enum):
    """현재 deterministic analysis가 실제로 다루는 지표만 담는다. YoY는
    REVENUE/OPERATING_PROFIT/NET_INCOME만, Trend는 5개 전부를 사용한다
    (연도별 실제 생성 경로가 이 조합만 만들도록 analysis.py가 보장한다)."""

    REVENUE = "revenue"
    OPERATING_PROFIT = "operating_profit"
    NET_INCOME = "net_income"
    OPERATING_MARGIN = "operating_margin"
    NET_MARGIN = "net_margin"


class AnnualFinancialFeatures(BaseModel):
    # 원본 revenue/operating_profit/자산 등은 여기서 복제하지 않는다 —
    # 이미 financial_history(FinancialSnapshot)에 있다.
    business_year: str
    operating_margin: float | None = None
    net_margin: float | None = None
    debt_ratio: float | None = None


class FinancialYoYChange(BaseModel):
    metric: FinancialMetric
    latest_year: str
    previous_year: str
    # growth_pct/transition은 상호배타적이다 — 정상적인 부호 유지 변동만
    # growth_pct로, 부호 전환/적자 규모 변화는 transition으로 표현한다
    # (기존 _classify_yoy 분기와 동일). 전년 값이 0이거나 값이 없으면
    # 이 entry 자체를 만들지 않는다(기존 fact 생략 semantics와 동일).
    growth_pct: float | None = None
    transition: FinancialTransition | None = None


class FinancialTrendEntry(BaseModel):
    # 방향이 실제로 판단될 때만(3개 연도 모두 존재 + 완전 단조) 생성된다
    # — 그 외에는 리스트에 아예 나타나지 않는다.
    metric: FinancialMetric
    direction: FinancialTrendDirection


class FinancialFeatures(BaseModel):
    # 오래된 연도 → 최신 연도 순(financial_history와 동일한 관례). 최소
    # 1개 연도(당기)만 있어도 채워진다 — YoY/trend와 달리 margin/debt_ratio는
    # 단일 연도만으로 계산 가능한 기존 deterministic formula이기 때문이다.
    annual: list[AnnualFinancialFeatures] = Field(default_factory=list)
    # 2개 연도 이상일 때만 채워진다(YoY는 연도쌍이 필요).
    yoy: list[FinancialYoYChange] = Field(default_factory=list)
    # 3개 연도 모두 있고 완전 단조일 때만 채워진다(기존 3개년 연속
    # 상승/하락 판단과 동일 조건).
    trends: list[FinancialTrendEntry] = Field(default_factory=list)


class StockAnalysis(BaseModel):
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)

    price: StockPriceSnapshot | None = None
    financials: FinancialSnapshot | None = None
    # 최근 3개 사업연도 재무 추세(오래된 연도 → 최신 연도 순). 사업보고서
    # (report_code=11011) 기준으로만 채워지며, 데이터가 2개 연도 미만이면
    # 추세라 부를 근거가 없으므로 빈 리스트로 둔다.
    financial_history: list[FinancialSnapshot] = Field(default_factory=list)
    # RE-01: financial_history/financials의 raw 수치로부터 계산된
    # deterministic feature(margin/debt_ratio/YoY/3개년 방향성)를
    # machine-readable 구조로 노출한다. Recommendation Engine이
    # Evidence 텍스트를 파싱하거나 raw OpenDART/Kiwoom을 다시 호출하지
    # 않고 list[StockAnalysis]만으로 이 값을 소비할 수 있게 하기 위함이다
    # — 새 투자 판단이 아니라 기존 계산의 구조화일 뿐이다. 기존
    # StockAnalysis 생성 코드/테스트와의 backward compatibility를 위해
    # 기본값 None을 둔다(analyze()가 실제로 만드는 값은 항상
    # FinancialFeatures 인스턴스다 — None은 이 필드를 모르는 옛 호출부만
    # 위한 fallback).
    financial_features: FinancialFeatures | None = None

    investment_thesis: str = Field(min_length=1)

    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    scenarios: list[StockScenario] = Field(default_factory=list)

    risk_level: RiskLevel
    confidence: AnalysisConfidence

    evidence: list[Evidence] = Field(default_factory=list)

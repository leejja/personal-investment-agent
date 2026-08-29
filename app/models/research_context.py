"""RE-05 Recommendation Evaluation Boundary & Input Contract.

이 모듈은 `docs/dev-log/2026-08-29.md` §32/§33이 확정한 conceptual
pipeline의 **입력 경계**를 담는다:

    External/Vendor Models (Kiwoom/OpenDART/ECOS raw)
          v
    Source Adapters / Deterministic Normalization
    (app/agents/stock_research/analysis.py의 analyze() 등 -- 기존 코드,
     LLM 호출 이전 단계)
          v
    NormalizedResearchData          <-- 이 모듈, canonical evaluator input
          v
    FeatureEvaluator(Protocol)      <-- 이 모듈(interface skeleton만)
          v
    FeatureEvaluationResult[]       (app/models/recommendation.py, 기존)
          v
    ... Component / Core / Policy ...

**`NormalizedResearchData`의 canonical source는 vendor -> deterministic
normalization 단계이지 `StockAnalysis`가 아니다**(§33.1). `StockAnalysis`
(`app/models/stock.py`)는 같은 deterministic normalization 결과에 LLM
narrative(investment_thesis/catalysts/risks/scenarios)를 더해 만든
**sibling** 산출물이다 -- `StockAnalysis`가 먼저 만들어지고 그로부터
`NormalizedResearchData`를 뽑아내는 방향이 아니다. 이 순서를 뒤집으면
LLM 생성 단계를 거친 뒤 그 안에서 "deterministic한 부분만" 다시 골라내야
하므로 LLM narrative가 실수로 섞여 들어올 표면이 생긴다 -- vendor
데이터에서 직접 만들면 그 표면 자체가 존재하지 않는다(§33.1 참고).

중요 -- 이 모듈이 하지 않는 것:
- feature scoring formula, normalization formula 구현 없음.
- threshold/weight/lookback/window 값 없음.
- evaluator/aggregator/policy 로직 없음(`FeatureEvaluator`는 method 본문이
  없는 `typing.Protocol`이다).
- vendor(Kiwoom/OpenDART/ECOS) 모델을 이 모듈 어디에서도 import하지 않는다
  -- 이 모듈 아래로는 항상 이미 정규화된 사실만 흐른다(§32.5).
- Portfolio/InvestorProfile을 포함하지 않는다 -- Stock Research evaluation은
  Portfolio Strategy evaluation과 다른 입력을 쓴다(§32.14).
- `StockAnalysis`를 이 모듈의 입력으로 쓰는 adapter를 구현하지 않는다 --
  그런 adapter가 존재하더라도 legacy compatibility 용도일 뿐 canonical
  production path가 아니다(§33.1).

기존 `app/models/stock.py`(`StockAnalysis` 등)와 `app/models/recommendation.py`
는 전혀 수정하지 않았다 -- 완전히 additive하며, 기존 타입(`StockPriceSnapshot`/
`FinancialSnapshot`/`FinancialFeatures`)을 그대로 재사용한다.
"""

from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from app.models.recommendation import (
    AvailabilityStatus,
    ComponentAssessment,
    ConfidenceAssessment,
    CoreAttractivenessAssessment,
    CorrelationRef,
    CoverageAssessment,
    EventOverlayReference,
    FeatureEvaluationResult,
    FeatureFamilyAssessment,
    FutureOpportunityEvidenceAssessment,
    MarketConfirmationAssessment,
    RiskAssessment,
)
from app.models.stock import FinancialFeatures, FinancialSnapshot, StockPriceSnapshot

# ============================== Scoped Fact Bundles ==============================
#
# 각 bundle은 "recommendation-ready normalized factual input"만 담는다 --
# attractiveness 판단(score/signal)은 여기 없다. 예:
#   PER = FinancialFacts/ValuationFacts의 factual 값
#   "PER이 매력적인가" = FeatureEvaluationResult(다른 모듈)의 몫.
#
# 모든 bundle이 `status: AvailabilityStatus`를 갖는다 -- source failure를
# 그냥 빈 필드로 흘리지 않고 구조적으로 보존하기 위함이다(§32.18).


class FinancialFacts(BaseModel):
    """OpenDART 기반 재무 사실. 기존 `FinancialSnapshot`/`FinancialFeatures`를
    그대로 재사용한다 -- 새 계산식을 만들지 않는다."""

    status: AvailabilityStatus
    current: FinancialSnapshot | None = None
    # 오래된 연도 -> 최신 연도 순(기존 StockAnalysis.financial_history와
    # 동일 관례).
    history: list[FinancialSnapshot] = Field(default_factory=list)
    features: FinancialFeatures | None = None
    warnings: list[str] = Field(default_factory=list)


class ValuationFacts(BaseModel):
    """Kiwoom 기반 현재 시점 valuation 사실. `market_cap`/`free_float_ratio`는
    RE-05 Data Verification(dev-log §26.5)에서 semantic까지 검증됐지만
    서비스 코드에는 아직 파싱되지 않은 상태(Implementation Gap)라 여기서도
    항상 None일 수 있다 -- 그 자체가 `status=UNAVAILABLE`로 표현된다."""

    status: AvailabilityStatus
    market_cap: float | None = None
    market_cap_unit: str | None = None
    free_float_ratio: float | None = None
    warnings: list[str] = Field(default_factory=list)


class FlowFacts(BaseModel):
    """Investor Flow 사실(Kiwoom `ka10059`/`ka10061` 계열). V1 Feature Set
    (dev-log §29.2)에서 raw는 확보됐으나 서비스 코드는 아직 없다
    (Implementation Gap) -- v1 현재는 `status=UNAVAILABLE`로 항상 비어
    있는 것이 정상이다. 필드 구조만 이번에 확정한다."""

    status: AvailabilityStatus
    daily_net_flow_ref: str | None = None  # source reference, 전체 series를 복제하지 않음
    period_aggregate_ref: str | None = None
    warnings: list[str] = Field(default_factory=list)


class PriceHistoryReference(BaseModel):
    """OHLCV historical의 **reference**만 담는다 -- 수백~수천 행의 시계열
    자체를 이 모델에 복제하지 않는다(source 재조회 경로를 가리킬 뿐).
    adjusted-price 안전성은 dev-log §28.8/§29.5에서 여전히
    VERIFICATION_REQUIRED다 -- 그 사실을 `adjusted_price_verified`로
    구조적으로 표현한다."""

    status: AvailabilityStatus
    source_ref: str | None = None
    available_from: datetime | None = None
    available_to: datetime | None = None
    adjusted_price_verified: bool = False
    warnings: list[str] = Field(default_factory=list)


class BenchmarkReference(BaseModel):
    """KOSPI/KOSDAQ 등 시장 벤치마크 reference(ECOS, Market Agent가 이미
    사용 중)."""

    status: AvailabilityStatus
    benchmark_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ForwardFacts(BaseModel):
    """§27.1/§27.2/§29.4가 확정한 대로, v1은 Forward Component에 usable
    input이 없다 -- 이 bundle은 **의도적으로 거의 항상 비어 있다**.
    `status=UNAVAILABLE`이 v1의 정상 상태이며, 이는 버그가 아니다."""

    status: AvailabilityStatus = AvailabilityStatus.UNAVAILABLE
    warnings: list[str] = Field(default_factory=list)


# ============================== NormalizedResearchData ==============================


class ResearchIdentity(BaseModel):
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)


class NormalizedResearchData(BaseModel):
    """§32.3/§32.4/§33.1 -- FeatureEvaluator의 canonical input(Option B).
    이 모델은 **사실(fact)만** 담는다 -- attractiveness 평가, score, signal은
    여기 없다(그건 `FeatureEvaluationResult`의 몫).

    **Canonical source는 vendor 데이터의 deterministic normalization
    단계**(`app/agents/stock_research/analysis.py`의 `analyze()`가 만드는
    `DeterministicAnalysisResult`와 동급 -- LLM 호출 이전)다. 향후 adapter/
    builder(미구현)는 이 deterministic 단계의 출력에서 이 모델을 조립해야
    하며, **`StockAnalysis`에서 값을 역추출하는 방식을 canonical 경로로
    쓰지 않는다**(§33.1).

    `StockAnalysis`(`app/models/stock.py`)와 관계: 이 모델을 대체하지도,
    `StockAnalysis`가 이 모델의 입력이 되지도 않는다 -- 둘은 **같은
    deterministic normalization 결과의 sibling 산출물**이다(`StockAnalysis`
    = deterministic 결과 + LLM narrative, 이 모델 = deterministic 결과만).
    `StockAnalysis`에서 deterministic field만 추출하는 legacy compatibility
    adapter가 필요할 수는 있지만(예: 이미 저장된 과거 `StockAnalysis`를
    재해석해야 하는 경우), 그것이 **production canonical path가 되어서는
    안 된다**(§33.1 Option C). 이 세션은 어떤 adapter도 구현하지 않는다."""

    identity: ResearchIdentity

    market_snapshot: StockPriceSnapshot | None = None
    financial_facts: FinancialFacts
    valuation_facts: ValuationFacts
    flow_facts: FlowFacts
    price_history: PriceHistoryReference
    benchmark: BenchmarkReference
    forward_facts: ForwardFacts

    as_of: datetime | None = None
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ============================== EvaluationContext ==============================


class EvaluationScope(str, Enum):
    """§32.14 -- 향후 evaluator가 어떤 범위까지 평가해야 하는지 지정할 때
    쓸 수 있는 최소 enum. numeric/threshold 값이 아니라 범위 선택만
    표현한다."""

    FULL = "full"
    FUNDAMENTAL_ONLY = "fundamental_only"
    VALUATION_ONLY = "valuation_only"


class EvaluationContext(BaseModel):
    """§32.14. Stock Research evaluation의 공통 context.

    **`PortfolioContext`/`InvestorProfile`을 의도적으로 포함하지 않는다**
    -- Stock Research evaluation != Portfolio Strategy evaluation(§32.14
    invariant). `policy_config_ref`는 실제 threshold/weight 값이 아니라
    참조 id일 뿐이다(`app.models.recommendation.PolicyConfigRef`와 동일한
    경계 원칙)."""

    symbol: str = Field(min_length=1)
    as_of: datetime

    analysis_id: str | None = None
    policy_config_ref: str | None = None
    benchmark_ref: str | None = None
    peer_group_ref: str | None = None

    requested_scope: EvaluationScope = EvaluationScope.FULL


# ============================== FeatureEvaluator (interface skeleton) ==============================


class FeatureEvaluator(Protocol):
    """§32.6. **구현 없음** -- method 본문이 없는 `typing.Protocol`이다.
    실제 evaluator 클래스는 이번 세션에서 만들지 않는다.

    책임(§32.6이 정의한 그대로): required factual input 확인, applicability
    확인, deterministic feature derivation, provenance 연결, availability/
    status 결정, `FeatureEvaluationResult` 생성. **normalized score
    formula는 여기 없다** -- `evaluate()`가 반환하는 `FeatureEvaluationResult
    .normalized_value`를 어떻게 계산할지는 이 Protocol의 관심사가 아니고,
    실제 구현 클래스가 나중에 결정한다."""

    @property
    def feature_id(self) -> str: ...

    def evaluate(
        self,
        data: NormalizedResearchData,
        context: EvaluationContext,
    ) -> FeatureEvaluationResult: ...


# ============================== RecommendationEvaluationState ==============================


class RecommendationEvaluationState(BaseModel):
    """§32.15/§33.2. Recommendation pipeline의 **progressively populated
    intermediate state container**다 -- "필요한 걸 전부 담은 최종 input"이
    아니라 각 pipeline 단계가 끝날 때마다 결과를 채워 넣는 누적 상태다.
    이름을 `RecommendationEvaluationInput`에서 `RecommendationEvaluationState`
    로 바꾼 이유가 이것이다(§33.2 Option B 채택) -- "input"이라는 이름은
    한 번에 다 채워 넣고 시작하는 required contract처럼 오해될 수 있었다.

    `context`/`normalized_research_data`만 **필수**다 -- 이 둘 없이는
    파이프라인이 시작될 수조차 없는 진짜 entry point이기 때문이다. 그
    아래(`feature_results` 이후)는 evaluator/aggregator/policy가 순서대로
    실행되며 하나씩 채워지는 것이 정상이라 전부 optional/default-empty로
    남긴다 -- 이 세션 시점에는 어떤 evaluator도 없어 실제로 채워지지
    않는다.

    동일 데이터를 중복 보관하지 않는다: 아래 필드들은 전부
    `app.models.recommendation`/이 모듈의 기존 타입을 그대로 참조할 뿐,
    이 모델이 별도 계산이나 사본을 만들지 않는다. 과도한 validator를
    추가하지 않았다 -- required/optional 구분만으로 충분하다고 판단했다."""

    context: EvaluationContext
    normalized_research_data: NormalizedResearchData

    feature_results: list[FeatureEvaluationResult] = Field(default_factory=list)
    family_assessments: list[FeatureFamilyAssessment] = Field(default_factory=list)
    component_assessments: list[ComponentAssessment] = Field(default_factory=list)

    core_attractiveness: CoreAttractivenessAssessment | None = None
    market_confirmation: MarketConfirmationAssessment | None = None
    risk: RiskAssessment | None = None
    coverage: CoverageAssessment | None = None
    confidence: ConfidenceAssessment | None = None
    event_overlay: EventOverlayReference | None = None
    future_opportunity_evidence: FutureOpportunityEvidenceAssessment | None = None
    correlation_metadata: list[CorrelationRef] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)

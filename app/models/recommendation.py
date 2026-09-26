"""RE-05 Recommendation / Scoring data model contract.

이 모듈은 RE-05(`docs/dev-log/2026-08-29.md` §24/§27/§29)가 정의한
Feature -> FeatureFamily -> Component -> Core/Market Confirmation ->
Recommendation Policy 흐름을 담기 위한 structured data contract다.

중요 -- 이 모듈이 하지 않는 것:
- evaluator/aggregator/scorer 구현 없음(계산 로직 없음, 순수 data contract).
- numeric threshold/weight/lookback/window 값 없음
  (PolicyConfigRef는 영역 이름만 나열하는 schema skeleton이다).
- LLM scoring 없음.
- production evaluation logic 없음
  (app/agents/* 등 기존 파이프라인과 아직 연결하지 않았다).

기존 `app/models/stock.py`의 `StockAnalysis`/`FinancialSnapshot` 등은 전혀
수정하지 않았다 -- 이 모듈은 완전히 additive하며, `StockAnalysis`와의 관계는
향후 설계 과제로 남긴다(dev-log §30.15 참고).
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.models.common import RiskLevel
from app.models.evidence import EvidenceReference

# ============================== Shared / Provenance ==============================


class AvailabilityStatus(str, Enum):
    """§24.2(2.8)/§29의 Data Availability semantics. 다섯 상태는 서로
    대체 불가능하다:
        missing data     != neutral feature
        NOT_APPLICABLE   != unavailable
        UNAVAILABLE      != invalid
        ESTIMATED        != observed
    """

    AVAILABLE = "available"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    INVALID = "invalid"


class EvaluationBasis(str, Enum):
    """§24.2(2.6) Feature Evaluation Basis. 복수 basis를 가질 수 있으므로
    `FeatureEvaluationResult.evaluation_basis`는 list다."""

    ABSOLUTE = "absolute"
    PEER_RELATIVE = "peer_relative"
    HISTORICAL_RELATIVE = "historical_relative"
    MARKET_RELATIVE = "market_relative"


class Directionality(str, Enum):
    """higher_is_better/lower_is_better 같은 semantic metadata. numeric
    normalization formula와는 분리된 순수 의미 정보다."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    CONTEXT_DEPENDENT = "context_dependent"


class RequirementRole(str, Enum):
    """§8 Coverage — Feature 하나가 소속 Component/Family에서 갖는 요구
    수준. `CoverageAssessment`의 available/missing 리스트가 이 role별로
    나뉜다."""

    REQUIRED = "required"
    IMPORTANT = "important"
    OPTIONAL = "optional"
    NOT_APPLICABLE = "not_applicable"


class Provenance(BaseModel):
    """공통 lineage structure. 각 model이 필드를 중복 선언하지 않도록 이
    구조를 재사용한다.

    RE-04 §7 AS_OF invariant("published_at > analysis.as_of인 evidence는
    사용하지 않는다")를 지원하기 위해 as_of/published_at/effective_at을
    분리한다. 이 모듈은 그 invariant를 "표현 가능"하게만 하고 실제로
    강제하지 않는다 -- 강제는 evaluator/policy 구현 시점의 책임이다.
    """

    source: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)

    formula_id: str | None = None
    formula_version: str | None = None
    policy_version: str | None = None

    as_of: datetime | None = None
    published_at: datetime | None = None
    effective_at: datetime | None = None
    retrieved_at: datetime | None = None

    # Evidence Identity Preservation: 이 결과가 나타내는 값의 typed evidence reference
    # (`app.models.evidence`). 위의 result-level 필드(source / evidence_ids / derived_from /
    # published_at / retrieved_at 등)는 재정의하지 않는다 — 정리는 OPEN(§7.10).
    evidence: list[EvidenceReference] = Field(default_factory=list)


class PolicyConfigRef(BaseModel):
    """§19 PolicyConfig Boundary — semantic result(이 모듈의 model들)와
    calibrated policy config를 구분하기 위한 schema skeleton이다.
    `config_domains`는 향후 PolicyConfig가 다룰 "영역 이름"만 나열할 뿐,
    실제 threshold/weight 값은 이 모듈 어디에도 존재하지 않는다."""

    version: str | None = None
    calibration_dataset_version: str | None = None
    calibration_period: str | None = None

    config_domains: list[str] = Field(
        default_factory=lambda: [
            "feature_normalization_config",
            "feature_weights",
            "family_weights",
            "component_weights",
            "signal_thresholds",
            "risk_policy",
            "coverage_policy",
            "confidence_policy",
            "correlation_policy",
            "recommendation_boundaries",
        ]
    )


# ============================== Data Sufficiency Layer ==============================
#
# Coverage/Confidence는 Feature Family/Component/Core/StockOpportunityAssessment
# 전 layer가 공유하는 개념이라, Feature Layer보다 먼저 정의한다(§8/§9).


class CoverageStatus(str, Enum):
    """critical-path sufficiency 자체를 표현하는 상태 -- percentage를
    decision authority로 쓰지 않는다(§8)."""

    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


class CoverageAssessment(BaseModel):
    """§8. Coverage != Confidence(§9). percentage 없이도 critical-path
    sufficiency를 표현할 수 있도록 설계했다 -- `coverage_percentage`는
    참고용일 뿐 판단 근거로 쓰지 않는다."""

    available_required: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    available_important: list[str] = Field(default_factory=list)
    missing_important: list[str] = Field(default_factory=list)
    optional_available: list[str] = Field(default_factory=list)
    optional_missing: list[str] = Field(default_factory=list)
    not_applicable: list[str] = Field(default_factory=list)

    critical_path_satisfied: bool
    coverage_status: CoverageStatus

    # 참고용 -- decision authority로 사용하지 않는다(§8 명시).
    coverage_percentage: float | None = Field(default=None, ge=0, le=1)

    source_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConfidenceFactor(str, Enum):
    VERIFICATION_STRENGTH = "verification_strength"
    FACT_COMPLETENESS = "fact_completeness"
    INFERENCE_SUPPORT = "inference_support"
    SOURCE_INDEPENDENCE = "source_independence"
    COUNTER_EVIDENCE = "counter_evidence"


class ConfidenceLevel(str, Enum):
    """RE-05 §24.9 Confidence semantics 전용 4-level enum이다.

    기존 `app/models/common.py`의 `AnalysisConfidence`(HIGH/MEDIUM/LOW,
    UNKNOWN 없음)를 재사용하지 않고 별도로 정의했다 -- Stock/Market/
    Portfolio Agent v1의 confidence는 항상 결정론적으로 부여돼 "insufficient
    basis" 상태가 없지만, RE-05는 `LOW != UNKNOWN`을 구조적으로 요구한다
    (§24.9). 기존 enum을 확장해 값을 추가하면 기존 3개 Agent의 기존
    contract를 건드리게 되므로, 새 enum을 만드는 쪽이 additive하다."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ConfidenceFactorAssessment(BaseModel):
    factor: ConfidenceFactor
    note: str | None = None


class ConfidenceAssessment(BaseModel):
    """§9. Coverage와 완전히 분리한다. "unsupported critical assumption이
    있으면 HIGH를 허용하지 않는다"는 policy는 이 model이 아니라 향후 policy
    layer가 적용한다 -- 이 model은 그 사실(critical_assumptions/
    unsupported_assumptions)을 표현만 하고 강제하지 않는다."""

    level: ConfidenceLevel
    factor_assessments: list[ConfidenceFactorAssessment] = Field(default_factory=list)

    critical_assumptions: list[str] = Field(default_factory=list)
    unsupported_assumptions: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)


# ============================== Component enum ==============================


class Component(str, Enum):
    """§24.4/§27.1 -- Canonical Core는 FUNDAMENTAL/VALUATION/FORWARD/FLOW
    4개뿐이다. MARKET_CONFIRMATION은 이 enum에는 존재하지만
    `CANONICAL_CORE_COMPONENTS`에는 없다 -- Core 밖이며 별도
    `MarketConfirmationAssessment`로 다룬다(§12)."""

    FUNDAMENTAL = "fundamental"
    VALUATION = "valuation"
    FORWARD = "forward"
    FLOW = "flow"
    MARKET_CONFIRMATION = "market_confirmation"


CANONICAL_CORE_COMPONENTS: tuple[Component, ...] = (
    Component.FUNDAMENTAL,
    Component.VALUATION,
    Component.FORWARD,
    Component.FLOW,
)


# ============================== Feature Layer ==============================


class FeatureValue(BaseModel):
    """raw 또는 derived 수치 하나. `normalized_value`/`score`와 반드시
    분리한다(§2 invariant: raw numeric value != normalized feature result
    != component score)."""

    value: float | None = None
    unit: str | None = None
    is_derived: bool = False


class FeatureEvaluationResult(BaseModel):
    """§2. 하나의 Feature 평가 결과. §24.2가 정의한 semantics를 그대로
    담는다 -- normalization formula 자체는 여기 없다(numeric policy 분리,
    `normalized_value`는 결과값 slot일 뿐 계산식이 아니다)."""

    feature_id: str = Field(min_length=1)
    component: Component
    feature_family: str = Field(min_length=1)

    raw: FeatureValue | None = None
    derived: FeatureValue | None = None

    availability: AvailabilityStatus
    requirement_role: RequirementRole | None = None
    evaluation_basis: list[EvaluationBasis] = Field(default_factory=list)
    directionality: Directionality | None = None

    normalized_value: float | None = None

    applicability_review_required: bool = False
    applicability_note: str | None = None

    provenance: Provenance = Field(default_factory=Provenance)
    warnings: list[str] = Field(default_factory=list)


# ============================== Feature Family Layer ==============================


class FeatureFamilyStatus(str, Enum):
    """Family 단위 evaluability. Coverage/Confidence와는 별개 축이다."""

    EVALUATED = "evaluated"
    PARTIALLY_EVALUATED = "partially_evaluated"
    NOT_EVALUATED = "not_evaluated"


class FeatureFamilyAssessment(BaseModel):
    """§4. intra-component correlation을 완화하는 중간 semantic layer
    (§24.2 2.9). `family_score`는 optional/nullable -- aggregator 자체는
    이 모듈에서 구현하지 않는다."""

    family_id: str = Field(min_length=1)
    component: Component

    feature_results: list[FeatureEvaluationResult] = Field(default_factory=list)
    family_status: FeatureFamilyStatus

    family_score: float | None = None

    coverage: CoverageAssessment | None = None
    confidence: ConfidenceAssessment | None = None

    warnings: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)


# ============================== Component Layer ==============================


class ComponentSignal(str, Enum):
    """§7(RE-05 §24.3). Score와 분리한다.
        NEUTRAL = sufficient evidence + no meaningful directional dominance
        UNKNOWN = insufficient basis
    Missing -> UNKNOWN. Missing -> NEUTRAL은 금지(구조적으로는 막지 않지만
    이 모듈 전체의 명시적 원칙이다)."""

    STRONG_POSITIVE = "strong_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    STRONG_NEGATIVE = "strong_negative"
    UNKNOWN = "unknown"


class ComponentStatus(str, Enum):
    EVALUATED = "evaluated"
    PARTIALLY_EVALUATED = "partially_evaluated"
    UNAVAILABLE = "unavailable"


class ComponentAssessment(BaseModel):
    """§5/§6. ComponentScore는 "특정 investment dimension에 대해 현재
    이용 가능한 evidence가 나타내는 dimensionless continuous standardized
    attractiveness representation"일 뿐이다 -- expected return/probability/
    confidence/coverage/recommendation이 아니다(§6 invariant).

    Forward unavailable 시:
        score=None, signal=ComponentSignal.UNKNOWN,
        coverage.coverage_status=CoverageStatus.INSUFFICIENT
    를 그대로 표현한다 -- **score를 0으로 넣지 않는다**(`score: float | None`,
    기본값도 None이지 0이 아니다)."""

    component: Component
    family_assessments: list[FeatureFamilyAssessment] = Field(default_factory=list)

    # dimensionless, numeric scale 미정 -- 어떤 범위/단위를 쓸지는
    # PolicyConfig 몫이다. None이 곧 "unavailable"을 뜻한다(0이 아님).
    score: float | None = None
    signal: ComponentSignal

    coverage: CoverageAssessment
    confidence: ConfidenceAssessment

    status: ComponentStatus

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    provenance: Provenance = Field(default_factory=Provenance)


# ============================== Risk ==============================


class RiskDimension(str, Enum):
    FINANCIAL = "financial"
    EARNINGS_BUSINESS = "earnings_business"
    LIQUIDITY_TRADABILITY = "liquidity_tradability"
    VOLATILITY_DRAWDOWN = "volatility_drawdown"
    STRUCTURAL = "structural"
    EVENT_RISK = "event_risk"


class RiskFactor(BaseModel):
    dimension: RiskDimension
    description: str = Field(min_length=1)
    # Event Risk는 Event Layer의 동일 risk를 참조만 한다 -- Event Overlay에서
    # 한 번, Broader Risk에서 또 한 번 독립 penalty로 이중 계산하지 않는다
    # (RE-04 §6/RE-05 §24.7).
    event_risk_ref: str | None = None


class RiskAssessment(BaseModel):
    """§16. Component Score에서 빼는 구조로 만들지 않는다 --
    `RiskAssessment`는 독립된 contract이며 Recommendation Policy에서
    constraint/guardrail/counter-thesis로만 소비된다(numeric penalty
    필드가 이 model에 없다).

    missing coverage != high risk, low confidence != high risk -- risk_level은
    evidence 부족과 별개 축이다(coverage/confidence가 낮아도 risk_level은
    독립적으로 아무 값이나 가질 수 있다).

    risk_level은 nullable이다. `None`은 **"LOW"가 아니라 "risk severity를
    판단할 근거(evidence)가 부족해 분류하지 못함"**을 뜻한다 -- LOW risk와
    UNKNOWN/insufficient basis는 반드시 구분돼야 한다. 기존
    `app/models/common.py`의 `RiskLevel`(LOW/MEDIUM/HIGH) enum 자체는
    변경하지 않았다(기존 Agent contract 보호) -- 대신 이 필드를
    `RiskLevel | None`으로 선언해 "값 자체가 없음"으로 UNKNOWN을
    표현한다."""

    # 기존 app/models/common.py의 RiskLevel(LOW/MEDIUM/HIGH)은 그대로
    # 유지한다(변경 없음) -- 대신 이 필드를 nullable로 선언해 "risk severity
    # 미분류" 상태를 표현한다. None != LOW, 반드시 구분해서 사용해야 한다.
    risk_level: RiskLevel | None = None

    risk_factors: list[RiskFactor] = Field(default_factory=list)
    mitigating_factors: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

    coverage: CoverageAssessment
    confidence: ConfidenceAssessment

    warnings: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)


# ============================== Event Overlay Reference ==============================


class EventRole(str, Enum):
    """§23.3(RE-04) -- Role은 Event가 아니라 Interpretation에 속한다. 여기서는
    reference 구조의 필드로만 존재하며, 이 enum이 RE-04의 InvestmentEvent
    자체를 재정의하지 않는다.

    Canonical ownership TODO: 이 enum과 `PricedInLevel`은 이 모듈
    (`app/models/recommendation.py`)이 **소유하지 않는다.** RE-04 Amendment 1
    (dev-log §23.3/§23.4)이 Role/Priced-In의 semantic을 이미 확정했지만,
    이 repository에는 아직 RE-04 Event 전용 production model이 없다 -- 그래서
    지금은 이 참조 layer가 임시로 값을 들고 있다. **RE-04 Event domain
    model이 실제로 구현되면 이 두 enum은 그 모듈에서 import하는 것으로
    교체돼야 하며, 여기서 두 번째 source of truth로 독립 진화해서는
    안 된다.** 이번 audit에서 Event architecture를 새로 설계하지 않았다 --
    이 TODO만 명시적으로 남긴다."""

    CATALYST = "catalyst"
    HEADWIND = "headwind"
    RISK = "risk"
    CONTEXT = "context"


class PricedInLevel(str, Enum):
    """Canonical ownership TODO: `EventRole`과 동일 -- RE-04 Event domain
    model이 구현되면 그쪽에서 import하도록 교체돼야 한다."""

    LOW = "low"
    PARTIAL = "partial"
    HIGH = "high"
    UNKNOWN = "unknown"


class EventInterpretationRef(BaseModel):
    """하나의 InvestmentInterpretation을 가리키는 reference + summary. Event
    Layer 전체를 복사하지 않는다(§14) -- `interpretation_id`로 원본을
    가리키고 Recommendation Policy가 참조할 최소 summary 필드만 중복한다.

    materiality/direction/realization/temporal_relevance는 RE-04
    Amendment 1(dev-log §23.1/§23.4)이 이미 semantic으로 확정한 개념이지만
    아직 이 repository에 Python enum으로 구현돼 있지 않다 -- 이번
    RE-05 세션에서 RE-04의 Event enum을 새로 만들지 않고 `str | None`으로만
    참조한다(RE-04 architecture를 이 세션에서 확장하지 않기 위함). `role`/
    `priced_in`(위 `EventRole`/`PricedInLevel`)도 같은 이유로 canonical
    ownership이 RE-04 Event domain model로 아직 이전되지 않은 임시
    참조다 -- 각 enum의 docstring TODO 참고.

    중요: 이 model에 numeric score 필드가 없다 -- Event가 ComponentScore에
    직접 더해지는 경로를 구조적으로 차단한다(§14 금지 사항)."""

    interpretation_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)

    role: EventRole
    materiality: str | None = None
    direction: str | None = None
    realization: str | None = None
    temporal_relevance: str | None = None
    confidence: ConfidenceLevel | None = None
    priced_in: PricedInLevel | None = None

    summary: str | None = None


class EventOverlayReference(BaseModel):
    """§14. Core Component와 병렬 input -- Component score를 직접 mutate하지
    않는다. numeric bonus/penalty 필드가 이 model에 없다는 것 자체가
    architecture 준수의 근거다(§14 금지: "Catalyst + 15 points처럼 arbitrary
    점수를 더하지 않는다")."""

    active_catalyst_refs: list[EventInterpretationRef] = Field(default_factory=list)
    active_headwind_refs: list[EventInterpretationRef] = Field(default_factory=list)
    active_risk_refs: list[EventInterpretationRef] = Field(default_factory=list)
    context_refs: list[EventInterpretationRef] = Field(default_factory=list)
    priced_in_refs: list[EventInterpretationRef] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)


# ============================== Future-Opportunity Evidence ==============================


class EvidencePathAvailability(str, Enum):
    """§27.3 Future-Opportunity Evidence Requirement의 A/B 경로가 실제로
    존재하는지 여부. RE-04 failure semantics(dev-log §23.7/§27:
    `Empty Result != No Event`, `Failure != Empty`, `Unknown != False`)를
    반영해 tri-state로 분리한다 -- bool 하나로는 "genuinely absent"(경로가
    실제로 확인됐고 없음)와 "source failure로 확인 자체를 못함"이 False
    하나로 collapse된다.

    기존 `AvailabilityStatus`(Feature 평가 전용, AVAILABLE/ESTIMATED/
    UNAVAILABLE/NOT_APPLICABLE/INVALID)를 재사용하지 않았다 -- 그 enum에는
    UNKNOWN이 없고, ESTIMATED/NOT_APPLICABLE/INVALID는 "evidence path
    존재 여부"라는 이 맥락의 의미와 맞지 않는다. 서로 다른 semantic
    질문에 같은 enum을 억지로 재사용하면 두 맥락이 뒤섞인다고 판단했다."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class RequirementSatisfaction(str, Enum):
    """`FutureOpportunityEvidenceAssessment.requirement_satisfied`용
    tri-state. `UNKNOWN`은 "만족하지 않음(False)"이 아니라 "판단에 필요한
    근거 자체가 부족함"을 뜻한다 -- policy가 A/B 판단을 아직 못 내린
    상태와, A/B를 확인했는데 둘 다 실패한 상태를 구분한다."""

    SATISFIED = "satisfied"
    NOT_SATISFIED = "not_satisfied"
    UNKNOWN = "unknown"


class FutureOpportunityEvidenceAssessment(BaseModel):
    """§15/§27.3. Decision Eligibility의 future-opportunity evidence
    requirement: A(reliable Forward evidence) OR B(qualifying future-facing
    Event evidence) 중 하나로 충족.

    `forward_path_availability`/`event_path_availability`는 각각
    `EvidencePathAvailability`(AVAILABLE/UNAVAILABLE/UNKNOWN)다 --
    "이 경로를 확인했더니 없더라"(UNAVAILABLE)와 "이 경로 자체를 아직
    확인하지 못했다"(UNKNOWN, 예: source failure)를 구분해서 표현한다.

    `requirement_satisfied`는 policy가 A/B 중 하나 충족 여부를 판단한
    "결과"를 담는 `RequirementSatisfaction` 필드일 뿐 -- 이 모듈이 그
    판단 로직(sufficient Materiality/adequate Confidence의 numeric
    boundary 포함)을 구현하지 않는다. 그 boundary는 여전히 OPEN이다
    (§27.3)."""

    forward_path_availability: EvidencePathAvailability
    event_path_availability: EvidencePathAvailability

    requirement_satisfied: RequirementSatisfaction = RequirementSatisfaction.UNKNOWN

    supporting_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ============================== Correlation Metadata ==============================


class CorrelationRelationship(str, Enum):
    SAME_CAUSAL_ORIGIN = "same_causal_origin"
    PARTIALLY_OVERLAPPING = "partially_overlapping"
    INDEPENDENT = "independent"
    UNKNOWN = "unknown"


class CorrelationRef(BaseModel):
    """§18(RE-05 §24.11 Step 10). numeric discount는 구현하지 않는다 --
    relationship과 provenance만 표현한다."""

    signal_refs: list[str] = Field(default_factory=list)
    relationship: CorrelationRelationship

    shared_evidence_refs: list[str] = Field(default_factory=list)
    shared_event_refs: list[str] = Field(default_factory=list)
    shared_impact_path_refs: list[str] = Field(default_factory=list)
    derived_dependency_refs: list[str] = Field(default_factory=list)

    note: str | None = None


# ============================== Core / Market Confirmation / Opportunity State ==============================


class CoreAttractivenessAssessment(BaseModel):
    """§11(RE-05 §24.4). Canonical Core = FUNDAMENTAL/VALUATION/FORWARD/FLOW,
    4-component 고정(§27.1 RESOLVED, 이 세션에서 변경하지 않음).
    `component_assessments`는 `aggregate_score`가 있어도 반드시 보존한다 --
    vector를 버리지 않는다.

    Forward가 UNKNOWN이어도 이 리스트에서 제거하지 않는다 -- 4개 Component
    전부를 담되 Forward 항목의 score만 None/signal만 UNKNOWN일 뿐이다.
    missing component를 zero-weight로 재정규화할지는 policy/calibration
    문제이며 이 모듈은 결정하지 않는다."""

    component_assessments: list[ComponentAssessment] = Field(default_factory=list)

    aggregate_score: float | None = None
    aggregate_signal: ComponentSignal | None = None

    dominant_strengths: list[str] = Field(default_factory=list)
    dominant_weaknesses: list[str] = Field(default_factory=list)

    coverage: CoverageAssessment | None = None
    confidence: ConfidenceAssessment | None = None

    warnings: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)


class MarketConfirmationRole(str, Enum):
    """§4(RE-05 §24.5)/§12. Market Confirmation은 Core에 포함되지 않고
    veto도 아니다 -- CONFIRMING/CONTRADICTING이어도 Opportunity State는
    policy가 결정한다(이 model이 스스로 결정하지 않는다)."""

    CONFIRMING = "confirming"
    NEUTRAL = "neutral"
    CONTRADICTING = "contradicting"
    UNKNOWN = "unknown"


class MarketConfirmationAssessment(BaseModel):
    """§12. Core 밖의 별도 top-level assessment -- `CoreAttractivenessAssessment`
    안에 nesting하지 않는다(구조적으로 분리해 Core에 포함되지 않음을
    표현한다)."""

    momentum: ComponentAssessment | None = None
    technical_confirmation: ComponentAssessment | None = None

    role: MarketConfirmationRole

    coverage: CoverageAssessment | None = None
    confidence: ConfidenceAssessment | None = None

    warnings: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)


class OpportunityState(str, Enum):
    """§13(RE-05 §24.6). Core x Market의 policy 결과 -- literal
    multiplication이 아니다(§24.5 금지: `CoreScore * MarketScore`).
    numeric boundary는 OPEN."""

    CONFIRMED_OPPORTUNITY = "confirmed_opportunity"
    EARLY_OPPORTUNITY = "early_opportunity"
    MOMENTUM_WITHOUT_CORE_SUPPORT = "momentum_without_core_support"
    CORE_MARKET_CONFLICT = "core_market_conflict"
    BALANCED = "balanced"
    DETERIORATING = "deteriorating"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


# ============================== StockOpportunityAssessment ==============================


class AssessmentStatus(str, Enum):
    ACTIONABLE = "actionable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class OpportunityClassification(str, Enum):
    """§17(RE-05 §24.12). `NEUTRAL != insufficient evidence`(그건 status가
    담당), `UNATTRACTIVE != SELL`(portfolio action은 별도 model)."""

    ATTRACTIVE = "attractive"
    NEUTRAL = "neutral"
    UNATTRACTIVE = "unattractive"


class DecisionReasons(BaseModel):
    primary_reasons: list[str] = Field(default_factory=list)
    counter_reasons: list[str] = Field(default_factory=list)
    signal_conflicts: list[str] = Field(default_factory=list)
    correlation_refs: list[CorrelationRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StockOpportunityAssessment(BaseModel):
    """§17. Stock Research의 최종 output -- RE-04 §10/dev-log §23.5의
    `StockOpportunityAssessment` contract를 실제 model로 구현한 것이다.

    invariant(model_validator로 양방향 모두 구조적으로 강제):
        status == INSUFFICIENT_EVIDENCE  =>  classification is None
        status == ACTIONABLE             =>  classification is not None

    다음은 이 model의 필드 목록 자체로 강제되는 invariant다(별도 코드
    없이 스키마만으로 성립):
        NEUTRAL != insufficient evidence
            (`status`와 `classification`이 분리된 필드이므로 혼동 불가)
        UNATTRACTIVE != SELL
            (`action`/`target_weight` 같은 portfolio 필드가 존재하지 않는다,
            이 양방향 invariant도 portfolio action과 무관하다)

    **이 model은 PortfolioActionRecommendation이 아니다** -- BUY/ADD/HOLD/
    REDUCE/EXIT 같은 portfolio action 필드를 의도적으로 포함하지 않는다
    (RE-04 §10/dev-log §23.5 책임 분리 그대로, 기존
    `app/models/strategy.py`의 `PositionRecommendation.action`과 절대
    합치지 않는다)."""

    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)

    status: AssessmentStatus
    classification: OpportunityClassification | None = None

    core_attractiveness: CoreAttractivenessAssessment | None = None
    market_confirmation: MarketConfirmationAssessment | None = None
    opportunity_state: OpportunityState | None = None

    coverage: CoverageAssessment
    confidence: ConfidenceAssessment
    risk: RiskAssessment | None = None

    event_overlay: EventOverlayReference | None = None
    future_opportunity_evidence: FutureOpportunityEvidenceAssessment | None = None

    reasons: DecisionReasons = Field(default_factory=DecisionReasons)

    as_of: datetime | None = None
    policy_version: str | None = None

    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _status_classification_invariant(self) -> "StockOpportunityAssessment":
        if (
            self.status == AssessmentStatus.INSUFFICIENT_EVIDENCE
            and self.classification is not None
        ):
            raise ValueError("classification must be null when status is INSUFFICIENT_EVIDENCE")
        if self.status == AssessmentStatus.ACTIONABLE and self.classification is None:
            raise ValueError("classification must be set when status is ACTIONABLE")
        return self

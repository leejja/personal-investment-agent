"""RE-05 두 번째 Fundamental FeatureEvaluator(Operating Margin) 테스트 +
`financial_facts.current`/`features` invariant audit 테스트.

`docs/dev-log/2026-08-29.md` §37이 이 슬라이스의 설계 결정(특히
financial_facts.current/features 결정 = LEGITIMATELY OPTIONAL)을 담는다.
numeric threshold/weight/window 테스트는 만들지 않는다.
"""

import inspect
from datetime import UTC, datetime

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.feature_registry import (
    FeatureApplicability,
    FeatureScopeStatus,
    get_feature_definition,
)
from app.evaluation.fundamental_evaluators import (
    OperatingMarginFeatureEvaluator,
    RoeFeatureEvaluator,
)
from app.evaluation.research_data_builder import build_normalized_research_data
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.evidence import FinancialFactsEvidence
from app.models.recommendation import AvailabilityStatus, Component
from app.models.research_context import EvaluationContext, FeatureEvaluator
from app.models.stock import (
    AnnualFinancialFeatures,
    FinancialFeatures,
    FinancialSnapshot,
    StockPriceSnapshot,
)
from tests.evidence_fixtures import attach_fixture_evidence

_OM_ID = "fundamental.profitability.operating_margin"
_AS_OF = datetime(2026, 8, 29, tzinfo=UTC)


def _context() -> EvaluationContext:
    return EvaluationContext(symbol="005930", as_of=_AS_OF)


def _result_with_annual(
    annual: list[AnnualFinancialFeatures],
    roe: float | None = 12.3,
) -> DeterministicAnalysisResult:
    return attach_fixture_evidence(DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", roe=roe),
        financial_features=FinancialFeatures(annual=annual),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    ))


# ============================== §37.1/§37.2/§37.3: financial_facts.current/features invariant ==============================


def test_deterministic_analysis_result_financials_is_never_none_by_type():
    """DeterministicAnalysisResult.financials는 애초에 non-Optional
    (FinancialSnapshot, `| None` 아님)이다 -- analyze()가 성공하면 이
    필드는 항상 채워진 객체다(빈 필드는 내부에서만 None일 수 있다)."""
    annotation = DeterministicAnalysisResult.model_fields["financials"].annotation
    assert annotation is FinancialSnapshot  # `FinancialSnapshot | None`이 아니다


def test_builder_always_populates_current_and_features_when_given_valid_result():
    """build_normalized_research_data()의 유일한 실제 production 경로에서
    current/features는 항상 채워진다 -- None이 아니다. 이것이 §37 audit의
    핵심 실측 근거다(추측이 아니라 실제 호출로 확인)."""
    result = _result_with_annual([AnnualFinancialFeatures(business_year="2025")])
    data = build_normalized_research_data(result, as_of=_AS_OF)

    assert data.financial_facts.current is not None
    assert data.financial_facts.features is not None


def test_financial_facts_current_and_features_remain_optional_in_schema():
    """§37 결정: financial_facts.current/features는 model 레벨에서는
    LEGITIMATELY OPTIONAL로 그대로 유지한다(Input Contract가 FROZEN이라
    destructive 변경을 하지 않았다) -- 실제로 None을 만들 수 있는지도
    확인한다(향후 soft-fail 빌더를 위한 여지)."""
    from app.models.research_context import FinancialFacts

    bundle = FinancialFacts(
        status=AvailabilityStatus.UNAVAILABLE,
        current=None,
        features=None,
        evidence=FinancialFactsEvidence(),
    )
    assert bundle.current is None
    assert bundle.features is None  # 스키마가 여전히 허용한다(변경 안 함)


def test_both_evaluators_defensively_handle_current_or_features_being_none():
    """current/features가 실제로 None인 (production 경로 밖의) state를
    두 evaluator 모두 안전하게 처리한다 -- 예외 없이 UNAVAILABLE을
    반환한다."""
    from app.models.research_context import (
        BenchmarkReference,
        FinancialFacts,
        FlowFacts,
        ForwardFacts,
        NormalizedResearchData,
        PriceHistoryReference,
        ResearchIdentity,
        ValuationFacts,
    )

    data = NormalizedResearchData(
        identity=ResearchIdentity(symbol="005930", name="삼성전자"),
        financial_facts=FinancialFacts(
            status=AvailabilityStatus.UNAVAILABLE,
            current=None,
            features=None,
            evidence=FinancialFactsEvidence(),
        ),
        valuation_facts=ValuationFacts(status=AvailabilityStatus.UNAVAILABLE),
        flow_facts=FlowFacts(status=AvailabilityStatus.UNAVAILABLE),
        price_history=PriceHistoryReference(status=AvailabilityStatus.UNAVAILABLE),
        benchmark=BenchmarkReference(status=AvailabilityStatus.UNAVAILABLE),
        forward_facts=ForwardFacts(),
        as_of=_AS_OF,
    )
    context = _context()

    roe_result = RoeFeatureEvaluator().evaluate(data, context)
    om_result = OperatingMarginFeatureEvaluator().evaluate(data, context)

    assert roe_result.availability == AvailabilityStatus.UNAVAILABLE
    assert om_result.availability == AvailabilityStatus.UNAVAILABLE


# ============================== Operating Margin V1 scope 확인 (§37.5) ==============================


def test_operating_margin_registry_entry_matches_frozen_v1_scope():
    definition = get_feature_definition(_OM_ID)
    assert definition.scope_status == FeatureScopeStatus.V1_REQUIRED
    assert definition.component == Component.FUNDAMENTAL
    assert definition.feature_family == "profitability"


def test_operating_margin_applicability_flags_financial_sector_review():
    """§26.2/§28.5에서 이미 확정된 "매출액 계정 없는 금융지주" 구조적
    제약을 반영해 REVIEW_REQUIRED로 분류돼야 한다(ROE의 UNIVERSAL과
    다르다)."""
    definition = get_feature_definition(_OM_ID)
    assert definition.applicability == FeatureApplicability.REVIEW_REQUIRED


# ============================== registry entry ==============================


def test_operating_margin_required_inputs_use_normalized_domain_path():
    definition = get_feature_definition(_OM_ID)
    for path in definition.required_inputs:
        assert not path.lower().startswith("kiwoom")
        assert not path.lower().startswith("opendart")
    assert definition.required_inputs == (
        "financial_facts.features.annual[latest].operating_margin",
    )


def test_operating_margin_registry_module_source_has_no_vendor_dependency():
    import app.evaluation.fundamental_evaluators as evaluator_module

    source = inspect.getsource(evaluator_module)
    forbidden = ("KiwoomStockInfo", "KeyFinancials", "app.services.", "app.mcp.")
    for name in forbidden:
        assert name not in source


# ============================== valid / missing Operating Margin ==============================


def test_evaluate_valid_operating_margin_returns_available_latest_year():
    """annual이 여러 연도를 담고 있으면 가장 최근(마지막) 연도 값을
    쓴다."""
    result = _result_with_annual(
        [
            AnnualFinancialFeatures(business_year="2023", operating_margin=10.0),
            AnnualFinancialFeatures(business_year="2024", operating_margin=15.0),
            AnnualFinancialFeatures(business_year="2025", operating_margin=18.5),
        ]
    )
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = OperatingMarginFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.raw.value == 18.5
    assert outcome.raw.unit == "percent"
    assert outcome.feature_id == _OM_ID
    assert outcome.component == Component.FUNDAMENTAL
    assert outcome.feature_family == "profitability"


def test_evaluate_missing_operating_margin_empty_annual_returns_unavailable():
    result = _result_with_annual([])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = OperatingMarginFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.UNAVAILABLE
    assert outcome.raw is None
    assert outcome.warnings != []


def test_evaluate_missing_operating_margin_latest_year_none_returns_unavailable():
    """annual은 있지만 최신 연도의 operating_margin 자체가 None(예:
    revenue=0)인 경우도 UNAVAILABLE이다."""
    result = _result_with_annual(
        [AnnualFinancialFeatures(business_year="2025", operating_margin=None)]
    )
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = OperatingMarginFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.UNAVAILABLE


# ============================== provenance / as_of ==============================


def test_operating_margin_provenance_as_of_matches_context():
    result = _result_with_annual(
        [AnnualFinancialFeatures(business_year="2025", operating_margin=18.5)]
    )
    data = build_normalized_research_data(result, as_of=_AS_OF)
    context = _context()
    outcome = OperatingMarginFeatureEvaluator().evaluate(data, context)

    assert outcome.provenance.as_of == context.as_of
    assert outcome.provenance.source == "OpenDART"


# ============================== normalized_value / signal semantics ==============================


def test_operating_margin_normalized_value_is_none_even_when_available():
    """AVAILABLE != normalized score already calibrated -- ROE와 동일한
    축 분리를 Operating Margin에서도 확인한다."""
    result = _result_with_annual(
        [AnnualFinancialFeatures(business_year="2025", operating_margin=99.9)]
    )
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = OperatingMarginFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.normalized_value is None


def test_operating_margin_evaluator_applies_no_numeric_comparison_to_raw_value():
    """양수라는 이유만으로 POSITIVE signal을 만들지 않는다 -- 애초에 이
    evaluator는 `signal` 필드 자체를 설정하지 않는다(FeatureEvaluationResult
    에 signal 필드가 없다 -- 그건 ComponentAssessment 몫)."""
    source = inspect.getsource(OperatingMarginFeatureEvaluator.evaluate)
    compact = source.replace(" ", "").replace("\n", "")
    for pattern in (
        "operating_margin>",
        "operating_margin<",
        ">operating_margin",
        "<operating_margin",
    ):
        assert pattern not in compact
    assert "signal" not in source.lower()


def test_feature_evaluation_result_has_no_signal_field():
    """FeatureEvaluationResult 자체에 signal 필드가 없다 -- Component
    레벨(ComponentAssessment.signal)에서만 존재한다. 두 evaluator 모두
    이 경계를 넘지 않는다."""
    from app.models.recommendation import FeatureEvaluationResult

    assert "signal" not in FeatureEvaluationResult.model_fields


# ============================== recommendation/portfolio 없음 ==============================


def test_operating_margin_result_has_no_recommendation_or_portfolio_fields():
    result = _result_with_annual(
        [AnnualFinancialFeatures(business_year="2025", operating_margin=18.5)]
    )
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = OperatingMarginFeatureEvaluator().evaluate(data, _context())

    field_names = set(type(outcome).model_fields.keys())
    for forbidden in ("action", "target_weight", "classification", "recommendation"):
        assert forbidden not in field_names


# ============================== Protocol compatibility ==============================


def test_operating_margin_evaluator_satisfies_feature_evaluator_protocol_shape():
    """RoeFeatureEvaluator와 동일하게 FeatureEvaluator Protocol이 요구하는
    `feature_id` 속성과 `evaluate(data, context)` 메서드를 구조적으로
    만족한다 -- Protocol 자체는 변경하지 않았다."""
    evaluator = OperatingMarginFeatureEvaluator()
    assert hasattr(evaluator, "feature_id")
    assert callable(evaluator.evaluate)

    sig = inspect.signature(OperatingMarginFeatureEvaluator.evaluate)
    param_names = list(sig.parameters.keys())
    assert param_names == ["self", "data", "context"]


def test_both_evaluators_share_identical_evaluate_signature():
    roe_sig = inspect.signature(RoeFeatureEvaluator.evaluate)
    om_sig = inspect.signature(OperatingMarginFeatureEvaluator.evaluate)
    assert list(roe_sig.parameters.keys()) == list(om_sig.parameters.keys())


def test_feature_evaluator_protocol_unchanged():
    """§37.14: FeatureEvaluator Protocol 자체를 이번에 변경하지 않았다 --
    여전히 feature_id property + evaluate(data, context) 두 멤버뿐이다."""
    source = inspect.getsource(FeatureEvaluator)
    assert "def feature_id" in source
    assert "def evaluate" in source


# ============================== builder는 여전히 mapping only ==============================


def test_builder_did_not_gain_new_computation_for_operating_margin():
    """Operating Margin 도입으로 builder에 새 계산이 추가되지 않았다 --
    financial_features를 여전히 그대로(재계산 없이) 참조한다."""
    import app.evaluation.research_data_builder as builder_module

    source = inspect.getsource(builder_module)
    assert "operating_margin" not in source.lower()

    result = _result_with_annual(
        [AnnualFinancialFeatures(business_year="2025", operating_margin=18.5)]
    )
    data = build_normalized_research_data(result, as_of=_AS_OF)
    assert data.financial_facts.features is result.financial_features

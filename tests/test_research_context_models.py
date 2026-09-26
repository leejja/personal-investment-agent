"""RE-05 Recommendation Evaluation Boundary & Input Contract 테스트.

`app/models/research_context.py`는 evaluator/aggregator/policy 로직이
없는 순수 boundary/input contract이므로, 여기서도 scoring 결과 숫자는
테스트하지 않는다 -- 스키마가 layer 경계(vendor 비노출/Portfolio 배제/
facts-vs-evaluation 분리/failure 보존/AS_OF 표현/Event 분리)를
"표현 가능"하게 하는지만 검증한다.
"""

import inspect
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import app.models.research_context as research_context_module
from app.models.evidence import FinancialFactsEvidence
from app.models.recommendation import AvailabilityStatus
from app.models.research_context import (
    BenchmarkReference,
    EvaluationContext,
    FeatureEvaluator,
    FinancialFacts,
    FlowFacts,
    ForwardFacts,
    NormalizedResearchData,
    PriceHistoryReference,
    RecommendationEvaluationState,
    ResearchIdentity,
    ValuationFacts,
)


def _normalized_research_data(**overrides) -> NormalizedResearchData:
    defaults = {
        "identity": ResearchIdentity(symbol="005930", name="삼성전자"),
        "financial_facts": FinancialFacts(
            status=AvailabilityStatus.AVAILABLE, evidence=FinancialFactsEvidence()
        ),
        "valuation_facts": ValuationFacts(status=AvailabilityStatus.AVAILABLE),
        "flow_facts": FlowFacts(status=AvailabilityStatus.UNAVAILABLE),
        "price_history": PriceHistoryReference(status=AvailabilityStatus.UNAVAILABLE),
        "benchmark": BenchmarkReference(status=AvailabilityStatus.UNAVAILABLE),
        "forward_facts": ForwardFacts(),
    }
    defaults.update(overrides)
    return NormalizedResearchData(**defaults)


# ============================== Vendor 비노출 ==============================


def test_research_context_module_does_not_reference_vendor_models():
    """vendor-specific model(KiwoomStockInfo/KeyFinancials 등)이 evaluator
    contract에 직접 노출되지 않는다 -- 모듈 소스 자체에 vendor 클래스명이
    등장하지 않는다."""
    source = inspect.getsource(research_context_module)
    forbidden = (
        "KiwoomStockInfo",
        "KiwoomAccountBalance",
        "KeyFinancials",
        "OpenDartFinancialAccount",
        "EcosStatisticPoint",
    )
    for name in forbidden:
        assert name not in source


def test_research_context_module_does_not_import_service_layer():
    """이 모듈이 app.services.*/app.mcp.*를 아예 import하지 않는다 -- 정규화된
    사실만 아래로 흐른다는 원칙을 import 구조로도 강제한다."""
    source = inspect.getsource(research_context_module)
    assert "app.services." not in source
    assert "app.mcp." not in source


# ============================== EvaluationContext에 Portfolio 없음 ==============================


def test_evaluation_context_has_no_portfolio_fields():
    field_names = set(EvaluationContext.model_fields.keys())
    for forbidden in ("portfolio_context", "investor_profile", "portfolio", "holdings"):
        assert forbidden not in field_names


def test_evaluation_context_requires_as_of():
    as_of = datetime(2026, 8, 29, tzinfo=UTC)
    context = EvaluationContext(symbol="005930", as_of=as_of)
    assert context.as_of == as_of
    assert context.symbol == "005930"


# ============================== NormalizedResearchData vs FeatureEvaluationResult 분리 ==============================


def test_normalized_research_data_has_no_evaluation_fields():
    """NormalizedResearchData는 사실만 담는다 -- score/signal/coverage 같은
    평가 결과 필드가 top-level에 없다(각 fact bundle에는 source
    availability를 뜻하는 `status`만 있을 뿐, "attractiveness"를 뜻하는
    필드가 아니다)."""
    field_names = set(NormalizedResearchData.model_fields.keys())
    for forbidden in ("score", "signal", "classification"):
        assert forbidden not in field_names


def test_normalized_research_data_is_distinct_type_from_feature_evaluation_result():
    from app.models.recommendation import FeatureEvaluationResult

    data = _normalized_research_data()
    assert not isinstance(data, FeatureEvaluationResult)
    assert type(data) is not FeatureEvaluationResult


# ============================== Source failure 보존 ==============================


def test_source_failure_is_representable_per_fact_bundle():
    """Investor Flow source가 미구현 상태(§26 Implementation Gap)라는 사실을
    UNAVAILABLE status + warnings로 구조적으로 보존할 수 있다 -- 조용히
    빈 필드로만 남지 않는다."""
    data = _normalized_research_data(
        flow_facts=FlowFacts(
            status=AvailabilityStatus.UNAVAILABLE,
            warnings=["ka10059/ka10061 service integration not implemented"],
        )
    )
    assert data.flow_facts.status == AvailabilityStatus.UNAVAILABLE
    assert data.flow_facts.warnings != []


def test_forward_facts_default_to_unavailable_not_neutral():
    """Forward Component의 v1 기본 상태(§27/§29)가 이 layer에서도
    UNAVAILABLE로 표현된다 -- neutral이나 0으로 대체되지 않는다."""
    forward = ForwardFacts()
    assert forward.status == AvailabilityStatus.UNAVAILABLE
    statuses = {s.value for s in AvailabilityStatus}
    assert "neutral" not in statuses


# ============================== AS_OF 표현 가능 ==============================


def test_as_of_is_representable_on_both_data_and_context():
    as_of = datetime(2026, 8, 29, 9, 0, 0, tzinfo=UTC)
    data = _normalized_research_data(as_of=as_of)
    context = EvaluationContext(symbol="005930", as_of=as_of)
    assert data.as_of == as_of
    assert context.as_of == as_of


# ============================== Event path 분리 ==============================


def test_normalized_research_data_has_no_event_fields():
    """Event Intelligence는 parallel path다 -- NormalizedResearchData에
    event 관련 필드가 없다(RE-04 Amendment 1 원칙, §32.13)."""
    field_names = set(NormalizedResearchData.model_fields.keys())
    for name in field_names:
        assert "event" not in name.lower()


def test_recommendation_evaluation_state_keeps_event_overlay_as_separate_field():
    """RecommendationEvaluationState에서도 event_overlay는 다른 필드와
    병렬로만 존재한다 -- feature_results/component_assessments 안에
    섞여 있지 않다(독립 필드 하나로만 참조됨)."""
    field_names = set(RecommendationEvaluationState.model_fields.keys())
    assert "event_overlay" in field_names
    assert "future_opportunity_evidence" in field_names


# ============================== StockOpportunityAssessment Portfolio Action 없음 (재확인) ==============================


def test_recommendation_evaluation_state_has_no_portfolio_action_field():
    field_names = set(RecommendationEvaluationState.model_fields.keys())
    assert "action" not in field_names
    assert "target_weight" not in field_names


# ============================== RecommendationEvaluationState: Input vs progressive State ==============================


def _minimal_context() -> EvaluationContext:
    return EvaluationContext(symbol="005930", as_of=datetime(2026, 8, 29, tzinfo=UTC))


def test_recommendation_evaluation_state_requires_context_and_normalized_data():
    """context/normalized_research_data 없이는 state를 만들 수 없다 --
    이 둘이 진짜 pipeline entry point다(§33.2 Option A+B 혼합 결정)."""
    with pytest.raises(ValidationError):
        RecommendationEvaluationState()


def test_recommendation_evaluation_state_allows_progressive_empty_downstream_fields():
    """context/normalized_research_data만 있으면 나머지(feature_results 이후)는
    전부 비어 있어도 유효하다 -- pipeline이 막 시작한 상태를 표현할 수
    있어야 한다(progressive state semantics)."""
    state = RecommendationEvaluationState(
        context=_minimal_context(),
        normalized_research_data=_normalized_research_data(),
    )
    assert state.feature_results == []
    assert state.component_assessments == []
    assert state.core_attractiveness is None


# ============================== StockAnalysis가 canonical dependency가 아님 ==============================


def test_research_context_module_does_not_import_stock_analysis():
    """NormalizedResearchData의 canonical source는 StockAnalysis가 아니다
    -- 이 모듈이 `StockAnalysis`를 실제 타입으로 import하지 않는다(§33.1,
    docstring 설명에 이름이 언급되는 것과는 별개다). 이 모듈이 재사용하는
    것은 StockAnalysis도 담고 있는 것과 동일한 개별 정규화 타입
    (StockPriceSnapshot/FinancialSnapshot/FinancialFeatures)뿐이다."""
    assert "StockAnalysis" not in dir(research_context_module)
    from app.models.stock import StockAnalysis

    field_types = {field.annotation for field in NormalizedResearchData.model_fields.values()}
    assert StockAnalysis not in field_types


def test_normalized_research_data_and_stock_analysis_are_independent_types():
    """두 모델이 서로를 필드로 담지 않는다 -- sibling 관계이지 종속 관계가
    아니다."""
    from app.models.stock import StockAnalysis

    data_fields = set(NormalizedResearchData.model_fields.keys())
    stock_analysis_fields = set(StockAnalysis.model_fields.keys())
    assert "stock_analysis" not in {f.lower() for f in data_fields}
    assert "normalized_research_data" not in {f.lower() for f in stock_analysis_fields}


# ============================== FeatureEvaluator Protocol은 구현이 없다 ==============================


def test_feature_evaluator_is_a_protocol_with_no_implementation():
    assert FeatureEvaluator.__mro__[0].__name__ == "FeatureEvaluator"
    # Protocol 메서드 본문이 없다는 것을 소스로 직접 확인한다(전부 `...`).
    source = inspect.getsource(FeatureEvaluator)
    assert "def evaluate" in source
    assert "..." in source

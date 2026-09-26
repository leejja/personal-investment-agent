"""RE-05 First Deterministic Feature Evaluation Vertical Slice 테스트.

`app/evaluation/research_data_builder.py`(builder)와
`app/evaluation/fundamental_evaluators.py`(첫 FeatureEvaluator: ROE)를
실제 실행 경로로 검증한다. numeric threshold/weight/lookback 테스트는
만들지 않는다 -- 이 슬라이스는 계산식이 아니라 contract wiring을
검증하는 것이 목적이다.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.fundamental_evaluators import RoeFeatureEvaluator
from app.evaluation.research_data_builder import build_normalized_research_data
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.recommendation import AvailabilityStatus, Component
from app.models.research_context import EvaluationContext
from app.models.stock import FinancialSnapshot, StockPriceSnapshot
from tests.evidence_fixtures import attach_fixture_evidence

_AS_OF = datetime(2026, 8, 29, tzinfo=UTC)


def _deterministic_result(roe: float | None) -> DeterministicAnalysisResult:
    return attach_fixture_evidence(DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", roe=roe),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    ))


def _context() -> EvaluationContext:
    return EvaluationContext(symbol="005930", as_of=_AS_OF)


# ============================== StockAnalysis 비사용 ==============================


def test_builder_module_does_not_import_stock_analysis():
    """builder가 StockAnalysis를 실제 타입으로 import하지 않는다(docstring
    설명에 이름이 언급되는 것과는 별개 -- §33.1과 동일한 검증 방식)."""
    import app.evaluation.research_data_builder as builder_module

    assert "StockAnalysis" not in dir(builder_module)


def test_builder_signature_does_not_accept_stock_analysis():
    """build_normalized_research_data()가 DeterministicAnalysisResult만
    받는다 -- StockAnalysis나 LLM output을 받는 파라미터가 없다."""
    import inspect

    sig = inspect.signature(build_normalized_research_data)
    param_names = list(sig.parameters.keys())
    assert "stock_analysis" not in param_names
    assert "reasoning_result" not in param_names
    assert param_names[0] == "result"


# ============================== vendor model 비노출 ==============================


def test_evaluator_module_does_not_reference_vendor_models():
    import inspect

    import app.evaluation.fundamental_evaluators as evaluator_module

    source = inspect.getsource(evaluator_module)
    forbidden = ("KiwoomStockInfo", "KeyFinancials", "KiwoomService", "OpenDartService")
    for name in forbidden:
        assert name not in source


def test_evaluator_module_does_not_import_service_or_mcp_layer():
    import inspect

    import app.evaluation.fundamental_evaluators as evaluator_module

    source = inspect.getsource(evaluator_module)
    assert "app.services." not in source
    assert "app.mcp." not in source


# ============================== missing ROE 처리 ==============================


def test_evaluate_missing_roe_returns_unavailable():
    data = build_normalized_research_data(_deterministic_result(roe=None), as_of=_AS_OF)
    result = RoeFeatureEvaluator().evaluate(data, _context())

    assert result.availability == AvailabilityStatus.UNAVAILABLE
    assert result.raw is None
    assert result.warnings != []


# ============================== valid ROE factual input 처리 ==============================


def test_evaluate_valid_roe_returns_available_with_raw_value():
    data = build_normalized_research_data(_deterministic_result(roe=12.3), as_of=_AS_OF)
    result = RoeFeatureEvaluator().evaluate(data, _context())

    assert result.availability == AvailabilityStatus.AVAILABLE
    assert result.raw is not None
    assert result.raw.value == 12.3
    assert result.raw.unit == "percent"
    assert result.component == Component.FUNDAMENTAL
    assert result.feature_family == "profitability"
    assert result.feature_id == "fundamental.profitability.roe"


# ============================== provenance/as_of 전달 ==============================


def test_provenance_as_of_matches_context():
    data = build_normalized_research_data(_deterministic_result(roe=12.3), as_of=_AS_OF)
    context = _context()
    result = RoeFeatureEvaluator().evaluate(data, context)

    assert result.provenance.as_of == context.as_of
    assert result.provenance.source == "Kiwoom"


def test_builder_preserves_as_of_on_normalized_research_data():
    data = build_normalized_research_data(_deterministic_result(roe=12.3), as_of=_AS_OF)
    assert data.as_of == _AS_OF


# ============================== normalized score 미정이면 None ==============================


def test_normalized_value_is_none_not_unknown_or_unavailable():
    """RE-05 Numeric Calibration = OPEN이므로 normalized_value는 항상
    None이다 -- 이는 availability=UNKNOWN/UNAVAILABLE과는 다른 축이다
    (실제로 값이 있는 AVAILABLE 케이스에서도 normalized_value는 None)."""
    data = build_normalized_research_data(_deterministic_result(roe=12.3), as_of=_AS_OF)
    result = RoeFeatureEvaluator().evaluate(data, _context())

    assert result.availability == AvailabilityStatus.AVAILABLE
    assert result.normalized_value is None


# ============================== recommendation/portfolio action 생성 없음 ==============================


def test_feature_evaluation_result_has_no_recommendation_or_portfolio_fields():
    data = build_normalized_research_data(_deterministic_result(roe=12.3), as_of=_AS_OF)
    result = RoeFeatureEvaluator().evaluate(data, _context())

    field_names = set(type(result).model_fields.keys())
    for forbidden in ("action", "target_weight", "classification", "recommendation"):
        assert forbidden not in field_names


def test_evaluator_return_type_is_feature_evaluation_result_not_assessment():
    from app.models.recommendation import ComponentAssessment, StockOpportunityAssessment

    data = build_normalized_research_data(_deterministic_result(roe=12.3), as_of=_AS_OF)
    result = RoeFeatureEvaluator().evaluate(data, _context())

    assert not isinstance(result, ComponentAssessment)
    assert not isinstance(result, StockOpportunityAssessment)


# ============================== builder는 factual mapping만(financial_facts 재사용) ==============================


def test_builder_reuses_financial_features_without_recomputation():
    """builder가 RE-01 financial_features를 새로 계산하지 않고 그대로
    옮긴다는 것을 확인한다(deterministic factual mapping만)."""
    result = _deterministic_result(roe=12.3)
    data = build_normalized_research_data(result, as_of=_AS_OF)

    assert data.financial_facts.features is result.financial_features
    assert data.financial_facts.current is result.financials
    assert data.financial_facts.status == AvailabilityStatus.AVAILABLE


def test_builder_marks_unimplemented_sources_as_unavailable():
    """Valuation/Flow/PriceHistory/Benchmark는 이 pipeline에 아직 연결된
    source가 없으므로 UNAVAILABLE로 정직하게 표시된다(임의 값 생성 없음)."""
    data = build_normalized_research_data(_deterministic_result(roe=12.3), as_of=_AS_OF)

    assert data.valuation_facts.status == AvailabilityStatus.UNAVAILABLE
    assert data.flow_facts.status == AvailabilityStatus.UNAVAILABLE
    assert data.price_history.status == AvailabilityStatus.UNAVAILABLE
    assert data.benchmark.status == AvailabilityStatus.UNAVAILABLE
    assert data.forward_facts.status == AvailabilityStatus.UNAVAILABLE


# ============================== numeric threshold 없음 ==============================


def test_evaluator_applies_no_numeric_comparison_to_raw_roe():
    """evaluator 코드가 roe 값에 어떤 numeric comparison(threshold 판정)도
    적용하지 않는다 -- `if roe`가 None-check 하나뿐이고 `>`/`<`/`>=`/`<=`
    같은 비교 연산자가 raw 값에 전혀 쓰이지 않았는지 소스로 직접 확인한다
    (docstring에 "threshold를 만들지 않는다"는 설명 자체는 등장할 수 있으므로
    단어 매칭이 아니라 비교 연산자 존재 여부로 검사한다)."""
    import inspect

    from app.evaluation.fundamental_evaluators import RoeFeatureEvaluator

    source = inspect.getsource(RoeFeatureEvaluator.evaluate)
    compact = source.replace(" ", "").replace("\n", "")
    for pattern in ("roe>", "roe<", ">roe", "<roe"):
        assert pattern not in compact


def test_normalized_value_field_holds_no_numeric_default_other_than_none():
    """evaluate()가 반환하는 결과의 normalized_value 대입부가 리터럴
    None으로 고정돼 있다 -- 실제 반환값으로도 재확인한다(위 테스트들과
    함께 numeric calibration이 도입되지 않았음을 이중으로 보장)."""
    data = build_normalized_research_data(_deterministic_result(roe=999.9), as_of=_AS_OF)
    result = RoeFeatureEvaluator().evaluate(data, _context())
    assert result.normalized_value is None


# ============================== RecommendationEvaluationState 조립 가능성(entry point 재확인) ==============================


def test_normalized_research_data_can_seed_recommendation_evaluation_state():
    from app.models.research_context import RecommendationEvaluationState

    data = build_normalized_research_data(_deterministic_result(roe=12.3), as_of=_AS_OF)
    context = _context()
    result = RoeFeatureEvaluator().evaluate(data, context)

    state = RecommendationEvaluationState(
        context=context,
        normalized_research_data=data,
        feature_results=[result],
    )
    assert state.feature_results[0].feature_id == "fundamental.profitability.roe"


def test_recommendation_evaluation_state_still_requires_context_and_data():
    with pytest.raises(ValidationError):
        from app.models.research_context import RecommendationEvaluationState

        RecommendationEvaluationState(feature_results=[])

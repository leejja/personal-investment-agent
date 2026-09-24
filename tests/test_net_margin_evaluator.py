"""RE-05 Post-Orchestration Architecture Review Step F(READY Evaluator
Expansion) -- `NetMarginFeatureEvaluator` 테스트.

`OperatingMarginFeatureEvaluator`와 완전히 동형인 `annual[-1]` selection
contract를 검증한다. numeric threshold/weight/window 테스트는 만들지
않는다 -- 이 evaluator는 계산식이 아니라 contract wiring만 검증한다.
"""

from datetime import UTC, datetime

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.feature_registry import FeatureApplicability, get_feature_definition
from app.evaluation.fundamental_evaluators import (
    _NET_MARGIN_APPLICABILITY_NOTE,
    _NET_MARGIN_UNAVAILABLE_WARNING,
    NetMarginFeatureEvaluator,
)
from app.evaluation.research_data_builder import build_normalized_research_data
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.recommendation import AvailabilityStatus, Component, EvaluationBasis
from app.models.research_context import EvaluationContext
from app.models.stock import (
    AnnualFinancialFeatures,
    FinancialFeatures,
    FinancialSnapshot,
    StockPriceSnapshot,
)

_NM_ID = "fundamental.profitability.net_margin"
_AS_OF = datetime(2026, 9, 7, tzinfo=UTC)


def _context() -> EvaluationContext:
    return EvaluationContext(symbol="005930", as_of=_AS_OF)


def _result_with_annual(annual: list[AnnualFinancialFeatures]) -> DeterministicAnalysisResult:
    return DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025"),
        financial_features=FinancialFeatures(annual=annual),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )


def test_registry_definition_is_implemented_with_expected_metadata():
    definition = get_feature_definition(_NM_ID)
    assert definition.evaluator_id == "NetMarginFeatureEvaluator"
    assert definition.evaluator_version == "v1"
    assert definition.applicability == FeatureApplicability.REVIEW_REQUIRED


def test_available_reads_latest_annual_net_margin():
    result = _result_with_annual([AnnualFinancialFeatures(business_year="2025", net_margin=8.5)])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = NetMarginFeatureEvaluator().evaluate(data, _context())

    assert outcome.feature_id == _NM_ID
    assert outcome.component == Component.FUNDAMENTAL
    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.raw is not None
    assert outcome.raw.value == 8.5
    assert outcome.raw.unit == "percent"
    assert outcome.normalized_value is None
    assert outcome.evaluation_basis == [EvaluationBasis.ABSOLUTE]
    assert outcome.applicability_review_required is True
    assert outcome.applicability_note == _NET_MARGIN_APPLICABILITY_NOTE
    assert outcome.warnings == []


def test_available_preserves_provenance_source_and_as_of():
    result = _result_with_annual([AnnualFinancialFeatures(business_year="2025", net_margin=8.5)])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = NetMarginFeatureEvaluator().evaluate(data, _context())

    assert outcome.provenance.source == "OpenDART"
    assert outcome.provenance.as_of == _AS_OF


def test_missing_annual_list_is_unavailable():
    result = _result_with_annual([])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = NetMarginFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.UNAVAILABLE
    assert outcome.raw is None
    assert outcome.normalized_value is None
    assert outcome.warnings == [_NET_MARGIN_UNAVAILABLE_WARNING]
    assert outcome.applicability_review_required is True
    assert outcome.applicability_note == _NET_MARGIN_APPLICABILITY_NOTE


def test_latest_annual_value_none_is_unavailable():
    result = _result_with_annual([AnnualFinancialFeatures(business_year="2025", net_margin=None)])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = NetMarginFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.UNAVAILABLE
    assert outcome.raw is None
    assert outcome.warnings == [_NET_MARGIN_UNAVAILABLE_WARNING]


def test_latest_selection_is_last_element_not_first():
    """annual은 오래된 -> 최신 순이다 -- evaluator는 반드시 마지막
    항목(annual[-1])을 읽어야 한다(첫 항목이 아니다)."""
    annual = [
        AnnualFinancialFeatures(business_year="2023", net_margin=3.0),
        AnnualFinancialFeatures(business_year="2024", net_margin=5.0),
        AnnualFinancialFeatures(business_year="2025", net_margin=9.9),
    ]
    result = _result_with_annual(annual)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = NetMarginFeatureEvaluator().evaluate(data, _context())

    assert outcome.raw.value == 9.9

"""RE-05 Post-Orchestration Architecture Review Step F(READY Evaluator
Expansion) -- `DebtRatioFeatureEvaluator` 테스트.

Operating Margin/Net Margin과 완전히 동형인 `annual[-1]` selection
contract를 검증한다. `LOWER_IS_BETTER` registry directionality를
runtime favorable/unfavorable 판단으로 변환하지 않는다는 invariant를
구조적으로(directionality output 미설정) 확인한다.
"""

from datetime import UTC, datetime

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.feature_registry import FeatureApplicability, get_feature_definition
from app.evaluation.fundamental_evaluators import (
    _DEBT_RATIO_APPLICABILITY_NOTE,
    _DEBT_RATIO_UNAVAILABLE_WARNING,
    DebtRatioFeatureEvaluator,
)
from app.evaluation.research_data_builder import build_normalized_research_data
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.recommendation import (
    AvailabilityStatus,
    Component,
    Directionality,
    EvaluationBasis,
)
from app.models.research_context import EvaluationContext
from app.models.stock import (
    AnnualFinancialFeatures,
    FinancialFeatures,
    FinancialSnapshot,
    StockPriceSnapshot,
)

_DR_ID = "fundamental.financial_resilience.debt_ratio"
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
    definition = get_feature_definition(_DR_ID)
    assert definition.evaluator_id == "DebtRatioFeatureEvaluator"
    assert definition.evaluator_version == "v1"
    assert definition.applicability == FeatureApplicability.REVIEW_REQUIRED
    # registry directionality는 LOWER_IS_BETTER지만, 이 evaluator의 output에는
    # 반영되지 않는다(아래 test_directionality_output_is_unset).
    assert definition.directionality == Directionality.LOWER_IS_BETTER


def test_available_reads_latest_annual_debt_ratio():
    result = _result_with_annual([AnnualFinancialFeatures(business_year="2025", debt_ratio=66.7)])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = DebtRatioFeatureEvaluator().evaluate(data, _context())

    assert outcome.feature_id == _DR_ID
    assert outcome.component == Component.FUNDAMENTAL
    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.raw.value == 66.7
    assert outcome.raw.unit == "percent"
    assert outcome.normalized_value is None
    assert outcome.evaluation_basis == [EvaluationBasis.ABSOLUTE]
    assert outcome.applicability_review_required is True
    assert outcome.applicability_note == _DEBT_RATIO_APPLICABILITY_NOTE
    assert outcome.warnings == []


def test_directionality_output_is_unset():
    """registry의 LOWER_IS_BETTER를 "낮음=favorable" 같은 runtime
    interpretation으로 변환하지 않는다 -- output에 directionality를
    아예 설정하지 않는다(ROE/Operating Margin과 동일)."""
    result = _result_with_annual([AnnualFinancialFeatures(business_year="2025", debt_ratio=200.0)])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = DebtRatioFeatureEvaluator().evaluate(data, _context())

    assert outcome.directionality is None


def test_available_preserves_provenance_source_and_as_of():
    result = _result_with_annual([AnnualFinancialFeatures(business_year="2025", debt_ratio=66.7)])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = DebtRatioFeatureEvaluator().evaluate(data, _context())

    assert outcome.provenance.source == "OpenDART"
    assert outcome.provenance.as_of == _AS_OF


def test_missing_annual_list_is_unavailable():
    result = _result_with_annual([])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = DebtRatioFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.UNAVAILABLE
    assert outcome.raw is None
    assert outcome.normalized_value is None
    assert outcome.warnings == [_DEBT_RATIO_UNAVAILABLE_WARNING]
    assert outcome.applicability_review_required is True
    assert outcome.applicability_note == _DEBT_RATIO_APPLICABILITY_NOTE


def test_latest_annual_value_none_is_unavailable():
    """equity<=0(자본잠식)이면 _debt_ratio()가 None을 반환한다 --
    evaluator는 이를 UNAVAILABLE로 정직하게 표현한다(INVALID가 아니다)."""
    result = _result_with_annual([AnnualFinancialFeatures(business_year="2025", debt_ratio=None)])
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = DebtRatioFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.UNAVAILABLE
    assert outcome.raw is None
    assert outcome.warnings == [_DEBT_RATIO_UNAVAILABLE_WARNING]


def test_latest_selection_is_last_element_not_first():
    annual = [
        AnnualFinancialFeatures(business_year="2023", debt_ratio=40.0),
        AnnualFinancialFeatures(business_year="2024", debt_ratio=55.0),
        AnnualFinancialFeatures(business_year="2025", debt_ratio=66.7),
    ]
    result = _result_with_annual(annual)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = DebtRatioFeatureEvaluator().evaluate(data, _context())

    assert outcome.raw.value == 66.7

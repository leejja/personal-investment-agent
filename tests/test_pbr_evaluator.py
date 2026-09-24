"""RE-05 Post-Orchestration Architecture Review Step F(READY Evaluator
Expansion) -- `PbrFeatureEvaluator` 테스트.

`test_trailing_per_evaluator.py`와 동일한 case matrix(0/음수/None) --
PBR도 동일 §2.8 FROZEN invariant(`INVALID != NEGATIVE`,
`UNAVAILABLE != 0`)를 그대로 적용한다.
"""

from datetime import UTC, datetime

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.feature_registry import FeatureApplicability, get_feature_definition
from app.evaluation.research_data_builder import build_normalized_research_data
from app.evaluation.valuation_evaluators import _PBR_UNAVAILABLE_WARNING, PbrFeatureEvaluator
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.recommendation import AvailabilityStatus, Component, EvaluationBasis
from app.models.research_context import EvaluationContext
from app.models.stock import FinancialSnapshot, StockPriceSnapshot

_PBR_ID = "valuation.asset_based.pbr"
_AS_OF = datetime(2026, 9, 7, tzinfo=UTC)


def _context() -> EvaluationContext:
    return EvaluationContext(symbol="005930", as_of=_AS_OF)


def _result_with_pbr(pbr: float | None) -> DeterministicAnalysisResult:
    return DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", pbr=pbr),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )


def test_registry_definition_is_implemented_with_expected_metadata():
    definition = get_feature_definition(_PBR_ID)
    assert definition.evaluator_id == "PbrFeatureEvaluator"
    assert definition.evaluator_version == "v1"
    assert definition.applicability == FeatureApplicability.UNIVERSAL


def test_positive_pbr_is_available():
    result = _result_with_pbr(1.2)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = PbrFeatureEvaluator().evaluate(data, _context())

    assert outcome.feature_id == _PBR_ID
    assert outcome.component == Component.VALUATION
    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.raw.value == 1.2
    assert outcome.raw.unit == "multiple"
    assert outcome.normalized_value is None
    assert outcome.evaluation_basis == [EvaluationBasis.ABSOLUTE]
    assert outcome.warnings == []


def test_zero_pbr_is_available_not_unavailable():
    result = _result_with_pbr(0.0)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = PbrFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.raw.value == 0.0
    assert outcome.normalized_value is None
    assert outcome.warnings == []


def test_negative_pbr_is_available_not_invalid():
    """자본잠식 등으로 PBR이 음수여도 AVAILABLE raw evidence다."""
    result = _result_with_pbr(-0.5)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = PbrFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.availability != AvailabilityStatus.INVALID
    assert outcome.raw.value == -0.5
    assert outcome.normalized_value is None
    assert outcome.warnings == []


def test_none_pbr_is_unavailable():
    result = _result_with_pbr(None)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = PbrFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.UNAVAILABLE
    assert outcome.raw is None
    assert outcome.normalized_value is None
    assert outcome.warnings == [_PBR_UNAVAILABLE_WARNING]


def test_available_preserves_provenance_source_and_as_of():
    result = _result_with_pbr(1.2)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = PbrFeatureEvaluator().evaluate(data, _context())

    assert outcome.provenance.source == "Kiwoom"
    assert outcome.provenance.as_of == _AS_OF


def test_applicability_review_required_is_default_false():
    result = _result_with_pbr(1.2)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = PbrFeatureEvaluator().evaluate(data, _context())

    assert outcome.applicability_review_required is False
    assert outcome.applicability_note is None


def test_directionality_output_is_unset():
    result = _result_with_pbr(1.2)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = PbrFeatureEvaluator().evaluate(data, _context())

    assert outcome.directionality is None

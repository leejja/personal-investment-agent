"""RE-05 Post-Orchestration Architecture Review Step F(READY Evaluator
Expansion) -- `TrailingPerFeatureEvaluator` 테스트.

핵심 회귀: 0/음수 PER을 `INVALID`/`UNAVAILABLE`로 재분류하거나
저평가/고평가 같은 economic interpretation을 추가하지 않는다는
`docs/dev-log/2026-08-29.md` §2.8 FROZEN invariant(`INVALID != NEGATIVE`,
`UNAVAILABLE != 0`)를 구조적으로 보호한다.
"""

from datetime import UTC, datetime

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.feature_registry import FeatureApplicability, get_feature_definition
from app.evaluation.research_data_builder import build_normalized_research_data
from app.evaluation.valuation_evaluators import (
    _TRAILING_PER_UNAVAILABLE_WARNING,
    TrailingPerFeatureEvaluator,
)
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.recommendation import AvailabilityStatus, Component, EvaluationBasis
from app.models.research_context import EvaluationContext
from app.models.stock import FinancialSnapshot, StockPriceSnapshot
from tests.evidence_fixtures import attach_fixture_evidence

_PER_ID = "valuation.earnings_based.trailing_per"
_AS_OF = datetime(2026, 9, 7, tzinfo=UTC)


def _context() -> EvaluationContext:
    return EvaluationContext(symbol="005930", as_of=_AS_OF)


def _result_with_per(per: float | None) -> DeterministicAnalysisResult:
    return attach_fixture_evidence(DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", per=per),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    ))


def test_registry_definition_is_implemented_with_expected_metadata():
    definition = get_feature_definition(_PER_ID)
    assert definition.evaluator_id == "TrailingPerFeatureEvaluator"
    assert definition.evaluator_version == "v1"
    assert definition.applicability == FeatureApplicability.UNIVERSAL


def test_positive_per_is_available():
    result = _result_with_per(10.5)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = TrailingPerFeatureEvaluator().evaluate(data, _context())

    assert outcome.feature_id == _PER_ID
    assert outcome.component == Component.VALUATION
    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.raw.value == 10.5
    assert outcome.raw.unit == "multiple"
    assert outcome.normalized_value is None
    assert outcome.evaluation_basis == [EvaluationBasis.ABSOLUTE]
    assert outcome.warnings == []


def test_zero_per_is_available_not_unavailable():
    """FROZEN invariant(§2.8): UNAVAILABLE != 0 -- 0은 정상 raw evidence다."""
    result = _result_with_per(0.0)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = TrailingPerFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.raw.value == 0.0
    assert outcome.normalized_value is None
    assert outcome.warnings == []


def test_negative_per_is_available_not_invalid():
    """FROZEN invariant(§2.8): INVALID != NEGATIVE -- 적자기업의 음수
    PER도 AVAILABLE raw evidence다. INVALID로 분류하지 않는다."""
    result = _result_with_per(-3.2)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = TrailingPerFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.availability != AvailabilityStatus.INVALID
    assert outcome.raw.value == -3.2
    assert outcome.normalized_value is None
    assert outcome.warnings == []


def test_none_per_is_unavailable():
    result = _result_with_per(None)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = TrailingPerFeatureEvaluator().evaluate(data, _context())

    assert outcome.availability == AvailabilityStatus.UNAVAILABLE
    assert outcome.raw is None
    assert outcome.normalized_value is None
    assert outcome.warnings == [_TRAILING_PER_UNAVAILABLE_WARNING]


def test_available_preserves_provenance_source_and_as_of():
    result = _result_with_per(10.5)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = TrailingPerFeatureEvaluator().evaluate(data, _context())

    assert outcome.provenance.source == "Kiwoom"
    assert outcome.provenance.as_of == _AS_OF


def test_applicability_review_required_is_default_false():
    """registry.applicability=UNIVERSAL이므로 ROE와 동일하게 이
    runtime flag를 설정하지 않는다(기본값 False)."""
    result = _result_with_per(10.5)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = TrailingPerFeatureEvaluator().evaluate(data, _context())

    assert outcome.applicability_review_required is False
    assert outcome.applicability_note is None


def test_directionality_output_is_unset():
    """registry.directionality=CONTEXT_DEPENDENT이지만 numeric
    interpretation으로 변환하지 않는다 -- output에 설정하지 않는다."""
    result = _result_with_per(10.5)
    data = build_normalized_research_data(result, as_of=_AS_OF)
    outcome = TrailingPerFeatureEvaluator().evaluate(data, _context())

    assert outcome.directionality is None

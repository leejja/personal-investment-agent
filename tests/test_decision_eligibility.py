"""RE-05 Recommendation Policy Step 1 -- Final Decision Eligibility 테스트.

FROZEN Design/Implementation Contract: `policy_may_proceed`는 State Coverage의
critical foundation만의 projection이고, FOE `RequirementSatisfaction`은
tri-state 그대로 보존된다. `coverage_status`는 입력이 아니며, producer가
실행되지 않은 `None`은 UNKNOWN evidence가 아니다.
"""

import ast
import inspect
from datetime import UTC, datetime

import pytest

import app.evaluation.decision_eligibility as decision_eligibility_module
from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.decision_eligibility import evaluate_decision_eligibility
from app.evaluation.orchestrator import run_first_deterministic_pipeline
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.recommendation import (
    CoverageAssessment,
    CoverageStatus,
    EvidencePathAvailability,
    FutureOpportunityEvidenceAssessment,
    RequirementSatisfaction,
)
from app.models.research_context import EvaluationContext
from app.models.stock import (
    AnnualFinancialFeatures,
    FinancialFeatures,
    FinancialSnapshot,
    StockPriceSnapshot,
)


def _coverage(
    critical_path_satisfied: bool,
    coverage_status: CoverageStatus = CoverageStatus.INSUFFICIENT,
) -> CoverageAssessment:
    return CoverageAssessment(
        critical_path_satisfied=critical_path_satisfied,
        coverage_status=coverage_status,
    )


def _foe(
    requirement_satisfied: RequirementSatisfaction,
    forward_path: EvidencePathAvailability = EvidencePathAvailability.UNAVAILABLE,
    event_path: EvidencePathAvailability = EvidencePathAvailability.UNKNOWN,
) -> FutureOpportunityEvidenceAssessment:
    return FutureOpportunityEvidenceAssessment(
        forward_path_availability=forward_path,
        event_path_availability=event_path,
        requirement_satisfied=requirement_satisfied,
    )


_SIX_CASES = [
    (False, RequirementSatisfaction.SATISFIED, False),
    (False, RequirementSatisfaction.UNKNOWN, False),
    (False, RequirementSatisfaction.NOT_SATISFIED, False),
    (True, RequirementSatisfaction.SATISFIED, True),
    (True, RequirementSatisfaction.UNKNOWN, True),
    (True, RequirementSatisfaction.NOT_SATISFIED, True),
]


# ============================== Six canonical cases ==============================


@pytest.mark.parametrize(("critical", "requirement", "expected_proceed"), _SIX_CASES)
def test_six_canonical_cases(critical, requirement, expected_proceed):
    coverage = _coverage(critical)
    foe = _foe(requirement)
    coverage_before = coverage.model_copy(deep=True)
    foe_before = foe.model_copy(deep=True)

    result = evaluate_decision_eligibility(coverage, foe)

    assert result.policy_may_proceed is expected_proceed
    assert result.policy_may_proceed is coverage.critical_path_satisfied
    assert result.forward_requirement is foe.requirement_satisfied
    assert coverage == coverage_before
    assert foe == foe_before


def test_foe_unknown_is_preserved_and_does_not_block_progression():
    """UNKNOWN != PASS, UNKNOWN != FALSE."""
    result = evaluate_decision_eligibility(
        _coverage(True), _foe(RequirementSatisfaction.UNKNOWN)
    )

    assert result.policy_may_proceed is True
    assert result.forward_requirement is RequirementSatisfaction.UNKNOWN
    assert result.forward_requirement is not RequirementSatisfaction.SATISFIED
    assert result.forward_requirement is not RequirementSatisfaction.NOT_SATISFIED


def test_foe_not_satisfied_is_preserved_and_does_not_block_progression():
    result = evaluate_decision_eligibility(
        _coverage(True), _foe(RequirementSatisfaction.NOT_SATISFIED)
    )

    assert result.policy_may_proceed is True
    assert result.forward_requirement is RequirementSatisfaction.NOT_SATISFIED


def test_foe_satisfied_does_not_rescue_missing_critical_foundation():
    result = evaluate_decision_eligibility(
        _coverage(False), _foe(RequirementSatisfaction.SATISFIED)
    )

    assert result.policy_may_proceed is False
    assert result.forward_requirement is RequirementSatisfaction.SATISFIED


# ============================== coverage_status is not an input ==============================


def test_runtime_shape_critical_true_status_insufficient_foe_unknown_proceeds():
    """현재 runtime 주 분기: Forward 때문에 status=INSUFFICIENT여도 Forward가
    간접 hard gate가 되지 않는다."""
    result = evaluate_decision_eligibility(
        _coverage(True, CoverageStatus.INSUFFICIENT),
        _foe(RequirementSatisfaction.UNKNOWN),
    )

    assert result.policy_may_proceed is True
    assert result.forward_requirement is RequirementSatisfaction.UNKNOWN


@pytest.mark.parametrize("critical", [True, False])
@pytest.mark.parametrize("coverage_status", list(CoverageStatus))
def test_coverage_status_does_not_affect_progression(critical, coverage_status):
    result = evaluate_decision_eligibility(
        _coverage(critical, coverage_status),
        _foe(RequirementSatisfaction.UNKNOWN),
    )

    assert result.policy_may_proceed is critical


# ============================== FOE producer ownership ==============================


@pytest.mark.parametrize("requirement", list(RequirementSatisfaction))
def test_foe_metadata_does_not_change_result(requirement):
    """Decision Eligibility는 FOE aggregation을 재구현하지 않는다 --
    `requirement_satisfied`와 모순되는 path availability/metadata를 줘도
    canonical producer output만 전달된다."""
    baseline = evaluate_decision_eligibility(_coverage(True), _foe(requirement))
    variants = [
        _foe(requirement, EvidencePathAvailability.AVAILABLE, EvidencePathAvailability.AVAILABLE),
        _foe(
            requirement,
            EvidencePathAvailability.UNAVAILABLE,
            EvidencePathAvailability.UNAVAILABLE,
        ),
        FutureOpportunityEvidenceAssessment(
            forward_path_availability=EvidencePathAvailability.UNKNOWN,
            event_path_availability=EvidencePathAvailability.UNKNOWN,
            requirement_satisfied=requirement,
            supporting_refs=["ref-1"],
            warnings=["warning-1"],
        ),
    ]

    for foe in variants:
        result = evaluate_decision_eligibility(_coverage(True), foe)
        assert result == baseline
        assert result.forward_requirement is requirement


# ============================== Missing producer (None != UNKNOWN) ==============================


def test_missing_coverage_raises():
    with pytest.raises(ValueError, match="coverage"):
        evaluate_decision_eligibility(None, _foe(RequirementSatisfaction.UNKNOWN))


def test_missing_future_opportunity_evidence_raises():
    with pytest.raises(ValueError, match="future_opportunity_evidence"):
        evaluate_decision_eligibility(_coverage(True), None)


def test_missing_both_producers_raises():
    with pytest.raises(ValueError):
        evaluate_decision_eligibility(None, None)


# ============================== Result immutability ==============================


def test_result_is_immutable():
    result = evaluate_decision_eligibility(
        _coverage(True), _foe(RequirementSatisfaction.UNKNOWN)
    )

    with pytest.raises(AttributeError):
        result.policy_may_proceed = False  # type: ignore[misc]


# ============================== Architecture boundary ==============================


def _module_imports_and_identifiers() -> tuple[set[str], set[str]]:
    tree = ast.parse(inspect.getsource(decision_eligibility_module))
    imported_modules: set[str] = set()
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
            identifiers.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
    return imported_modules, identifiers


def test_module_does_not_depend_on_final_assessment_concepts():
    _, identifiers = _module_imports_and_identifiers()

    assert identifiers.isdisjoint(
        {"AssessmentStatus", "StockOpportunityAssessment", "OpportunityClassification"}
    )


def test_module_does_not_import_orchestrator_or_external_layers():
    imported_modules, _ = _module_imports_and_identifiers()

    for module in imported_modules:
        assert module != "app.evaluation.orchestrator"
        assert not module.startswith(("app.services", "app.mcp", "app.agents", "app.api"))


# ============================== Runtime integration boundary ==============================


def test_first_deterministic_pipeline_state_is_eligible_with_unknown_forward_requirement():
    """First Deterministic Pipeline -> RecommendationEvaluationState ->
    Decision Eligibility. orchestrator는 이 함수를 호출하지 않는다 -- 여기서만
    실제 state로 호환성을 확인한다."""
    result_input = DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", roe=12.3, per=10.0),
        financial_features=FinancialFeatures(
            annual=[AnnualFinancialFeatures(business_year="2025", debt_ratio=66.7)]
        ),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )
    state = run_first_deterministic_pipeline(
        result_input,
        EvaluationContext(symbol="005930", as_of=datetime(2026, 8, 29, tzinfo=UTC)),
    )

    assert state.coverage is not None
    assert state.coverage.critical_path_satisfied is True
    assert state.coverage.coverage_status is CoverageStatus.INSUFFICIENT
    assert state.future_opportunity_evidence is not None
    assert (
        state.future_opportunity_evidence.requirement_satisfied
        is RequirementSatisfaction.UNKNOWN
    )

    result = evaluate_decision_eligibility(state.coverage, state.future_opportunity_evidence)

    assert result.policy_may_proceed is True
    assert result.forward_requirement is RequirementSatisfaction.UNKNOWN

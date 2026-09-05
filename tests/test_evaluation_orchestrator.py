"""RE-05 `RecommendationEvaluationState` Full Orchestration -- First
Deterministic Pipeline Slice 테스트.

`app/evaluation/orchestrator.py::run_first_deterministic_pipeline()`이 기존
building block(`research_data_builder`/`fundamental_evaluators`/
`coverage_evaluator`/`assembly`)을 정해진 순서로 연결할 뿐, 새 계산/semantics
를 만들지 않는다는 것을 검증한다. numeric threshold/weight/calibration
테스트는 만들지 않는다 -- 이 슬라이스는 orchestration wiring을 검증하는
것이 목적이다.
"""

from datetime import UTC, datetime

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.orchestrator import run_first_deterministic_pipeline
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.recommendation import (
    Component,
    ComponentSignal,
    ConfidenceLevel,
    CoverageStatus,
    EvidencePathAvailability,
)
from app.models.research_context import EvaluationContext
from app.models.stock import (
    AnnualFinancialFeatures,
    FinancialFeatures,
    FinancialSnapshot,
    StockPriceSnapshot,
)

_AS_OF = datetime(2026, 8, 29, tzinfo=UTC)

_ROE_ID = "fundamental.profitability.roe"
_OM_ID = "fundamental.profitability.operating_margin"

_CANONICAL_COMPONENT_ORDER = (
    Component.FUNDAMENTAL,
    Component.VALUATION,
    Component.FORWARD,
    Component.FLOW,
    Component.MARKET_CONFIRMATION,
)


def _context() -> EvaluationContext:
    return EvaluationContext(symbol="005930", as_of=_AS_OF)


def _deterministic_result(
    roe: float | None, operating_margin: float | None = None
) -> DeterministicAnalysisResult:
    financial_features = (
        FinancialFeatures(
            annual=[AnnualFinancialFeatures(business_year="2025", operating_margin=operating_margin)]
        )
        if operating_margin is not None
        else FinancialFeatures()
    )
    return DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", roe=roe),
        financial_features=financial_features,
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )


# ============================== 1. Happy path ==============================


def test_happy_path_produces_two_feature_results_and_five_components():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert len(state.feature_results) == 2
    assert len(state.component_assessments) == 5


# ============================== 2. Partial feature ==============================


def test_partial_feature_missing_operating_margin_still_completes():
    result_input = _deterministic_result(roe=12.3, operating_margin=None)
    state = run_first_deterministic_pipeline(result_input, _context())

    results_by_id = {r.feature_id: r for r in state.feature_results}
    assert len(state.feature_results) == 2
    assert results_by_id[_ROE_ID].raw is not None
    assert results_by_id[_ROE_ID].raw.value == 12.3
    assert results_by_id[_OM_ID].raw is None
    assert results_by_id[_OM_ID].warnings != []


# ============================== 3. No implemented feature data ==============================


def test_no_implemented_feature_data_still_completes_with_unavailable():
    from app.models.recommendation import AvailabilityStatus

    result_input = _deterministic_result(roe=None, operating_margin=None)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert len(state.feature_results) == 2
    for r in state.feature_results:
        assert r.availability == AvailabilityStatus.UNAVAILABLE
    assert len(state.component_assessments) == 5


# ============================== 4. Evaluator dispatch ==============================


def test_evaluator_dispatch_executes_exactly_roe_and_operating_margin():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    feature_ids = {r.feature_id for r in state.feature_results}
    assert feature_ids == {_ROE_ID, _OM_ID}


# ============================== 5. Canonical component ordering ==============================


def test_canonical_component_ordering():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert tuple(ca.component for ca in state.component_assessments) == _CANONICAL_COMPONENT_ORDER


# ============================== 6. Forward coverage ==============================


def test_forward_coverage_is_insufficient_and_critical_path_false():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    forward = next(ca for ca in state.component_assessments if ca.component == Component.FORWARD)
    assert forward.coverage.coverage_status == CoverageStatus.INSUFFICIENT
    assert forward.coverage.critical_path_satisfied is False


# ============================== 7. Component coverage identity ==============================


def test_component_coverage_identity_preserved_via_spy(monkeypatch):
    import app.evaluation.orchestrator as orchestrator_module

    original_map = dict(orchestrator_module._COMPONENT_COVERAGE_EVALUATORS)
    captured: dict[Component, object] = {}

    def make_spy(component, fn):
        def spy(feature_results):
            value = fn(feature_results)
            captured[component] = value
            return value

        return spy

    monkeypatch.setattr(
        orchestrator_module,
        "_COMPONENT_COVERAGE_EVALUATORS",
        {c: make_spy(c, fn) for c, fn in original_map.items()},
    )

    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert len(captured) == 5
    for ca in state.component_assessments:
        assert ca.coverage is captured[ca.component]


# ============================== 8. Family coverage identity ==============================


def test_family_coverage_identity_preserved_via_spy(monkeypatch):
    import app.evaluation.orchestrator as orchestrator_module
    from app.evaluation.coverage_evaluator import evaluate_family_coverage as real_evaluate

    captured: dict[tuple, object] = {}

    def spy(component, feature_family, feature_results):
        value = real_evaluate(component, feature_family, feature_results)
        captured[(component, feature_family)] = value
        return value

    monkeypatch.setattr(orchestrator_module, "evaluate_family_coverage", spy)

    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert captured  # spy actually invoked
    for fa in state.family_assessments:
        assert fa.coverage is captured[(fa.component, fa.family_id)]


# ============================== 9. Flatten identity ==============================


def test_flatten_identity_matches_nested_component_family_assessments():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    expected_flat = [fa for ca in state.component_assessments for fa in ca.family_assessments]
    assert len(state.family_assessments) == len(expected_flat)
    for actual, expected in zip(state.family_assessments, expected_flat, strict=True):
        assert actual is expected


# ============================== 10. Normalized data identity ==============================


def test_normalized_research_data_identity_via_builder_spy(monkeypatch):
    import app.evaluation.orchestrator as orchestrator_module
    from app.evaluation.research_data_builder import (
        build_normalized_research_data as real_builder,
    )

    captured = {}

    def spy(result, *, as_of):
        data = real_builder(result, as_of=as_of)
        captured["data"] = data
        return data

    monkeypatch.setattr(orchestrator_module, "build_normalized_research_data", spy)

    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert "data" in captured
    assert state.normalized_research_data is captured["data"]


# ============================== 11. State scope ==============================


def test_state_scope_defaults_stay_none_or_empty():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert state.core_attractiveness is None
    assert state.market_confirmation is None
    assert state.risk is None
    assert state.coverage is None
    assert state.confidence is None
    assert state.event_overlay is None
    assert state.correlation_metadata == []
    assert state.warnings == []


# ============================== 12. No accidental semantics ==============================


def test_component_score_and_signal_and_confidence_stay_unresolved():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    for ca in state.component_assessments:
        assert ca.score is None
        assert ca.signal == ComponentSignal.UNKNOWN
        assert ca.confidence.level == ConfidenceLevel.UNKNOWN


def test_no_recommendation_policy_or_stock_opportunity_assessment_produced():
    import ast
    import inspect

    import app.evaluation.orchestrator as orchestrator_module

    identifiers: set[str] = set()
    tree = ast.parse(inspect.getsource(orchestrator_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)

    forbidden = {
        "StockOpportunityAssessment",
        "RecommendationPolicy",
        "ATTRACTIVE",
        "UNATTRACTIVE",
        "NEUTRAL",
        "BUY",
        "SELL",
        "HOLD",
    }
    assert identifiers.isdisjoint(forbidden)


def test_no_fake_feature_result_for_unimplemented_registry_features():
    from app.evaluation.feature_registry import list_feature_definitions

    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    produced_ids = {r.feature_id for r in state.feature_results}
    all_registry_ids = {d.feature_id for d in list_feature_definitions()}
    assert len(all_registry_ids) == 14
    assert produced_ids == {_ROE_ID, _OM_ID}
    assert produced_ids < all_registry_ids


def test_future_opportunity_evidence_does_not_mutate_forward_component_assessment():
    from app.evaluation.coverage_evaluator import evaluate_future_opportunity_evidence

    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    forward = next(ca for ca in state.component_assessments if ca.component == Component.FORWARD)
    before = forward.model_copy(deep=True)

    evaluate_future_opportunity_evidence(forward.coverage, EvidencePathAvailability.AVAILABLE)

    assert forward == before


def test_future_opportunity_evidence_uses_default_unknown_event_path():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert state.future_opportunity_evidence is not None
    assert state.future_opportunity_evidence.event_path_availability == EvidencePathAvailability.UNKNOWN


# ============================== 13. Dependency boundary ==============================


def test_orchestrator_module_has_no_forbidden_dependencies():
    import ast
    import inspect

    import app.evaluation.orchestrator as orchestrator_module

    tree = ast.parse(inspect.getsource(orchestrator_module))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert not any(m.startswith("app.services.") for m in imported_modules)
    assert not any(m.startswith("app.mcp.") for m in imported_modules)
    assert not any(m.startswith("app.api.") for m in imported_modules)
    assert not any(m.startswith("app.supervisor.") for m in imported_modules)
    assert not any(m.startswith("app.discovery.") for m in imported_modules)
    assert not any("anthropic" in m for m in imported_modules)
    assert not any("openai" in m for m in imported_modules)
    # Stock Research Agent 실행(orchestrator/reasoning)을 소유하지 않는다 --
    # DeterministicAnalysisResult 타입만 가져온다.
    assert "app.agents.stock_research.orchestrator" not in imported_modules
    assert "app.agents.stock_research.reasoning" not in imported_modules

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
    RequirementSatisfaction,
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
_NM_ID = "fundamental.profitability.net_margin"
_DR_ID = "fundamental.financial_resilience.debt_ratio"
_PER_ID = "valuation.earnings_based.trailing_per"
_PBR_ID = "valuation.asset_based.pbr"

# RE-05 Post-Orchestration Architecture Review Step F(READY Evaluator
# Expansion)가 확정한 최종 dispatch order 그대로 -- registry 선언 순서.
_IMPLEMENTED_FEATURE_ORDER = (_ROE_ID, _OM_ID, _NM_ID, _DR_ID, _PER_ID, _PBR_ID)

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
    roe: float | None,
    operating_margin: float | None = None,
    net_margin: float | None = None,
    debt_ratio: float | None = None,
    per: float | None = None,
    pbr: float | None = None,
) -> DeterministicAnalysisResult:
    annual_kwargs = {}
    if operating_margin is not None:
        annual_kwargs["operating_margin"] = operating_margin
    if net_margin is not None:
        annual_kwargs["net_margin"] = net_margin
    if debt_ratio is not None:
        annual_kwargs["debt_ratio"] = debt_ratio
    financial_features = (
        FinancialFeatures(annual=[AnnualFinancialFeatures(business_year="2025", **annual_kwargs)])
        if annual_kwargs
        else FinancialFeatures()
    )
    return DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", roe=roe, per=per, pbr=pbr),
        financial_features=financial_features,
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )


# ============================== 1. Happy path ==============================


def test_happy_path_produces_six_feature_results_and_five_components():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert len(state.feature_results) == 6
    assert len(state.component_assessments) == 5


# ============================== 2. Partial feature ==============================


def test_partial_feature_missing_operating_margin_still_completes():
    result_input = _deterministic_result(roe=12.3, operating_margin=None)
    state = run_first_deterministic_pipeline(result_input, _context())

    results_by_id = {r.feature_id: r for r in state.feature_results}
    assert len(state.feature_results) == 6
    assert results_by_id[_ROE_ID].raw is not None
    assert results_by_id[_ROE_ID].raw.value == 12.3
    assert results_by_id[_OM_ID].raw is None
    assert results_by_id[_OM_ID].warnings != []


# ============================== 3. No implemented feature data ==============================


def test_no_implemented_feature_data_still_completes_with_unavailable():
    from app.models.recommendation import AvailabilityStatus

    result_input = _deterministic_result(roe=None, operating_margin=None)
    state = run_first_deterministic_pipeline(result_input, _context())

    assert len(state.feature_results) == 6
    for r in state.feature_results:
        assert r.availability == AvailabilityStatus.UNAVAILABLE
    assert len(state.component_assessments) == 5


# ============================== 4. Evaluator dispatch ==============================


def test_evaluator_dispatch_executes_exactly_the_six_implemented_features():
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    feature_ids = {r.feature_id for r in state.feature_results}
    assert feature_ids == set(_IMPLEMENTED_FEATURE_ORDER)


def test_evaluator_dispatch_order_is_deterministic():
    """RE-05 Post-Orchestration Architecture Review Step F: registry
    선언 순서(ROE -> Operating Margin -> Net Margin -> Debt Ratio ->
    Trailing PER -> PBR)를 그대로 재현한다 -- alphabetical order가
    아니다(예: Debt Ratio가 Net Margin보다 알파벳상 앞이지만 실제
    순서는 반대)."""
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    actual_order = tuple(r.feature_id for r in state.feature_results)
    assert actual_order == _IMPLEMENTED_FEATURE_ORDER


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
    # Step J: top-level coverage는 이제 채워진다(evidence-coverage summary일
    # 뿐 producer/policy가 아니다) -- 이 fixture는 Debt Ratio/Trailing PER가
    # 없어 Fundamental/Valuation critical-path가 False다.
    assert state.coverage is not None
    assert state.coverage.critical_path_satisfied is False
    assert state.coverage.coverage_status is CoverageStatus.INSUFFICIENT
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
    assert produced_ids == set(_IMPLEMENTED_FEATURE_ORDER)
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


# ============================== 14. READY Evaluator Expansion (Step F) ==============================
#
# RE-05 Post-Orchestration Architecture Review Step D §14 / Step E §14가
# 별도 스크립트로 empirically 확인한 두 coverage gate 전환을, 이번
# 구현에서 영구 회귀 테스트로 고정한다 -- coverage_evaluator.py는 이
# 슬라이스에서 전혀 수정하지 않았다(기존 FROZEN Tier 판정 로직이
# evaluator 6개 확장에 그대로 반응할 뿐이다).


def test_fundamental_critical_path_satisfied_when_debt_ratio_available():
    """Fundamental critical_path_satisfied는 이전에는 Debt Ratio
    evaluator가 없어 항상 False였다 -- Debt Ratio evaluator 하나만으로
    True로 전환된다(profitability family는 이미 ROE+Operating Margin
    으로 SUFFICIENT였다)."""
    result_input = _deterministic_result(
        roe=12.3, operating_margin=15.0, debt_ratio=66.7
    )
    state = run_first_deterministic_pipeline(result_input, _context())

    fundamental = next(
        ca for ca in state.component_assessments if ca.component == Component.FUNDAMENTAL
    )
    assert fundamental.coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert fundamental.coverage.critical_path_satisfied is True


def test_valuation_critical_path_satisfied_when_trailing_per_available():
    """Valuation critical_path_satisfied는 이전에는 evaluator가 0개라
    항상 False였다 -- Trailing PER evaluator 하나만으로 True로
    전환된다(existence-based OR, earnings_based family)."""
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0, per=10.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    valuation = next(
        ca for ca in state.component_assessments if ca.component == Component.VALUATION
    )
    assert valuation.coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert valuation.coverage.critical_path_satisfied is True


def test_fundamental_still_insufficient_without_debt_ratio():
    """회귀 방지: Net Margin만 추가되고 Debt Ratio가 여전히 없으면
    Fundamental critical_path_satisfied는 계속 False다(financial_resilience
    family가 여전히 비어 있으므로) -- evaluator 확장 자체가 아니라
    Debt Ratio raw evidence의 존재가 gate를 연다는 것을 대조 확인한다."""
    result_input = _deterministic_result(roe=12.3, operating_margin=15.0, net_margin=8.0)
    state = run_first_deterministic_pipeline(result_input, _context())

    fundamental = next(
        ca for ca in state.component_assessments if ca.component == Component.FUNDAMENTAL
    )
    assert fundamental.coverage.critical_path_satisfied is False


def test_producer_layer_still_none_after_evaluator_expansion():
    """evaluator breadth 확장이 producer semantics를 암묵적으로
    추가하지 않았음을 확인한다 -- state_scope 회귀(§11)와 별개로,
    coverage gate가 실제로 전환되는 fixture에서도 producer layer는
    여전히 전부 None이어야 한다."""
    result_input = _deterministic_result(
        roe=12.3, operating_margin=15.0, debt_ratio=66.7, per=10.0
    )
    state = run_first_deterministic_pipeline(result_input, _context())

    assert state.core_attractiveness is None
    assert state.market_confirmation is None
    assert state.risk is None
    assert state.confidence is None

    # Step J: top-level State Coverage -- Fundamental+Valuation critical
    # foundation은 충족, Forward(0 feature)는 status에만 기여해 INSUFFICIENT.
    assert state.coverage is not None
    assert state.coverage.critical_path_satisfied is True
    assert state.coverage.coverage_status is CoverageStatus.INSUFFICIENT
    assert state.coverage.coverage_percentage is None

    # FutureOpportunityEvidence는 State Coverage와 별개로 계속 계산된다.
    assert state.future_opportunity_evidence is not None
    assert (
        state.future_opportunity_evidence.requirement_satisfied
        is RequirementSatisfaction.UNKNOWN
    )


# ============================== 15. Top-level State Coverage (Step J) ==============================


def test_state_coverage_is_new_instance_distinct_from_every_component_coverage():
    result_input = _deterministic_result(
        roe=12.3, operating_margin=15.0, debt_ratio=66.7, per=10.0
    )
    state = run_first_deterministic_pipeline(result_input, _context())

    assert len(state.component_assessments) == 5
    for component_assessment in state.component_assessments:
        assert state.coverage is not component_assessment.coverage


def test_state_coverage_is_built_from_exact_component_coverages_via_spy(monkeypatch):
    """orchestrator가 state coverage producer에 이미 계산된 component
    coverage 객체를 그대로 넘기고, 그 반환값을 그대로 state에 싣는지
    확인한다(FutureOpportunityEvidence는 입력이 아니다)."""
    from app.evaluation import orchestrator as orchestrator_module
    from app.evaluation.coverage_evaluator import evaluate_recommendation_coverage

    captured = {}

    def spy(component_coverages):
        captured["input"] = dict(component_coverages)
        captured["output"] = evaluate_recommendation_coverage(component_coverages)
        return captured["output"]

    monkeypatch.setattr(orchestrator_module, "evaluate_recommendation_coverage", spy)

    result_input = _deterministic_result(
        roe=12.3, operating_margin=15.0, debt_ratio=66.7, per=10.0
    )
    state = run_first_deterministic_pipeline(result_input, _context())

    assert state.coverage is captured["output"]
    assert list(captured["input"]) == list(Component)
    for component_assessment in state.component_assessments:
        assert captured["input"][component_assessment.component] is component_assessment.coverage


def test_state_coverage_computed_before_future_opportunity_evidence(monkeypatch):
    from app.evaluation import orchestrator as orchestrator_module

    calls = []
    original_state_coverage = orchestrator_module.evaluate_recommendation_coverage
    original_foe = orchestrator_module.evaluate_future_opportunity_evidence

    def state_coverage_spy(*args, **kwargs):
        calls.append("state_coverage")
        return original_state_coverage(*args, **kwargs)

    def foe_spy(*args, **kwargs):
        calls.append("future_opportunity_evidence")
        return original_foe(*args, **kwargs)

    monkeypatch.setattr(
        orchestrator_module, "evaluate_recommendation_coverage", state_coverage_spy
    )
    monkeypatch.setattr(orchestrator_module, "evaluate_future_opportunity_evidence", foe_spy)

    run_first_deterministic_pipeline(_deterministic_result(roe=12.3), _context())

    assert calls == ["state_coverage", "future_opportunity_evidence"]

"""RE-05 FeatureFamilyAssessment / ComponentAssessment Assembly 테스트
(§47 첫 구현, §48 Assembly ↔ Coverage ownership boundary correction).

`docs/dev-log/2026-08-29.md` §47/§48이 이 구현의 설계 근거를 담는다. numeric
threshold/weight/count 테스트는 만들지 않는다(그런 필드 자체가 assembly
결과에 존재하지 않는다는 것만 검증한다).

§48부터 모든 테스트가 "Feature results 생성 -> CoverageEvaluator 명시
호출 -> Assembly에 결과 전달" 순서를 그대로 따른다(§48 지시사항 §4) --
assembly 함수가 Coverage를 스스로 계산하지 않는다는 것을 매 테스트가
구조적으로 보여준다.
"""

import ast
import inspect
from datetime import UTC, datetime

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.assembly import (
    assemble_component_assessment,
    assemble_feature_family_assessments,
)
from app.evaluation.coverage_evaluator import (
    evaluate_family_coverage,
    evaluate_flow_coverage,
    evaluate_forward_coverage,
    evaluate_fundamental_coverage,
    evaluate_future_opportunity_evidence,
    evaluate_market_coverage,
    evaluate_valuation_coverage,
    get_component_families,
)
from app.evaluation.feature_registry import get_feature_definition
from app.evaluation.fundamental_evaluators import (
    OperatingMarginFeatureEvaluator,
    RoeFeatureEvaluator,
)
from app.evaluation.research_data_builder import build_normalized_research_data
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.recommendation import (
    AvailabilityStatus,
    Component,
    ComponentSignal,
    ComponentStatus,
    ConfidenceLevel,
    CoverageAssessment,
    EvaluationBasis,
    EvidencePathAvailability,
    FeatureEvaluationResult,
    FeatureFamilyStatus,
    Provenance,
)
from app.models.research_context import EvaluationContext, RecommendationEvaluationState
from app.models.stock import (
    AnnualFinancialFeatures,
    FinancialFeatures,
    FinancialSnapshot,
    StockPriceSnapshot,
)

_AS_OF = datetime(2026, 8, 29, tzinfo=UTC)
_ROE_ID = "fundamental.profitability.roe"
_OM_ID = "fundamental.profitability.operating_margin"
_DEBT_RATIO_ID = "fundamental.financial_resilience.debt_ratio"
_FUNDAMENTAL_FAMILY_IDS = (
    "profitability",
    "observed_growth_quality",
    "cash_earnings_quality",
    "financial_resilience",
    "capital_efficiency",
)


def _context() -> EvaluationContext:
    return EvaluationContext(symbol="005930", as_of=_AS_OF)


def _real_roe_and_operating_margin_results() -> list[FeatureEvaluationResult]:
    result_input = DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", roe=12.3),
        financial_features=FinancialFeatures(
            annual=[AnnualFinancialFeatures(business_year="2025", operating_margin=15.0)]
        ),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )
    data = build_normalized_research_data(result_input, as_of=_AS_OF)
    context = _context()
    return [
        RoeFeatureEvaluator().evaluate(data, context),
        OperatingMarginFeatureEvaluator().evaluate(data, context),
    ]


def _hypothetical_result(
    feature_id: str, availability: AvailabilityStatus
) -> FeatureEvaluationResult:
    definition = get_feature_definition(feature_id)
    return FeatureEvaluationResult(
        feature_id=feature_id,
        component=definition.component,
        feature_family=definition.feature_family,
        availability=availability,
        requirement_role=definition.default_requirement_role,
        evaluation_basis=[EvaluationBasis.ABSOLUTE],
        provenance=Provenance(source="test"),
    )


def _fundamental_family_coverages(
    feature_results: list[FeatureEvaluationResult],
) -> dict[str, CoverageAssessment]:
    """§48 지시사항 §4의 순서 그대로: CoverageEvaluator를 명시적으로 먼저
    호출해 family_coverages map을 만든다 -- assembly 함수가 이 계산을
    스스로 하지 않는다는 것을 테스트 구조 자체로 보여준다."""
    return {
        family: evaluate_family_coverage(Component.FUNDAMENTAL, family, feature_results)
        for family in get_component_families(Component.FUNDAMENTAL)
    }


def _assemble_fundamental(
    feature_results: list[FeatureEvaluationResult],
):
    """테스트 편의 helper -- Coverage를 명시적으로 먼저 계산한 뒤
    assembly에 전달하는 §48 순서를 그대로 캡슐화한다(production
    orchestration이 아니다, 테스트 전용)."""
    family_coverages = _fundamental_family_coverages(feature_results)
    family_assessments = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, feature_results, family_coverages
    )
    component_coverage = evaluate_fundamental_coverage(feature_results)
    component_assessment = assemble_component_assessment(
        Component.FUNDAMENTAL, family_assessments, component_coverage
    )
    return family_assessments, component_assessment, family_coverages, component_coverage


# ============================== §49: generic multi-component helpers ==============================

_COMPONENT_COVERAGE_FN = {
    Component.FUNDAMENTAL: evaluate_fundamental_coverage,
    Component.VALUATION: evaluate_valuation_coverage,
    Component.FORWARD: evaluate_forward_coverage,
    Component.FLOW: evaluate_flow_coverage,
    Component.MARKET_CONFIRMATION: evaluate_market_coverage,
}

_ALL_COMPONENTS = (
    Component.FUNDAMENTAL,
    Component.VALUATION,
    Component.FORWARD,
    Component.FLOW,
    Component.MARKET_CONFIRMATION,
)


def _family_coverages(
    component: Component, feature_results: list[FeatureEvaluationResult]
) -> dict[str, CoverageAssessment]:
    """§48 순서(Coverage 먼저 계산 -> Assembly에 전달)를 임의 component에
    대해 일반화한 테스트 helper -- production orchestrator가 아니다."""
    return {
        family: evaluate_family_coverage(component, family, feature_results)
        for family in get_component_families(component)
    }


def _assemble(component: Component, feature_results: list[FeatureEvaluationResult]):
    """`_assemble_fundamental`의 component-agnostic 버전 -- §49가
    확인하려는 바로 그 사실(동일 generic assembly 함수가 5개 component
    전부에 재사용 가능하다는 것)을 테스트 helper 레벨에서도 실증한다."""
    family_coverages = _family_coverages(component, feature_results)
    family_assessments = assemble_feature_family_assessments(
        component, feature_results, family_coverages
    )
    component_coverage = _COMPONENT_COVERAGE_FN[component](feature_results)
    component_assessment = assemble_component_assessment(
        component, family_assessments, component_coverage
    )
    return family_assessments, component_assessment, family_coverages, component_coverage


def _module_code_identifiers() -> set[str]:
    """`assembly` 모듈의 실제 AST 식별자만 모은다 -- docstring 산문에
    등장하는 단어를 코드로 오인하지 않는다."""
    import app.evaluation.assembly as module

    tree = ast.parse(inspect.getsource(module))
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            identifiers.add(node.name)
    return identifiers


# ============================== §48 core audit: Assembly does not execute Coverage ==============================


def test_assembly_module_does_not_import_coverage_evaluator_execution_functions():
    """§48.1 correction 재확인: assembly.py는 evaluate_family_coverage/
    evaluate_fundamental_coverage/evaluate_*_coverage를 더 이상 import하지
    않는다 -- get_component_families(순수 family 목록 accessor, 실행이
    아니다)만 가져온다."""
    import app.evaluation.assembly as module

    tree = ast.parse(inspect.getsource(module))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)

    assert "evaluate_family_coverage" not in imported_names
    assert "evaluate_fundamental_coverage" not in imported_names
    assert not any(name.startswith("evaluate_") for name in imported_names)
    assert "get_component_families" in imported_names


def test_family_assembly_consumes_precomputed_coverage_by_identity():
    """§48 case 1/2/5: 호출자가 미리 계산한 CoverageAssessment 객체가
    assembly 결과에 identity(`is`)까지 보존된 채 그대로 들어간다 --
    value가 우연히 같은 게 아니라 동일 객체다."""
    results = _real_roe_and_operating_margin_results()
    family_coverages = _fundamental_family_coverages(results)
    assessments = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, results, family_coverages
    )

    for fa in assessments:
        assert fa.coverage is family_coverages[fa.family_id]


def test_component_assembly_consumes_precomputed_coverage_by_identity():
    """§48 case 1/2/5(component level)."""
    results = _real_roe_and_operating_margin_results()
    family_coverages = _fundamental_family_coverages(results)
    family_assessments = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, results, family_coverages
    )
    component_coverage = evaluate_fundamental_coverage(results)
    component_assessment = assemble_component_assessment(
        Component.FUNDAMENTAL, family_assessments, component_coverage
    )
    assert component_assessment.coverage is component_coverage


def test_coverage_not_reinterpreted_or_transformed():
    """§48 case 4: 전달된 CoverageAssessment의 필드 값이 assembly를
    거치며 변형되지 않는다 -- 그대로 보존된다(deep copy와 비교해 값도
    동일함을 재확인, identity 테스트와 상호 보완)."""
    results = _real_roe_and_operating_margin_results()
    family_coverages = _fundamental_family_coverages(results)
    snapshot = {k: v.model_copy(deep=True) for k, v in family_coverages.items()}

    assemble_feature_family_assessments(Component.FUNDAMENTAL, results, family_coverages)

    for family, coverage in family_coverages.items():
        assert coverage == snapshot[family]  # assembly 호출 후에도 원본 그대로


def test_assembly_does_not_recompute_when_coverage_changes_externally():
    """§48 case 6: 동일한 feature_results에 대해 서로 다른(가상의)
    CoverageAssessment를 넘기면 assembly는 그 값을 그대로 반영한다 --
    스스로 재계산해 덮어쓰지 않는다는 것을 반증한다."""
    results = _real_roe_and_operating_margin_results()
    real_coverage = evaluate_family_coverage(Component.FUNDAMENTAL, "profitability", results)
    fabricated_coverage = CoverageAssessment(
        critical_path_satisfied=True,
        coverage_status=real_coverage.coverage_status,  # 값 자체는 유지하되 새 객체
        warnings=["fabricated-for-test"],
    )
    family_coverages = _fundamental_family_coverages(results)
    family_coverages["profitability"] = fabricated_coverage

    assessments = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, results, family_coverages
    )
    profitability = next(fa for fa in assessments if fa.family_id == "profitability")
    assert profitability.coverage is fabricated_coverage
    assert "fabricated-for-test" in profitability.coverage.warnings


def test_missing_family_coverage_raises_key_error_not_silent_default():
    """§48: family_coverages에 특정 family가 빠져 있으면 KeyError -- 조용히
    기본값(None 등)을 만들지 않는다(fail-fast, registry 전반의 기존 원칙)."""
    import pytest

    results = _real_roe_and_operating_margin_results()
    incomplete_coverages = _fundamental_family_coverages(results)
    del incomplete_coverages["profitability"]

    with pytest.raises(KeyError):
        assemble_feature_family_assessments(Component.FUNDAMENTAL, results, incomplete_coverages)


# ============================== §18(§47 원 목록) case 1: 5 family identity deterministic ==============================


def test_all_five_fundamental_families_always_generated():
    family_coverages = _fundamental_family_coverages([])
    assessments = assemble_feature_family_assessments(Component.FUNDAMENTAL, [], family_coverages)
    family_ids = tuple(fa.family_id for fa in assessments)
    assert family_ids == _FUNDAMENTAL_FAMILY_IDS  # 순서까지 고정


def test_family_identity_deterministic_across_calls():
    family_coverages = _fundamental_family_coverages([])
    first = [
        fa.family_id
        for fa in assemble_feature_family_assessments(Component.FUNDAMENTAL, [], family_coverages)
    ]
    second = [
        fa.family_id
        for fa in assemble_feature_family_assessments(Component.FUNDAMENTAL, [], family_coverages)
    ]
    assert first == second


# ============================== case 2/3: ROE/Operating Margin placement ==============================


def test_roe_result_placed_in_profitability_family():
    results = _real_roe_and_operating_margin_results()
    family_coverages = _fundamental_family_coverages(results)
    assessments = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, results, family_coverages
    )
    profitability = next(fa for fa in assessments if fa.family_id == "profitability")
    assert _ROE_ID in {r.feature_id for r in profitability.feature_results}


def test_operating_margin_result_placed_in_profitability_family():
    results = _real_roe_and_operating_margin_results()
    family_coverages = _fundamental_family_coverages(results)
    assessments = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, results, family_coverages
    )
    profitability = next(fa for fa in assessments if fa.family_id == "profitability")
    assert _OM_ID in {r.feature_id for r in profitability.feature_results}


def test_roe_and_operating_margin_not_placed_in_other_families():
    results = _real_roe_and_operating_margin_results()
    family_coverages = _fundamental_family_coverages(results)
    assessments = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, results, family_coverages
    )
    for fa in assessments:
        if fa.family_id == "profitability":
            continue
        assert _ROE_ID not in {r.feature_id for r in fa.feature_results}
        assert _OM_ID not in {r.feature_id for r in fa.feature_results}


# ============================== case 4: unrelated component result not placed ==============================


def test_unrelated_component_result_not_placed_in_fundamental():
    """Valuation feature result를 Fundamental assembly에 섞어 넣어도
    어느 family에도 배치되지 않는다(component 불일치)."""
    per_definition = get_feature_definition("valuation.earnings_based.trailing_per")
    per_result = FeatureEvaluationResult(
        feature_id=per_definition.feature_id,
        component=per_definition.component,
        feature_family=per_definition.feature_family,
        availability=AvailabilityStatus.AVAILABLE,
        requirement_role=per_definition.default_requirement_role,
        evaluation_basis=[EvaluationBasis.ABSOLUTE],
        provenance=Provenance(source="test"),
    )
    results = [*_real_roe_and_operating_margin_results(), per_result]
    family_coverages = _fundamental_family_coverages(results)
    assessments = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, results, family_coverages
    )
    all_placed_ids = {r.feature_id for fa in assessments for r in fa.feature_results}
    assert per_definition.feature_id not in all_placed_ids


# ============================== case 5: false completeness via catalog-only feature ==============================


def test_catalog_only_unimplemented_feature_does_not_cause_false_completeness():
    """Debt Ratio(catalog에 있으나 evaluator 없음)가 있어도 family_status
    가 자동으로 EVALUATED가 되지 않는다 -- family identity는 보존되지만
    feature_results에는 나타나지 않는다."""
    family_coverages = _fundamental_family_coverages([])
    assessments = assemble_feature_family_assessments(Component.FUNDAMENTAL, [], family_coverages)
    financial_resilience = next(fa for fa in assessments if fa.family_id == "financial_resilience")
    assert financial_resilience.family_status == FeatureFamilyStatus.NOT_EVALUATED
    assert financial_resilience.feature_results == []
    assert _DEBT_RATIO_ID not in {r.feature_id for r in financial_resilience.feature_results}
    assert financial_resilience.family_id == "financial_resilience"


# ============================== case 8/9: score/signal missing != 0/NEUTRAL ==============================


def test_component_score_is_none_not_zero():
    results = _real_roe_and_operating_margin_results()
    _, component_assessment, _, _ = _assemble_fundamental(results)
    assert component_assessment.score is None
    assert component_assessment.score != 0


def test_component_signal_is_unknown_not_neutral():
    results = _real_roe_and_operating_margin_results()
    _, component_assessment, _, _ = _assemble_fundamental(results)
    assert component_assessment.signal == ComponentSignal.UNKNOWN
    assert component_assessment.signal != ComponentSignal.NEUTRAL


def test_family_score_is_always_none():
    results = _real_roe_and_operating_margin_results()
    family_assessments, _, _, _ = _assemble_fundamental(results)
    for fa in family_assessments:
        assert fa.family_score is None


# ============================== case 10/11: coverage != confidence, 자동 HIGH 생성 안 함 ==============================


def test_coverage_and_confidence_are_independent_fields():
    """SUFFICIENT coverage 상태에서도 confidence는 자동으로 HIGH가 되지
    않는다 -- 항상 UNKNOWN이다."""
    per_result = _hypothetical_result(
        "valuation.earnings_based.trailing_per", AvailabilityStatus.AVAILABLE
    )
    coverage = evaluate_valuation_coverage([per_result])
    assert coverage.coverage_status.value == "sufficient"  # earnings_based가 SUFFICIENT임을 재확인

    family_coverages = {
        family: evaluate_family_coverage(Component.VALUATION, family, [per_result])
        for family in get_component_families(Component.VALUATION)
    }
    family_assessments = assemble_feature_family_assessments(
        Component.VALUATION, [per_result], family_coverages
    )
    component_assessment = assemble_component_assessment(
        Component.VALUATION, family_assessments, coverage
    )
    assert component_assessment.confidence.level == ConfidenceLevel.UNKNOWN


def test_confidence_never_auto_generated_as_high_or_medium():
    results = _real_roe_and_operating_margin_results()
    family_assessments, component_assessment, _, _ = _assemble_fundamental(results)
    assert component_assessment.confidence.level == ConfidenceLevel.UNKNOWN
    assert len(component_assessment.confidence.warnings) >= 1
    for fa in family_assessments:
        assert fa.confidence is not None
        assert fa.confidence.level == ConfidenceLevel.UNKNOWN


# ============================== case 12: fake UNAVAILABLE result 생성 안 함 ==============================


def test_no_fake_feature_evaluation_result_generated():
    """Debt Ratio(evaluator 없음)에 대해 UNAVAILABLE fake result가 만들어
    지지 않는다 -- feature_results 리스트에 아예 나타나지 않아야 한다."""
    family_coverages = _fundamental_family_coverages([])
    assessments = assemble_feature_family_assessments(Component.FUNDAMENTAL, [], family_coverages)
    all_result_ids = {r.feature_id for fa in assessments for r in fa.feature_results}
    assert _DEBT_RATIO_ID not in all_result_ids
    assert all_result_ids == set()


# ============================== case 13: deterministic ordering ==============================


def test_feature_ordering_within_family_is_catalog_order_not_input_order():
    """입력 리스트 순서를 뒤집어도(Operating Margin 먼저, ROE 나중)
    family 안의 feature_results 순서는 catalog(registry) 순서를 따른다."""
    results = _real_roe_and_operating_margin_results()
    reversed_results = list(reversed(results))
    assert reversed_results[0].feature_id != results[0].feature_id

    forward_coverages = _fundamental_family_coverages(results)
    reversed_coverages = _fundamental_family_coverages(reversed_results)
    forward_order = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, results, forward_coverages
    )
    reversed_order = assemble_feature_family_assessments(
        Component.FUNDAMENTAL, reversed_results, reversed_coverages
    )

    forward_ids = [
        r.feature_id
        for r in next(fa for fa in forward_order if fa.family_id == "profitability").feature_results
    ]
    reversed_ids = [
        r.feature_id
        for r in next(
            fa for fa in reversed_order if fa.family_id == "profitability"
        ).feature_results
    ]
    assert forward_ids == reversed_ids


# ============================== case 14: deterministic output ==============================


def test_assembly_output_is_deterministic():
    results = _real_roe_and_operating_margin_results()
    _, first, _, _ = _assemble_fundamental(results)
    _, second, _, _ = _assemble_fundamental(results)
    assert first == second


# ============================== case 15: no threshold/weight/count ==============================


def test_assembly_module_source_has_no_numeric_policy():
    import app.evaluation.assembly as module

    source = inspect.getsource(module)
    for term in ("threshold=", "weight=", "lookback=", "window=", "cutoff=", "/ len("):
        assert term not in source


def test_component_assessment_has_no_computed_numeric_score():
    results = _real_roe_and_operating_margin_results()
    _, component_assessment, _, _ = _assemble_fundamental(results)
    assert component_assessment.score is None


# ============================== case 16: no recommendation classification ==============================


def test_assembly_module_produces_no_recommendation_classification():
    identifiers = _module_code_identifiers()
    forbidden = {"ATTRACTIVE", "UNATTRACTIVE", "BUY", "SELL", "HOLD", "OpportunityClassification"}
    assert identifiers.isdisjoint(forbidden)


# ============================== case 17: no LLM/API dependency ==============================


def test_assembly_module_has_no_vendor_llm_or_portfolio_dependency():
    """import 구문에 vendor/LLM/portfolio 의존성이 없는지 확인한다 --
    docstring 산문은 검사 대상이 아니다, 실제 import 문/식별자만 본다."""
    import app.evaluation.assembly as module

    tree = ast.parse(inspect.getsource(module))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert not any(m.startswith("app.services.") for m in imported_modules)
    assert not any(m.startswith("app.mcp.") for m in imported_modules)
    assert not any("anthropic" in m for m in imported_modules)
    assert not any("openai" in m for m in imported_modules)
    identifiers = _module_code_identifiers()
    assert "StockAnalysis" not in identifiers
    assert "PortfolioContext" not in identifiers


# ============================== case 18: RecommendationEvaluationState compatibility ==============================


def test_recommendation_evaluation_state_can_hold_fundamental_component_assessment():
    as_of = _AS_OF
    context = _context()
    result_input = DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=1.0),
        financials=FinancialSnapshot(business_year="2025", roe=12.3),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )
    normalized_data = build_normalized_research_data(result_input, as_of=as_of)
    results = _real_roe_and_operating_margin_results()
    _, component_assessment, _, _ = _assemble_fundamental(results)

    state = RecommendationEvaluationState(
        context=context,
        normalized_research_data=normalized_data,
        feature_results=results,
        component_assessments=[component_assessment],
    )
    assert state.component_assessments[0] is component_assessment
    assert state.component_assessments[0].component == Component.FUNDAMENTAL


# ============================== case 19: CoverageEvaluator regression ==============================


def test_coverage_evaluator_regression_unaffected_by_assembly_module():
    results = _real_roe_and_operating_margin_results()
    debt_ratio = _hypothetical_result(_DEBT_RATIO_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_fundamental_coverage([*results, debt_ratio])
    assert coverage.coverage_status.value == "sufficient"
    assert coverage.critical_path_satisfied is True


# ============================== case 20: existing feature evaluator regression ==============================


def test_roe_and_operating_margin_evaluator_regression_unaffected_by_assembly_module():
    results = _real_roe_and_operating_margin_results()
    assert results[0].feature_id == _ROE_ID
    assert results[0].availability == AvailabilityStatus.AVAILABLE
    assert results[0].raw.value == 12.3
    assert results[1].feature_id == _OM_ID


# ============================== Component/family status semantics ==============================


def test_component_status_partially_evaluated_when_some_families_have_results():
    results = _real_roe_and_operating_margin_results()
    _, component_assessment, _, _ = _assemble_fundamental(results)
    assert component_assessment.status == ComponentStatus.PARTIALLY_EVALUATED


def test_component_status_unavailable_when_nothing_evaluated():
    _, component_assessment, _, _ = _assemble_fundamental([])
    assert component_assessment.status == ComponentStatus.UNAVAILABLE


def test_family_status_not_evaluated_for_zero_registered_feature_family():
    """cash_earnings_quality는 등록 feature가 0개다 -- vacuous EVALUATED가
    아니라 NOT_EVALUATED로 정직하게 표현된다."""
    family_coverages = _fundamental_family_coverages([])
    assessments = assemble_feature_family_assessments(Component.FUNDAMENTAL, [], family_coverages)
    cash_earnings_quality = next(
        fa for fa in assessments if fa.family_id == "cash_earnings_quality"
    )
    assert cash_earnings_quality.family_status == FeatureFamilyStatus.NOT_EVALUATED


# ============================== Assembly boundary self-audit ==============================


def test_assembly_does_not_import_fundamental_evaluators():
    """assembly.py는 evaluator를 재구현하지 않는다 -- 오직
    FeatureEvaluationResult/FeatureDefinition/CoverageAssessment만
    소비한다."""
    import app.evaluation.assembly as module

    source = inspect.getsource(module)
    assert "fundamental_evaluators" not in source
    assert "RoeFeatureEvaluator" not in source
    assert "OperatingMarginFeatureEvaluator" not in source


def test_assembly_public_api_has_no_context_parameter():
    params_family = set(inspect.signature(assemble_feature_family_assessments).parameters)
    params_component = set(inspect.signature(assemble_component_assessment).parameters)
    assert params_family == {"component", "feature_results", "family_coverages"}
    assert params_component == {"component", "family_assessments", "component_coverage"}


def test_assembly_public_api_no_fundamental_specific_wrapper_left():
    """§48.3: coverage 실행 책임이 사라지면서 component별 wrapper
    (assemble_fundamental_component_assessment)를 유지할 이유도 함께
    사라졌다 -- generic assemble_component_assessment 하나로 모든
    component를 다룬다."""
    import app.evaluation.assembly as module

    assert not hasattr(module, "assemble_fundamental_component_assessment")
    assert hasattr(module, "assemble_component_assessment")


# ============================== §49: Component Assembly Expansion — Valuation/Forward/Flow/Market ==============================
#
# §49.1 감사 결과: assemble_feature_family_assessments()/
# assemble_component_assessment() 둘 다 이미 component-agnostic이다
# (source에 Component.FUNDAMENTAL 리터럴이 전혀 없음, 아래
# test_assembly_module_has_no_fundamental_specific_literal로 재확인) --
# 이번 세션은 새 production 코드를 추가하지 않고 4개 component 전부에서
# 기존 generic 함수가 실제로 정확히 동작하는지 실증한다.

_PER_ID = "valuation.earnings_based.trailing_per"
_EARNINGS_YIELD_ID = "valuation.earnings_based.earnings_yield"
_PBR_ID = "valuation.asset_based.pbr"

_VALUATION_FAMILY_IDS = (
    "earnings_based",
    "asset_based",
    "ev_based",
    "cash_flow_based",
    "relative_context",
)
_FORWARD_FAMILY_IDS = (
    "consensus_growth",
    "estimate_revision",
    "guidance",
    "expected_economics",
)
_FLOW_FAMILY_IDS = ("investor_flow",)
_MARKET_FAMILY_IDS = ("momentum", "technical_confirmation")


def test_assembly_module_has_no_fundamental_specific_literal():
    """§49.1: assembly.py 소스에 `Component.FUNDAMENTAL` 리터럴이 전혀
    없다 -- 특정 component를 위한 하드코딩이 아니라는 것을 직접 재확인
    한다(문서 주장이 아니라 실제 코드로)."""
    import app.evaluation.assembly as module

    source = inspect.getsource(module)
    assert "FUNDAMENTAL" not in source


# ---- Valuation ----


def test_valuation_canonical_family_generated_in_order():
    """§15 Valuation case 1."""
    family_assessments, _, _, _ = _assemble(Component.VALUATION, [])
    family_ids = tuple(fa.family_id for fa in family_assessments)
    assert family_ids == _VALUATION_FAMILY_IDS


def test_valuation_feature_results_placed_in_correct_family():
    """§15 Valuation case 2."""
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.AVAILABLE)
    pbr_result = _hypothetical_result(_PBR_ID, AvailabilityStatus.AVAILABLE)
    family_assessments, _, _, _ = _assemble(Component.VALUATION, [per_result, pbr_result])

    earnings_based = next(fa for fa in family_assessments if fa.family_id == "earnings_based")
    asset_based = next(fa for fa in family_assessments if fa.family_id == "asset_based")
    assert _PER_ID in {r.feature_id for r in earnings_based.feature_results}
    assert _PBR_ID in {r.feature_id for r in asset_based.feature_results}
    assert _PBR_ID not in {r.feature_id for r in earnings_based.feature_results}
    assert _PER_ID not in {r.feature_id for r in asset_based.feature_results}


def test_valuation_precomputed_coverage_identity_preserved():
    """§15 Valuation case 3."""
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.AVAILABLE)
    family_assessments, component_assessment, family_coverages, component_coverage = _assemble(
        Component.VALUATION, [per_result]
    )
    for fa in family_assessments:
        assert fa.coverage is family_coverages[fa.family_id]
    assert component_assessment.coverage is component_coverage


def test_valuation_asset_based_context_dependent_warning_passed_through_unchanged():
    """Asset-based(CONTEXT_DEPENDENT) semantics는 이미 coverage 결과에
    반영돼 있다 -- assembly가 이를 재해석하지 않고 그대로 통과시킨다."""
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.AVAILABLE)
    family_assessments, _, _, component_coverage = _assemble(Component.VALUATION, [per_result])
    asset_based = next(fa for fa in family_assessments if fa.family_id == "asset_based")
    assert any("CONTEXT_DEPENDENT" in w for w in component_coverage.warnings)
    # family-level coverage 자체에는 CONTEXT_DEPENDENT note가 없다(그 note는
    # component 레벨 집계에서 붙는다, §45/§46) -- assembly는 이 구분을
    # 만들지도 지우지도 않고 각 레벨의 coverage를 있는 그대로 전달한다.
    assert asset_based.coverage is not None


# ---- Forward ----


def test_forward_four_families_generated_even_with_zero_features():
    """§15 Forward case 4."""
    family_assessments, _, _, _ = _assemble(Component.FORWARD, [])
    family_ids = tuple(fa.family_id for fa in family_assessments)
    assert family_ids == _FORWARD_FAMILY_IDS
    for fa in family_assessments:
        assert fa.feature_results == []
        assert fa.family_status == FeatureFamilyStatus.NOT_EVALUATED


def test_forward_coverage_identity_preserved():
    """§15 Forward case 5."""
    _, component_assessment, _, component_coverage = _assemble(Component.FORWARD, [])
    assert component_assessment.coverage is component_coverage
    # §46.4가 확정한 그대로 -- Forward는 Flow/Market과 달리 INSUFFICIENT다.
    assert component_coverage.coverage_status.value == "insufficient"
    assert component_coverage.critical_path_satisfied is False


def test_future_opportunity_evidence_not_placed_inside_forward_component():
    """§15 Forward case 6 + 핵심 boundary 확인: Forward
    ComponentAssessment에는 future_opportunity_evidence 같은 필드가
    아예 없다 -- 넣을 방법 자체가 model에 없다(model 필드 목록으로 재확인)."""
    _, component_assessment, _, _ = _assemble(Component.FORWARD, [])
    assert not hasattr(component_assessment, "future_opportunity_evidence")
    assert "future_opportunity_evidence" not in type(component_assessment).model_fields


def test_event_evidence_does_not_mutate_forward_component_assessment():
    """Event evidence가 AVAILABLE이어도 이미 조립된 Forward
    ComponentAssessment는 그대로다(RE-04 Event Overlay 원칙, §46.9의
    component-assembly 버전)."""
    _, component_assessment, _, forward_coverage = _assemble(Component.FORWARD, [])
    before = component_assessment.model_copy(deep=True)
    evaluate_future_opportunity_evidence(forward_coverage, EvidencePathAvailability.AVAILABLE)
    assert component_assessment == before


# ---- Flow ----


def test_flow_investor_flow_family_generated():
    """§15 Flow case 7."""
    family_assessments, _, _, _ = _assemble(Component.FLOW, [])
    family_ids = tuple(fa.family_id for fa in family_assessments)
    assert family_ids == _FLOW_FAMILY_IDS


def test_flow_allows_zero_features_without_disappearing():
    """§15 Flow case 8."""
    family_assessments, component_assessment, _, _ = _assemble(Component.FLOW, [])
    investor_flow = family_assessments[0]
    assert investor_flow.family_id == "investor_flow"
    assert investor_flow.feature_results == []
    assert component_assessment.status == ComponentStatus.UNAVAILABLE


def test_flow_unknown_coverage_preserved_not_upgraded_to_sufficient():
    """§15 Flow case 9 + §14 false-completeness 핵심: registered feature가
    0개인데도 coverage가 SUFFICIENT로 승격되지 않는다."""
    _, component_assessment, _, component_coverage = _assemble(Component.FLOW, [])
    assert component_coverage.coverage_status.value == "unknown"
    assert component_assessment.coverage.coverage_status.value != "sufficient"
    assert component_assessment.score is None
    assert component_assessment.signal == ComponentSignal.UNKNOWN


# ---- Market ----


def test_market_momentum_and_technical_confirmation_families_generated():
    """§15 Market case 10."""
    family_assessments, _, _, _ = _assemble(Component.MARKET_CONFIRMATION, [])
    family_ids = tuple(fa.family_id for fa in family_assessments)
    assert family_ids == _MARKET_FAMILY_IDS


def test_market_allows_zero_features_without_disappearing():
    """§15 Market case 11."""
    family_assessments, _, _, _ = _assemble(Component.MARKET_CONFIRMATION, [])
    for fa in family_assessments:
        assert fa.feature_results == []
        assert fa.family_status == FeatureFamilyStatus.NOT_EVALUATED


def test_market_non_gating_coverage_state_passed_through_unchanged():
    """§15 Market case 12: Assembly는 NOT_DECISION_GATING 여부를 다시
    판단하지 않는다 -- CoverageEvaluator가 이미 만든 warning/상태를
    그대로 소비한다."""
    _, component_assessment, _, component_coverage = _assemble(Component.MARKET_CONFIRMATION, [])
    assert component_assessment.coverage is component_coverage
    assert any("NOT_DECISION_GATING" in w for w in component_coverage.warnings)
    assert component_assessment.coverage.coverage_status.value == "unknown"


# ---- 공통 (§15 case 13~19) ----


def test_score_none_across_all_five_components():
    for component in _ALL_COMPONENTS:
        _, component_assessment, _, _ = _assemble(component, [])
        assert component_assessment.score is None


def test_signal_unknown_across_all_five_components():
    for component in _ALL_COMPONENTS:
        _, component_assessment, _, _ = _assemble(component, [])
        assert component_assessment.signal == ComponentSignal.UNKNOWN


def test_confidence_unknown_across_all_five_components():
    for component in _ALL_COMPONENTS:
        _, component_assessment, _, _ = _assemble(component, [])
        assert component_assessment.confidence.level == ConfidenceLevel.UNKNOWN


def test_no_fake_feature_evaluation_result_across_all_five_components():
    for component in _ALL_COMPONENTS:
        family_assessments, _, _, _ = _assemble(component, [])
        all_ids = {r.feature_id for fa in family_assessments for r in fa.feature_results}
        assert all_ids == set()


def test_deterministic_family_order_across_all_five_components():
    for component in _ALL_COMPONENTS:
        first = [fa.family_id for fa in _assemble(component, [])[0]]
        second = [fa.family_id for fa in _assemble(component, [])[0]]
        assert first == second
        assert tuple(first) == get_component_families(component)


def test_deterministic_feature_order_for_valuation_regardless_of_input_order():
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.AVAILABLE)
    ey_result = _hypothetical_result(_EARNINGS_YIELD_ID, AvailabilityStatus.AVAILABLE)

    forward_order, _, _, _ = _assemble(Component.VALUATION, [per_result, ey_result])
    reversed_order, _, _, _ = _assemble(Component.VALUATION, [ey_result, per_result])

    forward_ids = [
        r.feature_id
        for r in next(
            fa for fa in forward_order if fa.family_id == "earnings_based"
        ).feature_results
    ]
    reversed_ids = [
        r.feature_id
        for r in next(
            fa for fa in reversed_order if fa.family_id == "earnings_based"
        ).feature_results
    ]
    assert forward_ids == reversed_ids


def test_assembly_never_calls_coverage_evaluator_for_any_component():
    """§3/§49 self-audit: source scan으로 재확인(모듈 전체에 대해 이미
    test_assembly_module_does_not_import_coverage_evaluator_execution_functions
    가 있지만, 여기서는 5개 component 전부에 대해 identity 보존이라는
    행동적 증거로 다시 확인한다 -- source scan과 행동 증거 둘 다
    갖춘다)."""
    for component in _ALL_COMPONENTS:
        feature_results: list[FeatureEvaluationResult] = []
        family_coverages = _family_coverages(component, feature_results)
        family_assessments = assemble_feature_family_assessments(
            component, feature_results, family_coverages
        )
        for fa in family_assessments:
            assert fa.coverage is family_coverages[fa.family_id]


def test_fundamental_regression_after_component_expansion():
    """§20."""
    results = _real_roe_and_operating_margin_results()
    debt_ratio = _hypothetical_result(_DEBT_RATIO_ID, AvailabilityStatus.AVAILABLE)
    _, component_assessment, _, _ = _assemble_fundamental([*results, debt_ratio])
    assert component_assessment.coverage.coverage_status.value == "sufficient"
    assert component_assessment.status == ComponentStatus.PARTIALLY_EVALUATED


def test_coverage_layer_regression_after_component_expansion():
    """§21."""
    results = _real_roe_and_operating_margin_results()
    coverage = evaluate_fundamental_coverage(results)
    assert coverage.critical_path_satisfied is False  # Debt Ratio 없음


def test_recommendation_evaluation_state_holds_all_five_component_assessments():
    """§13/§22: 5개 component ComponentAssessment 전부를
    RecommendationEvaluationState에 동시에 배치할 수 있다(model 변경
    없음)."""
    as_of = _AS_OF
    context = _context()
    result_input = DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=1.0),
        financials=FinancialSnapshot(business_year="2025", roe=12.3),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )
    normalized_data = build_normalized_research_data(result_input, as_of=as_of)

    component_assessments = [_assemble(component, [])[1] for component in _ALL_COMPONENTS]

    state = RecommendationEvaluationState(
        context=context,
        normalized_research_data=normalized_data,
        component_assessments=component_assessments,
    )
    assert len(state.component_assessments) == 5
    assert {ca.component for ca in state.component_assessments} == set(_ALL_COMPONENTS)


def test_future_opportunity_evidence_stays_top_level_alongside_five_components():
    """§13/§23: FutureOpportunityEvidenceAssessment가
    RecommendationEvaluationState의 top-level/parallel 필드로,
    component_assessments 리스트 안의 Forward ComponentAssessment와
    별개로 공존한다."""
    as_of = _AS_OF
    context = _context()
    result_input = DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=1.0),
        financials=FinancialSnapshot(business_year="2025", roe=12.3),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )
    normalized_data = build_normalized_research_data(result_input, as_of=as_of)

    component_assessments = [_assemble(component, [])[1] for component in _ALL_COMPONENTS]
    forward_coverage = evaluate_forward_coverage([])
    future_opportunity_evidence = evaluate_future_opportunity_evidence(forward_coverage)

    state = RecommendationEvaluationState(
        context=context,
        normalized_research_data=normalized_data,
        component_assessments=component_assessments,
        future_opportunity_evidence=future_opportunity_evidence,
    )
    assert state.future_opportunity_evidence is future_opportunity_evidence
    forward_assessment = next(
        ca for ca in state.component_assessments if ca.component == Component.FORWARD
    )
    assert "future_opportunity_evidence" not in type(forward_assessment).model_fields


def test_no_numeric_params_across_component_expansion_tests():
    """§24."""
    import app.evaluation.assembly as module

    source = inspect.getsource(module)
    for term in ("threshold=", "weight=", "lookback=", "window=", "cutoff=", "/ len("):
        assert term not in source


def test_no_recommendation_classification_across_component_expansion():
    """§25."""
    identifiers = _module_code_identifiers()
    forbidden = {"ATTRACTIVE", "UNATTRACTIVE", "BUY", "SELL", "HOLD", "OpportunityClassification"}
    assert identifiers.isdisjoint(forbidden)


def test_no_llm_api_dependency_across_component_expansion():
    """§26."""
    import app.evaluation.assembly as module

    tree = ast.parse(inspect.getsource(module))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert not any(m.startswith("app.services.") for m in imported_modules)
    assert not any(m.startswith("app.mcp.") for m in imported_modules)
    assert not any("anthropic" in m for m in imported_modules)
    assert not any("openai" in m for m in imported_modules)

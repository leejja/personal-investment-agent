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
    evaluate_fundamental_coverage,
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

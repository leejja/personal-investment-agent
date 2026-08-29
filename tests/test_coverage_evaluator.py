"""RE-05 CoverageEvaluator deterministic Coverage vertical slice 테스트
(Fundamental §43, Valuation §44).

`docs/dev-log/2026-08-29.md` §43/§44가 이 구현의 설계 근거를 담는다. numeric
threshold/weight/window/percentage/count 테스트는 만들지 않는다(그런 필드
자체가 존재하지 않는다는 것만 검증한다).
"""

import inspect
from datetime import UTC, datetime

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.evaluation.coverage_evaluator import (
    FamilyCriticality,
    evaluate_family_coverage,
    evaluate_fundamental_coverage,
    evaluate_valuation_coverage,
    get_family_criticality,
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
    CoverageStatus,
    EvaluationBasis,
    FeatureEvaluationResult,
    Provenance,
    RequirementRole,
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
_DEBT_RATIO_ID = "fundamental.financial_resilience.debt_ratio"
_NET_MARGIN_ID = "fundamental.profitability.net_margin"
_REVENUE_GROWTH_ID = "fundamental.observed_growth_quality.revenue_growth"
_ASSET_TURNOVER_ID = "fundamental.capital_efficiency.asset_turnover"
_ROIC_ID = "fundamental.capital_efficiency.roic"
_PER_ID = "valuation.earnings_based.trailing_per"
_EARNINGS_YIELD_ID = "valuation.earnings_based.earnings_yield"
_PBR_ID = "valuation.asset_based.pbr"


def _module_code_body() -> str:
    """`coverage_evaluator` 모듈 소스에서 module docstring을 제외한 나머지
    부분만 반환한다 -- docstring이 "이 모듈이 하지 않는 것"을 설명하며
    ATTRACTIVE/StockAnalysis/percentage 같은 금지어를 스스로 언급하기
    때문에, source-scan 테스트가 실제 코드가 아니라 문서 텍스트에 false
    positive를 내지 않게 한다."""
    import app.evaluation.coverage_evaluator as module

    source = inspect.getsource(module)
    _, _, body = source.partition('"""')
    _, _, body = body.partition('"""')
    return body


def _context() -> EvaluationContext:
    return EvaluationContext(symbol="005930", as_of=_AS_OF)


def _real_roe_and_operating_margin_results(
    roe: float | None,
    operating_margin: float | None,
) -> list[FeatureEvaluationResult]:
    """실제 ROE/OperatingMargin evaluator를 그대로 실행해 result를 얻는다
    -- coverage 테스트가 evaluator 동작을 재구현하지 않는다."""
    result_input = DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", roe=roe),
        financial_features=FinancialFeatures(
            annual=[
                AnnualFinancialFeatures(business_year="2025", operating_margin=operating_margin)
            ]
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
    feature_id: str,
    availability: AvailabilityStatus,
    requirement_role: RequirementRole | None = None,
) -> FeatureEvaluationResult:
    definition = get_feature_definition(feature_id)
    return FeatureEvaluationResult(
        feature_id=feature_id,
        component=definition.component,
        feature_family=definition.feature_family,
        availability=availability,
        requirement_role=requirement_role
        if requirement_role is not None
        else definition.default_requirement_role,
        evaluation_basis=[EvaluationBasis.ABSOLUTE],
        provenance=Provenance(source="test"),
    )


# ============================== §19-1/2: ROE/Operating Margin AVAILABLE, missing ==============================


def test_roe_and_operating_margin_both_available_still_insufficient_without_debt_ratio():
    """§19 case 1 + §20 false-completeness regression: ROE/Operating
    Margin이 둘 다 AVAILABLE이어도 Debt Ratio(REQUIRED, evaluator 없음)가
    빠져 있으므로 Fundamental coverage는 SUFFICIENT가 아니다 -- 들어온
    result 목록만 보고 "다 있다"고 오판하지 않는다."""
    results = _real_roe_and_operating_margin_results(roe=12.3, operating_margin=15.0)
    assert results[0].availability == AvailabilityStatus.AVAILABLE
    assert results[1].availability == AvailabilityStatus.AVAILABLE

    coverage = evaluate_fundamental_coverage(results)

    assert _ROE_ID in coverage.available_required
    assert _OM_ID in coverage.available_required
    assert _DEBT_RATIO_ID in coverage.missing_required
    assert coverage.coverage_status != CoverageStatus.SUFFICIENT
    assert coverage.critical_path_satisfied is False


def test_roe_missing_from_result_list():
    """§19 case 2: ROE evaluator가 애초에 실행되지 않아 result 자체가
    없다 -- RESULT_MISSING으로 분류되고 missing_required에 남는다."""
    coverage = evaluate_fundamental_coverage([])
    assert _ROE_ID in coverage.missing_required
    assert any("no result provided this cycle" in w for w in coverage.warnings if _ROE_ID in w)


# ============================== §19-3: NOT_APPLICABLE ==============================


def test_operating_margin_not_applicable_excluded_from_missing_required():
    """§19 case 3: Operating Margin이 runtime NOT_APPLICABLE이면
    missing_required가 아니라 not_applicable bucket으로 간다(§41.9 우선순위
    규칙) -- 이 결과만으로 Profitability family가 자동 INSUFFICIENT가
    되지 않는다(ROE만 effective REQUIRED로 남는다)."""
    roe_result = _hypothetical_result(_ROE_ID, AvailabilityStatus.AVAILABLE)
    om_result = _hypothetical_result(_OM_ID, AvailabilityStatus.NOT_APPLICABLE)

    profitability = evaluate_family_coverage(
        Component.FUNDAMENTAL, "profitability", [roe_result, om_result]
    )
    assert _OM_ID in profitability.not_applicable
    assert _OM_ID not in profitability.missing_required
    # ROE만 남은 effective REQUIRED가 AVAILABLE이므로 family 자체는
    # sufficient다(§42.4 금융업 사례가 요구한 정확한 동작).
    assert profitability.coverage_status == CoverageStatus.SUFFICIENT
    assert profitability.critical_path_satisfied is True


# ============================== §19-4: required feature runtime UNAVAILABLE ==============================


def test_required_feature_runtime_unavailable_goes_to_missing_required():
    roe_result = _hypothetical_result(_ROE_ID, AvailabilityStatus.UNAVAILABLE)
    coverage = evaluate_family_coverage(Component.FUNDAMENTAL, "profitability", [roe_result])
    assert _ROE_ID in coverage.missing_required
    assert any("evaluated but UNAVAILABLE at runtime" in w for w in coverage.warnings)


# ============================== §19-5: Debt Ratio catalog exists, evaluator not implemented ==============================


def test_debt_ratio_not_implemented_distinct_from_unavailable():
    """§19 case 5 + §18: Debt Ratio는 evaluator_id=None(NOT_IMPLEMENTED)이지
    실행됐다가 실패한 것(UNAVAILABLE)이 아니다 -- warning 문구가 이를
    구분한다."""
    coverage = evaluate_family_coverage(Component.FUNDAMENTAL, "financial_resilience", [])
    assert _DEBT_RATIO_ID in coverage.missing_required
    assert any("NOT_IMPLEMENTED" in w and _DEBT_RATIO_ID in w for w in coverage.warnings)
    assert not any("UNAVAILABLE at runtime" in w and _DEBT_RATIO_ID in w for w in coverage.warnings)


# ============================== §19-6/7: Growth family existence-based OR ==============================


def test_growth_family_all_absent_is_insufficient_but_not_a_universal_blocker():
    """§19 case 6: Growth 3개 feature 전부 result 없음 -- family
    coverage는 INSUFFICIENT(evidence 없음)이지만 SUPPORTING이라
    critical_path_satisfied는 여전히 True다(component critical-path를
    단독으로 막지 않는다, §42.4)."""
    coverage = evaluate_family_coverage(Component.FUNDAMENTAL, "observed_growth_quality", [])
    assert coverage.coverage_status == CoverageStatus.INSUFFICIENT
    assert coverage.critical_path_satisfied is True  # family 자체는 gate가 아니다


def test_one_growth_evidence_available_makes_family_sufficient():
    """§19 case 7: existence-based OR -- 3개 중 1개만 AVAILABLE이어도
    family coverage는 SUFFICIENT다(개수를 세지 않는다)."""
    revenue_growth = _hypothetical_result(_REVENUE_GROWTH_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_family_coverage(
        Component.FUNDAMENTAL, "observed_growth_quality", [revenue_growth]
    )
    assert coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert _REVENUE_GROWTH_ID in coverage.optional_available


# ============================== §19-8: ROIC V1_BLOCKED does not block Capital Efficiency ==============================


def test_roic_blocked_does_not_prevent_capital_efficiency_sufficiency():
    """§19 case 8: ROIC는 V1_BLOCKED라 항상 evidence를 못 낸다 -- Asset
    Turnover 하나만 AVAILABLE이어도 capital_efficiency family는
    SUFFICIENT에 도달할 수 있다(blocked feature가 family를 영구
    봉쇄하지 않는다, §42.7)."""
    asset_turnover = _hypothetical_result(_ASSET_TURNOVER_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_family_coverage(
        Component.FUNDAMENTAL, "capital_efficiency", [asset_turnover]
    )
    assert coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert _ROIC_ID not in coverage.optional_available
    assert any("V1_BLOCKED" in w and _ROIC_ID in w for w in coverage.warnings)


def test_capital_efficiency_all_missing_or_blocked_is_insufficient_not_sufficient():
    """ROIC(blocked)만 있고 Asset Turnover도 없으면 -- non-blocked
    contributor가 하나도 AVAILABLE이 아니므로 INSUFFICIENT다(blocked만
    있다고 자동으로 sufficient가 되지 않는다)."""
    coverage = evaluate_family_coverage(Component.FUNDAMENTAL, "capital_efficiency", [])
    assert coverage.coverage_status == CoverageStatus.INSUFFICIENT
    assert coverage.critical_path_satisfied is True  # SUPPORTING family


# ============================== §19-9: catalog feature absent from results doesn't disappear ==============================


def test_all_fourteen_fundamental_and_valuation_features_never_silently_vanish():
    """§19 case 9 + §20: 완전히 빈 result 목록을 줘도 Fundamental
    9개(profitability 4 + growth 4 + financial_resilience 1 +
    capital_efficiency 2 -- 실제로는 5+4+1+2=... 아래에서 정확한 개수로
    재확인) feature 전부가 available/missing 어느 bucket에든 나타난다
    -- 하나도 사라지지 않는다."""
    coverage = evaluate_fundamental_coverage([])
    all_ids = (
        coverage.available_required
        + coverage.missing_required
        + coverage.available_important
        + coverage.missing_important
        + coverage.optional_available
        + coverage.optional_missing
        + coverage.not_applicable
    )
    fundamental_feature_ids = {
        "fundamental.profitability.roe",
        "fundamental.profitability.operating_margin",
        "fundamental.profitability.net_margin",
        "fundamental.profitability.roa",
        "fundamental.observed_growth_quality.revenue_growth",
        "fundamental.observed_growth_quality.operating_profit_growth",
        "fundamental.observed_growth_quality.net_income_growth",
        "fundamental.observed_growth_quality.eps_growth",
        "fundamental.financial_resilience.debt_ratio",
        "fundamental.capital_efficiency.asset_turnover",
        "fundamental.capital_efficiency.roic",
    }
    assert fundamental_feature_ids <= set(all_ids)
    assert len(all_ids) == len(fundamental_feature_ids)  # 중복 없이 정확히 1번씩


# ============================== §19-10/11: NOT_IMPLEMENTED != UNAVAILABLE, NOT_APPLICABLE != missing ==============================


def test_not_implemented_and_unavailable_produce_different_warning_text():
    """Debt Ratio(evaluator_id=None, result 없음)는 NOT_IMPLEMENTED로,
    Operating Margin(evaluator 있음, runtime UNAVAILABLE인 결과)은
    UNAVAILABLE로 -- 같은 "missing" 부류여도 코드가 두 원인을 구분해서
    다른 문구를 남긴다."""
    not_implemented_coverage = evaluate_family_coverage(
        Component.FUNDAMENTAL, "financial_resilience", []
    )
    om_result = _hypothetical_result(_OM_ID, AvailabilityStatus.UNAVAILABLE)
    unavailable_coverage = evaluate_family_coverage(
        Component.FUNDAMENTAL, "profitability", [om_result]
    )
    not_implemented_text = next(w for w in not_implemented_coverage.warnings if _DEBT_RATIO_ID in w)
    unavailable_text = next(w for w in unavailable_coverage.warnings if _OM_ID in w)
    assert not_implemented_text != unavailable_text
    assert "NOT_IMPLEMENTED" in not_implemented_text
    assert "UNAVAILABLE" in unavailable_text


def test_not_applicable_never_lands_in_missing_buckets():
    om_result = _hypothetical_result(_OM_ID, AvailabilityStatus.NOT_APPLICABLE)
    coverage = evaluate_family_coverage(Component.FUNDAMENTAL, "profitability", [om_result])
    assert _OM_ID not in coverage.missing_required
    assert _OM_ID not in coverage.missing_important
    assert _OM_ID not in coverage.optional_missing
    assert _OM_ID in coverage.not_applicable


# ============================== §19-12/13: SUPPORTING vs CRITICAL family propagation ==============================


def test_supporting_family_insufficient_does_not_fail_component():
    """Growth(SUPPORTING)가 완전히 비어 있어도, Profitability/Financial
    Resilience(CRITICAL)가 둘 다 satisfied면 component critical-path는
    satisfied다."""
    results = _real_roe_and_operating_margin_results(roe=12.3, operating_margin=15.0)
    debt_ratio = _hypothetical_result(_DEBT_RATIO_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_fundamental_coverage([*results, debt_ratio])

    assert coverage.critical_path_satisfied is True
    assert coverage.coverage_status == CoverageStatus.SUFFICIENT
    # Growth family 자체는 여전히 비어 있다는 사실이 보인다(숨기지 않음).
    assert _REVENUE_GROWTH_ID in coverage.optional_missing


def test_critical_family_insufficient_does_affect_component():
    """§19 case 13: Financial Resilience(CRITICAL)가 비어 있으면(Debt
    Ratio 없음) ROE/Operating Margin이 다 있어도 component critical-path
    는 satisfied가 아니다."""
    results = _real_roe_and_operating_margin_results(roe=12.3, operating_margin=15.0)
    coverage = evaluate_fundamental_coverage(results)
    assert coverage.critical_path_satisfied is False


# ============================== §19-14: Cash/Earnings Quality unsupported ==============================


def test_cash_earnings_quality_unknown_does_not_universal_block():
    coverage = evaluate_family_coverage(Component.FUNDAMENTAL, "cash_earnings_quality", [])
    assert coverage.coverage_status == CoverageStatus.UNKNOWN
    assert coverage.critical_path_satisfied is True

    results = _real_roe_and_operating_margin_results(roe=12.3, operating_margin=15.0)
    debt_ratio = _hypothetical_result(_DEBT_RATIO_ID, AvailabilityStatus.AVAILABLE)
    component_coverage = evaluate_fundamental_coverage([*results, debt_ratio])
    assert component_coverage.critical_path_satisfied is True


# ============================== §19-15: determinism ==============================


def test_output_is_deterministic_for_same_input():
    results = _real_roe_and_operating_margin_results(roe=12.3, operating_margin=15.0)
    first = evaluate_fundamental_coverage(results)
    second = evaluate_fundamental_coverage(results)
    assert first == second


# ============================== §19-16/17/22: no numeric fields ==============================


def test_coverage_assessment_has_no_computed_percentage():
    coverage = evaluate_fundamental_coverage([])
    assert coverage.coverage_percentage is None


def test_coverage_evaluator_module_source_has_no_numeric_policy_literals():
    body = _module_code_body()
    forbidden = (
        "threshold=",
        "weight=",
        "lookback=",
        "window=",
        "cutoff=",
        "/ len(",
        "min_count",
        "n_of_m",
    )
    for term in forbidden:
        assert term not in body
    # coverage_percentage 필드 자체는 존재하되(기존 model 그대로) 값은
    # 항상 None -- 실제로 숫자를 계산하는 코드가 없는지 별도로 확인한다.
    assert "coverage_percentage=None" in body


# ============================== §19-18: existing evaluator tests unchanged (regression proof) ==============================


def test_roe_and_operating_margin_evaluators_untouched_by_coverage_module():
    """coverage_evaluator.py는 fundamental_evaluators.py를 import하지
    않는다(오직 FeatureEvaluationResult/FeatureDefinition만 소비) --
    evaluator 동작을 재사용하되 재구현하지 않는다."""
    body = _module_code_body()
    assert "fundamental_evaluators" not in body
    assert "RoeFeatureEvaluator" not in body
    assert "OperatingMarginFeatureEvaluator" not in body


# ============================== requirement_role ownership (§4) ==============================


def test_canonical_role_wins_on_conflict_with_result_requirement_role():
    """§4: FeatureEvaluationResult.requirement_role이 canonical
    definition.default_requirement_role과 다르면(가상 상황), canonical
    값을 쓰고 warning을 남긴다 -- 임의로 조용히 무시하지 않는다."""
    conflicting = _hypothetical_result(
        _NET_MARGIN_ID, AvailabilityStatus.AVAILABLE, requirement_role=RequirementRole.REQUIRED
    )
    canonical = get_feature_definition(_NET_MARGIN_ID).default_requirement_role
    assert canonical == RequirementRole.OPTIONAL  # 실제 canonical 값(§42) 재확인
    assert conflicting.requirement_role != canonical

    coverage = evaluate_family_coverage(Component.FUNDAMENTAL, "profitability", [conflicting])
    # canonical(OPTIONAL)이 이겼다 -- REQUIRED bucket이 아니라 OPTIONAL bucket.
    assert _NET_MARGIN_ID in coverage.optional_available
    assert _NET_MARGIN_ID not in coverage.available_required
    assert any("differs from canonical" in w for w in coverage.warnings)


def test_real_evaluator_requirement_role_never_conflicts_today():
    """§4 audit 결과 재확인: 실제 ROE/Operating Margin evaluator는 항상
    canonical 값을 그대로 pass-through하므로 conflict warning이 생기지
    않는다(회귀 확인)."""
    results = _real_roe_and_operating_margin_results(roe=12.3, operating_margin=15.0)
    coverage = evaluate_fundamental_coverage(results)
    assert not any("differs from canonical" in w for w in coverage.warnings)


# ============================== registry role resolution (§4 지시사항 마지막 문장) ==============================


def test_all_fourteen_registry_roles_are_resolved_none_left():
    """§4: "현재 production 14개 role은 §42 이후 전부 확정됐는지 실제
    registry를 확인한다" -- 실제로 확인한다."""
    from app.evaluation.feature_registry import list_feature_definitions

    definitions = list_feature_definitions()
    assert len(definitions) == 14
    assert all(d.default_requirement_role is not None for d in definitions)


# ============================== family criticality policy (§12) ==============================


def test_family_criticality_policy_matches_42_freeze():
    assert (
        get_family_criticality(Component.FUNDAMENTAL, "profitability") == FamilyCriticality.CRITICAL
    )
    assert (
        get_family_criticality(Component.FUNDAMENTAL, "observed_growth_quality")
        == FamilyCriticality.SUPPORTING
    )
    assert (
        get_family_criticality(Component.FUNDAMENTAL, "cash_earnings_quality")
        == FamilyCriticality.CURRENTLY_UNSUPPORTED
    )
    assert (
        get_family_criticality(Component.FUNDAMENTAL, "financial_resilience")
        == FamilyCriticality.CRITICAL
    )
    assert (
        get_family_criticality(Component.FUNDAMENTAL, "capital_efficiency")
        == FamilyCriticality.SUPPORTING
    )


def test_family_criticality_lookup_fails_fast_on_unknown_family():
    import pytest

    with pytest.raises(KeyError):
        get_family_criticality(Component.FUNDAMENTAL, "nonexistent_family")


# ============================== no recommendation semantics (§21) ==============================


def test_coverage_evaluator_module_does_not_import_recommendation_policy_concepts():
    body = _module_code_body()
    forbidden = (
        "ATTRACTIVE",
        "UNATTRACTIVE",
        "OpportunityClassification",
        "BUY",
        "SELL",
        "HOLD",
        "probability",
        "expected_return",
    )
    for term in forbidden:
        assert term not in body


# ============================== no vendor/LLM/portfolio dependency (§16/§17) ==============================


def test_coverage_evaluator_module_has_no_vendor_llm_or_portfolio_dependency():
    body = _module_code_body()
    for forbidden in (
        "app.services.",
        "app.mcp.",
        "StockAnalysis",
        "PortfolioContext",
        "anthropic",
        "openai",
    ):
        assert forbidden not in body


# ============================== §44.7 correction: PARTIAL critical family should not block component ==============================


def test_partial_critical_family_does_not_block_component_critical_path():
    """§44.7 bug fix regression: 이전 구현은 component-level
    critical_path_satisfied를 family의 critical_path_satisfied 불리언으로
    계산해, CRITICAL family가 PARTIAL(REQUIRED 2개 중 1개만 AVAILABLE)일
    때도 component 전체를 부당하게 block했다. §42.14 원문("SUFFICIENT
    또는 PARTIAL 모두 비차단")대로 family.coverage_status를 기준으로
    correction했다 -- Profitability가 PARTIAL(ROE AVAILABLE, Operating
    Margin UNAVAILABLE)이어도, Financial Resilience까지 SUFFICIENT면
    component critical-path는 이제 True다."""
    roe_result = _hypothetical_result(_ROE_ID, AvailabilityStatus.AVAILABLE)
    om_result = _hypothetical_result(_OM_ID, AvailabilityStatus.UNAVAILABLE)
    debt_ratio_result = _hypothetical_result(_DEBT_RATIO_ID, AvailabilityStatus.AVAILABLE)

    profitability = evaluate_family_coverage(
        Component.FUNDAMENTAL, "profitability", [roe_result, om_result]
    )
    assert profitability.coverage_status == CoverageStatus.PARTIAL
    assert profitability.critical_path_satisfied is False  # family 자체는 여전히 False(정확)

    component_coverage = evaluate_fundamental_coverage([roe_result, om_result, debt_ratio_result])
    assert component_coverage.critical_path_satisfied is True  # PARTIAL도 component는 비차단


# ============================== §44: Valuation Coverage ==============================


def test_per_available_makes_earnings_based_sufficient():
    """§10 case 1."""
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_valuation_coverage([per_result])
    assert coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert coverage.critical_path_satisfied is True
    assert _PER_ID in coverage.optional_available


def test_earnings_yield_available_makes_earnings_based_sufficient():
    """§10 case 2."""
    ey_result = _hypothetical_result(_EARNINGS_YIELD_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_valuation_coverage([ey_result])
    assert coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert coverage.critical_path_satisfied is True


def test_per_and_earnings_yield_both_available_not_double_counted():
    """§10 case 3 + §2/§8 double-counting 금지: 둘 다 AVAILABLE이어도
    existence-based OR는 "하나라도 있다"만 판단한다 -- coverage_status는
    둘 다 있을 때와 하나만 있을 때 동일(SUFFICIENT)하다, 더 강한 상태가
    없다(예: 그런 상태 자체가 CoverageStatus enum에 존재하지 않는다)."""
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.AVAILABLE)
    ey_result = _hypothetical_result(_EARNINGS_YIELD_ID, AvailabilityStatus.AVAILABLE)

    both_available = evaluate_family_coverage(
        Component.VALUATION, "earnings_based", [per_result, ey_result]
    )
    only_per = evaluate_family_coverage(Component.VALUATION, "earnings_based", [per_result])

    assert both_available.coverage_status == only_per.coverage_status == CoverageStatus.SUFFICIENT
    assert both_available.critical_path_satisfied == only_per.critical_path_satisfied is True
    # bucket에는 둘 다 보인다(투명성) -- 다만 "판정"은 동일하다는 것이 핵심.
    assert set(both_available.optional_available) == {_PER_ID, _EARNINGS_YIELD_ID}
    assert set(only_per.optional_available) == {_PER_ID}


def test_per_and_earnings_yield_both_missing_earnings_based_insufficient():
    """§10 case 4."""
    coverage = evaluate_family_coverage(Component.VALUATION, "earnings_based", [])
    assert coverage.coverage_status == CoverageStatus.INSUFFICIENT
    assert _PER_ID in coverage.optional_missing
    assert _EARNINGS_YIELD_ID in coverage.optional_missing


def test_per_not_applicable_excluded_from_missing():
    """§10 case 5."""
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.NOT_APPLICABLE)
    coverage = evaluate_family_coverage(Component.VALUATION, "earnings_based", [per_result])
    assert _PER_ID in coverage.not_applicable
    assert _PER_ID not in coverage.optional_missing


def test_catalog_only_unimplemented_valuation_feature_visible():
    """§10 case 6: 아무 result도 안 줘도 PER/Earnings Yield/PBR 전부
    NOT_IMPLEMENTED로 표시된다(catalog-only)."""
    coverage = evaluate_valuation_coverage([])
    assert any(_PER_ID in w and "NOT_IMPLEMENTED" in w for w in coverage.warnings)
    assert any(_EARNINGS_YIELD_ID in w and "NOT_IMPLEMENTED" in w for w in coverage.warnings)
    assert any(_PBR_ID in w and "NOT_IMPLEMENTED" in w for w in coverage.warnings)


def test_pbr_available():
    """§10 case 7."""
    pbr_result = _hypothetical_result(_PBR_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_family_coverage(Component.VALUATION, "asset_based", [pbr_result])
    assert coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert _PBR_ID in coverage.optional_available


def test_pbr_missing():
    """§10 case 8."""
    coverage = evaluate_family_coverage(Component.VALUATION, "asset_based", [])
    assert coverage.coverage_status == CoverageStatus.INSUFFICIENT
    assert _PBR_ID in coverage.optional_missing


def test_asset_based_context_dependent_not_a_universal_blocker():
    """§10 case 9: PBR이 완전히 없어도(asset_based INSUFFICIENT) Valuation
    critical-path는 이것만으로 막히지 않는다(CONTEXT_DEPENDENT는
    context-free baseline에서 gate에 포함되지 않는다, §44.3/§44.4) --
    다만 PBR 부재가 SUFFICIENT로 위장되지도 않는다(family 자체는
    INSUFFICIENT로 정직하게 남는다)."""
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_valuation_coverage([per_result])

    assert _PBR_ID in coverage.optional_missing
    assert coverage.critical_path_satisfied is True  # Earnings-based만으로 satisfied
    assert any("CONTEXT_DEPENDENT" in w and "asset_based" in w for w in coverage.warnings)


def test_earnings_based_insufficient_makes_valuation_critical_path_insufficient():
    """§10 case 10: Earnings-based(CRITICAL)가 완전히 비어 있으면 PBR이
    있어도 Valuation critical-path는 satisfied가 아니다(CONTEXT_DEPENDENT
    family가 CRITICAL family의 부재를 대신 메꾸지 않는다)."""
    pbr_result = _hypothetical_result(_PBR_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_valuation_coverage([pbr_result])
    assert coverage.critical_path_satisfied is False
    assert coverage.coverage_status == CoverageStatus.INSUFFICIENT


def test_valuation_uses_full_catalog_not_just_results_given():
    """§10 case 12 + false-completeness 재확인: PER 하나만 AVAILABLE인
    result를 줘도, Earnings Yield/PBR이 catalog에 있다는 사실이 그대로
    보인다(NOT_IMPLEMENTED로 missing 계열에 남는다) -- "PER 하나 있으니
    다 됐다"고 오판하지 않는다."""
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_valuation_coverage([per_result])
    all_ids = (
        coverage.optional_available
        + coverage.optional_missing
        + coverage.available_required
        + coverage.missing_required
        + coverage.not_applicable
    )
    assert {_PER_ID, _EARNINGS_YIELD_ID, _PBR_ID} <= set(all_ids)


def test_valuation_not_implemented_distinct_from_unavailable():
    """§10 case 13."""
    not_implemented_coverage = evaluate_family_coverage(Component.VALUATION, "asset_based", [])
    unavailable_result = _hypothetical_result(_PBR_ID, AvailabilityStatus.UNAVAILABLE)
    unavailable_coverage = evaluate_family_coverage(
        Component.VALUATION, "asset_based", [unavailable_result]
    )
    not_implemented_text = next(w for w in not_implemented_coverage.warnings if _PBR_ID in w)
    unavailable_text = next(w for w in unavailable_coverage.warnings if _PBR_ID in w)
    assert "NOT_IMPLEMENTED" in not_implemented_text
    assert "UNAVAILABLE" in unavailable_text
    assert not_implemented_text != unavailable_text


def test_fundamental_evaluator_unaffected_by_valuation_addition():
    """§10 case 14: Valuation 추가로 Fundamental 결과가 바뀌지 않는다."""
    results = _real_roe_and_operating_margin_results(roe=12.3, operating_margin=15.0)
    debt_ratio = _hypothetical_result(_DEBT_RATIO_ID, AvailabilityStatus.AVAILABLE)
    coverage = evaluate_fundamental_coverage([*results, debt_ratio])
    assert coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert coverage.critical_path_satisfied is True


def test_valuation_output_is_deterministic():
    """§10 case 15."""
    per_result = _hypothetical_result(_PER_ID, AvailabilityStatus.AVAILABLE)
    first = evaluate_valuation_coverage([per_result])
    second = evaluate_valuation_coverage([per_result])
    assert first == second


def test_valuation_coverage_has_no_numeric_fields():
    """§10 case 16."""
    coverage = evaluate_valuation_coverage([])
    assert coverage.coverage_percentage is None


def test_valuation_family_criticality_matches_42_freeze():
    assert (
        get_family_criticality(Component.VALUATION, "earnings_based") == FamilyCriticality.CRITICAL
    )
    assert (
        get_family_criticality(Component.VALUATION, "asset_based")
        == FamilyCriticality.CONTEXT_DEPENDENT
    )
    assert (
        get_family_criticality(Component.VALUATION, "ev_based")
        == FamilyCriticality.CURRENTLY_UNSUPPORTED
    )
    assert (
        get_family_criticality(Component.VALUATION, "cash_flow_based")
        == FamilyCriticality.CURRENTLY_UNSUPPORTED
    )
    assert (
        get_family_criticality(Component.VALUATION, "relative_context")
        == FamilyCriticality.CURRENTLY_UNSUPPORTED
    )


def test_valuation_coverage_public_api_has_no_context_parameter():
    """§44.5 context audit 결론(옵션 A) 재확인: public API 어디에도
    EvaluationContext 파라미터가 없다(signature 자체로 확인, 문자열
    검색이 아니다 -- CONTEXT_DEPENDENT 같은 정당한 이름과 혼동하지 않음)."""
    import app.evaluation.coverage_evaluator as module

    fundamental_params = set(inspect.signature(module.evaluate_fundamental_coverage).parameters)
    valuation_params = set(inspect.signature(module.evaluate_valuation_coverage).parameters)
    family_params = set(inspect.signature(module.evaluate_family_coverage).parameters)

    assert fundamental_params == {"feature_results"}
    assert valuation_params == {"feature_results"}
    assert family_params == {"component", "feature_family", "feature_results"}

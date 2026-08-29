"""RE-05 CoverageEvaluator -- 첫 deterministic Coverage vertical slice
(Fundamental only, §43).

`docs/dev-log/2026-08-29.md` §41(Coverage Contract FROZEN)/§42(Family-Level
Coverage Policy FROZEN)/§43(이 구현의 설계 근거)이 이 모듈의 semantic 근거를
담는다 -- 이 모듈은 그 두 세션이 이미 확정한 규칙을 코드로 옮길 뿐, 새로운
policy 결정을 내리지 않는다.

**입력**: 이미 실행된 `FeatureEvaluationResult`의 목록 하나뿐이다(§41.7 C
계층 -- FeatureEvaluator는 role을 소유하지 않고, 이 모듈이 canonical
`FeatureDefinition`과 그 role을 최종 소비한다). vendor model, `StockAnalysis`,
LLM output, PortfolioContext는 받지 않는다 -- 전부 import하지 않는다.

**feature universe는 반드시 `feature_registry.list_feature_definitions()`
(canonical Full V1 Feature Catalog)다** -- 들어온 `feature_results`
목록이 아니다(§38.2 FALSE COMPLETENESS 재발 방지, §42.20 지시사항 §2/§20
핵심 원칙). catalog에는 있지만 `feature_results`에 없는 feature는 절대
사라지지 않는다 -- `NOT_IMPLEMENTED`(evaluator_id=None)이든
`RESULT_MISSING`(evaluator는 있는데 이번 cycle에 결과가 없음)이든 항상
missing 계열 bucket에 남는다.

**결정론적**: 동일 input(`feature_results`)이면 항상 동일 output이다.
LLM 호출, 외부 API 호출, 시계열 계산 없음 -- 이미 평가된 evidence와
module-level static family-criticality policy(§42.13, §43.4)만 본다.

**하지 않는 것**:
- `ATTRACTIVE`/`NEUTRAL`/`UNATTRACTIVE`/`BUY`/`SELL`/`HOLD` 같은
  recommendation classification(§42.15, Coverage는 evidence sufficiency
  판단까지만).
- score/probability/expected return.
- coverage percentage/N-of-M/minimum count/threshold/weight 같은 numeric
  policy(existence-based OR는 counting이 아니라 "존재 여부"만 판단한다,
  §42.1/§43 지시사항 §22).
- Valuation/Forward/Flow/Market Confirmation coverage(§43.14, 다음 slice로
  분리).
"""

from collections.abc import Mapping, Sequence
from enum import Enum
from types import MappingProxyType

from app.evaluation.feature_registry import (
    FeatureDefinition,
    FeatureScopeStatus,
    is_implemented,
    list_feature_definitions,
)
from app.models.recommendation import (
    AvailabilityStatus,
    Component,
    CoverageAssessment,
    CoverageStatus,
    FeatureEvaluationResult,
    RequirementRole,
)

# ============================== Family Criticality (§42.13 policy, 이번에 코드화) ==============================


class FamilyCriticality(str, Enum):
    """§42.3 audit classification을 그대로 코드로 옮긴 것 -- production
    registry(`feature_registry.py`)에는 넣지 않는다(§42.13: family
    criticality는 feature identity가 아니므로 registry의 책임 범위 밖).
    이 enum은 이 모듈(미래 CoverageEvaluator)만의 내부 policy 표현이다."""

    CRITICAL = "critical"
    SUPPORTING = "supporting"
    CONTEXT_DEPENDENT = "context_dependent"
    CURRENTLY_UNSUPPORTED = "currently_unsupported"
    NOT_DECISION_GATING = "not_decision_gating"


# §42.4가 확정한 Fundamental 5-family 판정을 그대로 옮긴다 -- 여기서 새로
# 판단하지 않는다. Valuation/Forward/Flow/Market은 아직 채우지 않는다
# (§43.14, 다음 slice에서 각 component의 §42 판정을 옮긴다).
_FAMILY_CRITICALITY: Mapping[tuple[Component, str], FamilyCriticality] = MappingProxyType(
    {
        (Component.FUNDAMENTAL, "profitability"): FamilyCriticality.CRITICAL,
        (Component.FUNDAMENTAL, "observed_growth_quality"): FamilyCriticality.SUPPORTING,
        (Component.FUNDAMENTAL, "cash_earnings_quality"): FamilyCriticality.CURRENTLY_UNSUPPORTED,
        (Component.FUNDAMENTAL, "financial_resilience"): FamilyCriticality.CRITICAL,
        (Component.FUNDAMENTAL, "capital_efficiency"): FamilyCriticality.SUPPORTING,
    }
)

# §42.2가 재확인한 Fundamental 5-family 목록 -- cash_earnings_quality처럼
# 등록된 feature가 0개인 family도 "존재는 한다"는 사실 자체가 중요하다
# (§38.2 FALSE COMPLETENESS와 동일한 이유로, family 목록도 registry
# 등록 여부와 무관하게 고정된 canonical 목록이어야 한다).
_FUNDAMENTAL_FAMILIES: tuple[str, ...] = (
    "profitability",
    "observed_growth_quality",
    "cash_earnings_quality",
    "financial_resilience",
    "capital_efficiency",
)


def get_family_criticality(component: Component, feature_family: str) -> FamilyCriticality:
    """§42.13 policy lookup의 공개 accessor. 등록되지 않은 (component,
    family) 조합은 `KeyError`를 raise한다 -- 조용히 기본값을 만들지
    않는다(get_feature_definition과 동일한 fail-fast 원칙, §35)."""
    return _FAMILY_CRITICALITY[(component, feature_family)]


# ============================== Feature-level matching (§43.3 A~G) ==============================


class _FeatureMatchState(str, Enum):
    """§43 지시사항 §3의 A~F를 그대로 코드화한 내부 상태. G(deferred/not
    catalogued)는 별도 state가 필요 없다 -- catalog에 없는 feature는
    애초에 이 loop에 들어오지 않는다(V1_DEFERRED feature는 registry에
    등록되지 않는다는 §39/§41.11의 기존 결정 그대로).

    NOT_IMPLEMENTED != UNAVAILABLE != RESULT_MISSING != BLOCKED를
    구조적으로 분리한다(§43 지시사항 §18 핵심 원칙)."""

    AVAILABLE = "available"  # A: result 존재 + AVAILABLE/ESTIMATED
    UNAVAILABLE = "unavailable"  # B: result 존재 + UNAVAILABLE/INVALID
    NOT_APPLICABLE = "not_applicable"  # C: result 존재 + NOT_APPLICABLE
    NOT_IMPLEMENTED = "not_implemented"  # D: catalog에 있으나 evaluator_id=None
    RESULT_MISSING = "result_missing"  # E: evaluator는 있으나 이번 cycle에 result 없음
    BLOCKED = "blocked"  # F: scope_status=V1_BLOCKED(항상 최우선 분류)


# Coverage 목적의 "evidence로 인정하는" AvailabilityStatus 집합 -- ESTIMATED도
# evidence는 evidence다(신뢰도 차이는 Confidence의 몫이지 Coverage의 몫이
# 아니다, §41.1 Coverage != Confidence). INVALID는 UNAVAILABLE과 동일하게
# "evidence 아님"으로 취급한다.
_AVAILABLE_LIKE = frozenset({AvailabilityStatus.AVAILABLE, AvailabilityStatus.ESTIMATED})


def _classify_feature(
    definition: FeatureDefinition,
    result: FeatureEvaluationResult | None,
) -> _FeatureMatchState:
    # V1_BLOCKED는 result 존재 여부와 무관하게 항상 최우선으로 BLOCKED다
    # (§41.11: blocked feature는 v1에서 구조적으로 evidence를 낼 수 없다 --
    # 현재 registry에는 V1_BLOCKED feature에 evaluator가 하나도 없어 result가
    # 존재하는 경우가 실제로는 없지만, 향후에도 이 우선순위를 지킨다).
    if definition.scope_status is FeatureScopeStatus.V1_BLOCKED:
        return _FeatureMatchState.BLOCKED

    if result is None:
        if is_implemented(definition):
            return _FeatureMatchState.RESULT_MISSING
        return _FeatureMatchState.NOT_IMPLEMENTED

    if result.availability is AvailabilityStatus.NOT_APPLICABLE:
        return _FeatureMatchState.NOT_APPLICABLE
    if result.availability in _AVAILABLE_LIKE:
        return _FeatureMatchState.AVAILABLE
    return _FeatureMatchState.UNAVAILABLE


def _resolve_requirement_role(
    definition: FeatureDefinition,
    result: FeatureEvaluationResult | None,
    warnings: list[str],
) -> RequirementRole | None:
    """§43 지시사항 §4: canonical `FeatureDefinition.default_requirement_role`
    이 항상 authoritative source다(§41.7 A). `FeatureEvaluator`는 role을
    소유하지 않으므로(§41.7 B, 이미 실제로 pass-through만 함을 §37/§41에서
    확인) `result.requirement_role`을 신뢰해서 canonical 값을 대체하지
    않는다 -- **임의 fallback이 아니라, registry가 항상 이긴다는 고정
    규칙**이다. 다만 `result.requirement_role`이 canonical 값과 다르면
    (미래에 runtime override를 하는 evaluator가 생길 가능성 대비) 조용히
    무시하지 않고 `warnings`에 명시적으로 남긴다(§43 지시사항 §4: "충돌 시
    어떻게 처리할지 audit" -> 기록은 하되 canonical이 최종값)."""
    canonical = definition.default_requirement_role
    if (
        result is not None
        and result.requirement_role is not None
        and result.requirement_role != canonical
    ):
        warnings.append(
            f"{definition.feature_id}: FeatureEvaluationResult.requirement_role="
            f"{result.requirement_role.value if result.requirement_role else None} "
            f"differs from canonical FeatureDefinition.default_requirement_role="
            f"{canonical.value if canonical else None} -- canonical value used"
        )
    return canonical


def _missing_reason(definition: FeatureDefinition, state: _FeatureMatchState) -> str:
    """§43 지시사항 §18: missing 사유를 구분 가능하게 남긴다 -- 전부 같은
    문구로 뭉개지 않는다."""
    if state is _FeatureMatchState.NOT_IMPLEMENTED:
        return f"{definition.feature_id}: NOT_IMPLEMENTED (no evaluator, catalog identity only)"
    if state is _FeatureMatchState.RESULT_MISSING:
        return (
            f"{definition.feature_id}: evaluator implemented but no result "
            "provided this cycle (execution/result gap, not implementation gap)"
        )
    if state is _FeatureMatchState.UNAVAILABLE:
        return f"{definition.feature_id}: evaluated but UNAVAILABLE at runtime"
    if state is _FeatureMatchState.BLOCKED:
        return f"{definition.feature_id}: V1_BLOCKED (scope) -- never expected to produce evidence in v1"
    raise AssertionError(
        f"_missing_reason called for non-missing state: {state}"
    )  # pragma: no cover


# ============================== Bucket assignment ==============================

_BUCKET_BY_ROLE: Mapping[RequirementRole, tuple[str, str]] = MappingProxyType(
    {
        RequirementRole.REQUIRED: ("available_required", "missing_required"),
        RequirementRole.IMPORTANT: ("available_important", "missing_important"),
        RequirementRole.OPTIONAL: ("optional_available", "optional_missing"),
        # role 자체가 NOT_APPLICABLE(런타임 AvailabilityStatus.NOT_APPLICABLE과는
        # 다른 축, RequirementRole의 값)인 경우도 not_applicable bucket을
        # 공유한다 -- CoverageAssessment에 이 조합 전용 필드가 없고, 의미상
        # "이 evaluation에서 고려 대상이 아니다"라는 점이 동일하다.
        RequirementRole.NOT_APPLICABLE: ("not_applicable", "not_applicable"),
    }
)


def _assign_bucket(
    buckets: dict[str, list[str]],
    definition: FeatureDefinition,
    state: _FeatureMatchState,
    role: RequirementRole | None,
    warnings: list[str],
) -> None:
    # §41.9 재확인: runtime NOT_APPLICABLE은 role 값과 무관하게 항상
    # not_applicable bucket 우선(REQUIRED라도 missing_required에 넣지 않는다).
    if state is _FeatureMatchState.NOT_APPLICABLE:
        buckets["not_applicable"].append(definition.feature_id)
        return

    if role is None:
        # default_requirement_role이 여전히 None(design-time 미확정)인
        # feature -- 현재 production 14개는 §42 이후 전부 확정됐지만(§43.5
        # 실측 재확인), 스키마상 여전히 가능한 상태이므로 조용히 누락시키지
        # 않고 별도로 기록한다(임의로 OPTIONAL 취급하지 않는다, §40.1 원칙).
        warnings.append(
            f"{definition.feature_id}: default_requirement_role is unresolved (None) "
            "-- excluded from all role-based buckets, not silently treated as OPTIONAL"
        )
        return

    available_key, missing_key = _BUCKET_BY_ROLE[role]
    if state is _FeatureMatchState.AVAILABLE:
        buckets[available_key].append(definition.feature_id)
    else:
        buckets[missing_key].append(definition.feature_id)
        if role is not RequirementRole.NOT_APPLICABLE:
            warnings.append(_missing_reason(definition, state))


# ============================== Family-level coverage ==============================


def evaluate_family_coverage(
    component: Component,
    feature_family: str,
    feature_results: Sequence[FeatureEvaluationResult],
) -> CoverageAssessment:
    """§42.3의 3-tier family coverage policy를 실행한다.

    feature universe는 `feature_registry.list_feature_definitions()`에서
    `component`+`feature_family`가 일치하는 catalog 전체다 -- `feature_results`
    는 그중 실제로 값이 있는 항목을 찾는 lookup용일 뿐, universe 자체를
    정의하지 않는다(§43 지시사항 §2/§20)."""
    definitions = tuple(
        d
        for d in list_feature_definitions()
        if d.component is component and d.feature_family == feature_family
    )
    results_by_id = {r.feature_id: r for r in feature_results}

    buckets: dict[str, list[str]] = {
        "available_required": [],
        "missing_required": [],
        "available_important": [],
        "missing_important": [],
        "optional_available": [],
        "optional_missing": [],
        "not_applicable": [],
    }
    warnings: list[str] = []

    states: dict[str, _FeatureMatchState] = {}
    roles: dict[str, RequirementRole | None] = {}
    for definition in definitions:
        result = results_by_id.get(definition.feature_id)
        state = _classify_feature(definition, result)
        # 정확히 한 번만 계산한다 -- 아래 Tier 판정에서 재사용(중복 계산
        # 방지, warnings도 두 번 쌓이지 않는다).
        role = _resolve_requirement_role(definition, result, warnings)
        states[definition.feature_id] = state
        roles[definition.feature_id] = role
        _assign_bucket(buckets, definition, state, role, warnings)

    # §42.3 Tier 판정: NOT_APPLICABLE인 feature는 전부 제외하고 판단한다
    # (§41.9 규칙을 family 판정에도 그대로 적용 -- 특정 종목에서 family가
    # 영구 봉쇄되지 않게 한다).
    applicable = [
        d for d in definitions if states[d.feature_id] is not _FeatureMatchState.NOT_APPLICABLE
    ]
    effective_required = [d for d in applicable if roles[d.feature_id] is RequirementRole.REQUIRED]

    if effective_required:
        # Tier 1
        required_states = [states[d.feature_id] for d in effective_required]
        if all(s is _FeatureMatchState.AVAILABLE for s in required_states):
            coverage_status = CoverageStatus.SUFFICIENT
            critical_path_satisfied = True
        elif any(s is _FeatureMatchState.AVAILABLE for s in required_states):
            coverage_status = CoverageStatus.PARTIAL
            critical_path_satisfied = False
        else:
            coverage_status = CoverageStatus.INSUFFICIENT
            critical_path_satisfied = False
    else:
        # non-blocked candidate: BLOCKED feature는 existence-based OR
        # 대상에서 제외한다(§42.7/§42.20 §10: blocked feature가 family를
        # 영구 봉쇄하면 안 된다).
        non_blocked = [
            d for d in applicable if states[d.feature_id] is not _FeatureMatchState.BLOCKED
        ]
        if not non_blocked:
            # Tier 3: 등록된 feature가 없거나 전부 blocked/not-applicable.
            coverage_status = CoverageStatus.UNKNOWN
            critical_path_satisfied = (
                True  # Tier 2/3 family는 스스로 critical-path를 막지 않는다(§42.14).
            )
        else:
            # Tier 2: existence-based OR -- counting이 아니라 존재 여부만 본다.
            if any(states[d.feature_id] is _FeatureMatchState.AVAILABLE for d in non_blocked):
                coverage_status = CoverageStatus.SUFFICIENT
            else:
                coverage_status = CoverageStatus.INSUFFICIENT
            critical_path_satisfied = True

    return CoverageAssessment(
        available_required=tuple(buckets["available_required"]),
        missing_required=tuple(buckets["missing_required"]),
        available_important=tuple(buckets["available_important"]),
        missing_important=tuple(buckets["missing_important"]),
        optional_available=tuple(buckets["optional_available"]),
        optional_missing=tuple(buckets["optional_missing"]),
        not_applicable=tuple(buckets["not_applicable"]),
        critical_path_satisfied=critical_path_satisfied,
        coverage_status=coverage_status,
        # 참고용 필드조차 계산하지 않는다 -- coverage_status/critical_path_satisfied
        # 만으로 판정이 끝나야 한다는 원칙을 코드로도 지킨다(§24.8/§43 지시사항 §22).
        coverage_percentage=None,
        source_failures=(),
        warnings=tuple(warnings),
    )


# ============================== Component-level coverage (Fundamental only, §43.14) ==============================


def evaluate_fundamental_coverage(
    feature_results: Sequence[FeatureEvaluationResult],
) -> CoverageAssessment:
    """§42.14 component propagation rule의 Fundamental 적용.

    Fundamental critical-path = Profitability(CRITICAL) sufficient AND
    Financial Resilience(CRITICAL) sufficient. Observed Growth Quality/
    Capital Efficiency(SUPPORTING)와 Cash/Earnings Quality
    (CURRENTLY_UNSUPPORTED)는 단독으로 critical-path를 막지 않는다 --
    다만 그 feature들의 상태도 component-level bucket에서 전부 보인다
    (§42.4/§42.20 §9: "구현 부족을 숨기기 위해 family를 sufficient
    처리하지 않는다" -- family를 건너뛰지 않고 전부 평가한 뒤 합친다)."""
    family_results = {
        family: evaluate_family_coverage(Component.FUNDAMENTAL, family, feature_results)
        for family in _FUNDAMENTAL_FAMILIES
    }

    # component-level list bucket = 전체 family bucket의 union(순서
    # 보존을 위해 family 순서대로 이어붙인다) -- 어떤 feature도 누락되지
    # 않는다.
    merged: dict[str, list[str]] = {
        "available_required": [],
        "missing_required": [],
        "available_important": [],
        "missing_important": [],
        "optional_available": [],
        "optional_missing": [],
        "not_applicable": [],
    }
    warnings: list[str] = []
    for family in _FUNDAMENTAL_FAMILIES:
        assessment = family_results[family]
        for key, values in merged.items():
            values.extend(getattr(assessment, key))
        warnings.extend(assessment.warnings)

    critical_families = [
        family
        for family in _FUNDAMENTAL_FAMILIES
        if get_family_criticality(Component.FUNDAMENTAL, family) is FamilyCriticality.CRITICAL
    ]
    critical_assessments = [family_results[family] for family in critical_families]

    critical_path_satisfied = all(a.critical_path_satisfied for a in critical_assessments)
    if all(a.coverage_status is CoverageStatus.SUFFICIENT for a in critical_assessments):
        coverage_status = CoverageStatus.SUFFICIENT
    elif any(a.coverage_status is CoverageStatus.INSUFFICIENT for a in critical_assessments):
        coverage_status = CoverageStatus.INSUFFICIENT
    else:
        coverage_status = CoverageStatus.PARTIAL

    return CoverageAssessment(
        available_required=tuple(merged["available_required"]),
        missing_required=tuple(merged["missing_required"]),
        available_important=tuple(merged["available_important"]),
        missing_important=tuple(merged["missing_important"]),
        optional_available=tuple(merged["optional_available"]),
        optional_missing=tuple(merged["optional_missing"]),
        not_applicable=tuple(merged["not_applicable"]),
        critical_path_satisfied=critical_path_satisfied,
        coverage_status=coverage_status,
        coverage_percentage=None,
        source_failures=(),
        warnings=tuple(warnings),
    )

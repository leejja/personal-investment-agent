"""RE-05 FeatureFamilyAssessment / ComponentAssessment Assembly -- first
structural slice (§47, boundary corrected in §48).

`docs/dev-log/2026-08-29.md` §41~§46(Coverage Layer, FROZEN/IMPLEMENTATION
COMPLETE)/§47(첫 구현)/§48(Assembly ↔ Coverage ownership boundary
correction)이 이 모듈의 semantic 근거를 담는다.

**이 모듈이 하는 일**: 이미 존재하는 `FeatureEvaluationResult[]`와 **이미
계산된** `CoverageAssessment`(호출자가 `app.evaluation.coverage_evaluator`
로 미리 계산해 전달)를 canonical `FeatureFamilyAssessment`/
`ComponentAssessment` 구조로 **조립만** 한다.

**§48 correction -- Coverage execution ownership**: 이 모듈은
`evaluate_family_coverage()`/`evaluate_*_coverage()`를 **호출하지
않는다**(더 이상 import조차 하지 않는다). §47의 첫 구현은 "Coverage
policy를 재구현하지 않는다"는 것만 지켰을 뿐, Coverage **실행**(execution)
자체는 assembly 함수 내부에서 매번 다시 수행하고 있었다 -- 이는
"Assembly는 조립 책임이고 Coverage policy execution owner가 아니다"라는
architecture 의도와 어긋난다(§48.1에서 실제 코드로 확인한 사실, 추측이
아니다). 이제 이 모듈의 모든 public 함수는 이미 계산된
`CoverageAssessment`를 **입력 파라미터**로만 받는다 -- 누가 그 값을
계산했는지는 이 모듈의 관심사가 아니다. 값을 재해석하거나 변형하지
않고 그대로 nested field에 배치한다(identity까지 보존된다, §48 테스트로
확인).

**"그럼 누가 Coverage를 먼저 계산하나?"는 이 모듈의 책임이 아니다** --
향후 orchestration 단계의 몫이다(§48.4, 이번에도 구현하지 않는다).

**이 모듈이 절대 하지 않는 것**:
- 새 FeatureEvaluator 구현, feature normalization, component score 계산,
  signal threshold 구현, Core aggregation, Recommendation Policy.
- ROE/Operating Margin 같은 개별 feature의 attractiveness 판단, family/
  component score 계산, signal 생성 -- `family_score`/`ComponentAssessment.
  score`는 항상 `None`이고 `signal`은 항상 `ComponentSignal.UNKNOWN`이다
  (score 없음 != 0, signal UNKNOWN != NEUTRAL).
- Coverage 계산(실행조차) -- 호출자가 이미 계산한 `CoverageAssessment`를
  그대로 소비한다(§48).
- Confidence 자동 생성 -- confidence evaluator가 아직 없으므로 항상
  `ConfidenceLevel.UNKNOWN` + 이유를 담은 warning으로 정직하게 표현한다
  (coverage가 충분하다고 confidence를 HIGH로 유도하지 않는다).
- 존재하지 않는 `FeatureEvaluationResult`를 fake로 만들어 UNAVAILABLE로
  가장하는 것 -- catalog에 있지만 evaluator가 없는 feature는 단순히
  `feature_results`에 나타나지 않을 뿐이고, 그 사실은 이미 nested
  `coverage.warnings`(NOT_IMPLEMENTED 등, §43)가 표현한다.
- `FutureOpportunityEvidenceAssessment`를 `ComponentAssessment` 내부로
  밀어넣는 것 -- `RecommendationEvaluationState`의 top-level/parallel
  필드 그대로 유지한다(§46).

**입력**: `FeatureEvaluationResult`의 목록과 이미 계산된
`CoverageAssessment`(들)뿐이다(vendor model/`StockAnalysis`/LLM output/
PortfolioContext를 받지 않는다).

**feature/family universe는 반드시 Feature Registry의 canonical
definitions**다(`feature_registry.list_feature_definitions()`) --
들어온 `feature_results` 목록이 아니다(§38.2 FALSE COMPLETENESS와 동일한
원칙을 assembly에도 그대로 적용). catalog에 있지만 evaluator가 없는
feature는 `feature_results` 목록에서 조용히 빠질 뿐, family identity
자체는(`FeatureFamilyAssessment.family_id`) 사라지지 않는다.

**결정론적 순서**: family는 Feature Registry가 이미 확정한 canonical
family 목록 순서(`coverage_evaluator.get_component_families()`), family
안의 feature는 catalog(registry) 등록 순서를 쓴다 -- 입력
`feature_results` 리스트의 순서에 좌우되지 않는다.
"""

from collections.abc import Mapping, Sequence

from app.evaluation.coverage_evaluator import get_component_families
from app.evaluation.feature_registry import FeatureDefinition, list_feature_definitions
from app.models.recommendation import (
    Component,
    ComponentAssessment,
    ComponentSignal,
    ComponentStatus,
    ConfidenceAssessment,
    ConfidenceLevel,
    CoverageAssessment,
    FeatureEvaluationResult,
    FeatureFamilyAssessment,
    FeatureFamilyStatus,
)

# ============================== Confidence (자동 생성 금지, 정직한 UNKNOWN) ==============================


def _unknown_confidence(reason: str) -> ConfidenceAssessment:
    """confidence evaluator가 아직 하나도 없다 -- coverage가 얼마나
    충분하든(SUFFICIENT여도) confidence를 HIGH로 자동 유도하지 않는다
    (Coverage != Confidence 원칙을 이 모듈에서도 지킨다). `reason`을
    `warnings`에 남겨 "판단하지 않았다"는 사실 자체를 투명하게 기록한다."""
    return ConfidenceAssessment(level=ConfidenceLevel.UNKNOWN, warnings=[reason])


# ============================== Feature Family Layer ==============================


def _compute_family_status(
    catalog: Sequence[FeatureDefinition],
    results_by_id: Mapping[str, FeatureEvaluationResult],
) -> tuple[FeatureFamilyStatus, int]:
    """family_status는 Coverage/Confidence와 별개 축이다(model docstring:
    "Family 단위 evaluability... Coverage/Confidence와는 별개 축") -- "이
    family의 evidence가 충분한가"(Coverage)나 "얼마나 확신하는가"
    (Confidence)가 아니라 "이번 cycle에 이 family의 catalog feature들에
    대해 실제로 평가가 실행됐는가"라는 순수 기계적 사실만 담는다.
    등록된 feature가 0개인 family(예: cash_earnings_quality)는 평가할
    대상 자체가 없으므로 NOT_EVALUATED다(전부 평가됐다는 vacuous
    EVALUATED로 표현하지 않는다 -- Coverage Tier 3/UNKNOWN과 같은
    이유)."""
    if not catalog:
        return FeatureFamilyStatus.NOT_EVALUATED, 0
    evaluated_count = sum(1 for d in catalog if d.feature_id in results_by_id)
    if evaluated_count == 0:
        return FeatureFamilyStatus.NOT_EVALUATED, 0
    if evaluated_count == len(catalog):
        return FeatureFamilyStatus.EVALUATED, evaluated_count
    return FeatureFamilyStatus.PARTIALLY_EVALUATED, evaluated_count


def assemble_feature_family_assessments(
    component: Component,
    feature_results: Sequence[FeatureEvaluationResult],
    family_coverages: Mapping[str, CoverageAssessment],
) -> list[FeatureFamilyAssessment]:
    """`component`의 canonical family 전부(등록 feature가 0개인 family
    포함, false-completeness 원칙)에 대해 `FeatureFamilyAssessment`를
    조립한다.

    `family_coverages`는 `get_component_families(component)`가 반환하는
    모든 family_id를 key로 가진 `CoverageAssessment` mapping이어야 한다
    (호출자가 `evaluate_family_coverage(component, family, feature_results)`
    로 미리 계산해 전달, §48) -- 이 함수는 그 값을 그대로 nested field에
    배치할 뿐 재계산하거나 재해석하지 않는다(전달된 객체와 identity(`is`)
    까지 보존된다). 어떤 family의 coverage가 빠져 있으면(호출자 실수)
    `KeyError`를 raise한다 -- 조용히 기본값을 만들지 않는다(fail-fast,
    registry 전반의 기존 원칙과 동일).

    `feature_results`에 있는 것 중 그 family 소속인 것만 `member_results`
    로 담는다 -- catalog에 있지만 결과가 없는 feature를 위해 fake
    `FeatureEvaluationResult`를 만들지 않는다(NOT_IMPLEMENTED
    != UNAVAILABLE 원칙 그대로 -- 그 사실은 nested `coverage.warnings`가
    이미 표현한다, §43)."""
    results_by_id = {r.feature_id: r for r in feature_results}
    assessments: list[FeatureFamilyAssessment] = []

    for family in get_component_families(component):
        # catalog(registry) 등록 순서 그대로 -- 입력 list 순서에 좌우되지
        # 않는 deterministic order.
        catalog = tuple(
            d
            for d in list_feature_definitions()
            if d.component is component and d.feature_family == family
        )
        member_results = [
            results_by_id[d.feature_id] for d in catalog if d.feature_id in results_by_id
        ]
        family_status, evaluated_count = _compute_family_status(catalog, results_by_id)

        warnings: list[str] = []
        if family_status is not FeatureFamilyStatus.EVALUATED:
            warnings.append(
                f"{family}: family_status={family_status.value} "
                f"({evaluated_count}/{len(catalog)} catalog feature(s) have a "
                "FeatureEvaluationResult this cycle)"
            )

        assessments.append(
            FeatureFamilyAssessment(
                family_id=family,
                component=component,
                feature_results=member_results,
                family_status=family_status,
                # numeric normalization/aggregation이 아직 없으므로
                # family_score는 항상 None이다 -- 0으로 채우지 않는다
                # (model docstring이 이미 "aggregator는 이 모듈에서 구현하지
                # 않는다"고 명시).
                family_score=None,
                # §48: 호출자가 이미 계산한 값을 그대로 배치한다 -- 이
                # 함수 내부에서 Coverage를 계산/재계산하지 않는다.
                coverage=family_coverages[family],
                confidence=_unknown_confidence(
                    f"no confidence evaluator implemented for family '{family}' yet"
                ),
                warnings=warnings,
            )
        )

    return assessments


# ============================== Component Layer ==============================


def _compute_component_status(
    family_assessments: Sequence[FeatureFamilyAssessment],
) -> ComponentStatus:
    """family_status와 동일한 원칙을 component 레벨로 확장한다 --
    "이번 cycle에 이 component의 family들에 대해 실제로 평가가 얼마나
    실행됐는가"만 본다."""
    if not family_assessments:
        return ComponentStatus.UNAVAILABLE
    statuses = {fa.family_status for fa in family_assessments}
    if statuses == {FeatureFamilyStatus.NOT_EVALUATED}:
        return ComponentStatus.UNAVAILABLE
    if statuses == {FeatureFamilyStatus.EVALUATED}:
        return ComponentStatus.EVALUATED
    return ComponentStatus.PARTIALLY_EVALUATED


def assemble_component_assessment(
    component: Component,
    family_assessments: Sequence[FeatureFamilyAssessment],
    component_coverage: CoverageAssessment,
) -> ComponentAssessment:
    """§48: component-agnostic 조립 -- 모든 component(Fundamental/
    Valuation/Forward/Flow/Market)가 동일한 이 함수를 그대로 재사용할 수
    있다(더 이상 component별 wrapper가 Coverage를 계산할 필요가 없어져
    Fundamental 전용 함수를 따로 두지 않는다, §48.3 API 단순화).

    `family_assessments`는 `assemble_feature_family_assessments()`가 만든
    결과를 그대로 전달받는다(이 함수가 다시 만들지 않는다).
    `component_coverage`는 호출자가 `evaluate_*_coverage()`로 미리 계산해
    전달한다(재계산하지 않는다, §48) -- 전달된 객체와 identity까지
    보존된다."""
    status = _compute_component_status(family_assessments)

    return ComponentAssessment(
        component=component,
        family_assessments=list(family_assessments),
        # score/signal 정규화·집계가 아직 없다 -- score는 None(0이 아니다),
        # signal은 ComponentSignal.UNKNOWN(NEUTRAL이 아니다).
        # ComponentAssessment model docstring이 이미 이 정확한 조합
        # (score=None, signal=UNKNOWN)을 "Forward unavailable" 예시로
        # 명시해뒀다 -- 이 assembly는 모든 component에 동일한 원칙을
        # 적용한다(아직 어떤 component도 scoring되지 않았으므로).
        score=None,
        signal=ComponentSignal.UNKNOWN,
        coverage=component_coverage,
        confidence=_unknown_confidence(
            f"no confidence evaluator implemented for component '{component.value}' yet"
        ),
        status=status,
    )

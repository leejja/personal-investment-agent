"""RE-05 `RecommendationEvaluationState` Full Orchestration -- First
Deterministic Pipeline Slice.

`docs/dev-log/2026-08-29.md` §49.19/§49.20/§50.2가 이 슬라이스의 readiness를
확인해뒀다 -- Coverage(§43~§46)/Assembly(§47~§49)/FutureOpportunityEvidence
(§46) 3개 산출물은 이미 개별적으로 완성돼 있었고, 남은 것은 이들을 정해진
순서로 호출해 하나의 완성된 `RecommendationEvaluationState`를 만드는 것뿐
이었다. 이 모듈이 그 orchestrator다.

**이 모듈이 하는 일**: 이미 구현·테스트된 deterministic building block
(`research_data_builder`/`fundamental_evaluators`/`coverage_evaluator`/
`assembly`)을 정해진 순서로 호출해 연결할 뿐이다 -- 새 계산 로직, 새
architecture, 새 semantics를 만들지 않는다.

**이 모듈이 절대 하지 않는 것**:
- Recommendation Policy, `StockOpportunityAssessment` 생성.
- numeric scoring/calibration/threshold/weighted sum.
- `CoreAttractivenessAssessment`/`MarketConfirmationAssessment` aggregate
  생성 -- `RecommendationEvaluationState.core_attractiveness`/
  `market_confirmation`은 이 슬라이스에서 항상 `None`이다.
- `RiskAssessment`/`ConfidenceAssessment` producer, top-level `coverage`
  aggregation -- 전부 `None`으로 남긴다(aggregation 정책이 아직 없다는
  기존 원칙을 top-level 단일 필드에도 동일하게 적용한다).
- 새 Event Overlay/Event Intelligence semantics -- `event_path_availability`
  는 항상 기존 default(`UNKNOWN`)를 그대로 쓴다.
- Feature Registry를 순회해 evaluator를 동적으로 만드는 것, 또는 registry에
  등록만 되고 evaluator가 없는 feature에 대해 fake `FeatureEvaluationResult`
  를 만드는 것 -- 실제 구현된 evaluator만 실행한다
  (`fundamental_evaluators.IMPLEMENTED_FUNDAMENTAL_EVALUATORS`).
- vendor/Service/MCP/LLM 호출, Stock Research Agent 실행 -- 이미 만들어진
  `DeterministicAnalysisResult`만 입력으로 받는다.
"""

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
from app.evaluation.fundamental_evaluators import IMPLEMENTED_FUNDAMENTAL_EVALUATORS
from app.evaluation.research_data_builder import build_normalized_research_data
from app.models.recommendation import (
    Component,
    ComponentAssessment,
    CoverageAssessment,
    FeatureEvaluationResult,
    FeatureFamilyAssessment,
)
from app.models.research_context import EvaluationContext, RecommendationEvaluationState

# §4(사용자 지시): coverage/assembly/family flattening 전체에서 동일하게
# 유지하는 canonical component 순서 -- `Component` enum 선언 순서 그대로
# (`recommendation.py`의 `CANONICAL_CORE_COMPONENTS` 4개 + `MARKET_CONFIRMATION`).
_CANONICAL_COMPONENT_ORDER: tuple[Component, ...] = (
    Component.FUNDAMENTAL,
    Component.VALUATION,
    Component.FORWARD,
    Component.FLOW,
    Component.MARKET_CONFIRMATION,
)

# Coverage 계층은 component-agnostic 함수 하나가 아니라 5개 개별 함수다
# (Assembly와 다른 점 -- assembly.py는 이미 generic). 이 dispatch table은
# 새 coverage semantics를 만들지 않고 기존 5개 함수를 그대로 가리킬 뿐이다.
_COMPONENT_COVERAGE_EVALUATORS = {
    Component.FUNDAMENTAL: evaluate_fundamental_coverage,
    Component.VALUATION: evaluate_valuation_coverage,
    Component.FORWARD: evaluate_forward_coverage,
    Component.FLOW: evaluate_flow_coverage,
    Component.MARKET_CONFIRMATION: evaluate_market_coverage,
}

# 현재는 Fundamental evaluator 2개(ROE/Operating Margin)뿐이다. 향후
# Valuation/Forward/Flow/Market evaluator module이 생기면 그 모듈이 자신의
# IMPLEMENTED_* tuple을 소유하고 여기서 이어붙인다(§2 사용자 지시) --
# registry를 순회해 동적으로 만들지 않는다.
_IMPLEMENTED_EVALUATORS = IMPLEMENTED_FUNDAMENTAL_EVALUATORS


def run_first_deterministic_pipeline(
    result: DeterministicAnalysisResult,
    context: EvaluationContext,
) -> RecommendationEvaluationState:
    """`DeterministicAnalysisResult` -> `RecommendationEvaluationState`를
    하나의 deterministic execution 경로로 연결한다(First Slice).

    `symbol`/`as_of`를 별도 인자로 받지 않는다 -- `context.symbol`은
    `EvaluationContext`가 이미 필수로 요구하고, `context.as_of`를
    normalization에 그대로 넘긴다. `context.symbol`과 `result.price.symbol`
    사이의 consistency는 이 슬라이스에서 caller contract로 둔다(새
    assert/validator를 추가하지 않는다).
    """
    normalized_data = build_normalized_research_data(result, as_of=context.as_of)

    feature_results: list[FeatureEvaluationResult] = [
        evaluator.evaluate(normalized_data, context) for evaluator in _IMPLEMENTED_EVALUATORS
    ]

    component_assessments: list[ComponentAssessment] = []
    flattened_family_assessments: list[FeatureFamilyAssessment] = []
    component_coverages: dict[Component, CoverageAssessment] = {}

    for component in _CANONICAL_COMPONENT_ORDER:
        family_coverages = {
            family: evaluate_family_coverage(component, family, feature_results)
            for family in get_component_families(component)
        }
        component_coverage = _COMPONENT_COVERAGE_EVALUATORS[component](feature_results)
        component_coverages[component] = component_coverage

        family_assessments = assemble_feature_family_assessments(
            component, feature_results, family_coverages
        )
        component_assessment = assemble_component_assessment(
            component, family_assessments, component_coverage
        )

        # flatten -- 재계산/재생성 없이 assembly가 이미 만든 exact 객체를
        # 그대로 이어붙인다(identity 보존, §7 사용자 지시).
        flattened_family_assessments.extend(family_assessments)
        component_assessments.append(component_assessment)

    # §8: Forward의 이미 계산된 component coverage를 그대로 재사용한다 --
    # 재계산하지 않는다. event_path_availability는 기본값(UNKNOWN)을 그대로
    # 쓴다 -- Event Intelligence가 아직 없으므로 임의로 값을 지정하지 않는다.
    future_opportunity_evidence = evaluate_future_opportunity_evidence(
        component_coverages[Component.FORWARD]
    )

    return RecommendationEvaluationState(
        context=context,
        normalized_research_data=normalized_data,
        feature_results=feature_results,
        family_assessments=flattened_family_assessments,
        component_assessments=component_assessments,
        future_opportunity_evidence=future_opportunity_evidence,
        # core_attractiveness / market_confirmation / risk / coverage /
        # confidence / event_overlay / correlation_metadata / warnings는
        # 전부 model default(None 또는 빈 리스트)를 그대로 둔다 -- §9 사용자
        # 지시: aggregation/scoring/policy 이전 단계이므로 이 슬라이스가
        # 채우지 않는다.
    )

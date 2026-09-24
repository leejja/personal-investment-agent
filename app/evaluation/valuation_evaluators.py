"""RE-05 Valuation Component, earnings_based/asset_based family
`FeatureEvaluator` 구현체 -- `TrailingPerFeatureEvaluator` +
`PbrFeatureEvaluator`(RE-05 Post-Orchestration Architecture Review
Step A~F, READY Evaluator Expansion -- Valuation Extension).

이 모듈은 `app/models/research_context.FeatureEvaluator` Protocol(§32.6)의
Valuation component 첫 실제 구현이다. `app/evaluation/fundamental_evaluators.py`
의 `RoeFeatureEvaluator`/`OperatingMarginFeatureEvaluator`와 완전히 동일한
architectural contract(입력 `NormalizedResearchData`+`EvaluationContext`,
출력 `FeatureEvaluationResult`, availability 판정, `normalized_value`는
항상 `None`)를 따른다 -- 새 generic base class/helper/factory를 만들지
않는다(RE-05 Post-Orchestration Architecture Review Step B §4.3/Step D §7
에서 이미 이 선택을 확정했다).

책임(Fundamental evaluator와 동일): required input 존재 여부 확인,
source/provenance 전달, `as_of` 유지, raw value/unit 유지, availability
status 결정, `FeatureEvaluationResult` 생성.

**하지 않는 것**:
- attractiveness threshold, normalized numeric score(`RE-05 Numeric
  Calibration = OPEN`이므로 `normalized_value`는 항상 `None`이다).
- component aggregation(`ComponentAssessment` 생성 없음).
- recommendation/portfolio action 생성.
- vendor API 호출(`NormalizedResearchData`만 소비, Kiwoom을 직접 import
  하지 않는다).
- PER/PBR의 0/negative(적자기업 등) 값을 `INVALID`/`UNAVAILABLE`로
  재분류하거나 저평가/고평가 같은 economic interpretation을 추가하는 것
  -- `docs/dev-log/2026-08-29.md` §2.8 FROZEN invariant(`INVALID !=
  NEGATIVE`, `UNAVAILABLE != 0`)를 그대로 적용해, `None`이 아닌 모든
  수치(0/음수 포함)를 `AVAILABLE` raw evidence로 보존한다(RE-05
  Post-Orchestration Architecture Review Step D §6/§7 FROZEN).
- Earnings Yield evaluator(별도 CONTRACT REQUIRED slice, 이 모듈이
  구현하지 않는다).

이 evaluator의 metadata는 이 클래스가 독립적으로 소유하지 않는다 --
`app.evaluation.feature_registry`의 `FeatureDefinition`을 canonical
source로 참조한다(`feature_id`/`component`/`feature_family`가 전부
registry에서 온다).
"""

from app.evaluation.feature_registry import get_feature_definition
from app.models.recommendation import (
    AvailabilityStatus,
    EvaluationBasis,
    FeatureEvaluationResult,
    FeatureValue,
    Provenance,
)
from app.models.research_context import (
    EvaluationContext,
    FeatureEvaluator,
    NormalizedResearchData,
)

_TRAILING_PER_UNAVAILABLE_WARNING = (
    "PER not present in NormalizedResearchData.financial_facts.current"
)


class TrailingPerFeatureEvaluator:
    """Trailing PER(주가수익비율) 하나만 담당하는 최소 evaluator.

    raw source: `NormalizedResearchData.financial_facts.current.per`
    (Kiwoom `ka10001.per`, `analysis.py`의 `_map_financial_snapshot()`이
    이미 채워놓은 값 -- 이 evaluator가 vendor를 직접 호출하지 않는다).

    0/음수 PER(적자기업 등)도 `AVAILABLE` raw evidence로 그대로
    보존한다 -- `None`만 `UNAVAILABLE`이다. `docs/dev-log/2026-08-29.md`
    §2.8의 FROZEN invariant(`INVALID != NEGATIVE`, `UNAVAILABLE != 0`)를
    그대로 적용한 것이며, "PER<=0 -> 고평가/저평가/무효" 같은 economic
    interpretation을 이 evaluator가 새로 만들지 않는다.
    """

    definition = get_feature_definition("valuation.earnings_based.trailing_per")
    feature_id = definition.feature_id
    component = definition.component
    feature_family = definition.feature_family

    def evaluate(
        self,
        data: NormalizedResearchData,
        context: EvaluationContext,
    ) -> FeatureEvaluationResult:
        current = data.financial_facts.current
        per = current.per if current is not None else None

        provenance = Provenance(
            source="Kiwoom",
            as_of=context.as_of,
        )

        if per is None:
            return FeatureEvaluationResult(
                feature_id=self.feature_id,
                component=self.component,
                feature_family=self.feature_family,
                raw=None,
                availability=AvailabilityStatus.UNAVAILABLE,
                requirement_role=self.definition.default_requirement_role,
                evaluation_basis=[EvaluationBasis.ABSOLUTE],
                normalized_value=None,
                provenance=provenance,
                warnings=[_TRAILING_PER_UNAVAILABLE_WARNING],
            )

        return FeatureEvaluationResult(
            feature_id=self.feature_id,
            component=self.component,
            feature_family=self.feature_family,
            raw=FeatureValue(value=per, unit="multiple"),
            availability=AvailabilityStatus.AVAILABLE,
            requirement_role=self.definition.default_requirement_role,
            evaluation_basis=[EvaluationBasis.ABSOLUTE],
            # normalized score/threshold는 RE-05 Numeric Calibration이 OPEN인
            # 동안 정의하지 않는다 -- 0/음수를 포함한 모든 AVAILABLE 값에
            # 대해 항상 None이다.
            normalized_value=None,
            provenance=provenance,
        )


_PBR_UNAVAILABLE_WARNING = (
    "PBR not present in NormalizedResearchData.financial_facts.current"
)


class PbrFeatureEvaluator:
    """PBR(주가순자산비율) 하나만 담당하는 최소 evaluator --
    `TrailingPerFeatureEvaluator`와 완전히 동일한 architectural contract을
    따른다.

    raw source: `NormalizedResearchData.financial_facts.current.pbr`
    (Kiwoom `ka10001.pbr`). 0/음수 PBR(자본잠식 등)도 `TrailingPer
    FeatureEvaluator`와 동일한 근거(§2.8 FROZEN invariant)로 `AVAILABLE`
    raw evidence로 보존한다 -- "PBR<1 -> 저평가" 같은 interpretation을
    추가하지 않는다.
    """

    definition = get_feature_definition("valuation.asset_based.pbr")
    feature_id = definition.feature_id
    component = definition.component
    feature_family = definition.feature_family

    def evaluate(
        self,
        data: NormalizedResearchData,
        context: EvaluationContext,
    ) -> FeatureEvaluationResult:
        current = data.financial_facts.current
        pbr = current.pbr if current is not None else None

        provenance = Provenance(
            source="Kiwoom",
            as_of=context.as_of,
        )

        if pbr is None:
            return FeatureEvaluationResult(
                feature_id=self.feature_id,
                component=self.component,
                feature_family=self.feature_family,
                raw=None,
                availability=AvailabilityStatus.UNAVAILABLE,
                requirement_role=self.definition.default_requirement_role,
                evaluation_basis=[EvaluationBasis.ABSOLUTE],
                normalized_value=None,
                provenance=provenance,
                warnings=[_PBR_UNAVAILABLE_WARNING],
            )

        return FeatureEvaluationResult(
            feature_id=self.feature_id,
            component=self.component,
            feature_family=self.feature_family,
            raw=FeatureValue(value=pbr, unit="multiple"),
            availability=AvailabilityStatus.AVAILABLE,
            requirement_role=self.definition.default_requirement_role,
            evaluation_basis=[EvaluationBasis.ABSOLUTE],
            normalized_value=None,
            provenance=provenance,
        )


# ============================== Implemented Evaluator Dispatch ==============================
#
# `app/evaluation/fundamental_evaluators.py`의 IMPLEMENTED_FUNDAMENTAL_EVALUATORS
# 와 동일한 설계 원칙: explicit immutable dispatch, registry(14개
# definition)를 순회해 evaluator를 동적으로 만들지 않는다. 이 모듈에 실제로
# 구현된 evaluator class만 나열한다 -- Earnings Yield는 아직 evaluator가
# 없으므로(CONTRACT REQUIRED, 별도 slice) 여기 포함하지 않는다.
#
# 순서: Trailing PER -> PBR. registry `_ALL_DEFINITIONS` 선언 순서
# (feature_registry.py)를 그대로 따른다(alphabetical order 아님).
IMPLEMENTED_VALUATION_EVALUATORS: tuple[FeatureEvaluator, ...] = (
    TrailingPerFeatureEvaluator(),
    PbrFeatureEvaluator(),
)

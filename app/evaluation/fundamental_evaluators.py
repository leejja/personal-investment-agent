"""RE-05 첫 `FeatureEvaluator` 구현체 -- Fundamental Component, Profitability
family.

이 모듈은 `app/models/research_context.FeatureEvaluator` Protocol(§32.6)의
첫 실제 구현이다. `docs/dev-log/2026-08-29.md` §34가 이 vertical slice의
설계 결정을 기록한다.

책임(§32.6/§34가 정의한 그대로): required input 존재 여부 확인,
applicability 확인, source/provenance 전달, `as_of` 유지, raw value/unit
유지, availability status 결정, `FeatureEvaluationResult` 생성.

**하지 않는 것**:
- attractiveness threshold, normalized numeric score(`RE-05 Numeric
  Calibration = OPEN`이므로 `normalized_value`는 항상 `None`이다 --
  `None`은 "아직 정의되지 않음"이지 `UNKNOWN`/`UNAVAILABLE`이 아니다).
- component aggregation(`ComponentAssessment` 생성 없음).
- recommendation/portfolio action 생성.
- vendor API 호출(`NormalizedResearchData`만 소비, Kiwoom/OpenDART를
  직접 import하지 않는다).

Feature Registry는 이번에도 만들지 않는다(§32.7/§33.4 trigger 유지) --
이 evaluator의 metadata(`feature_id`/`component`/`feature_family`)는
**이 클래스 자체에 class attribute로만 존재**한다. scope_status
(`V1_REQUIRED`)/requirement_role은 코드로 다시 선언하지 않고
`docs/dev-log/2026-08-29.md` §29.2 V1 Feature Set 표를 그대로 참조한다
(중복 진실 공급원을 만들지 않기 위함, §32.7 판단과 일관).
"""

from app.models.recommendation import (
    AvailabilityStatus,
    Component,
    EvaluationBasis,
    FeatureEvaluationResult,
    FeatureValue,
    Provenance,
    RequirementRole,
)
from app.models.research_context import EvaluationContext, NormalizedResearchData

# RE-02 조사(README Phase 7)에서 이미 확인된 known quality issue를 재인용한
# 것뿐이다 -- 이번에 새로 판단한 신뢰도 평가가 아니다.
_ROE_RELIABILITY_WARNING = (
    "Kiwoom ROE reliability not independently verified against "
    "OpenDART-derived net income sign in all cases (RE-02)"
)


class RoeFeatureEvaluator:
    """ROE(자기자본이익률) 하나만 담당하는 최소 evaluator.

    raw source: `NormalizedResearchData.financial_facts.current.roe`
    (Kiwoom `ka10001.roe`, `analysis.py`의 `_map_financial_snapshot()`이
    이미 채워놓은 값 -- 이 evaluator가 vendor를 직접 호출하지 않는다).

    known quality issue(신규 발견 아님, 재인용): Kiwoom ROE와 OpenDART
    파생 순이익의 부호가 실제로 불일치하는 사례가 있었다(RE-02 조사,
    README Phase 7 참고) -- ROE를 무조건 신뢰 가능하다고 가정하지 않는다.
    이 사실을 `warnings`에 남긴다(수치 판단은 아니다).
    """

    feature_id = "fundamental.profitability.roe"
    component = Component.FUNDAMENTAL
    feature_family = "profitability"

    def evaluate(
        self,
        data: NormalizedResearchData,
        context: EvaluationContext,
    ) -> FeatureEvaluationResult:
        current = data.financial_facts.current
        roe = current.roe if current is not None else None

        provenance = Provenance(
            source="Kiwoom",
            as_of=context.as_of,
        )

        if roe is None:
            return FeatureEvaluationResult(
                feature_id=self.feature_id,
                component=self.component,
                feature_family=self.feature_family,
                raw=None,
                availability=AvailabilityStatus.UNAVAILABLE,
                requirement_role=RequirementRole.REQUIRED,
                evaluation_basis=[EvaluationBasis.ABSOLUTE],
                normalized_value=None,
                provenance=provenance,
                warnings=["ROE not present in NormalizedResearchData.financial_facts.current"],
            )

        return FeatureEvaluationResult(
            feature_id=self.feature_id,
            component=self.component,
            feature_family=self.feature_family,
            raw=FeatureValue(value=roe, unit="percent"),
            availability=AvailabilityStatus.AVAILABLE,
            requirement_role=RequirementRole.REQUIRED,
            evaluation_basis=[EvaluationBasis.ABSOLUTE],
            # normalized score/threshold는 RE-05 Numeric Calibration이 OPEN인
            # 동안 정의하지 않는다 -- None으로 남긴다(UNKNOWN/UNAVAILABLE과
            # 혼동하지 않는다: availability는 위에서 이미 AVAILABLE로 확정됐다).
            normalized_value=None,
            provenance=provenance,
            warnings=[_ROE_RELIABILITY_WARNING],
        )

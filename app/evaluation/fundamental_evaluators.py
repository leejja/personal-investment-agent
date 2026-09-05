"""RE-05 Fundamental Component, Profitability family `FeatureEvaluator`
구현체 -- `RoeFeatureEvaluator`(§34) + `OperatingMarginFeatureEvaluator`
(§37, 두 번째 evaluator).

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

§35(Minimal Feature Registry)부터 이 evaluator의 metadata는 더 이상 이
클래스가 독립적으로 소유하지 않는다 -- `app.evaluation.feature_registry`의
`FeatureDefinition`을 canonical source로 참조한다(`feature_id`/
`component`/`feature_family`/`default_requirement_role`이 전부 registry
에서 온다 -- `requirement_role`은 §36에서 `default_requirement_role`로
개명됐다). 이 evaluator는 그 definition에 대한 **calculation/execution
책임만** 진다(§35.9의 ownership 경계) -- 값 자체를 두 번째로 선언하지
않는다.
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

    definition = get_feature_definition("fundamental.profitability.roe")
    feature_id = definition.feature_id
    component = definition.component
    feature_family = definition.feature_family

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
                requirement_role=self.definition.default_requirement_role,
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
            requirement_role=self.definition.default_requirement_role,
            evaluation_basis=[EvaluationBasis.ABSOLUTE],
            # normalized score/threshold는 RE-05 Numeric Calibration이 OPEN인
            # 동안 정의하지 않는다 -- None으로 남긴다(UNKNOWN/UNAVAILABLE과
            # 혼동하지 않는다: availability는 위에서 이미 AVAILABLE로 확정됐다).
            normalized_value=None,
            provenance=provenance,
            warnings=[_ROE_RELIABILITY_WARNING],
        )


_OPERATING_MARGIN_UNAVAILABLE_WARNING = (
    "Operating margin not present in NormalizedResearchData.financial_facts"
    ".features.annual (latest year) -- may be a data gap or a structural "
    "sector exception (e.g. no revenue account, see applicability note)"
)

# ROE와 달리 revenue 기반 비율이라 매출액 계정이 없는 업종(금융지주 등,
# §26.2/§28.5 실측)에서는 구조적으로 계산 자체가 안 될 수 있다 --
# NormalizedResearchData에 업종 정보가 없어 evaluator가 "이 종목이 그
# 케이스인지" 스스로 판별할 수 없으므로, 매번 review 필요 flag를 켠다
# (rule engine이 아니라 단순 고정 flag, §37.5).
_OPERATING_MARGIN_APPLICABILITY_NOTE = (
    "Revenue-based ratio; not structurally computable for companies "
    "without a revenue account (e.g. financial holding companies, "
    "§26.2/§28.5) -- NormalizedResearchData carries no sector "
    "classification, so this flag is set unconditionally pending a "
    "future applicability rule"
)


class OperatingMarginFeatureEvaluator:
    """Operating Margin(영업이익률) 하나만 담당하는 최소 evaluator --
    `RoeFeatureEvaluator`와 동일한 architectural contract(입력
    `NormalizedResearchData`+`EvaluationContext`, 출력
    `FeatureEvaluationResult`)를 따른다.

    raw source가 ROE와 다르다: ROE는 `financial_facts.current.roe`
    (Kiwoom 사전계산 스칼라)를 직접 읽지만, Operating Margin은 RE-01이
    이미 계산해둔 `financial_facts.features.annual`(오래된 -> 최신 순
    리스트, `analysis.py`의 `_operating_margin()` 결과)의 **마지막
    항목**을 읽는다 -- `FinancialSnapshot.current`에는 이 값이 없다
    (§37.1 감사 결과). 이 evaluator가 `operating_profit/revenue`를
    새로 계산하지 않는다 -- RE-01의 single source of truth를 그대로
    재사용한다(중복 계산 경로를 만들지 않는다).
    """

    definition = get_feature_definition("fundamental.profitability.operating_margin")
    feature_id = definition.feature_id
    component = definition.component
    feature_family = definition.feature_family

    def evaluate(
        self,
        data: NormalizedResearchData,
        context: EvaluationContext,
    ) -> FeatureEvaluationResult:
        features = data.financial_facts.features
        annual = features.annual if features is not None else []
        latest = annual[-1] if annual else None
        operating_margin = latest.operating_margin if latest is not None else None

        provenance = Provenance(
            source="OpenDART",
            as_of=context.as_of,
        )

        if operating_margin is None:
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
                applicability_review_required=True,
                applicability_note=_OPERATING_MARGIN_APPLICABILITY_NOTE,
                warnings=[_OPERATING_MARGIN_UNAVAILABLE_WARNING],
            )

        return FeatureEvaluationResult(
            feature_id=self.feature_id,
            component=self.component,
            feature_family=self.feature_family,
            raw=FeatureValue(value=operating_margin, unit="percent"),
            availability=AvailabilityStatus.AVAILABLE,
            requirement_role=self.definition.default_requirement_role,
            evaluation_basis=[EvaluationBasis.ABSOLUTE],
            # normalized score/threshold는 RE-05 Numeric Calibration이 OPEN인
            # 동안 정의하지 않는다 -- AVAILABLE이어도 None으로 남긴다(§37.10:
            # AVAILABLE != normalized score already calibrated).
            normalized_value=None,
            provenance=provenance,
            applicability_review_required=True,
            applicability_note=_OPERATING_MARGIN_APPLICABILITY_NOTE,
        )


# ============================== Implemented Evaluator Dispatch ==============================
#
# §RE-05 Full Orchestration First Slice가 소비하는 explicit immutable dispatch다.
# Feature Registry(14개 definition)를 순회해 evaluator를 동적으로 만들지 않는다 --
# 이 모듈에 실제로 구현된 evaluator class만 이 tuple에 나열한다(§38 NOT_IMPLEMENTED
# 원칙 그대로: registry에 있다는 사실이 곧 실행 가능하다는 뜻이 아니다). 새 evaluator
# module(예: valuation_evaluators.py)이 생기면 그 모듈이 자신의 IMPLEMENTED_*
# tuple을 스스로 소유하고, orchestrator가 그것들을 이어붙인다 -- 이 tuple이
# 모든 component의 evaluator를 대표하지 않는다.
#
# 순서: ROE -> Operating Margin(등록 순서 그대로, dev-log §34/§37). 두 evaluator
# 모두 상태를 갖지 않으므로(§34/§37 docstring 참고) 인스턴스를 재사용해도 안전하다
# -- 매 evaluate() 호출마다 새로 만들 필요가 없다.
IMPLEMENTED_FUNDAMENTAL_EVALUATORS: tuple[FeatureEvaluator, ...] = (
    RoeFeatureEvaluator(),
    OperatingMarginFeatureEvaluator(),
)

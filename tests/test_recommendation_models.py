"""RE-05 Recommendation / Scoring data model contract 테스트.

`app/models/recommendation.py`는 evaluator/aggregator/scorer/policy 로직을
전혀 담지 않는 순수 data contract이므로, 여기서도 numeric threshold 테스트는
만들지 않는다 -- 스키마가 RE-05가 요구하는 invariant를 "표현 가능"하게
하는지만 검증한다.
"""

import pytest
from pydantic import ValidationError

from app.models.common import RiskLevel
from app.models.recommendation import (
    CANONICAL_CORE_COMPONENTS,
    AssessmentStatus,
    AvailabilityStatus,
    Component,
    ComponentAssessment,
    ComponentSignal,
    ComponentStatus,
    ConfidenceAssessment,
    ConfidenceLevel,
    CoreAttractivenessAssessment,
    CoverageAssessment,
    CoverageStatus,
    EventOverlayReference,
    EvidencePathAvailability,
    FeatureEvaluationResult,
    FutureOpportunityEvidenceAssessment,
    OpportunityClassification,
    RequirementSatisfaction,
    RiskAssessment,
    StockOpportunityAssessment,
)


def _insufficient_coverage() -> CoverageAssessment:
    return CoverageAssessment(
        missing_required=["forward_consensus_growth"],
        critical_path_satisfied=False,
        coverage_status=CoverageStatus.INSUFFICIENT,
    )


def _sufficient_coverage() -> CoverageAssessment:
    return CoverageAssessment(
        available_required=["roe", "operating_margin"],
        critical_path_satisfied=True,
        coverage_status=CoverageStatus.SUFFICIENT,
    )


def _unknown_confidence() -> ConfidenceAssessment:
    return ConfidenceAssessment(level=ConfidenceLevel.UNKNOWN)


def _high_confidence() -> ConfidenceAssessment:
    return ConfidenceAssessment(level=ConfidenceLevel.HIGH)


# ============================== Score / Signal 분리 ==============================


def test_component_score_and_signal_are_independent_fields():
    """score(연속값)와 signal(범주형)이 서로 다른 필드로 존재한다 --
    score만 보고 signal을 유추할 수 없다는 것이 스키마 레벨로 표현된다."""
    assessment = ComponentAssessment(
        component=Component.FUNDAMENTAL,
        score=0.42,
        signal=ComponentSignal.POSITIVE,
        coverage=_sufficient_coverage(),
        confidence=_high_confidence(),
        status=ComponentStatus.EVALUATED,
    )
    assert assessment.score == 0.42
    assert assessment.signal == ComponentSignal.POSITIVE


def test_unknown_signal_allows_score_none():
    """UNKNOWN signal + score=None 조합이 허용돼야 한다(Forward unavailable
    표현의 기반)."""
    assessment = ComponentAssessment(
        component=Component.FORWARD,
        score=None,
        signal=ComponentSignal.UNKNOWN,
        coverage=_insufficient_coverage(),
        confidence=_unknown_confidence(),
        status=ComponentStatus.UNAVAILABLE,
    )
    assert assessment.score is None
    assert assessment.signal == ComponentSignal.UNKNOWN


def test_neutral_signal_is_distinct_from_unknown_signal():
    neutral = ComponentAssessment(
        component=Component.VALUATION,
        score=0.0,
        signal=ComponentSignal.NEUTRAL,
        coverage=_sufficient_coverage(),
        confidence=_high_confidence(),
        status=ComponentStatus.EVALUATED,
    )
    unknown = ComponentAssessment(
        component=Component.FORWARD,
        score=None,
        signal=ComponentSignal.UNKNOWN,
        coverage=_insufficient_coverage(),
        confidence=_unknown_confidence(),
        status=ComponentStatus.UNAVAILABLE,
    )
    assert neutral.signal != unknown.signal


# ============================== Forward unavailable ==============================


def test_forward_unavailable_is_not_score_zero():
    """Forward Component가 usable input이 없을 때 score=unavailable(None)로
    표현되고, 0으로 대체되지 않는다는 것을 직접 검증한다."""
    forward = ComponentAssessment(
        component=Component.FORWARD,
        score=None,
        signal=ComponentSignal.UNKNOWN,
        coverage=_insufficient_coverage(),
        confidence=_unknown_confidence(),
        status=ComponentStatus.UNAVAILABLE,
    )
    assert forward.score is None
    assert forward.score != 0
    assert forward.coverage.coverage_status == CoverageStatus.INSUFFICIENT
    assert forward.coverage.critical_path_satisfied is False


def test_core_attractiveness_keeps_forward_component_in_vector():
    """Core는 항상 4-component vector를 보존한다 -- Forward가 unavailable
    이어도 리스트에서 제거되지 않고 UNKNOWN 상태로 그대로 포함된다."""
    forward = ComponentAssessment(
        component=Component.FORWARD,
        score=None,
        signal=ComponentSignal.UNKNOWN,
        coverage=_insufficient_coverage(),
        confidence=_unknown_confidence(),
        status=ComponentStatus.UNAVAILABLE,
    )
    fundamental = ComponentAssessment(
        component=Component.FUNDAMENTAL,
        score=0.6,
        signal=ComponentSignal.POSITIVE,
        coverage=_sufficient_coverage(),
        confidence=_high_confidence(),
        status=ComponentStatus.EVALUATED,
    )
    core = CoreAttractivenessAssessment(
        component_assessments=[fundamental, forward],
    )

    components_present = {c.component for c in core.component_assessments}
    assert Component.FORWARD in components_present
    assert set(CANONICAL_CORE_COMPONENTS) == {
        Component.FUNDAMENTAL,
        Component.VALUATION,
        Component.FORWARD,
        Component.FLOW,
    }
    assert Component.MARKET_CONFIRMATION not in CANONICAL_CORE_COMPONENTS


# ============================== Coverage / Confidence 독립 ==============================


def test_coverage_and_confidence_are_independent():
    """Coverage HIGH + Confidence LOW, Coverage LOW + Confidence HIGH 둘 다
    가능해야 한다(§24.9) -- 어느 한쪽이 다른 쪽을 강제하지 않는다."""
    high_coverage_low_confidence = ComponentAssessment(
        component=Component.FUNDAMENTAL,
        score=0.1,
        signal=ComponentSignal.NEUTRAL,
        coverage=_sufficient_coverage(),
        confidence=ConfidenceAssessment(
            level=ConfidenceLevel.LOW,
            unsupported_assumptions=["single-source estimate"],
        ),
        status=ComponentStatus.EVALUATED,
    )
    low_coverage_high_confidence = ComponentAssessment(
        component=Component.VALUATION,
        score=0.2,
        signal=ComponentSignal.POSITIVE,
        coverage=CoverageAssessment(
            missing_important=["ev_ebitda"],
            critical_path_satisfied=True,
            coverage_status=CoverageStatus.PARTIAL,
        ),
        confidence=_high_confidence(),
        status=ComponentStatus.PARTIALLY_EVALUATED,
    )

    assert high_coverage_low_confidence.coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert high_coverage_low_confidence.confidence.level == ConfidenceLevel.LOW
    assert low_coverage_high_confidence.coverage.coverage_status == CoverageStatus.PARTIAL
    assert low_coverage_high_confidence.confidence.level == ConfidenceLevel.HIGH


# ============================== StockOpportunityAssessment invariant ==============================


def test_insufficient_evidence_forbids_classification():
    """status=INSUFFICIENT_EVIDENCE이면 classification은 반드시 None이어야
    한다 -- model_validator가 구조적으로 강제한다."""
    with pytest.raises(ValidationError):
        StockOpportunityAssessment(
            symbol="005930",
            name="삼성전자",
            status=AssessmentStatus.INSUFFICIENT_EVIDENCE,
            classification=OpportunityClassification.ATTRACTIVE,
            coverage=_insufficient_coverage(),
            confidence=_unknown_confidence(),
        )


def test_insufficient_evidence_with_null_classification_is_valid():
    assessment = StockOpportunityAssessment(
        symbol="005930",
        name="삼성전자",
        status=AssessmentStatus.INSUFFICIENT_EVIDENCE,
        classification=None,
        coverage=_insufficient_coverage(),
        confidence=_unknown_confidence(),
    )
    assert assessment.classification is None


def test_actionable_neutral_is_not_insufficient_evidence():
    """NEUTRAL classification != insufficient evidence -- 둘은 서로 다른
    필드(status/classification)이므로 혼동될 수 없다."""
    assessment = StockOpportunityAssessment(
        symbol="005930",
        name="삼성전자",
        status=AssessmentStatus.ACTIONABLE,
        classification=OpportunityClassification.NEUTRAL,
        coverage=_sufficient_coverage(),
        confidence=_high_confidence(),
    )
    assert assessment.status == AssessmentStatus.ACTIONABLE
    assert assessment.classification == OpportunityClassification.NEUTRAL


def test_stock_opportunity_assessment_has_no_portfolio_action_field():
    """StockOpportunityAssessment != PortfolioActionRecommendation -- action/
    target_weight 같은 portfolio 필드가 스키마에 존재하지 않는다."""
    field_names = set(StockOpportunityAssessment.model_fields.keys())
    assert "action" not in field_names
    assert "target_weight" not in field_names
    assert "current_weight" not in field_names


# ============================== Event Overlay가 Core를 직접 mutate하지 않음 ==============================


def test_event_overlay_reference_has_no_numeric_score_field():
    """Event Overlay가 ComponentScore를 직접 담지 않는다 -- 이 model에는
    numeric score/bonus/penalty 필드 자체가 없다."""
    field_names = set(EventOverlayReference.model_fields.keys())
    for forbidden in ("score", "bonus", "penalty", "points"):
        assert forbidden not in field_names


# ============================== Risk가 score penalty가 아님 ==============================


def test_risk_assessment_has_no_score_penalty_field():
    field_names = set(RiskAssessment.model_fields.keys())
    for forbidden in ("score", "penalty", "score_adjustment"):
        assert forbidden not in field_names


def test_risk_level_reuses_existing_common_enum():
    risk = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        coverage=_sufficient_coverage(),
        confidence=_high_confidence(),
    )
    assert risk.risk_level == RiskLevel.HIGH


# ============================== Availability semantics ==============================


def test_availability_status_distinguishes_missing_from_neutral_states():
    statuses = {s.value for s in AvailabilityStatus}
    assert statuses == {
        "available",
        "estimated",
        "unavailable",
        "not_applicable",
        "invalid",
    }
    # NEUTRAL이라는 값이 이 enum에 존재하지 않는다는 것 자체가
    # "missing data != neutral feature" 원칙을 스키마로 강제한다.
    assert "neutral" not in statuses


def test_feature_evaluation_result_separates_raw_and_normalized_value():
    from app.models.recommendation import FeatureValue

    result = FeatureEvaluationResult(
        feature_id="roe",
        component=Component.FUNDAMENTAL,
        feature_family="profitability",
        raw=FeatureValue(value=12.5, unit="percent"),
        availability=AvailabilityStatus.AVAILABLE,
        normalized_value=0.31,
    )
    # raw value != normalized value -- 서로 다른 필드다.
    assert result.raw.value == 12.5
    assert result.normalized_value == 0.31
    assert result.raw.value != result.normalized_value


# ============================== Risk UNKNOWN representability ==============================


def test_risk_level_none_is_valid_with_insufficient_coverage():
    """risk severity를 판단할 근거가 부족하면 risk_level=None -- LOW로
    강제되지 않는다."""
    risk = RiskAssessment(
        risk_level=None,
        coverage=_insufficient_coverage(),
        confidence=_unknown_confidence(),
    )
    assert risk.risk_level is None


def test_risk_level_none_is_not_low():
    """None(판단 불가)과 LOW(판단했더니 낮음)는 서로 다른 값이다."""
    unclassified = RiskAssessment(
        risk_level=None,
        coverage=_insufficient_coverage(),
        confidence=_unknown_confidence(),
    )
    classified_low = RiskAssessment(
        risk_level=RiskLevel.LOW,
        coverage=_sufficient_coverage(),
        confidence=_high_confidence(),
    )
    assert unclassified.risk_level is None
    assert classified_low.risk_level == RiskLevel.LOW
    assert unclassified.risk_level != classified_low.risk_level


def test_risk_level_independent_of_coverage_and_confidence():
    """risk_level=None(미분류)이면서 coverage/confidence는 각각 독립적인
    값을 가질 수 있다 -- 서로 강제하지 않는다."""
    risk = RiskAssessment(
        risk_level=None,
        coverage=_sufficient_coverage(),  # coverage는 SUFFICIENT여도
        confidence=_unknown_confidence(),  # confidence는 UNKNOWN일 수 있다
    )
    assert risk.risk_level is None
    assert risk.coverage.coverage_status == CoverageStatus.SUFFICIENT
    assert risk.confidence.level == ConfidenceLevel.UNKNOWN


# ============================== FutureOpportunityEvidence tri-state ==============================


def test_forward_path_unknown_is_representable():
    """Forward path를 아직 확인하지 못한 상태(source failure 등)는 UNKNOWN
    -- UNAVAILABLE(확인했더니 없음)과 다른 값이다."""
    assessment = FutureOpportunityEvidenceAssessment(
        forward_path_availability=EvidencePathAvailability.UNKNOWN,
        event_path_availability=EvidencePathAvailability.UNAVAILABLE,
        requirement_satisfied=RequirementSatisfaction.UNKNOWN,
    )
    assert assessment.forward_path_availability == EvidencePathAvailability.UNKNOWN
    assert assessment.forward_path_availability != EvidencePathAvailability.UNAVAILABLE


def test_event_path_unknown_is_representable():
    assessment = FutureOpportunityEvidenceAssessment(
        forward_path_availability=EvidencePathAvailability.UNAVAILABLE,
        event_path_availability=EvidencePathAvailability.UNKNOWN,
        requirement_satisfied=RequirementSatisfaction.UNKNOWN,
    )
    assert assessment.event_path_availability == EvidencePathAvailability.UNKNOWN


def test_confirmed_unavailable_is_distinct_from_unknown():
    """ "확인했더니 genuinely absent"와 "확인 자체를 못함"이 같은 값으로
    collapse되지 않는다."""
    confirmed_absent = FutureOpportunityEvidenceAssessment(
        forward_path_availability=EvidencePathAvailability.UNAVAILABLE,
        event_path_availability=EvidencePathAvailability.UNAVAILABLE,
        requirement_satisfied=RequirementSatisfaction.NOT_SATISFIED,
    )
    unknown = FutureOpportunityEvidenceAssessment(
        forward_path_availability=EvidencePathAvailability.UNKNOWN,
        event_path_availability=EvidencePathAvailability.UNKNOWN,
        requirement_satisfied=RequirementSatisfaction.UNKNOWN,
    )
    assert confirmed_absent.forward_path_availability != unknown.forward_path_availability
    assert confirmed_absent.requirement_satisfied != unknown.requirement_satisfied


def test_requirement_satisfaction_unknown_does_not_serialize_as_false():
    """UNKNOWN이 bool False로 눌리지 않는다 -- serialize한 값이 여전히
    "unknown" 문자열이지 false/코드상 falsy 값이 아니다."""
    assessment = FutureOpportunityEvidenceAssessment(
        forward_path_availability=EvidencePathAvailability.UNKNOWN,
        event_path_availability=EvidencePathAvailability.UNKNOWN,
        requirement_satisfied=RequirementSatisfaction.UNKNOWN,
    )
    dumped = assessment.model_dump()
    assert dumped["requirement_satisfied"] == "unknown"
    assert dumped["requirement_satisfied"] is not False
    assert dumped["forward_path_availability"] == "unknown"


def test_requirement_satisfied_defaults_to_unknown_not_false():
    """requirement_satisfied를 아예 넘기지 않으면 기본값이 UNKNOWN이다 --
    False로 암묵 처리되지 않는다."""
    assessment = FutureOpportunityEvidenceAssessment(
        forward_path_availability=EvidencePathAvailability.AVAILABLE,
        event_path_availability=EvidencePathAvailability.UNAVAILABLE,
    )
    assert assessment.requirement_satisfied == RequirementSatisfaction.UNKNOWN


# ============================== StockOpportunityAssessment 양방향 invariant ==============================


def test_actionable_forbids_null_classification():
    """status=ACTIONABLE이면 classification이 반드시 non-None이어야 한다 --
    §17 반대 방향 invariant도 model_validator가 강제한다."""
    with pytest.raises(ValidationError):
        StockOpportunityAssessment(
            symbol="005930",
            name="삼성전자",
            status=AssessmentStatus.ACTIONABLE,
            classification=None,
            coverage=_sufficient_coverage(),
            confidence=_high_confidence(),
        )


def test_actionable_with_classification_is_valid():
    for classification in (
        OpportunityClassification.ATTRACTIVE,
        OpportunityClassification.NEUTRAL,
        OpportunityClassification.UNATTRACTIVE,
    ):
        assessment = StockOpportunityAssessment(
            symbol="005930",
            name="삼성전자",
            status=AssessmentStatus.ACTIONABLE,
            classification=classification,
            coverage=_sufficient_coverage(),
            confidence=_high_confidence(),
        )
        assert assessment.classification == classification

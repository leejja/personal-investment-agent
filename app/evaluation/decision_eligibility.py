"""RE-05 Recommendation Policy Step 1 -- Final Decision Eligibility.

이미 채워진 두 producer output을 deterministic하게 투영(projection)할 뿐이다:

    policy_may_proceed  = coverage.critical_path_satisfied
    forward_requirement = future_opportunity_evidence.requirement_satisfied

- Decision Eligibility는 `AssessmentStatus`가 아니다 -- ACTIONABLE/
  INSUFFICIENT_EVIDENCE는 이후 policy 단계가 결정한다.
- `coverage.coverage_status`는 eligibility 입력이 아니다(Forward가 status에
  포함되므로, 이를 gate로 쓰면 Forward가 간접 universal hard gate가 된다).
- FOE의 `RequirementSatisfaction` tri-state를 그대로 보존한다 -- UNKNOWN은
  SATISFIED도 NOT_SATISFIED도 아니다. FOE를 재계산하지 않는다.
- producer가 실행되지 않은 `None`은 UNKNOWN evidence가 아니다 -- ValueError.
- `RequirementSatisfaction`은 str Enum이라 모든 값이 truthy다 -- truthiness로
  판단하지 않는다.

결과는 저장되지 않는 transient 값이며, 이 모듈은 warnings/DecisionReasons를
만들지 않고 입력을 mutate하지 않는다.
"""

from dataclasses import dataclass

from app.models.recommendation import (
    CoverageAssessment,
    FutureOpportunityEvidenceAssessment,
    RequirementSatisfaction,
)


@dataclass(frozen=True, slots=True)
class DecisionEligibility:
    """Policy Step 1의 transient 결과(영속 domain model 아님)."""

    policy_may_proceed: bool
    forward_requirement: RequirementSatisfaction


def evaluate_decision_eligibility(
    coverage: CoverageAssessment | None,
    future_opportunity_evidence: FutureOpportunityEvidenceAssessment | None,
) -> DecisionEligibility:
    """State Coverage의 critical foundation과 FOE tri-state를 투영한다.

    `policy_may_proceed`는 critical foundation만으로 결정된다 -- FOE
    NOT_SATISFIED/UNKNOWN은 progression을 막지 않고 `forward_requirement`로
    그대로 전달된다."""
    if coverage is None:
        raise ValueError(
            "decision eligibility requires coverage; the state coverage producer has not run"
        )
    if future_opportunity_evidence is None:
        raise ValueError(
            "decision eligibility requires future_opportunity_evidence; "
            "the future opportunity evidence producer has not run"
        )

    return DecisionEligibility(
        policy_may_proceed=coverage.critical_path_satisfied,
        forward_requirement=future_opportunity_evidence.requirement_satisfied,
    )

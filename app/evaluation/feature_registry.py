"""RE-05 Minimal Feature Registry -- Feature identity의 canonical single
source of truth.

`docs/dev-log/2026-08-29.md` §35(초기 설계)/§36(final contract audit --
scope status orthogonality correction, `requirement_role` rename)가 이
설계의 audit/결정 근거를 담는다.

이 모듈이 관리하는 것: feature identity, component/family ownership,
V1 scope contract, verification/precondition 여부(scope와 orthogonal,
§36), default coverage requirement role, semantic direction,
applicability 여부(review 필요성), required factual input, evaluator
identity/version.

이 모듈이 **하지 않는 것**(RE-05 Numeric Calibration = OPEN 원칙 그대로):
- threshold, weight, lookback, window
- normalization formula parameter
- signal boundary, score cutoff
- aggregation weight
- scoring policy 전반

`FeatureDefinition`은 "이 feature란 무엇인가"(design-time, immutable)를
담고, `app.models.recommendation.FeatureEvaluationResult`는 "이 종목/
시점에 대한 평가 결과가 무엇이었나"(runtime)를 담는다 -- 이 둘을
섞지 않는다.
"""

from enum import Enum
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from app.models.recommendation import Component, Directionality, RequirementRole

# ============================== Scope Status ==============================


class FeatureScopeStatus(str, Enum):
    """`docs/dev-log/2026-08-29.md` §29(V1 Feature Set FROZEN)의 canonical
    scope terminology를 그대로 가져온다 -- **design-time** 개념이다.

    §36.1 correction: 이 enum에는 더 이상 `VERIFICATION_REQUIRED`가 없다
    (§35에서는 다섯 번째 값으로 포함했었다). §29.2/§29(dev-log 2503-2826행
    부근)의 실제 frozen 서술을 재확인한 결과, `VERIFICATION_REQUIRED`는
    이 4개 scope status와 **mutually exclusive한 다섯 번째 상태가 아니라**
    orthogonal한 "runtime/precondition verification" 축이었다 -- 예:
    Momentum은 `scope_status=V1_OPTIONAL`이면서 동시에 `runtime =
    VERIFICATION_REQUIRED`(adjusted-price corporate-action safety 미확정,
    §29.5)다. 그 축은 `FeatureDefinition.verification_requirements`로
    분리했다(아래).

    `app.models.recommendation.AvailabilityStatus`(runtime, "이번 평가에서
    값을 실제로 구했는가")와도 절대 혼동하지 않는다. 예: Forward feature는
    `scope_status=V1_BLOCKED`이면서 동시에(향후 evaluator가 생기면) runtime
    `AvailabilityStatus.UNAVAILABLE`을 낼 수 있다 -- 둘은 서로 다른 축이다."""

    V1_REQUIRED = "v1_required"
    V1_OPTIONAL = "v1_optional"
    V1_DEFERRED = "v1_deferred"
    V1_BLOCKED = "v1_blocked"


class FeatureApplicability(str, Enum):
    """§8. "항상 적용 가능"과 "적용 가능 여부에 semantic rule이 필요함"만
    구분한다 -- 실제 업종별 applicability rule engine은 만들지 않는다.

    `FeatureEvaluationResult.applicability_review_required`(런타임, 특정
    평가 1건에 대한 flag)와는 다른 축이다 -- 이 필드는 registry
    definition 수준에서 "이 feature 자체가 review가 필요한 부류인가"를
    나타내는 static 분류다."""

    UNIVERSAL = "universal"
    REVIEW_REQUIRED = "review_required"


# ============================== FeatureDefinition ==============================


class FeatureDefinition(BaseModel):
    """§6. Immutable -- runtime evaluation 중 mutate되지 않는다
    (`model_config = ConfigDict(frozen=True)`). "이 feature란 무엇인가"만
    담고 "이번 평가 결과가 무엇이었나"는 담지 않는다(그건
    `FeatureEvaluationResult`).

    `scope_status`(V1 scope classification)와 `default_requirement_role`
    (coverage critical-path role, §8 Coverage 관점)은 **의도적으로 분리된
    필드**다 -- 둘 다 "REQUIRED"라는 이름을 쓸 수 있지만 다른 질문에
    답한다: scope_status는 "v1 로드맵에 포함되는가", default_requirement_role
    은 "이 feature가 없으면 이 family/component의 critical-path coverage가
    깨지는가"다. 현재는 ROE 하나뿐이라 둘 다 REQUIRED 계열 값이 우연히
    일치하지만, 이 프로젝트에서 그것이 항상 같은 개념이라고 architecture
    레벨에서 확정된 적은 없다 -- 그래서 merge하지 않았다(§5/§36.4).

    `requirement_role` -> `default_requirement_role`로 개명했다(§36.4).
    이 필드는 registry가 선언하는 **default/canonical** coverage role일
    뿐이다 -- 특정 종목의 runtime 평가가 `AvailabilityStatus.NOT_APPLICABLE`
    을 내는 것과 모순되지 않는다(예: 이 feature의 default role이 REQUIRED
    여도, 금융업 같은 특정 종목에서는 runtime에 NOT_APPLICABLE이 나올 수
    있다 -- "일반적으로 요구된다"와 "이번 종목에는 해당 안 한다"는 서로
    다른 layer의 판단이다). 이름 자체가 이 관계를 드러내도록 했다.

    `verification_requirements`(§36.1/§36.2)는 scope_status와
    orthogonal한 축이다 -- 예: Momentum 같은 future feature는
    `scope_status=V1_OPTIONAL`이면서 동시에
    `verification_requirements=("adjusted-price corporate-action safety
    unresolved, §29.5",)`를 가질 수 있다. 빈 tuple은 "현재 알려진
    verification precondition이 없다"는 뜻이다(ROE가 그 경우). 별도
    enum/rule engine을 만들지 않고 free-text tuple로 최소 구현했다 --
    §28.14의 Data/Semantic/Calibration Question taxonomy와 연결하는 것도
    이번에는 하지 않는다(over-engineering 방지).

    `required_inputs`는 vendor field 이름(`opendart.account_xxx`,
    `kiwoom.foo` 같은 것)을 쓰지 않는다 -- `NormalizedResearchData`의
    normalized-domain semantic path(dot-separated 문자열)만 쓴다. 별도
    DSL이나 typed path object를 만들지 않았다 -- 이 규모(feature 1~2개)
    에서는 plain string으로 충분하다고 판단했다(§7/§10)."""

    model_config = ConfigDict(frozen=True)

    feature_id: str
    component: Component
    feature_family: str

    scope_status: FeatureScopeStatus
    # scope_status와 orthogonal한 runtime/precondition verification 축.
    # 빈 tuple = 현재 알려진 verification precondition 없음.
    verification_requirements: tuple[str, ...] = Field(default_factory=tuple)

    default_requirement_role: RequirementRole
    directionality: Directionality | None = None
    applicability: FeatureApplicability

    # NormalizedResearchData 내부의 semantic path만 쓴다(vendor field 이름 금지).
    required_inputs: tuple[str, ...] = Field(default_factory=tuple)

    evaluator_id: str
    evaluator_version: str


# ============================== Registry ==============================
#
# 구현 형태 비교(§10):
#   A. module-level immutable dict/mapping        <- 채택
#   B. tuple/list of frozen FeatureDefinition만 두고 매번 순회
#   C. FeatureRegistry class(등록/조회 메서드, plugin architecture)
#   D. 기타
#
# feature가 1개(곧 2개)인 현재 규모에서 B/C는 과도하다 -- 검색/plugin
# 등록 같은 기능이 실제로 필요하지 않다(runtime dynamic registration
# 요구사항 없음). module-level MappingProxyType(읽기 전용 dict)에 조회
# 함수 하나만 더한 것이 가장 단순하면서 "mutation 불가"/"single source
# of truth" 요구를 모두 만족한다.

_ROE_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.profitability.roe",
    component=Component.FUNDAMENTAL,
    feature_family="profitability",
    # dev-log §29.2 V1 Feature Set 표(Fundamental Quality, ROE 행)의
    # 값을 그대로 옮긴 것이다 -- 이번에 새로 판단하지 않았다.
    scope_status=FeatureScopeStatus.V1_REQUIRED,
    # ROE는 Kiwoom이 이미 계산해 제공하는 필드라(§34.3) Momentum류와 달리
    # 알려진 verification precondition이 없다 -- 빈 tuple(§36.3).
    verification_requirements=(),
    # §24.8 Coverage 관점: ROE 없이는 Fundamental/Profitability family의
    # critical-path coverage가 깨진다고 판단한 기존 evaluator 동작
    # (RequirementRole.REQUIRED)을 그대로 옮겼다 -- V1_REQUIRED와 값이
    # 같더라도 별도 필드로 유지한다(위 docstring 참고).
    default_requirement_role=RequirementRole.REQUIRED,
    directionality=Directionality.HIGHER_IS_BETTER,
    # Kiwoom이 전 종목에 균일하게 제공하는 사전 계산 필드라 업종별
    # applicability 예외를 실측으로 발견한 적이 없다(§34.3, Interest
    # Coverage/Asset Turnover 같은 OpenDART raw-account 파생 feature와는
    # 다르다) -- UNIVERSAL로 분류한다.
    applicability=FeatureApplicability.UNIVERSAL,
    required_inputs=("financial_facts.current.roe",),
    evaluator_id="RoeFeatureEvaluator",
    evaluator_version="v1",
)

_DEFINITIONS: Final[MappingProxyType[str, FeatureDefinition]] = MappingProxyType(
    {definition.feature_id: definition for definition in (_ROE_DEFINITION,)}
)


def get_feature_definition(feature_id: str) -> FeatureDefinition:
    """`feature_id`에 대응하는 canonical `FeatureDefinition`을 반환한다.
    등록되지 않은 `feature_id`는 `KeyError`를 raise한다 -- 조용히 None을
    반환하거나 임의 기본값을 만들지 않는다."""
    return _DEFINITIONS[feature_id]


def list_feature_definitions() -> tuple[FeatureDefinition, ...]:
    """현재 registry에 등록된 모든 definition을 반환한다(향후 Coverage
    evaluator가 "이 component에 어떤 feature가 있는가"를 열거할 때 쓸
    수 있는 최소 조회 API, §13). 정렬/필터링 같은 추가 기능은 이번에
    만들지 않는다."""
    return tuple(_DEFINITIONS.values())

"""RE-05 Feature Registry -- Feature identity의 canonical single source
of truth.

`docs/dev-log/2026-08-29.md` §35(초기 설계)/§36(scope status orthogonality
correction, `requirement_role` rename)/§38(completeness & coverage
readiness audit -- semantic role을 **FULL V1 CATALOG**로 명시적으로
확정, `evaluator_id`/`evaluator_version`을 optional로 correction)/§39
(Complete V1 Feature Catalog -- semantic resolution & population, raw
fact/reference input과 evaluated feature를 구분해 REGISTER_NOW로 판단된
항목을 실제로 등록)가 이 설계의 audit/결정 근거를 담는다.

**semantic role(§38 확정)**: 이 registry는 "evaluator가 구현된 feature만
담는 execution registry"가 아니라 **FROZEN V1 Feature Set(§29) 전체의
canonical catalog**다 -- evaluator 유무와 무관하게 v1 scope에 속하는
모든 feature identity를 담는 것이 목표다(그래야 Coverage가 "evaluator가
없다"와 "feature 자체가 없다"를 혼동하지 않는다, §38.2 FALSE
COMPLETENESS). **모든 §29.2 V1 인벤토리 항목이 FeatureDefinition은
아니다**(§39.0 원칙) -- Raw Fact(예: 250d High/Low)와 Reference/Context
Input(예: KOSPI/KOSDAQ Benchmark, Market Cap 정규화)은 의도적으로
등록하지 않는다. **completeness는 현재 PARTIAL이다** -- §29가 FROZEN한
전체 인벤토리(약 40개 이상) 중 §39가 evaluated feature identity로
분류하고 semantic이 충분히 해소됐다고 판단한 항목만 등록돼 있다(§39.13
REGISTER_NOW 목록). Forward/Market Confirmation/Flow의 다수 항목과
FCF/Cash Conversion/Interest Coverage 등은 여전히 미등록이다(§39.15/
§39.16 참고, formula semantic question 또는 model-wiring gap으로 인해
이번에도 등록하지 않았다).

이 모듈이 관리하는 것: feature identity, component/family ownership,
V1 scope contract, verification/precondition 여부(scope와 orthogonal,
§36), default coverage requirement role, semantic direction,
applicability 여부(review 필요성), required factual input, evaluator
identity/version(선택적 -- §38 correction, feature가 evaluator 없이도
등록 가능).

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
    에서는 plain string으로 충분하다고 판단했다(§7/§10).

    §38 correction: `evaluator_id`/`evaluator_version`이 `str | None`
    (기본값 `None`)으로 바뀌었다 -- 원래는 required `str`였다. 이 registry
    는 "Feature identity의 canonical single source of truth"(§35 모듈
    docstring)를 자처하는데, FROZEN V1 Feature Set(§29)에는 아직 evaluator
    가 구현되지 않은 feature가 다수 존재한다(예: Net Margin, Debt Ratio,
    Trailing PER 등 — 전부 V1_REQUIRED이지만 evaluator 없음, §38.6). 이
    필드가 required였다면 "이 feature가 v1 scope에 존재한다"는 사실 자체를
    evaluator 구현 전까지 registry에 담을 방법이 없었다 -- Coverage가
    registry만 보고 "이 feature는 아예 존재하지 않는다"고 오판할 위험
    (§38.2 FALSE COMPLETENESS)이 있었다. `evaluator_id is None`은 정확히
    "feature identity는 정의됐지만 실행 구현이 아직 없다"(`NOT_IMPLEMENTED`)
    를 뜻한다 -- 별도 `implementation_status` enum 필드는 추가하지 않았다
    (`evaluator_id is None`이 이미 그 정보를 정확히 담고 있어 중복
    필드가 되기 때문, §38.12). **`NOT_IMPLEMENTED`(evaluator_id=None)와
    runtime `AvailabilityStatus.UNAVAILABLE`은 다른 축이다** -- 전자는
    "이 feature를 계산할 코드가 없다"(software capability), 후자는
    "코드는 있는데 이번 평가에서 값을 못 구했다"(data/runtime state).

    §40 correction: `default_requirement_role`이 `RequirementRole | None`
    (기본값 `None`)으로 바뀌었다 -- 원래는 required `RequirementRole`이었다.
    §39가 registry를 12개 신규 entry로 채우면서 "이 feature가 없으면
    critical-path coverage가 깨지는가"에 대해 실제로는 근거가 없는
    항목에도 `REQUIRED`/`OPTIONAL` 같은 구체적인 값을 강제로 채워야
    했다(스키마가 다른 선택지를 주지 않았기 때문) -- 이는 §39 자체
    보고서가 "OPEN"/"강한 근거로 도달한 값 아님"이라고 명시한 상태와
    모순이었다(§40.1). **`None`은 "coverage default role이 아직
    design-time에 확정되지 않았다"는 뜻이다** -- 다음과 절대 혼동하지
    않는다:
    - `RequirementRole.OPTIONAL`(coverage 관점에서 "선택적이라고 확정
      판단됨")과 다르다 -- `None`은 판단을 아직 안 한 것이고, `OPTIONAL`
      은 "선택적"이라고 적극적으로 판단한 것이다.
    - `RequirementRole.NOT_APPLICABLE`(특정 종목에 해당 없음이라고
      확정 판단됨, runtime에서도 쓰이는 값)과도 다르다.
    - runtime `AvailabilityStatus`(이 필드는 애초에 존재하지 않는
      축 -- `FeatureDefinition`은 design-time 모델이라 runtime 값을
      담지 않는다)와도 다르다.
    `scope_status`(V1 scope)에서 `default_requirement_role`을 자동
    유도하는 규칙은 존재하지 않는다(코드 어디에도 그런 매핑 로직이
    없다) -- `V1_REQUIRED`이면서 `default_requirement_role=None`인
    feature, `V1_OPTIONAL`/`V1_BLOCKED`이면서도 마찬가지인 feature가
    모두 유효하게 표현 가능하다(§40.7)."""

    model_config = ConfigDict(frozen=True)

    feature_id: str
    component: Component
    feature_family: str

    scope_status: FeatureScopeStatus
    # scope_status와 orthogonal한 runtime/precondition verification 축.
    # 빈 tuple = 현재 알려진 verification precondition 없음.
    verification_requirements: tuple[str, ...] = Field(default_factory=tuple)

    # None = coverage default role이 design-time에 아직 확정되지 않음
    # (§40 correction) -- RequirementRole.OPTIONAL/NOT_APPLICABLE과
    # 구분되는 별개의 "미확정" 상태다. 위 클래스 docstring 참고.
    default_requirement_role: RequirementRole | None = None
    directionality: Directionality | None = None
    applicability: FeatureApplicability

    # NormalizedResearchData 내부의 semantic path만 쓴다(vendor field 이름 금지).
    required_inputs: tuple[str, ...] = Field(default_factory=tuple)

    # None = 아직 evaluator가 구현되지 않은 feature(§38 correction).
    evaluator_id: str | None = None
    evaluator_version: str | None = None


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

_OPERATING_MARGIN_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.profitability.operating_margin",
    component=Component.FUNDAMENTAL,
    # dev-log §24.2가 정의한 Fundamental Quality family 목록에서 ROE와
    # Operating Margin은 둘 다 "Profitability" 아래에 있다 -- 새 family를
    # 만들지 않고 그 이름을 그대로 썼다(§37.7).
    feature_family="profitability",
    # dev-log §29.2 V1 Feature Set 표(Fundamental Quality, "Operating
    # Margin / Net Margin" 행)의 값을 그대로 옮겼다 -- 이번에 새로
    # 판단하지 않았다.
    scope_status=FeatureScopeStatus.V1_REQUIRED,
    # ROE와 달리 별도 vendor 신뢰도 이슈는 없지만, revenue 기반 비율이라
    # applicability(아래)와는 별개로 "값을 못 구하는" precondition은
    # 없다 -- 빈 tuple.
    verification_requirements=(),
    default_requirement_role=RequirementRole.REQUIRED,
    directionality=Directionality.HIGHER_IS_BETTER,
    # §26.2/§28.5에서 이미 실측 확정된 사실: KB금융(금융지주)은 "매출액"
    # 계정 자체가 없다(순이자손익/순수수료손익으로 대체) -- Operating
    # Margin(operating_profit/revenue)은 Asset Turnover와 동일하게 이
    # 구조적 제약을 그대로 물려받는다. ROE(Kiwoom 사전계산 필드)와 달리
    # REVIEW_REQUIRED로 분류한다(새 rule engine을 만들지 않고 분류만
    # 반영, §37.5/§35.7).
    applicability=FeatureApplicability.REVIEW_REQUIRED,
    # RE-01 financial_features.annual(오래된→최신 순)의 마지막 항목이
    # "현재" 연도에 해당한다 -- FinancialSnapshot.current에는 이 값이
    # 없다(§37.1 확인). 새 계산식을 만들지 않고 analysis.py가 이미
    # 계산해둔 값만 읽는다.
    required_inputs=("financial_facts.features.annual[latest].operating_margin",),
    evaluator_id="OperatingMarginFeatureEvaluator",
    evaluator_version="v1",
)

# ---- §39 Complete V1 Feature Catalog: 신규 등록 (evaluator 전부 미구현) ----
#
# 아래 항목은 전부 evaluator_id/evaluator_version을 생략한다(기본값
# None, §38 correction) -- feature identity만 선언할 뿐 어떤 evaluator도
# 구현하지 않는다(§39.14). 각 항목의 상세 분류 근거(REGISTER_NOW 판단
# 이유, raw fact/reference input과의 구분)는 dev-log §39를 참고한다 --
# 여기서는 §29.2 FROZEN 표에 이미 기록된 사실만 옮긴다.

_NET_MARGIN_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.profitability.net_margin",
    component=Component.FUNDAMENTAL,
    feature_family="profitability",
    scope_status=FeatureScopeStatus.V1_REQUIRED,
    verification_requirements=(),
    # §41.5 CONFIRMED_OPTIONAL (anchor rule): profitability family는 이미
    # ROE/Operating Margin이 REQUIRED anchor로 존재한다 -- family
    # critical-path evidence가 이 둘로 이미 보장되므로, Net Margin
    # 개별이 REQUIRED일 근거는 없지만 "판단을 아직 안 함"(None)도 더는
    # 맞지 않다 -- OPTIONAL이 정확한 판단이다(§40.4의 UNRESOLVED에서
    # correction).
    default_requirement_role=RequirementRole.OPTIONAL,
    directionality=Directionality.HIGHER_IS_BETTER,
    # Operating Margin과 동일한 revenue-dependency 구조적 제약(§26.2/§28.5).
    applicability=FeatureApplicability.REVIEW_REQUIRED,
    required_inputs=("financial_facts.features.annual[latest].net_margin",),
)

_REVENUE_GROWTH_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.observed_growth_quality.revenue_growth",
    component=Component.FUNDAMENTAL,
    # §24.2 family 목록: "Observed Growth Quality"는 Profitability와
    # 구분되는 독립 family다 -- Growth 항목을 profitability에 합치지
    # 않는다(§39.2).
    feature_family="observed_growth_quality",
    scope_status=FeatureScopeStatus.V1_REQUIRED,
    verification_requirements=(),
    # §41.5 CONFIRMED_OPTIONAL (family-policy-deferred rule): family
    # (observed_growth_quality) 안에 3개의 non-blocked candidate가
    # 공존하고 그중 어느 것도 개별적으로 "이거 하나 없으면 무조건 결정
    # 불가"는 아니다 -- family 전체의 evidence 충분성은 개별 feature
    # role이 아니라 family/component 단위 Coverage policy(§41.4)가
    # 판단한다. 개별 feature는 OPTIONAL(가능하면 좋은 evidence
    # contributor)로 확정한다.
    default_requirement_role=RequirementRole.OPTIONAL,
    directionality=Directionality.HIGHER_IS_BETTER,
    # revenue 기반이라 Operating Margin과 동일한 applicability 제약을 받는다.
    applicability=FeatureApplicability.REVIEW_REQUIRED,
    # analysis.py의 FinancialFeatures.yoy/trends는 metric별로 독립된
    # entry다(FinancialMetric.REVENUE) -- 단일 dotted path가 아니라 두
    # 개의 semantic path로 표현한다(§39.2).
    required_inputs=(
        "financial_facts.features.yoy[metric=REVENUE]",
        "financial_facts.features.trends[metric=REVENUE]",
    ),
)

_OPERATING_PROFIT_GROWTH_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.observed_growth_quality.operating_profit_growth",
    component=Component.FUNDAMENTAL,
    feature_family="observed_growth_quality",
    scope_status=FeatureScopeStatus.V1_REQUIRED,
    verification_requirements=(),
    # §41.5 CONFIRMED_OPTIONAL: 위 Revenue Growth와 동일한
    # family-policy-deferred rule.
    default_requirement_role=RequirementRole.OPTIONAL,
    directionality=Directionality.HIGHER_IS_BETTER,
    # 영업이익 계정 자체가 없는 업종 가능성이 §26.2 실측으로 완전히
    # 배제되지 않았다 -- 보수적으로 REVIEW_REQUIRED(§39.2).
    applicability=FeatureApplicability.REVIEW_REQUIRED,
    required_inputs=(
        "financial_facts.features.yoy[metric=OPERATING_PROFIT]",
        "financial_facts.features.trends[metric=OPERATING_PROFIT]",
    ),
)

_NET_INCOME_GROWTH_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.observed_growth_quality.net_income_growth",
    component=Component.FUNDAMENTAL,
    feature_family="observed_growth_quality",
    scope_status=FeatureScopeStatus.V1_REQUIRED,
    verification_requirements=(),
    # §41.5 CONFIRMED_OPTIONAL: 위 두 Growth feature와 동일한
    # family-policy-deferred rule.
    default_requirement_role=RequirementRole.OPTIONAL,
    directionality=Directionality.HIGHER_IS_BETTER,
    # 순이익 계정은 §26.2에서 KB금융(금융지주) 포함 전 업종에 존재함이
    # 실측 확인됐다 -- revenue/영업이익과 달리 UNIVERSAL(§39.2, §40.5에서
    # applicability는 이 판단 그대로 재확인했다 -- default_requirement_role
    # 미확정과는 별개 축이다).
    applicability=FeatureApplicability.UNIVERSAL,
    required_inputs=(
        "financial_facts.features.yoy[metric=NET_INCOME]",
        "financial_facts.features.trends[metric=NET_INCOME]",
    ),
)

_DEBT_RATIO_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.financial_resilience.debt_ratio",
    component=Component.FUNDAMENTAL,
    feature_family="financial_resilience",
    # §29.2 표 행 이름은 "Debt Ratio(비금융)"이지만 §29.3이 이 한정을
    # "review 완료 전까지의 임시 scope 한정"이라고 명시했다 -- scope_status
    # 자체는 변경하지 않는다(§39.3, 업종 부적합 가능성 != V1_REQUIRED
    # scope 축소).
    scope_status=FeatureScopeStatus.V1_REQUIRED,
    verification_requirements=(),
    # §41.5 REMAIN_UNRESOLVED (sole-representative rule): financial_resilience
    # family에서 현재 유일한 등록 feature다 -- profitability/
    # observed_growth_quality처럼 다른 anchor나 복수 candidate가 없어
    # anchor rule도 family-policy-deferred rule도 적용할 수 없다.
    # OPTIONAL로 확정하면 "Financial Resilience family 전체가 v1
    # coverage에서 critical하지 않다"는 실질적 family-level 정책 결정을
    # 개별 feature 값으로 몰래 내리는 셈이 된다 -- 이 family 자체가
    # Fundamental coverage에 critical한지는 별도 family/component policy
    # 결정이 필요하다(§41.4/§41.11, 아직 없음). 그 결정 전까지 None 유지.
    default_requirement_role=None,
    directionality=Directionality.LOWER_IS_BETTER,
    # §29.3 FINANCIAL_SECTOR_APPLICABILITY_REVIEW_REQUIRED 목록에 포함,
    # 여전히 OPEN.
    applicability=FeatureApplicability.REVIEW_REQUIRED,
    required_inputs=("financial_facts.features.annual[latest].debt_ratio",),
)

_ROA_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.profitability.roa",
    component=Component.FUNDAMENTAL,
    # §24.2: ROA는 Profitability family 소속(ROE/ROIC/Margin과 동일)이지
    # Capital Efficiency가 아니다(§39.2).
    feature_family="profitability",
    scope_status=FeatureScopeStatus.V1_OPTIONAL,
    verification_requirements=(),
    # §41.5 CONFIRMED_OPTIONAL (anchor rule): Net Margin과 동일 -- ROE/
    # Operating Margin이 이미 profitability family의 REQUIRED anchor다.
    # §40에서는 "V1_OPTIONAL이니 OPTIONAL" 자동 유도를 correction해
    # None으로 바꿨는데, 이번엔 자동 유도가 아니라 anchor rule이라는
    # 독립적인 근거로 다시 OPTIONAL에 도달했다 -- 결과값은 같지만 근거의
    # 질이 다르다(§40.1의 문제였던 "OPEN인데 구체값"과는 다른 상태).
    default_requirement_role=RequirementRole.OPTIONAL,
    directionality=Directionality.HIGHER_IS_BETTER,
    # net_income/total_assets 둘 다 금융업 포함 전 업종에 존재(§26.2).
    applicability=FeatureApplicability.UNIVERSAL,
    required_inputs=(
        "financial_facts.current.net_income",
        "financial_facts.current.total_assets",
    ),
)

_ASSET_TURNOVER_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.capital_efficiency.asset_turnover",
    component=Component.FUNDAMENTAL,
    feature_family="capital_efficiency",
    scope_status=FeatureScopeStatus.V1_OPTIONAL,
    verification_requirements=(),
    # §41.5 REMAIN_UNRESOLVED (sole-representative rule): capital_efficiency
    # family의 다른 등록 feature는 ROIC뿐인데 ROIC는 V1_BLOCKED다 --
    # "현재 v1에서 실제로 evidence를 낼 수 있는" 유일한 candidate라는
    # 점에서 Debt Ratio와 같은 상황이다. Debt Ratio와 동일한 이유로 None
    # 유지(§41.4/§41.11 family-level policy 결정 필요).
    default_requirement_role=None,
    directionality=Directionality.HIGHER_IS_BETTER,
    # revenue 기반 -- §29.3 review 목록에 포함.
    applicability=FeatureApplicability.REVIEW_REQUIRED,
    required_inputs=(
        "financial_facts.current.revenue",
        "financial_facts.current.total_assets",
    ),
)

_ROIC_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.capital_efficiency.roic",
    component=Component.FUNDAMENTAL,
    feature_family="capital_efficiency",
    # §29.2: raw ingredient(Invested Capital 분모) 자체가 불안정 --
    # V1_BLOCKED. identity(ROIC라는 개념 자체)는 표준적이고 명확해
    # evaluator 없이도 등록 가능하다고 판단한다(§39.4).
    scope_status=FeatureScopeStatus.V1_BLOCKED,
    verification_requirements=(
        "invested capital denominator account naming unstable across companies (§29.2)",
    ),
    # §41.5 CONFIRMED_OPTIONAL (blocked rule): scope_status=V1_BLOCKED인
    # feature는 v1에서 구조적으로 evidence를 낼 수 없다 -- critical-path
    # REQUIRED/IMPORTANT일 수 없다는 것이 scope 정의 자체에서 나온다
    # (V1_BLOCKED -> OPTIONAL은 "BLOCKED는 절대 critical-path gate가 될
    # 수 없다"는 명시적 semantic rule이지, "V1_REQUIRED -> REQUIRED"류의
    # 근거 없는 자동 유도가 아니다, §41.11).
    default_requirement_role=RequirementRole.OPTIONAL,
    directionality=Directionality.HIGHER_IS_BETTER,
    applicability=FeatureApplicability.REVIEW_REQUIRED,
    required_inputs=(),
)

_EPS_GROWTH_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="fundamental.observed_growth_quality.eps_growth",
    component=Component.FUNDAMENTAL,
    feature_family="observed_growth_quality",
    # §29.2: 과거 발행주식수 source 없음 -- V1_BLOCKED. identity(순수
    # EPS 증가율)는 명확하다(§39.4).
    scope_status=FeatureScopeStatus.V1_BLOCKED,
    verification_requirements=("historical shares outstanding series not available (§29.2)",),
    # §41.5 CONFIRMED_OPTIONAL (blocked rule): ROIC와 동일.
    default_requirement_role=RequirementRole.OPTIONAL,
    directionality=Directionality.HIGHER_IS_BETTER,
    applicability=FeatureApplicability.UNIVERSAL,
    required_inputs=(),
)

_TRAILING_PER_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="valuation.earnings_based.trailing_per",
    component=Component.VALUATION,
    feature_family="earnings_based",
    scope_status=FeatureScopeStatus.V1_REQUIRED,
    verification_requirements=(),
    # §41.5 CONFIRMED_OPTIONAL (family-policy-deferred rule): earnings_based
    # family에 Earnings Yield도 있어 PER 혼자 family를 대표하지 않는다 --
    # Growth ×3과 동일한 논리(복수 non-blocked candidate 존재).
    default_requirement_role=RequirementRole.OPTIONAL,
    # PER는 ROE처럼 단순 HIGHER/LOWER_IS_BETTER가 아니다 -- 극단적으로
    # 낮은 PER는 저평가가 아니라 실적 악화/부실 신호일 수 있다(§39.9).
    # 이 axis를 numeric threshold 없이 이미 존재하는
    # `Directionality.CONTEXT_DEPENDENT`로 표현한다(enum 확장 불필요).
    # directionality와 default_requirement_role은 독립 축이다 -- 후자가
    # 미확정이라고 전자의 판단(§39.9, 이번 audit에서 재확인)도 흔들리지
    # 않는다(§40.6).
    directionality=Directionality.CONTEXT_DEPENDENT,
    applicability=FeatureApplicability.UNIVERSAL,
    required_inputs=("financial_facts.current.per",),
)

_PBR_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="valuation.asset_based.pbr",
    component=Component.VALUATION,
    feature_family="asset_based",
    scope_status=FeatureScopeStatus.V1_REQUIRED,
    verification_requirements=(),
    # §41.5 REMAIN_UNRESOLVED (sole-representative rule): asset_based
    # family의 유일한 등록 feature다 -- Debt Ratio/Asset Turnover와 동일한
    # 이유로 family-level policy 결정 전까지 None 유지.
    default_requirement_role=None,
    # PER와 동일한 이유(극단적 저PBR = 자산 부실/청산가치 우려 신호
    # 가능성, §39.9) -- CONTEXT_DEPENDENT. directionality는 이번 audit
    # 대상이 아니며 재확인 결과 변경 없음(§40.6).
    directionality=Directionality.CONTEXT_DEPENDENT,
    applicability=FeatureApplicability.UNIVERSAL,
    required_inputs=("financial_facts.current.pbr",),
)

_EARNINGS_YIELD_DEFINITION: Final[FeatureDefinition] = FeatureDefinition(
    feature_id="valuation.earnings_based.earnings_yield",
    component=Component.VALUATION,
    feature_family="earnings_based",
    scope_status=FeatureScopeStatus.V1_OPTIONAL,
    verification_requirements=(),
    # §41.5 CONFIRMED_OPTIONAL (family-policy-deferred rule): PER와 동일 --
    # earnings_based family에 복수 candidate 존재.
    default_requirement_role=RequirementRole.OPTIONAL,
    # yield framing은 관례상 monotonic하게 다뤄진다(PER의 raw multiple
    # framing과 달리) -- HIGHER_IS_BETTER로 유지하되, 동일한 극단값
    # distress 신호 가능성은 PER만큼 크지 않다고 판단한다(§39.9).
    directionality=Directionality.HIGHER_IS_BETTER,
    applicability=FeatureApplicability.UNIVERSAL,
    # 1/PER로 파생되는 값이라 raw ingredient는 PER와 동일하다 -- 새 raw
    # data가 필요하지 않다.
    required_inputs=("financial_facts.current.per",),
)

_ALL_DEFINITIONS: Final[tuple[FeatureDefinition, ...]] = (
    _ROE_DEFINITION,
    _OPERATING_MARGIN_DEFINITION,
    _NET_MARGIN_DEFINITION,
    _REVENUE_GROWTH_DEFINITION,
    _OPERATING_PROFIT_GROWTH_DEFINITION,
    _NET_INCOME_GROWTH_DEFINITION,
    _DEBT_RATIO_DEFINITION,
    _ROA_DEFINITION,
    _ASSET_TURNOVER_DEFINITION,
    _ROIC_DEFINITION,
    _EPS_GROWTH_DEFINITION,
    _TRAILING_PER_DEFINITION,
    _PBR_DEFINITION,
    _EARNINGS_YIELD_DEFINITION,
)

if len({d.feature_id for d in _ALL_DEFINITIONS}) != len(_ALL_DEFINITIONS):
    # §37.12 multi-feature audit: feature_id 중복을 dict comprehension이
    # 조용히 덮어쓰지 않도록 module import 시점에 fail-fast한다.
    raise ValueError("Duplicate feature_id detected in feature registry")

_DEFINITIONS: Final[MappingProxyType[str, FeatureDefinition]] = MappingProxyType(
    {definition.feature_id: definition for definition in _ALL_DEFINITIONS}
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


def is_implemented(definition: FeatureDefinition) -> bool:
    """§38.12: 별도 `implementation_status` enum을 추가하지 않고
    `evaluator_id is None`을 그대로 판단 기준으로 쓴다 -- 이 함수는 그
    판단을 한 곳에 모아두는 얇은 편의 함수일 뿐, 새로운 상태나 semantics를
    추가하지 않는다."""
    return definition.evaluator_id is not None

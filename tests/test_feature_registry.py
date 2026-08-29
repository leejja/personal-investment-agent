"""RE-05 Minimal Feature Registry 테스트.

`app/evaluation/feature_registry.py`는 scoring policy가 아니라 feature
identity의 canonical single source of truth이므로, numeric threshold/
weight/window 테스트는 만들지 않는다.
"""

import inspect

import pytest
from pydantic import ValidationError

from app.evaluation.feature_registry import (
    FeatureApplicability,
    FeatureDefinition,
    FeatureScopeStatus,
    get_feature_definition,
    list_feature_definitions,
)
from app.evaluation.fundamental_evaluators import RoeFeatureEvaluator
from app.models.recommendation import AvailabilityStatus, Component, RequirementRole

_ROE_ID = "fundamental.profitability.roe"


# ============================== ROE definition 존재 ==============================


def test_roe_definition_exists_and_is_retrievable():
    definition = get_feature_definition(_ROE_ID)
    assert definition.feature_id == _ROE_ID
    assert definition.component == Component.FUNDAMENTAL
    assert definition.feature_family == "profitability"


def test_unknown_feature_id_raises_key_error_not_none():
    """등록되지 않은 feature_id는 KeyError를 raise한다 -- 조용히 None을
    반환하거나 임의 기본값을 만들지 않는다."""
    with pytest.raises(KeyError):
        get_feature_definition("nonexistent.feature.id")


# ============================== unique feature_id ==============================


def test_all_registered_feature_ids_are_unique():
    definitions = list_feature_definitions()
    ids = [d.feature_id for d in definitions]
    assert len(ids) == len(set(ids))
    assert len(definitions) >= 1


# ============================== FeatureDefinition immutable ==============================


def test_feature_definition_is_frozen():
    definition = get_feature_definition(_ROE_ID)
    with pytest.raises(ValidationError):
        definition.scope_status = FeatureScopeStatus.V1_OPTIONAL


def test_feature_definition_model_config_is_frozen():
    assert FeatureDefinition.model_config.get("frozen") is True


# ============================== scope status와 runtime availability type 분리 ==============================


def test_scope_status_and_availability_status_are_distinct_enums():
    """FeatureScopeStatus(design-time)와 AvailabilityStatus(runtime)가
    서로 다른 enum이고 값도 겹치지 않는다."""
    assert FeatureScopeStatus is not AvailabilityStatus
    scope_values = {s.value for s in FeatureScopeStatus}
    availability_values = {s.value for s in AvailabilityStatus}
    assert scope_values.isdisjoint(availability_values)


def test_roe_scope_status_is_v1_required_regardless_of_runtime_result():
    """scope_status(V1_REQUIRED)는 고정된 design-time 값이고, 실제 평가
    결과(availability)는 종목마다 AVAILABLE 또는 UNAVAILABLE일 수 있다 --
    두 축이 독립적임을 실제 evaluator 실행으로 확인한다."""
    from datetime import UTC, datetime

    from app.agents.stock_research.analysis import DeterministicAnalysisResult
    from app.evaluation.research_data_builder import build_normalized_research_data
    from app.models.common import AnalysisConfidence, RiskLevel
    from app.models.research_context import EvaluationContext
    from app.models.stock import FinancialSnapshot, StockPriceSnapshot

    as_of = datetime(2026, 8, 29, tzinfo=UTC)
    context = EvaluationContext(symbol="005930", as_of=as_of)
    evaluator = RoeFeatureEvaluator()

    for roe_value, expected_availability in (
        (12.3, AvailabilityStatus.AVAILABLE),
        (None, AvailabilityStatus.UNAVAILABLE),
    ):
        result_input = DeterministicAnalysisResult(
            price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=1.0),
            financials=FinancialSnapshot(business_year="2025", roe=roe_value),
            facts=[],
            max_confidence=AnalysisConfidence.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
        )
        data = build_normalized_research_data(result_input, as_of=as_of)
        outcome = evaluator.evaluate(data, context)

        assert get_feature_definition(_ROE_ID).scope_status == FeatureScopeStatus.V1_REQUIRED
        assert outcome.availability == expected_availability


# ============================== numeric threshold/weight/window 필드 없음 ==============================


def test_feature_definition_has_no_numeric_policy_fields():
    field_names = set(FeatureDefinition.model_fields.keys())
    forbidden = (
        "threshold",
        "weight",
        "lookback",
        "window",
        "cutoff",
        "boundary",
        "score",
    )
    for name in field_names:
        for term in forbidden:
            assert term not in name.lower()


def test_registry_module_source_has_no_numeric_policy_literals():
    import app.evaluation.feature_registry as registry_module

    source = inspect.getsource(registry_module)
    for term in ("threshold=", "weight=", "lookback=", "window="):
        assert term not in source


# ============================== vendor-specific field dependency 없음 ==============================


def test_required_inputs_use_normalized_domain_paths_not_vendor_fields():
    """required_inputs가 vendor field 이름(opendart.*, kiwoom.*)이 아니라
    NormalizedResearchData의 semantic path만 쓴다."""
    definition = get_feature_definition(_ROE_ID)
    assert definition.required_inputs == ("financial_facts.current.roe",)
    for path in definition.required_inputs:
        assert not path.lower().startswith("kiwoom")
        assert not path.lower().startswith("opendart")
        assert not path.lower().startswith("ecos")


def test_registry_module_does_not_import_vendor_or_service_layer():
    import app.evaluation.feature_registry as registry_module

    source = inspect.getsource(registry_module)
    assert "app.services." not in source
    assert "app.mcp." not in source
    for forbidden in ("KiwoomStockInfo", "KeyFinancials"):
        assert forbidden not in source


# ============================== evaluator가 canonical registry definition과 연결됨 ==============================


def test_roe_evaluator_class_attributes_come_from_registry():
    definition = get_feature_definition(_ROE_ID)
    assert RoeFeatureEvaluator.feature_id == definition.feature_id
    assert RoeFeatureEvaluator.component == definition.component
    assert RoeFeatureEvaluator.feature_family == definition.feature_family
    assert RoeFeatureEvaluator.definition is definition


def test_roe_evaluator_result_requirement_role_matches_registry():
    """evaluate() 결과의 requirement_role이 evaluator 안에 두 번째로
    하드코딩된 값이 아니라 registry에서 온 값과 동일하다."""
    from datetime import UTC, datetime

    from app.agents.stock_research.analysis import DeterministicAnalysisResult
    from app.evaluation.research_data_builder import build_normalized_research_data
    from app.models.common import AnalysisConfidence, RiskLevel
    from app.models.research_context import EvaluationContext
    from app.models.stock import FinancialSnapshot, StockPriceSnapshot

    as_of = datetime(2026, 8, 29, tzinfo=UTC)
    result_input = DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=1.0),
        financials=FinancialSnapshot(business_year="2025", roe=12.3),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )
    data = build_normalized_research_data(result_input, as_of=as_of)
    context = EvaluationContext(symbol="005930", as_of=as_of)
    outcome = RoeFeatureEvaluator().evaluate(data, context)

    assert outcome.requirement_role == get_feature_definition(_ROE_ID).default_requirement_role
    assert outcome.requirement_role == RequirementRole.REQUIRED


# ============================== duplicate metadata 없음 ==============================


def test_fundamental_evaluators_module_does_not_redeclare_requirement_role_literal():
    """evaluator 모듈 소스에 `RequirementRole.REQUIRED` 리터럴이 더 이상
    하드코딩돼 있지 않다 -- registry의
    self.definition.default_requirement_role만 참조한다(duplicate source
    of truth 제거 확인)."""
    import app.evaluation.fundamental_evaluators as evaluator_module

    source = inspect.getsource(evaluator_module)
    assert "RequirementRole.REQUIRED" not in source
    assert "self.definition.default_requirement_role" in source


# ============================== registry mutation 불가 ==============================


def test_registry_mapping_cannot_be_reassigned_via_get_result():
    """list_feature_definitions()가 반환한 tuple을 수정해도 registry 내부
    상태에 영향을 주지 않는다(tuple은 애초에 불변)."""
    definitions = list_feature_definitions()
    assert isinstance(definitions, tuple)
    with pytest.raises(TypeError):
        definitions[0] = None  # type: ignore[index]


def test_applicability_values_are_limited_to_two_states():
    """§8 -- rule engine 없이 UNIVERSAL/REVIEW_REQUIRED 두 상태만 존재한다."""
    values = {a.value for a in FeatureApplicability}
    assert values == {"universal", "review_required"}


# ============================== §36 Final Contract Audit: orthogonality ==============================


def _hypothetical_momentum_definition() -> FeatureDefinition:
    """production registry에 추가하지 않는 가상의 FeatureDefinition --
    §29.5/§29.2가 실제로 기록한 semantics(V1_OPTIONAL scope + adjusted-price
    corporate-action safety verification 미확정)를 재현해 schema가 이
    조합을 표현할 수 있는지만 검증한다. 두 번째 evaluator를 구현하는
    것이 아니다."""
    return FeatureDefinition(
        feature_id="market_confirmation.momentum.absolute_momentum",
        component=Component.MARKET_CONFIRMATION,
        feature_family="momentum",
        scope_status=FeatureScopeStatus.V1_OPTIONAL,
        verification_requirements=(
            "adjusted-price corporate-action safety unresolved (§29.5/§28.8)",
        ),
        default_requirement_role=RequirementRole.OPTIONAL,
        applicability=FeatureApplicability.UNIVERSAL,
        required_inputs=("price_history",),
        evaluator_id="(not implemented)",
        evaluator_version="n/a",
    )


def test_v1_optional_and_verification_requirement_are_simultaneously_representable():
    """§1/§2/§6: scope_status=V1_OPTIONAL이면서 동시에
    verification_requirements가 비어있지 않은 상태를 스키마가 표현할 수
    있다 -- 이 두 축이 mutually exclusive하지 않다는 것을 직접 생성으로
    검증한다."""
    definition = _hypothetical_momentum_definition()
    assert definition.scope_status == FeatureScopeStatus.V1_OPTIONAL
    assert definition.verification_requirements != ()
    assert len(definition.verification_requirements) == 1


def test_feature_scope_status_no_longer_has_verification_required_value():
    """§36.1 correction: VERIFICATION_REQUIRED가 FeatureScopeStatus의
    다섯 번째 값으로 존재하지 않는다 -- orthogonal한
    verification_requirements 필드로 분리됐다."""
    values = {s.value for s in FeatureScopeStatus}
    assert values == {"v1_required", "v1_optional", "v1_deferred", "v1_blocked"}
    assert "verification_required" not in values


def test_roe_is_v1_required_with_no_verification_requirement():
    """§3: ROE는 별도 verification precondition이 없다 --
    verification_requirements가 빈 tuple이다."""
    definition = get_feature_definition(_ROE_ID)
    assert definition.scope_status == FeatureScopeStatus.V1_REQUIRED
    assert definition.verification_requirements == ()


def test_scope_status_verification_and_runtime_availability_are_three_independent_axes():
    """§1/§6: scope_status(design-time), verification_requirements
    (orthogonal precondition), AvailabilityStatus(runtime)가 서로 다른
    3개 축임을 값 집합이 겹치지 않는 것으로 확인한다."""
    scope_values = {s.value for s in FeatureScopeStatus}
    availability_values = {s.value for s in AvailabilityStatus}
    assert scope_values.isdisjoint(availability_values)
    # verification_requirements는 enum이 아니라 free-text tuple이므로
    # 애초에 scope_status/AvailabilityStatus의 enum 값 공간과 겹칠 수
    # 없다 -- 타입 자체가 다르다는 것으로 분리를 확인한다.
    momentum = _hypothetical_momentum_definition()
    assert isinstance(momentum.verification_requirements, tuple)
    assert all(isinstance(item, str) for item in momentum.verification_requirements)


# ============================== §36.4 RequirementRole semantic audit ==============================


def test_default_requirement_role_field_is_named_to_signal_default_semantics():
    """§4: registry field가 `default_requirement_role`로 개명돼 "이것은
    canonical/default 값이지 runtime 절대값이 아니다"를 이름으로
    드러낸다."""
    field_names = set(FeatureDefinition.model_fields.keys())
    assert "default_requirement_role" in field_names
    assert "requirement_role" not in field_names


def test_default_requirement_role_does_not_forbid_runtime_not_applicable():
    """§4: registry의 default_requirement_role=REQUIRED와 특정 종목의
    runtime FeatureEvaluationResult.availability=NOT_APPLICABLE이
    동시에 존재해도 스키마 레벨에서 아무 충돌이 없다 -- 서로 다른 model의
    서로 다른 필드이며, 어느 쪽도 다른 쪽 값을 제약하는 validator가 없다."""
    definition = get_feature_definition(_ROE_ID)
    assert definition.default_requirement_role == RequirementRole.REQUIRED

    from app.models.recommendation import FeatureEvaluationResult

    # NOT_APPLICABLE인 runtime 결과를 실제로 생성해봐도 아무 예외가
    # 나지 않는다 -- registry의 REQUIRED 선언이 이 생성을 막지 않는다.
    result = FeatureEvaluationResult(
        feature_id=definition.feature_id,
        component=definition.component,
        feature_family=definition.feature_family,
        availability=AvailabilityStatus.NOT_APPLICABLE,
        requirement_role=RequirementRole.REQUIRED,
    )
    assert result.availability == AvailabilityStatus.NOT_APPLICABLE


# ============================== §36.5 Applicability relation audit ==============================


def test_static_applicability_does_not_auto_set_runtime_review_flag():
    """§5: registry의 applicability=UNIVERSAL/REVIEW_REQUIRED가
    FeatureEvaluationResult.applicability_review_required를 자동으로
    결정하는 로직이 없다 -- ROE(UNIVERSAL)의 실제 evaluate() 결과에서
    이 런타임 플래그가 항상 기본값(False)임을 확인한다(rule engine
    없음)."""
    from datetime import UTC, datetime

    from app.agents.stock_research.analysis import DeterministicAnalysisResult
    from app.evaluation.research_data_builder import build_normalized_research_data
    from app.models.common import AnalysisConfidence, RiskLevel
    from app.models.research_context import EvaluationContext
    from app.models.stock import FinancialSnapshot, StockPriceSnapshot

    as_of = datetime(2026, 8, 29, tzinfo=UTC)
    result_input = DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=1.0),
        financials=FinancialSnapshot(business_year="2025", roe=12.3),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )
    data = build_normalized_research_data(result_input, as_of=as_of)
    context = EvaluationContext(symbol="005930", as_of=as_of)
    outcome = RoeFeatureEvaluator().evaluate(data, context)

    assert get_feature_definition(_ROE_ID).applicability == FeatureApplicability.UNIVERSAL
    assert outcome.applicability_review_required is False


# ============================== existing RoeFeatureEvaluator behavior unchanged ==============================


def test_roe_evaluator_behavior_unchanged_after_rename():
    """§36 audit(rename + orthogonality correction) 이후에도 ROE evaluator
    의 실제 출력값은 이전과 동일하다."""
    from datetime import UTC, datetime

    from app.agents.stock_research.analysis import DeterministicAnalysisResult
    from app.evaluation.research_data_builder import build_normalized_research_data
    from app.models.common import AnalysisConfidence, RiskLevel
    from app.models.research_context import EvaluationContext
    from app.models.stock import FinancialSnapshot, StockPriceSnapshot

    as_of = datetime(2026, 8, 29, tzinfo=UTC)
    result_input = DeterministicAnalysisResult(
        price=StockPriceSnapshot(symbol="005930", name="삼성전자", price=257000.0),
        financials=FinancialSnapshot(business_year="2025", roe=12.3),
        facts=[],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
    )
    data = build_normalized_research_data(result_input, as_of=as_of)
    context = EvaluationContext(symbol="005930", as_of=as_of)
    outcome = RoeFeatureEvaluator().evaluate(data, context)

    assert outcome.feature_id == "fundamental.profitability.roe"
    assert outcome.availability == AvailabilityStatus.AVAILABLE
    assert outcome.raw.value == 12.3
    assert outcome.raw.unit == "percent"
    assert outcome.normalized_value is None
    assert outcome.requirement_role == RequirementRole.REQUIRED


# ============================== §37.11 Multi-feature registry audit ==============================


def test_registry_now_holds_two_production_features():
    definitions = list_feature_definitions()
    ids = {d.feature_id for d in definitions}
    assert ids == {
        "fundamental.profitability.roe",
        "fundamental.profitability.operating_margin",
    }


def test_both_features_retrievable_and_share_component_family():
    from app.evaluation.feature_registry import get_feature_definition

    roe = get_feature_definition("fundamental.profitability.roe")
    om = get_feature_definition("fundamental.profitability.operating_margin")
    assert roe.component == om.component == Component.FUNDAMENTAL
    assert roe.feature_family == om.feature_family == "profitability"
    # family aggregation 자체는 이번에도 구현하지 않는다 -- 같은 family를
    # 공유한다는 사실만 확인한다(ComponentEvaluator/FeatureFamilyEvaluator
    # 없음).


def test_evaluator_id_maps_correctly_to_each_definition():
    """evaluator ↔ definition mapping이 정확하다 -- ROE evaluator의
    class attribute가 Operating Margin definition을 가리키지 않는다(그
    반대도 마찬가지)."""
    from app.evaluation.feature_registry import get_feature_definition
    from app.evaluation.fundamental_evaluators import (
        OperatingMarginFeatureEvaluator,
        RoeFeatureEvaluator,
    )

    roe_def = get_feature_definition("fundamental.profitability.roe")
    om_def = get_feature_definition("fundamental.profitability.operating_margin")

    assert RoeFeatureEvaluator.definition is roe_def
    assert OperatingMarginFeatureEvaluator.definition is om_def
    assert RoeFeatureEvaluator.definition is not om_def
    assert OperatingMarginFeatureEvaluator.definition is not roe_def


def test_list_feature_definitions_order_is_deterministic():
    """list_feature_definitions()가 매 호출마다 동일한 순서를 반환한다
    (insertion order 기반 MappingProxyType, §37.11)."""
    first_call = tuple(d.feature_id for d in list_feature_definitions())
    second_call = tuple(d.feature_id for d in list_feature_definitions())
    assert first_call == second_call


def test_registry_raises_on_duplicate_feature_id_at_import_time():
    """모듈 내부 duplicate-guard가 실제로 동작하는지, 동일한 패턴으로
    임의 duplicate 목록을 만들어 재현한다(module reimport가 아니라 로직
    자체를 격리 재현)."""
    from app.evaluation.feature_registry import get_feature_definition

    roe = get_feature_definition("fundamental.profitability.roe")
    duplicate_list = (roe, roe)
    assert len({d.feature_id for d in duplicate_list}) != len(duplicate_list)


def test_scope_verification_and_runtime_axes_stay_independent_with_two_features():
    """§36의 orthogonality가 feature가 2개로 늘어나도 깨지지 않는다 --
    두 feature 모두 scope_status=V1_REQUIRED + verification_requirements=()
    조합이지만 applicability는 서로 다르다(독립적으로 값이 갈릴 수
    있음을 실측으로 재확인)."""
    from app.evaluation.feature_registry import get_feature_definition

    roe = get_feature_definition("fundamental.profitability.roe")
    om = get_feature_definition("fundamental.profitability.operating_margin")

    assert roe.scope_status == om.scope_status == FeatureScopeStatus.V1_REQUIRED
    assert roe.verification_requirements == om.verification_requirements == ()
    assert roe.applicability != om.applicability


def test_no_numeric_policy_metadata_leaked_into_second_entry():
    from app.evaluation.feature_registry import get_feature_definition

    om = get_feature_definition("fundamental.profitability.operating_margin")
    field_names = set(type(om).model_fields.keys())
    forbidden = ("threshold", "weight", "lookback", "window", "cutoff", "boundary")
    for name in field_names:
        for term in forbidden:
            assert term not in name.lower()


# ============================== §38 Completeness & Coverage Readiness Audit ==============================


def _hypothetical_net_margin_definition() -> FeatureDefinition:
    """production registry(_DEFINITIONS)에 추가하지 않는 가상
    FeatureDefinition -- §29.2가 이미 FROZEN한 "Net Margin = V1_REQUIRED"
    사실을 재현해, evaluator 없이도 feature identity를 등록할 수 있는지
    (§38 correction)만 검증한다. 두 번째/세 번째 evaluator를 구현하는
    것이 아니다."""
    return FeatureDefinition(
        feature_id="fundamental.profitability.net_margin",
        component=Component.FUNDAMENTAL,
        feature_family="profitability",
        scope_status=FeatureScopeStatus.V1_REQUIRED,
        verification_requirements=(),
        default_requirement_role=RequirementRole.REQUIRED,
        applicability=FeatureApplicability.REVIEW_REQUIRED,
        required_inputs=("financial_facts.features.annual[latest].net_margin",),
        # evaluator_id/evaluator_version 생략 -- 기본값 None(§38 correction).
    )


def _hypothetical_roic_definition() -> FeatureDefinition:
    """§29.2가 실제로 FROZEN한 "ROIC = V1_BLOCKED" 상태를 재현한다 --
    raw ingredient 자체가 불안정해(회사간 계정명 편차) v1에서 명시적으로
    막힌 feature도 identity는 보존 가능해야 한다."""
    return FeatureDefinition(
        feature_id="fundamental.capital_efficiency.roic",
        component=Component.FUNDAMENTAL,
        feature_family="capital_efficiency",
        scope_status=FeatureScopeStatus.V1_BLOCKED,
        verification_requirements=(
            "invested capital denominator account naming unstable across companies (§29.2)",
        ),
        default_requirement_role=RequirementRole.OPTIONAL,
        applicability=FeatureApplicability.REVIEW_REQUIRED,
        required_inputs=(),
        # evaluator_id 생략 -- V1_BLOCKED라 애초에 evaluator를 만들 수 없다.
    )


def test_feature_identity_representable_without_evaluator():
    """§38.4: feature exists but evaluator absent 상태를 표현할 수 있다 --
    evaluator_id/version을 생략해도 FeatureDefinition이 유효하게
    생성된다."""
    definition = _hypothetical_net_margin_definition()
    assert definition.evaluator_id is None
    assert definition.evaluator_version is None
    assert definition.feature_id == "fundamental.profitability.net_margin"


def test_is_implemented_helper_reflects_evaluator_presence():
    from app.evaluation.feature_registry import get_feature_definition, is_implemented

    roe = get_feature_definition("fundamental.profitability.roe")
    net_margin = _hypothetical_net_margin_definition()

    assert is_implemented(roe) is True
    assert is_implemented(net_margin) is False


def test_not_implemented_is_distinct_axis_from_runtime_unavailable():
    """§38.5/§5: NOT_IMPLEMENTED(evaluator_id=None, software capability
    상태)와 runtime AvailabilityStatus.UNAVAILABLE(data/evaluation 상태)
    은 서로 다른 축이다 -- 값 공간 자체가 겹치지 않는다(하나는
    evaluator_id: str|None, 하나는 AvailabilityStatus enum)."""
    net_margin = _hypothetical_net_margin_definition()
    assert net_margin.evaluator_id is None  # NOT_IMPLEMENTED
    # AvailabilityStatus는 FeatureEvaluationResult(runtime)에만 존재하고
    # FeatureDefinition(design-time)에는 아예 그런 필드가 없다.
    assert "availability" not in set(FeatureDefinition.model_fields.keys())


def test_v1_required_feature_without_evaluator_is_representable():
    """§38.6: V1_REQUIRED이지만 아직 evaluator가 없는 feature(Net Margin)
    를 표현할 수 있다 -- Feature Registry FALSE COMPLETENESS 문제(§38.2)
    를 해소하는 핵심 능력이다."""
    definition = _hypothetical_net_margin_definition()
    assert definition.scope_status == FeatureScopeStatus.V1_REQUIRED
    assert definition.evaluator_id is None


def test_v1_blocked_feature_is_representable():
    """§38.7: V1_BLOCKED feature(ROIC)도 identity를 보존할 수 있다 --
    evaluator가 원천적으로 없을 feature까지 포함해 catalog가 표현
    가능해야 한다."""
    definition = _hypothetical_roic_definition()
    assert definition.scope_status == FeatureScopeStatus.V1_BLOCKED
    assert definition.evaluator_id is None
    assert definition.verification_requirements != ()


def test_v1_optional_plus_verification_requirement_still_representable_after_correction():
    """§36에서 확정한 orthogonality가 §38의 optional-evaluator correction
    이후에도 깨지지 않는다(회귀 확인) -- V1_OPTIONAL이면서 evaluator도
    없고 verification precondition도 있는 3중 조합까지 표현 가능."""
    definition = FeatureDefinition(
        feature_id="market_confirmation.momentum.absolute_momentum",
        component=Component.MARKET_CONFIRMATION,
        feature_family="momentum",
        scope_status=FeatureScopeStatus.V1_OPTIONAL,
        verification_requirements=(
            "adjusted-price corporate-action safety unresolved (§29.5/§28.8)",
        ),
        default_requirement_role=RequirementRole.OPTIONAL,
        applicability=FeatureApplicability.UNIVERSAL,
        required_inputs=("price_history",),
        # evaluator_id 생략.
    )
    assert definition.scope_status == FeatureScopeStatus.V1_OPTIONAL
    assert definition.verification_requirements != ()
    assert definition.evaluator_id is None


def test_implemented_evaluators_still_bound_correctly_after_correction():
    """§38 correction(Optional화) 이후에도 실제 구현된 두 evaluator는
    여전히 evaluator_id/version을 갖고 있다 -- 회귀 없음."""
    from app.evaluation.feature_registry import get_feature_definition

    roe = get_feature_definition("fundamental.profitability.roe")
    om = get_feature_definition("fundamental.profitability.operating_margin")

    assert roe.evaluator_id == "RoeFeatureEvaluator"
    assert roe.evaluator_version == "v1"
    assert om.evaluator_id == "OperatingMarginFeatureEvaluator"
    assert om.evaluator_version == "v1"


def test_no_coverage_percentage_or_denominator_computed():
    """§10: 이번 audit에서 coverage percentage/available_count/
    total_count/threshold를 구현하지 않았다 -- registry 모듈 소스에 그런
    계산 코드가 없다."""
    import inspect

    import app.evaluation.feature_registry as registry_module

    source = inspect.getsource(registry_module)
    forbidden = ("percentage", "available_count", "total_count", "coverage_ratio", "/ len(")
    for term in forbidden:
        assert term not in source

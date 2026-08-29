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

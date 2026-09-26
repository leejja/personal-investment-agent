"""Test-only evidence fixtures for hand-built `DeterministicAnalysisResult`s.

Evaluation-pipeline tests construct `DeterministicAnalysisResult` directly with fixture
values instead of going through provider services. The evaluation pipeline now requires
evidence identity for every evaluator-consumed value, so this helper attaches fixture
evidence that is consistent with the result's values: Kiwoom-shaped SOURCE_REPORTED
references for ROE / PER / PBR, and DERIVED references (built with the same derivation
helper `analyze()` uses) over OpenDART-shaped source inputs for the three derived values.

This fabricates identity for test fixtures only; production evidence comes from
`OpenDartTools.get_key_financials_history_with_evidence` /
`KiwoomTools.get_stock_info_with_evidence`.
"""

from datetime import UTC, datetime

from app.agents.stock_research.analysis import (
    DeterministicAnalysisResult,
    _derived_reference,
)
from app.models.evidence import (
    MEASURE_DEBT_RATIO,
    MEASURE_NET_INCOME,
    MEASURE_NET_MARGIN,
    MEASURE_OPERATING_MARGIN,
    MEASURE_OPERATING_PROFIT,
    MEASURE_PBR,
    MEASURE_PER,
    MEASURE_REVENUE,
    MEASURE_ROE,
    MEASURE_TOTAL_EQUITY,
    MEASURE_TOTAL_LIABILITIES,
    EvidenceItemIdentity,
    EvidenceOrigin,
    EvidenceReference,
    EvidenceSource,
    FinancialFactsEvidence,
    ObservationIdentity,
)

FIXTURE_RETRIEVED_AT = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
FIXTURE_RCEPT_NO = "20260310000001"


def kiwoom_reference(entity: str, measure: str) -> EvidenceReference:
    return EvidenceReference(
        identity=EvidenceItemIdentity(
            entity=entity,
            measure=measure,
            origin=EvidenceOrigin.SOURCE_REPORTED,
            source=EvidenceSource(provider="Kiwoom", interface="ka10001"),
        ),
        retrieved_at=FIXTURE_RETRIEVED_AT,
    )


def opendart_reference(entity: str, measure: str, period_label: str | None) -> EvidenceReference:
    return EvidenceReference(
        identity=EvidenceItemIdentity(
            entity=entity,
            measure=measure,
            origin=EvidenceOrigin.SOURCE_REPORTED,
            source=EvidenceSource(provider="OpenDART", interface="fnlttSinglAcnt"),
            observation=ObservationIdentity(
                period_label=period_label,
                source_term="current",
                report_type="11011",
                reporting_basis="CFS",
            ),
            version_anchor=FIXTURE_RCEPT_NO,
        ),
        retrieved_at=FIXTURE_RETRIEVED_AT,
    )


def fixture_evidence_for(result: DeterministicAnalysisResult) -> FinancialFactsEvidence:
    entity = result.price.symbol
    annual = result.financial_features.annual
    latest = annual[-1] if annual else None
    period_label = latest.business_year if latest is not None else None

    inputs = {
        measure: opendart_reference(entity, measure, period_label)
        for measure in (
            MEASURE_REVENUE,
            MEASURE_OPERATING_PROFIT,
            MEASURE_NET_INCOME,
            MEASURE_TOTAL_LIABILITIES,
            MEASURE_TOTAL_EQUITY,
        )
    }

    def source(value: float | None, measure: str) -> EvidenceReference | None:
        return kiwoom_reference(entity, measure) if value is not None else None

    def derived(value: float | None, measure: str) -> EvidenceReference | None:
        return _derived_reference(value, measure, entity, inputs)

    return FinancialFactsEvidence(
        roe=source(result.financials.roe, MEASURE_ROE),
        per=source(result.financials.per, MEASURE_PER),
        pbr=source(result.financials.pbr, MEASURE_PBR),
        operating_margin=derived(
            latest.operating_margin if latest is not None else None, MEASURE_OPERATING_MARGIN
        ),
        net_margin=derived(latest.net_margin if latest is not None else None, MEASURE_NET_MARGIN),
        debt_ratio=derived(latest.debt_ratio if latest is not None else None, MEASURE_DEBT_RATIO),
    )


def attach_fixture_evidence(result: DeterministicAnalysisResult) -> DeterministicAnalysisResult:
    return result.model_copy(update={"evidence": fixture_evidence_for(result)})

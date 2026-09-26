"""Evidence Identity Preservation (RE-05, §7.10 identity-only slice) invariants.

No external API calls: provider services are replaced by in-process fakes that return the
same internal carriers the real services produce.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.agents.stock_research.analysis import (
    AnalysisEvidenceInput,
    DeterministicAnalysisResult,
    analyze,
)
from app.evaluation.decision_eligibility import evaluate_decision_eligibility
from app.evaluation.orchestrator import run_first_deterministic_pipeline
from app.evaluation.research_data_builder import build_normalized_research_data
from app.mcp.kiwoom_tools import KiwoomTools
from app.mcp.opendart_tools import CompanyFinancials, KeyFinancials, OpenDartTools
from app.models.evidence import (
    DerivationLineage,
    EvidenceItemIdentity,
    EvidenceOrigin,
    EvidenceReference,
    EvidenceSource,
    FinancialFactsEvidence,
)
from app.models.recommendation import AvailabilityStatus
from app.models.research_context import EvaluationContext, FinancialFacts
from app.models.stock import (
    AnnualFinancialFeatures,
    FinancialFeatures,
    FinancialSnapshot,
    StockAnalysis,
)
from app.services.kiwoom import KiwoomStockInfo, KiwoomStockInfoRetrieval
from app.services.opendart import (
    OpenDartFinancialAccount,
    OpenDartFinancialAccountsRetrieval,
)

_RCEPT_NO = "20250311001085"
_OPENDART_RETRIEVED_AT = datetime(2026, 9, 27, 1, 0, tzinfo=UTC)
_KIWOOM_RETRIEVED_AT = datetime(2026, 9, 27, 1, 0, 5, tzinfo=UTC)
_AS_OF = datetime(2026, 9, 27, tzinfo=UTC)


def _account(name: str, sj_div: str, current: int, previous: int) -> OpenDartFinancialAccount:
    return OpenDartFinancialAccount(
        rcept_no=_RCEPT_NO,
        bsns_year="2024",
        stock_code="005930",
        reprt_code="11011",
        account_name=name,
        fs_div="CFS",
        fs_name="연결재무제표",
        statement_div=sj_div,
        statement_name="",
        current_term_name="제 56 기",
        current_term_date="2024.01.01 ~ 2024.12.31",
        current_term_amount=current,
        previous_term_name="제 55 기",
        previous_term_date="2023.01.01 ~ 2023.12.31",
        previous_term_amount=previous,
        currency="KRW",
    )


_ACCOUNTS = [
    _account("매출액", "IS", 3000, 2500),
    _account("영업이익", "IS", 300, 200),
    _account("당기순이익", "IS", 150, 100),
    _account("자산총계", "BS", 5000, 4500),
    _account("부채총계", "BS", 1000, 900),
    _account("자본총계", "BS", 4000, 3600),
]


class _FakeOpenDartService:
    async def resolve_corp_code(self, stock_code: str) -> str:
        return "00126380"

    async def fetch_financial_accounts(self, **_: str) -> OpenDartFinancialAccountsRetrieval:
        return OpenDartFinancialAccountsRetrieval(
            accounts=_ACCOUNTS, retrieved_at=_OPENDART_RETRIEVED_AT
        )


class _Token:
    token = "fake"


class _FakeKiwoomService:
    async def get_access_token(self) -> _Token:
        return _Token()

    async def fetch_stock_info(self, **_: str) -> KiwoomStockInfoRetrieval:
        return KiwoomStockInfoRetrieval(
            stock_info=KiwoomStockInfo(
                stock_code="005930",
                stock_name="삼성전자",
                current_price=60000,
                change=0,
                change_rate=0.0,
                trading_volume=1,
                per=12.5,
                pbr=1.1,
                roe=8.8,
                eps=None,
                bps=None,
                high_250d=None,
                low_250d=None,
            ),
            retrieved_at=_KIWOOM_RETRIEVED_AT,
        )


async def _evidence_path():
    history = await OpenDartTools(_FakeOpenDartService()).get_key_financials_history_with_evidence(
        stock_code="005930", business_year="2024"
    )
    stock = await KiwoomTools(_FakeKiwoomService()).get_stock_info_with_evidence("005930")
    result = analyze(
        stock.stock_info,
        history[0].key_financials,
        [entry.key_financials for entry in history],
        evidence=AnalysisEvidenceInput(
            stock_info=stock.evidence, latest_financials=history[0].evidence
        ),
    )
    return history, stock, result


def _source_reference(retrieved_at: datetime) -> EvidenceReference:
    return EvidenceReference(
        identity=EvidenceItemIdentity(
            entity="005930",
            measure="revenue",
            origin=EvidenceOrigin.SOURCE_REPORTED,
            source=EvidenceSource(provider="OpenDART", interface="fnlttSinglAcnt"),
            version_anchor=_RCEPT_NO,
        ),
        retrieved_at=retrieved_at,
    )


# ============================== R1: semantic identity != retrieval ==============================


def test_semantic_identity_is_independent_of_retrieved_at():
    monday = _source_reference(_OPENDART_RETRIEVED_AT)
    tuesday = _source_reference(_OPENDART_RETRIEVED_AT + timedelta(days=1))

    assert monday.identity == tuesday.identity
    assert hash(monday.identity) == hash(tuesday.identity)
    assert monday.retrieved_at != tuesday.retrieved_at
    assert monday != tuesday


def test_derived_semantic_identity_excludes_input_retrieval_times():
    def derived(input_ref: EvidenceReference) -> EvidenceReference:
        return EvidenceReference(
            identity=EvidenceItemIdentity(
                entity="005930",
                measure="operating_margin",
                origin=EvidenceOrigin.DERIVED,
                derivation=DerivationLineage(
                    formula_id="operating_margin", formula_version="1", inputs=(input_ref.identity,)
                ),
            ),
            input_references=(input_ref,),
        )

    a = derived(_source_reference(_OPENDART_RETRIEVED_AT))
    b = derived(_source_reference(_OPENDART_RETRIEVED_AT + timedelta(hours=3)))
    assert a.identity == b.identity
    assert a.input_references[0].retrieved_at != b.input_references[0].retrieved_at


# ============================== OpenDART / comparative / Kiwoom ==============================


@pytest.mark.anyio
async def test_opendart_identity_is_preserved_from_matched_row():
    history, _, _ = await _evidence_path()
    revenue = history[0].evidence["revenue"]

    assert revenue.identity.origin == EvidenceOrigin.SOURCE_REPORTED
    assert revenue.identity.version_anchor == _RCEPT_NO
    assert revenue.identity.source == EvidenceSource(provider="OpenDART", interface="fnlttSinglAcnt")
    observation = revenue.identity.observation
    assert observation is not None
    assert observation.report_type == "11011"
    assert observation.reporting_basis == "CFS"
    assert observation.statement == "IS"
    assert observation.source_term == "current"
    assert observation.period_notation == "2024.01.01 ~ 2024.12.31"
    assert observation.period_label == "2024"
    assert revenue.retrieved_at == _OPENDART_RETRIEVED_AT
    assert history[0].evidence["total_liabilities"].identity.observation.statement == "BS"
    # one HTTP response -> one shared retrieval timestamp
    assert {ref.retrieved_at for ref in history[0].evidence.values()} == {_OPENDART_RETRIEVED_AT}


@pytest.mark.anyio
async def test_comparative_evidence_keeps_later_filing_anchor_and_source_term():
    history, _, _ = await _evidence_path()
    current = history[0].evidence["revenue"].identity
    comparative = history[1].evidence["revenue"].identity

    assert history[1].key_financials.business_year == "2023"  # existing label unchanged
    assert comparative.observation.source_term == "previous"
    assert comparative.observation.period_notation == "2023.01.01 ~ 2023.12.31"
    assert comparative.version_anchor == _RCEPT_NO  # later (FY2024) filing, not FY2023 original
    assert comparative != current


@pytest.mark.anyio
async def test_kiwoom_ratios_are_source_reported_without_invented_anchor_or_lineage():
    _, stock, _ = await _evidence_path()

    for measure in ("roe", "per", "pbr"):
        reference = stock.evidence[measure]
        assert reference.identity.origin == EvidenceOrigin.SOURCE_REPORTED
        assert reference.identity.derivation is None
        assert reference.identity.version_anchor is None
        assert reference.identity.source == EvidenceSource(provider="Kiwoom", interface="ka10001")
        assert reference.retrieved_at == _KIWOOM_RETRIEVED_AT


# ============================== derived lineage → provenance ==============================


@pytest.mark.anyio
async def test_derived_features_carry_formula_and_input_lineage_into_provenance():
    history, stock, result = await _evidence_path()
    state = run_first_deterministic_pipeline(
        result, EvaluationContext(symbol="005930", as_of=_AS_OF)
    )
    by_id = {r.feature_id: r for r in state.feature_results}
    source = history[0].evidence

    expected = {
        "fundamental.profitability.operating_margin": ("operating_margin", ("revenue", "operating_profit")),
        "fundamental.profitability.net_margin": ("net_margin", ("revenue", "net_income")),
        "fundamental.financial_resilience.debt_ratio": (
            "debt_ratio",
            ("total_liabilities", "total_equity"),
        ),
    }
    for feature_id, (formula_id, input_measures) in expected.items():
        result_ = by_id[feature_id]
        assert result_.raw is not None and result_.raw.is_derived is True
        assert len(result_.provenance.evidence) == 1
        reference = result_.provenance.evidence[0]
        assert reference.identity.origin == EvidenceOrigin.DERIVED
        assert reference.retrieved_at is None
        assert reference.identity.derivation.formula_id == formula_id
        assert reference.identity.derivation.formula_version == "1"
        assert reference.identity.derivation.inputs == tuple(
            source[m].identity for m in input_measures
        )
        assert reference.input_references == tuple(source[m] for m in input_measures)
        assert all(ref.identity.observation.source_term == "current" for ref in reference.input_references)

    for feature_id, measure in (
        ("fundamental.profitability.roe", "roe"),
        ("valuation.earnings_based.trailing_per", "per"),
        ("valuation.asset_based.pbr", "pbr"),
    ):
        result_ = by_id[feature_id]
        assert result_.raw is not None and result_.raw.is_derived is False
        assert result_.provenance.evidence == [stock.evidence[measure]]


@pytest.mark.anyio
async def test_evidence_does_not_change_values_or_downstream_decisions():
    _, _, result = await _evidence_path()
    context = EvaluationContext(symbol="005930", as_of=_AS_OF)
    with_evidence = run_first_deterministic_pipeline(result, context)

    def later_retrieval(ref: EvidenceReference | None) -> EvidenceReference | None:
        if ref is None or ref.retrieved_at is None:
            return ref
        return ref.model_copy(update={"retrieved_at": ref.retrieved_at + timedelta(days=1)})

    shifted_evidence = FinancialFactsEvidence(
        **{
            slot: later_retrieval(getattr(result.evidence, slot))
            for slot in FinancialFactsEvidence.model_fields
        }
    )
    assert shifted_evidence.per != result.evidence.per  # retrieval facts actually differ
    shifted = result.model_copy(update={"evidence": shifted_evidence})
    shifted_state = run_first_deterministic_pipeline(shifted, context)

    assert all(r.normalized_value is None for r in with_evidence.feature_results)
    assert [r.raw for r in with_evidence.feature_results] == [
        r.raw for r in shifted_state.feature_results
    ]
    assert with_evidence.coverage == shifted_state.coverage
    assert with_evidence.future_opportunity_evidence == shifted_state.future_opportunity_evidence
    assert evaluate_decision_eligibility(
        with_evidence.coverage, with_evidence.future_opportunity_evidence
    ) == evaluate_decision_eligibility(
        shifted_state.coverage, shifted_state.future_opportunity_evidence
    )


# ============================== fail-fast ==============================


@pytest.mark.anyio
async def test_builder_fails_fast_without_evidence():
    _, _, result = await _evidence_path()
    with pytest.raises(ValueError, match="evidence is required"):
        build_normalized_research_data(result.model_copy(update={"evidence": None}), as_of=_AS_OF)


def test_financial_facts_fails_fast_when_consumed_value_lacks_reference():
    with pytest.raises(ValidationError, match="'per' is missing"):
        FinancialFacts(
            status=AvailabilityStatus.AVAILABLE,
            current=FinancialSnapshot(per=10.0),
            evidence=FinancialFactsEvidence(),
        )
    with pytest.raises(ValidationError, match="'debt_ratio' is missing"):
        FinancialFacts(
            status=AvailabilityStatus.AVAILABLE,
            features=FinancialFeatures(
                annual=[AnnualFinancialFeatures(business_year="2024", debt_ratio=25.0)]
            ),
            evidence=FinancialFactsEvidence(),
        )


def test_missing_value_does_not_require_reference():
    facts = FinancialFacts(
        status=AvailabilityStatus.AVAILABLE,
        current=FinancialSnapshot(per=None),
        evidence=FinancialFactsEvidence(),
    )
    assert facts.evidence.per is None


@pytest.mark.anyio
async def test_analyze_fails_fast_when_derived_input_reference_was_lost():
    history, stock, _ = await _evidence_path()
    latest = dict(history[0].evidence)
    del latest["revenue"]
    with pytest.raises(ValueError, match="input evidence 'revenue'"):
        analyze(
            stock.stock_info,
            history[0].key_financials,
            [entry.key_financials for entry in history],
            evidence=AnalysisEvidenceInput(stock_info=stock.evidence, latest_financials=latest),
        )


def test_evidence_model_invariants_fail_fast():
    source_ref = _source_reference(_OPENDART_RETRIEVED_AT)
    with pytest.raises(ValidationError, match="timezone-aware"):
        _source_reference(datetime(2026, 9, 27))  # noqa: DTZ001 — intentionally naive
    with pytest.raises(ValidationError, match="requires a derivation"):
        EvidenceItemIdentity(entity="005930", measure="x", origin=EvidenceOrigin.DERIVED)
    derived_identity = EvidenceItemIdentity(
        entity="005930",
        measure="operating_margin",
        origin=EvidenceOrigin.DERIVED,
        derivation=DerivationLineage(
            formula_id="operating_margin", formula_version="1", inputs=(source_ref.identity,)
        ),
    )
    with pytest.raises(ValidationError, match="requires input references"):
        EvidenceReference(identity=derived_identity)
    with pytest.raises(ValidationError, match="retrieved_at must be None"):
        EvidenceReference(
            identity=derived_identity,
            retrieved_at=_OPENDART_RETRIEVED_AT,
            input_references=(source_ref,),
        )
    other = _source_reference(_OPENDART_RETRIEVED_AT).identity.model_copy(update={"measure": "net_income"})
    with pytest.raises(ValidationError, match="must match"):
        EvidenceReference(
            identity=derived_identity,
            input_references=(EvidenceReference(identity=other, retrieved_at=_OPENDART_RETRIEVED_AT),),
        )


# ============================== public contracts unchanged ==============================


def test_v1_stock_analysis_models_are_unchanged():
    assert set(StockAnalysis.model_fields) == {
        "symbol", "name", "price", "financials", "financial_history", "financial_features",
        "investment_thesis", "catalysts", "risks", "scenarios", "risk_level", "confidence",
        "evidence",
    }
    assert set(FinancialSnapshot.model_fields) == {
        "business_year", "revenue", "operating_profit", "net_income", "total_assets",
        "total_liabilities", "total_equity", "per", "pbr", "roe",
    }
    assert set(AnnualFinancialFeatures.model_fields) == {
        "business_year", "operating_margin", "net_margin", "debt_ratio",
    }
    assert set(FinancialFeatures.model_fields) == {"annual", "yoy", "trends"}


def test_analyze_without_evidence_keeps_existing_behavior():
    result = analyze(
        KiwoomStockInfo(
            stock_code="005930", stock_name="삼성전자", current_price=1, change=0,
            change_rate=0.0, trading_volume=0, per=None, pbr=None, roe=None, eps=None,
            bps=None, high_250d=None, low_250d=None,
        ),
        KeyFinancials(
            stock_code="005930", corp_code="00126380", business_year="2024",
            report_code="11011", fs_div="CFS", revenue=None, operating_profit=None,
            net_income=None, total_assets=None, total_liabilities=None, total_equity=None,
        ),
    )
    assert isinstance(result, DeterministicAnalysisResult)
    assert result.evidence is None


def test_mcp_public_output_schema_and_structured_output_unchanged():
    from mcp.server.mcpserver.utilities.func_metadata import func_metadata

    from app.mcp import server

    expected = {
        server.get_key_financials: {
            "stock_code", "corp_code", "business_year", "report_code", "fs_div", "revenue",
            "operating_profit", "net_income", "total_assets", "total_liabilities",
            "total_equity",
        },
        server.get_company_financials: {
            "stock_code", "corp_code", "business_year", "report_code", "accounts",
        },
        server.get_stock_info: {
            "stock_code", "stock_name", "current_price", "change", "change_rate",
            "trading_volume", "per", "pbr", "roe", "eps", "bps", "high_250d", "low_250d",
        },
    }
    for tool, properties in expected.items():
        schema = func_metadata(tool).output_schema
        assert schema is not None
        assert set(schema["properties"]) == properties
        assert "evidence" not in schema["properties"]
        assert "retrieved_at" not in schema["properties"]

    account_schema = func_metadata(server.get_company_financials).output_schema["$defs"][
        "OpenDartFinancialAccount"
    ]
    assert "retrieved_at" not in account_schema["properties"]

    structured = func_metadata(server.get_company_financials).convert_result(
        CompanyFinancials(
            stock_code="005930",
            corp_code="00126380",
            business_year="2024",
            report_code="11011",
            accounts=_ACCOUNTS[:1],
        )
    ).structured_content
    assert "retrieved_at" not in structured["accounts"][0]
    assert "evidence" not in structured

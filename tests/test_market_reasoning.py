import json
from unittest.mock import AsyncMock

import pytest

from app.agents.market.analysis import DeterministicFact, MarketDeterministicAnalysisResult
from app.agents.market.reasoning import ReasoningError, generate_reasoning
from app.models.common import AnalysisConfidence
from app.services.llm import LLMResponse, LLMService


def _analysis(facts: list[DeterministicFact] | None = None) -> MarketDeterministicAnalysisResult:
    return MarketDeterministicAnalysisResult(
        base_rate_latest=2.75,
        base_rate_change_bp=25.0,
        usd_krw_latest=1383.1,
        usd_krw_change_20d_pct=-1.5,
        usd_krw_change_60d_pct=-2.0,
        kospi_latest=6808.21,
        kospi_change_20d_pct=1.6,
        kospi_change_60d_pct=2.4,
        kosdaq_latest=826.87,
        kosdaq_change_20d_pct=0.5,
        kosdaq_change_60d_pct=0.9,
        facts=facts
        if facts is not None
        else [
            DeterministicFact(
                id="base_rate_change",
                description="한국 기준금리는 최근 60일간 2.50% → 2.75%로 25bp 상승",
                source="ECOS",
            ),
            DeterministicFact(
                id="usd_krw_change_20d",
                description="USD/KRW 환율은 최근 20거래일 -1.5% 변동",
                source="ECOS",
            ),
            DeterministicFact(
                id="kospi_change_20d",
                description="KOSPI지수은 최근 20거래일 +1.6% 변동",
                source="ECOS",
            ),
        ],
        max_confidence=AnalysisConfidence.MEDIUM,
    )


def _valid_json(
    *,
    regime_fact_ids: list[str] | None = None,
    risk_fact_ids: list[str] | None = None,
    suggested_confidence: str = "medium",
) -> str:
    return json.dumps(
        {
            "summary": "기준금리 인상과 원화 약세가 동시에 관찰됨",
            "suggested_regime": "neutral",
            "suggested_risk_level": "medium",
            "suggested_confidence": suggested_confidence,
            "regime_fact_ids": (
                regime_fact_ids if regime_fact_ids is not None else ["base_rate_change"]
            ),
            "risk_fact_ids": (
                risk_fact_ids if risk_fact_ids is not None else ["usd_krw_change_20d"]
            ),
        },
        ensure_ascii=False,
    )


def _llm_with_responses(contents: list[str]) -> LLMService:
    llm_service = LLMService(api_key="test-key", model="test-model")
    llm_service.complete = AsyncMock(
        side_effect=[
            LLMResponse(content=content, model="test-model", finish_reason="stop")
            for content in contents
        ]
    )
    return llm_service


@pytest.mark.anyio
async def test_generate_reasoning_returns_valid_result() -> None:
    llm_service = _llm_with_responses([_valid_json()])

    result = await generate_reasoning(llm_service, _analysis())

    assert result.summary
    assert result.regime_fact_ids == ["base_rate_change"]
    assert result.risk_fact_ids == ["usd_krw_change_20d"]


@pytest.mark.anyio
async def test_generate_reasoning_retries_on_invalid_json() -> None:
    llm_service = _llm_with_responses(["이건 JSON이 아닙니다", _valid_json()])

    result = await generate_reasoning(llm_service, _analysis())

    assert result.regime_fact_ids == ["base_rate_change"]
    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_generate_reasoning_raises_after_max_attempts_on_invalid_json() -> None:
    llm_service = _llm_with_responses(["이건 JSON이 아닙니다", "여전히 JSON이 아닙니다"])

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_retries_when_regime_fact_ids_empty() -> None:
    llm_service = _llm_with_responses(
        [_valid_json(regime_fact_ids=[]), _valid_json()]
    )

    result = await generate_reasoning(llm_service, _analysis())

    assert result.regime_fact_ids == ["base_rate_change"]
    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_regime_fact_ids_empty_after_retry() -> None:
    llm_service = _llm_with_responses(
        [_valid_json(regime_fact_ids=[]), _valid_json(regime_fact_ids=[])]
    )

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_risk_fact_ids_empty_after_retry() -> None:
    llm_service = _llm_with_responses(
        [_valid_json(risk_fact_ids=[]), _valid_json(risk_fact_ids=[])]
    )

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_unknown_fact_id_present() -> None:
    # regime_fact_ids에 유효한 id("base_rate_change")와 존재하지 않는 id가
    # 함께 있어도 일부만 걸러내지 않고 전체를 실패로 처리해야 한다.
    llm_service = _llm_with_responses(
        [
            _valid_json(regime_fact_ids=["base_rate_change", "no_such_fact"]),
            _valid_json(regime_fact_ids=["base_rate_change", "no_such_fact"]),
        ]
    )

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_recovers_from_unknown_fact_id_on_retry() -> None:
    llm_service = _llm_with_responses(
        [
            _valid_json(regime_fact_ids=["no_such_fact"]),
            _valid_json(regime_fact_ids=["base_rate_change"]),
        ]
    )

    result = await generate_reasoning(llm_service, _analysis())

    assert result.regime_fact_ids == ["base_rate_change"]

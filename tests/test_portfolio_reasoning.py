import json
from unittest.mock import AsyncMock

import pytest

from app.agents.portfolio.analysis import (
    DeterministicFact,
    PortfolioDeterministicAnalysisResult,
    SymbolContext,
)
from app.agents.portfolio.reasoning import ReasoningError, generate_reasoning
from app.models.common import AnalysisConfidence
from app.models.strategy import InvestmentAction
from app.services.llm import LLMResponse, LLMService


def _analysis(
    symbol_contexts: list[SymbolContext] | None = None,
    facts: list[DeterministicFact] | None = None,
) -> PortfolioDeterministicAnalysisResult:
    return PortfolioDeterministicAnalysisResult(
        symbol_contexts=symbol_contexts
        if symbol_contexts is not None
        else [
            SymbolContext(
                symbol="005930",
                name="삼성전자",
                current_weight=0.50,
                allowed_actions=[
                    InvestmentAction.ADD,
                    InvestmentAction.HOLD,
                    InvestmentAction.REDUCE,
                    InvestmentAction.SELL,
                ],
            ),
            SymbolContext(
                symbol="000660",
                name="SK하이닉스",
                current_weight=None,
                allowed_actions=[InvestmentAction.BUY, InvestmentAction.AVOID],
            ),
        ],
        facts=facts
        if facts is not None
        else [
            DeterministicFact(
                id="portfolio_top1_weight",
                description="단일 최대 비중 종목의 비중은 50.0%",
                source="PortfolioContext",
            ),
            DeterministicFact(
                id="005930_current_weight",
                description="삼성전자(005930)의 현재 포트폴리오 비중은 50.0%",
                source="PortfolioContext",
            ),
            DeterministicFact(
                id="000660_not_held",
                description="SK하이닉스(000660)은 현재 미보유",
                source="PortfolioContext",
            ),
        ],
        max_confidence=AnalysisConfidence.MEDIUM,
    )


def _recommendation(
    *,
    symbol: str = "005930",
    suggested_action: str = "reduce",
    fact_ids: list[str] | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "suggested_action": suggested_action,
        "rationale": "비중이 높아 축소를 검토",
        "conditions": [],
        "fact_ids": fact_ids if fact_ids is not None else ["005930_current_weight"],
    }


def _valid_json(
    *,
    recommendations: list[dict] | None = None,
    portfolio_risk_fact_ids: list[str] | None = None,
    suggested_confidence: str = "medium",
) -> str:
    return json.dumps(
        {
            "portfolio_summary": "삼성전자 비중이 높아 축소를 검토할 시점",
            "recommendations": (
                recommendations if recommendations is not None else [_recommendation()]
            ),
            "suggested_portfolio_risk": "medium",
            "portfolio_risk_fact_ids": (
                portfolio_risk_fact_ids
                if portfolio_risk_fact_ids is not None
                else ["portfolio_top1_weight"]
            ),
            "suggested_confidence": suggested_confidence,
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

    assert result.portfolio_summary
    assert result.recommendations[0].symbol == "005930"
    assert result.recommendations[0].suggested_action == InvestmentAction.REDUCE
    assert result.portfolio_risk_fact_ids == ["portfolio_top1_weight"]


@pytest.mark.anyio
async def test_generate_reasoning_allows_empty_recommendations() -> None:
    llm_service = _llm_with_responses([_valid_json(recommendations=[])])

    result = await generate_reasoning(llm_service, _analysis())

    assert result.recommendations == []


@pytest.mark.anyio
async def test_generate_reasoning_retries_on_invalid_json() -> None:
    llm_service = _llm_with_responses(["이건 JSON이 아닙니다", _valid_json()])

    result = await generate_reasoning(llm_service, _analysis())

    assert result.recommendations[0].symbol == "005930"
    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_generate_reasoning_raises_after_max_attempts_on_invalid_json() -> None:
    llm_service = _llm_with_responses(["이건 JSON이 아닙니다", "여전히 아닙니다"])

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_portfolio_risk_fact_ids_empty_after_retry() -> None:
    bad_json = _valid_json(portfolio_risk_fact_ids=[])
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_portfolio_risk_fact_id_unknown() -> None:
    bad_json = _valid_json(portfolio_risk_fact_ids=["no_such_fact"])
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_recommendation_symbol_unknown() -> None:
    bad_json = _valid_json(
        recommendations=[_recommendation(symbol="999999", fact_ids=["portfolio_top1_weight"])]
    )
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_recommendation_fact_ids_empty() -> None:
    bad_json = _valid_json(recommendations=[_recommendation(fact_ids=[])])
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_recommendation_fact_id_unknown() -> None:
    # 일부만 유효한 id("005930_current_weight")여도 나머지에 존재하지 않는
    # id가 섞이면 전체를 실패로 처리해야 한다(부분 valid만 남겨 통과시키지
    # 않음).
    bad_json = _valid_json(
        recommendations=[
            _recommendation(fact_ids=["005930_current_weight", "no_such_fact"])
        ]
    )
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_action_not_allowed_for_held_symbol() -> None:
    # 005930은 보유 종목이라 BUY/AVOID가 허용되지 않는다.
    bad_json = _valid_json(recommendations=[_recommendation(suggested_action="buy")])
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_raises_when_action_not_allowed_for_unheld_symbol() -> None:
    # 000660은 미보유 종목이라 SELL/REDUCE/ADD/HOLD가 허용되지 않는다.
    bad_json = _valid_json(
        recommendations=[
            _recommendation(
                symbol="000660",
                suggested_action="sell",
                fact_ids=["000660_not_held"],
            )
        ]
    )
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, _analysis())


@pytest.mark.anyio
async def test_generate_reasoning_allows_buy_for_unheld_symbol() -> None:
    ok_json = _valid_json(
        recommendations=[
            _recommendation(
                symbol="000660",
                suggested_action="buy",
                fact_ids=["000660_not_held"],
            )
        ]
    )
    llm_service = _llm_with_responses([ok_json])

    result = await generate_reasoning(llm_service, _analysis())

    assert result.recommendations[0].suggested_action == InvestmentAction.BUY


@pytest.mark.anyio
async def test_generate_reasoning_recovers_from_invalid_action_on_retry() -> None:
    bad_json = _valid_json(recommendations=[_recommendation(suggested_action="buy")])
    good_json = _valid_json()
    llm_service = _llm_with_responses([bad_json, good_json])

    result = await generate_reasoning(llm_service, _analysis())

    assert result.recommendations[0].suggested_action == InvestmentAction.REDUCE
    assert llm_service.complete.await_count == 2

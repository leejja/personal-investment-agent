import json
from unittest.mock import AsyncMock

import pytest

from app.models.common import UserRequest
from app.models.supervisor import Intent
from app.services.llm import LLMResponse, LLMService
from app.supervisor.routing import RoutingError, classify


def _request(question: str = "시장 상황 알려줘") -> UserRequest:
    return UserRequest(question=question)


def _valid_json(
    *,
    intent: str = "market_only",
    mentioned_stock_terms: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "intent": intent,
            "mentioned_stock_terms": (
                mentioned_stock_terms if mentioned_stock_terms is not None else []
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
async def test_classify_market_only() -> None:
    llm_service = _llm_with_responses([_valid_json(intent="market_only")])

    result = await classify(llm_service, _request("시장 상황 알려줘"))

    assert result.intent == Intent.MARKET_ONLY
    assert result.mentioned_stock_terms == []


@pytest.mark.anyio
async def test_classify_stock_research_with_mentioned_term() -> None:
    llm_service = _llm_with_responses(
        [_valid_json(intent="stock_research", mentioned_stock_terms=["삼성전자"])]
    )

    result = await classify(llm_service, _request("삼성전자 분석해줘"))

    assert result.intent == Intent.STOCK_RESEARCH
    assert result.mentioned_stock_terms == ["삼성전자"]


@pytest.mark.anyio
async def test_classify_portfolio_strategy_for_whole_portfolio() -> None:
    llm_service = _llm_with_responses(
        [_valid_json(intent="portfolio_strategy")]
    )

    result = await classify(llm_service, _request("내 포트폴리오 분석해줘"))

    assert result.intent == Intent.PORTFOLIO_STRATEGY
    assert result.mentioned_stock_terms == []


@pytest.mark.anyio
async def test_classify_portfolio_strategy_for_specific_symbol() -> None:
    llm_service = _llm_with_responses(
        [
            _valid_json(
                intent="portfolio_strategy", mentioned_stock_terms=["삼성전자"]
            )
        ]
    )

    result = await classify(llm_service, _request("내가 삼성전자를 더 사도 될까?"))

    assert result.intent == Intent.PORTFOLIO_STRATEGY
    assert result.mentioned_stock_terms == ["삼성전자"]


@pytest.mark.anyio
async def test_classify_retries_on_invalid_json() -> None:
    llm_service = _llm_with_responses(
        ["이건 JSON이 아닙니다", _valid_json(intent="market_only")]
    )

    result = await classify(llm_service, _request())

    assert result.intent == Intent.MARKET_ONLY
    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_classify_retries_on_unknown_intent_value() -> None:
    unknown_intent_json = json.dumps(
        {"intent": "buy_everything", "mentioned_stock_terms": []}
    )
    llm_service = _llm_with_responses(
        [unknown_intent_json, _valid_json(intent="market_only")]
    )

    result = await classify(llm_service, _request())

    assert result.intent == Intent.MARKET_ONLY
    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_classify_raises_after_max_attempts() -> None:
    llm_service = _llm_with_responses(["이건 JSON이 아닙니다", "여전히 아닙니다"])

    with pytest.raises(RoutingError):
        await classify(llm_service, _request())

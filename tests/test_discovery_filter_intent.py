import json
from unittest.mock import AsyncMock

import pytest

from app.discovery.filter_intent import FilterIntentError, classify
from app.models.discovery import MarketFilter
from app.services.llm import LLMResponse, LLMService

_KNOWN_SECTORS = ["반도체와반도체장비", "제약", "운송장비/부품"]
_KNOWN_SIZES = ["대형주", "중형주", "소형주"]


def _valid_json(
    *,
    market: str | None = None,
    sector_terms: list[str] | None = None,
    size_terms: list[str] | None = None,
    exclude_owned: bool = False,
) -> str:
    return json.dumps(
        {
            "market": market,
            "sector_terms": sector_terms or [],
            "size_terms": size_terms or [],
            "exclude_owned": exclude_owned,
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
async def test_classify_returns_valid_filter() -> None:
    llm_service = _llm_with_responses(
        [_valid_json(sector_terms=["반도체와반도체장비"])]
    )

    result = await classify(
        llm_service,
        "반도체 종목 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.sector_terms == ["반도체와반도체장비"]
    assert result.market is None
    assert result.exclude_owned is False


@pytest.mark.anyio
async def test_classify_allows_empty_filter() -> None:
    llm_service = _llm_with_responses([_valid_json()])

    result = await classify(
        llm_service,
        "아무 조건도 없는 질문",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.market is None
    assert result.sector_terms == []
    assert result.size_terms == []
    assert result.exclude_owned is False


@pytest.mark.anyio
async def test_classify_market_enum_validated_structurally() -> None:
    llm_service = _llm_with_responses([_valid_json(market="kospi")])

    result = await classify(
        llm_service,
        "코스피 종목 중에서 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.market == MarketFilter.KOSPI


@pytest.mark.anyio
async def test_classify_retries_when_market_is_unknown_enum_value() -> None:
    bad_json = json.dumps(
        {
            "market": "nasdaq",
            "sector_terms": [],
            "size_terms": [],
            "exclude_owned": False,
        }
    )
    llm_service = _llm_with_responses([bad_json, _valid_json()])

    result = await classify(
        llm_service,
        "질문",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.market is None
    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_classify_raises_when_sector_term_not_in_known_set() -> None:
    # 일부만 유효한 값이어도(예: 두 개 중 하나만 실재) 전체를 실패로
    # 처리해야 한다(부분 valid만 남겨 통과시키지 않음).
    bad_json = _valid_json(sector_terms=["반도체와반도체장비", "존재하지않는업종"])
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(FilterIntentError):
        await classify(
            llm_service,
            "질문",
            known_sectors=_KNOWN_SECTORS,
            known_sizes=_KNOWN_SIZES,
        )


@pytest.mark.anyio
async def test_classify_raises_when_size_term_not_in_known_set() -> None:
    bad_json = _valid_json(size_terms=["초대형주"])
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(FilterIntentError):
        await classify(
            llm_service,
            "질문",
            known_sectors=_KNOWN_SECTORS,
            known_sizes=_KNOWN_SIZES,
        )


@pytest.mark.anyio
async def test_classify_recovers_from_unknown_sector_on_retry() -> None:
    llm_service = _llm_with_responses(
        [
            _valid_json(sector_terms=["존재하지않는업종"]),
            _valid_json(sector_terms=["제약"]),
        ]
    )

    result = await classify(
        llm_service,
        "질문",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.sector_terms == ["제약"]


@pytest.mark.anyio
async def test_classify_exclude_owned_true_when_llm_says_so() -> None:
    llm_service = _llm_with_responses([_valid_json(exclude_owned=True)])

    result = await classify(
        llm_service,
        "내 포트폴리오에 없는 반도체 후보 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.exclude_owned is True


@pytest.mark.anyio
async def test_classify_raises_after_max_attempts_on_invalid_json() -> None:
    llm_service = _llm_with_responses(["이건 JSON이 아닙니다", "여전히 아닙니다"])

    with pytest.raises(FilterIntentError):
        await classify(
            llm_service,
            "질문",
            known_sectors=_KNOWN_SECTORS,
            known_sizes=_KNOWN_SIZES,
        )

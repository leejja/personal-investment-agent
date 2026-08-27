import json
from unittest.mock import AsyncMock

import pytest

from app.discovery.orchestrator import (
    MAX_STOCK_RESEARCH_FANOUT,
    DiscoveryError,
    DiscoveryOrchestrator,
)
from app.models.portfolio import PortfolioContext, PortfolioPosition
from app.services.kiwoom import KiwoomStockListItem
from app.services.llm import LLMResponse, LLMService


def _item(
    symbol: str,
    name: str,
    *,
    sector: str = "반도체와반도체장비",
    size: str = "대형주",
) -> KiwoomStockListItem:
    return KiwoomStockListItem(
        symbol=symbol,
        name=name,
        market_name="거래소",
        sector_name=sector,
        size_name=size,
        listed_shares=1_000_000,
        last_price=50_000,
        audit_info="정상",
        order_warning="0",
    )


class _FakeKiwoomTools:
    def __init__(
        self,
        kospi: list[KiwoomStockListItem] | None = None,
        kosdaq: list[KiwoomStockListItem] | None = None,
    ) -> None:
        self.kospi = kospi or []
        self.kosdaq = kosdaq or []

    async def get_kospi_stock_list(self) -> list[KiwoomStockListItem]:
        return self.kospi

    async def get_kosdaq_stock_list(self) -> list[KiwoomStockListItem]:
        return self.kosdaq


def _filter_json(
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


def _portfolio_context(symbols: list[str]) -> PortfolioContext:
    return PortfolioContext(
        total_value=1_000_000,
        cash=0,
        positions=[
            PortfolioPosition(
                symbol=symbol,
                name=symbol,
                quantity=1,
                average_price=1000,
                current_price=1000,
                market_value=1000,
                profit_loss=0,
                profit_loss_pct=0,
                weight=0.1,
            )
            for symbol in symbols
        ],
    )


@pytest.mark.anyio
async def test_run_returns_none_when_no_active_constraint() -> None:
    kiwoom = _FakeKiwoomTools(kospi=[_item("000660", "SK하이닉스")])
    llm_service = _llm_with_responses([_filter_json()])
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("좋은 종목 추천해줘")

    assert result is None


@pytest.mark.anyio
async def test_run_filters_by_sector() -> None:
    kiwoom = _FakeKiwoomTools(
        kospi=[
            _item("000660", "SK하이닉스", sector="반도체와반도체장비"),
            _item("000020", "동화약품", sector="제약"),
        ]
    )
    llm_service = _llm_with_responses(
        [_filter_json(sector_terms=["반도체와반도체장비"])]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("반도체 종목 찾아줘")

    assert result is not None
    assert [c.symbol for c in result] == ["000660"]
    assert result[0].matched_filters["sector"] == "반도체와반도체장비"


@pytest.mark.anyio
async def test_run_filters_by_market() -> None:
    kiwoom = _FakeKiwoomTools(
        kospi=[_item("000660", "SK하이닉스")],
        kosdaq=[_item("123456", "코스닥종목")],
    )
    llm_service = _llm_with_responses([_filter_json(market="kosdaq")])
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("코스닥 종목 중에서 찾아줘")

    assert result is not None
    assert [c.symbol for c in result] == ["123456"]
    assert result[0].market.value == "kosdaq"


@pytest.mark.anyio
async def test_run_excludes_owned_when_exclude_owned_true() -> None:
    kiwoom = _FakeKiwoomTools(
        kospi=[
            _item("000660", "SK하이닉스"),
            _item("005930", "삼성전자"),
        ]
    )
    llm_service = _llm_with_responses(
        [_filter_json(sector_terms=["반도체와반도체장비"], exclude_owned=True)]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run(
        "내 포트폴리오에 없는 반도체 후보 찾아줘",
        portfolio_context=_portfolio_context(["005930"]),
    )

    assert result is not None
    assert [c.symbol for c in result] == ["000660"]


@pytest.mark.anyio
async def test_run_does_not_exclude_owned_when_exclude_owned_false() -> None:
    # exclude_owned가 false면 보유 여부와 무관하게 조건에 맞는 종목 전부
    # 반환한다 — personalized discovery라는 이유만으로 자동으로 제외하지
    # 않는다.
    kiwoom = _FakeKiwoomTools(
        kospi=[
            _item("000660", "SK하이닉스"),
            _item("005930", "삼성전자"),
        ]
    )
    llm_service = _llm_with_responses(
        [_filter_json(sector_terms=["반도체와반도체장비"], exclude_owned=False)]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run(
        "반도체 종목 중에서 후보 찾아줘",
        portfolio_context=_portfolio_context(["005930"]),
    )

    assert result is not None
    assert sorted(c.symbol for c in result) == ["000660", "005930"]


@pytest.mark.anyio
async def test_run_raises_when_matched_count_exceeds_fanout_limit() -> None:
    items = [
        _item(f"{i:06d}", f"종목{i}") for i in range(MAX_STOCK_RESEARCH_FANOUT + 1)
    ]
    kiwoom = _FakeKiwoomTools(kospi=items)
    llm_service = _llm_with_responses(
        [_filter_json(sector_terms=["반도체와반도체장비"])]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    with pytest.raises(DiscoveryError):
        await orchestrator.run("반도체 종목 찾아줘")


@pytest.mark.anyio
async def test_run_does_not_narrow_arbitrarily_when_within_limit() -> None:
    # 한도 이하면 일부를 골라내지 않고 전부 반환한다(임의 top-N 선택 없음).
    items = [
        _item(f"{i:06d}", f"종목{i}") for i in range(MAX_STOCK_RESEARCH_FANOUT)
    ]
    kiwoom = _FakeKiwoomTools(kospi=items)
    llm_service = _llm_with_responses(
        [_filter_json(sector_terms=["반도체와반도체장비"])]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("반도체 종목 찾아줘")

    assert result is not None
    assert len(result) == MAX_STOCK_RESEARCH_FANOUT


@pytest.mark.anyio
async def test_run_excludes_items_with_no_symbol_or_name() -> None:
    kiwoom = _FakeKiwoomTools(
        kospi=[
            _item("000660", "SK하이닉스"),
            _item("", "이름만있음"),
            _item("999999", ""),
        ]
    )
    # exclude_owned로 조건을 하나 걸어 활성 제약이 있게 만든다.
    llm_service = _llm_with_responses([_filter_json(exclude_owned=True)])
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("미보유 종목 찾아줘")

    assert result is not None
    assert [c.symbol for c in result] == ["000660"]

import json
from unittest.mock import AsyncMock

import pytest

from app.discovery.orchestrator import (
    MAX_STOCK_RESEARCH_FANOUT,
    DiscoveryError,
    DiscoveryOrchestrator,
)
from app.models.portfolio import PortfolioContext, PortfolioPosition
from app.services.kiwoom import KiwoomStockListItem, KiwoomThemeGroup, KiwoomThemeStock
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
        theme_groups: list[KiwoomThemeGroup] | None = None,
        theme_stocks: dict[str, list[KiwoomThemeStock]] | None = None,
    ) -> None:
        self.kospi = kospi or []
        self.kosdaq = kosdaq or []
        # UX-01: theme catalog(ka90001)/membership(ka90002) fakes. 기본값은
        # 빈 카탈로그 — 테마를 다루지 않는 기존 테스트는 이 값을 그대로
        # 두면 theme_requests가 항상 빈 채로 grounding을 통과해 기존과
        # 동일하게 동작한다.
        self.theme_groups = theme_groups or []
        self.theme_stocks = theme_stocks or {}
        self.theme_stocks_calls: list[str] = []

    async def get_kospi_stock_list(self) -> list[KiwoomStockListItem]:
        return self.kospi

    async def get_kosdaq_stock_list(self) -> list[KiwoomStockListItem]:
        return self.kosdaq

    async def get_theme_groups(self) -> list[KiwoomThemeGroup]:
        return self.theme_groups

    async def get_theme_stocks(self, theme_code: str) -> list[KiwoomThemeStock]:
        self.theme_stocks_calls.append(theme_code)
        return self.theme_stocks.get(theme_code, [])


def _filter_json(
    *,
    market: str | None = None,
    sector_terms: list[str] | None = None,
    size_terms: list[str] | None = None,
    theme_requests: list[dict] | None = None,
    exclude_owned: bool = False,
) -> str:
    return json.dumps(
        {
            "market": market,
            "sector_terms": sector_terms or [],
            "size_terms": size_terms or [],
            "theme_requests": theme_requests or [],
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


# ============================== UX-01: theme axis ==============================


def _theme_group(code: str, name: str, stock_count: int = 1) -> KiwoomThemeGroup:
    return KiwoomThemeGroup(theme_code=code, theme_name=name, stock_count=stock_count)


def _theme_stock(code: str, name: str) -> KiwoomThemeStock:
    return KiwoomThemeStock(stock_code=code, stock_name=name)


@pytest.mark.anyio
async def test_run_regression_sector_query_unaffected_by_theme_catalog() -> None:
    # 기존 "대형 통신 종목 후보 찾아줘" 같은 sector-only 요청은 theme
    # catalog가 존재해도 동작이 그대로여야 하고, theme membership을
    # 조회(get_theme_stocks)하지 않아야 한다.
    kiwoom = _FakeKiwoomTools(
        kospi=[
            _item("000660", "SK하이닉스", sector="반도체와반도체장비"),
            _item("000020", "동화약품", sector="제약"),
        ],
        theme_groups=[_theme_group("550", "반도체_생산")],
    )
    llm_service = _llm_with_responses(
        [_filter_json(sector_terms=["반도체와반도체장비"])]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("반도체와반도체장비 종목 찾아줘")

    assert result is not None
    assert [c.symbol for c in result] == ["000660"]
    assert "theme" not in result[0].matched_filters
    assert kiwoom.theme_stocks_calls == []


@pytest.mark.anyio
async def test_run_filters_by_theme_union_of_matched_themes() -> None:
    # 같은 concept의 여러 테마는 UNION된다 — 테마 A={005930}, 테마
    # B={000660}이면 결과는 {005930, 000660} 둘 다 포함해야 한다.
    kiwoom = _FakeKiwoomTools(
        kospi=[
            _item("005930", "삼성전자"),
            _item("000660", "SK하이닉스"),
            _item("999999", "무관종목"),
        ],
        theme_groups=[
            _theme_group("550", "반도체_생산"),
            _theme_group("551", "반도체_설계(fabless)"),
        ],
        theme_stocks={
            "550": [_theme_stock("005930", "삼성전자")],
            "551": [_theme_stock("000660", "SK하이닉스")],
        },
    )
    llm_service = _llm_with_responses(
        # concept "반도체" 자체가 이미 두 테마 모두에 prefix 매칭되므로
        # normalized_concepts는 필요 없다 — Python이 결정론적으로 매칭한다.
        [_filter_json(theme_requests=[{"concept": "반도체", "normalized_concepts": []}])]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("반도체 관련 종목 후보 찾아줘")

    assert result is not None
    assert sorted(c.symbol for c in result) == ["000660", "005930"]


@pytest.mark.anyio
async def test_run_theme_intersects_with_market_and_size() -> None:
    # Market ∩ Size ∩ Theme — 서로 다른 axis는 교집합이다.
    kiwoom = _FakeKiwoomTools(
        kospi=[
            _item("005930", "삼성전자", size="대형주"),
            _item("000990", "DB하이텍", size="중형주"),
        ],
        kosdaq=[_item("123456", "코스닥반도체", size="대형주")],
        theme_groups=[_theme_group("550", "반도체_생산")],
        theme_stocks={
            "550": [
                _theme_stock("005930", "삼성전자"),
                _theme_stock("000990", "DB하이텍"),
                _theme_stock("123456", "코스닥반도체"),
            ]
        },
    )
    llm_service = _llm_with_responses(
        [
            _filter_json(
                market="kospi",
                size_terms=["대형주"],
                theme_requests=[{"concept": "반도체", "normalized_concepts": []}],
            )
        ]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("코스피 대형주 중 반도체 관련 종목 찾아줘")

    # KOSPI(005930, 000990) ∩ 대형주(005930) ∩ 반도체_생산(전부) = {005930}
    assert result is not None
    assert [c.symbol for c in result] == ["005930"]


@pytest.mark.anyio
async def test_run_raises_discovery_error_for_unsupported_theme_concept() -> None:
    # "AI"는 카탈로그에 대응하는 테마가 없다 — 조용히 무시하고 나머지
    # 조건(있다면)만으로 좁혀서는 안 되고 명시적으로 실패해야 한다.
    kiwoom = _FakeKiwoomTools(
        kospi=[_item("005930", "삼성전자")],
        theme_groups=[_theme_group("550", "반도체_생산")],
    )
    llm_service = _llm_with_responses(
        [_filter_json(theme_requests=[{"concept": "AI", "normalized_concepts": []}])]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    with pytest.raises(DiscoveryError, match="AI"):
        await orchestrator.run("AI 관련주 찾아줘")

    # unsupported concept 판정은 theme membership 조회(ka90002) 이전에
    # 끝나야 한다 — 불필요한 API 호출을 만들지 않는다.
    assert kiwoom.theme_stocks_calls == []


@pytest.mark.anyio
async def test_run_raises_discovery_error_when_any_concept_unsupported_even_if_others_match() -> None:
    # "AI 반도체 관련주"처럼 하나는 지원되고 하나는 지원되지 않으면,
    # 지원되는 개념(반도체)만으로 조용히 좁혀서 반환하면 안 된다.
    kiwoom = _FakeKiwoomTools(
        kospi=[_item("005930", "삼성전자")],
        theme_groups=[_theme_group("550", "반도체_생산")],
        theme_stocks={"550": [_theme_stock("005930", "삼성전자")]},
    )
    llm_service = _llm_with_responses(
        [
            _filter_json(
                theme_requests=[
                    {"concept": "AI", "normalized_concepts": []},
                    {"concept": "반도체", "normalized_concepts": []},
                ]
            )
        ]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    with pytest.raises(DiscoveryError, match="AI"):
        await orchestrator.run("AI 반도체 관련주 찾아줘")

    assert kiwoom.theme_stocks_calls == []


@pytest.mark.anyio
async def test_run_theme_lazy_lookup_only_calls_requested_theme_codes() -> None:
    # 카탈로그에 여러 테마가 있어도, 실제로 grounding된(요청된) 테마
    # 코드에 대해서만 ka90002를 호출해야 한다(전체 사전 구축 금지).
    kiwoom = _FakeKiwoomTools(
        kospi=[_item("005930", "삼성전자")],
        theme_groups=[
            _theme_group("550", "반도체_생산"),
            _theme_group("140", "2차전지_완제품"),
            _theme_group("213", "로봇_지능형"),
        ],
        theme_stocks={"550": [_theme_stock("005930", "삼성전자")]},
    )
    llm_service = _llm_with_responses(
        [_filter_json(theme_requests=[{"concept": "반도체", "normalized_concepts": []}])]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    await orchestrator.run("반도체 관련 종목 찾아줘")

    assert kiwoom.theme_stocks_calls == ["550"]


@pytest.mark.anyio
async def test_run_theme_membership_recorded_in_matched_filters() -> None:
    # 최종 Candidate가 어떤 concept/실제 테마 때문에 포함됐는지 추적
    # 가능해야 한다(evidence/traceability).
    kiwoom = _FakeKiwoomTools(
        kospi=[_item("005930", "삼성전자")],
        theme_groups=[_theme_group("550", "반도체_생산")],
        theme_stocks={"550": [_theme_stock("005930", "삼성전자")]},
    )
    llm_service = _llm_with_responses(
        [_filter_json(theme_requests=[{"concept": "반도체", "normalized_concepts": []}])]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("반도체 관련 종목 찾아줘")

    assert result is not None
    assert result[0].matched_filters["theme"] == "반도체_생산"
    assert result[0].matched_filters["theme_concept"] == "반도체"


@pytest.mark.anyio
async def test_run_theme_axis_active_but_no_stock_matches_yields_empty_result() -> None:
    # 요청한 테마에 속한 종목이 universe에 하나도 없으면(코스피/코스닥
    # universe와 겹치지 않으면) 빈 리스트를 반환한다 — None(무제약)과는
    # 구분된다.
    kiwoom = _FakeKiwoomTools(
        kospi=[_item("000020", "동화약품", sector="제약")],
        theme_groups=[_theme_group("550", "반도체_생산")],
        theme_stocks={"550": [_theme_stock("005930", "삼성전자")]},
    )
    llm_service = _llm_with_responses(
        [_filter_json(theme_requests=[{"concept": "반도체", "normalized_concepts": []}])]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("반도체 관련 종목 찾아줘")

    assert result == []


@pytest.mark.anyio
async def test_run_theme_normalization_end_to_end() -> None:
    # "원전" concept 자체로는 카탈로그에 매칭되지 않고, LLM이 제안한
    # normalized_concepts("원자력")를 통해 실제 "원자력_*" 테마로
    # grounding되는 전체 경로(orchestrator 레벨)를 확인한다. 최종
    # matched_themes는 항상 Python의 결정론적 매칭 결과다.
    kiwoom = _FakeKiwoomTools(
        kospi=[_item("034020", "두산에너빌리티")],
        theme_groups=[_theme_group("110", "원자력_기자재")],
        theme_stocks={"110": [_theme_stock("034020", "두산에너빌리티")]},
    )
    llm_service = _llm_with_responses(
        [
            _filter_json(
                theme_requests=[{"concept": "원전", "normalized_concepts": ["원자력"]}]
            )
        ]
    )
    orchestrator = DiscoveryOrchestrator(kiwoom_tools=kiwoom, llm_service=llm_service)

    result = await orchestrator.run("원전 관련주 찾아줘")

    assert result is not None
    assert [c.symbol for c in result] == ["034020"]
    assert result[0].matched_filters["theme"] == "원자력_기자재"
    assert result[0].matched_filters["theme_concept"] == "원전"

import json
from unittest.mock import AsyncMock

import pytest

from app.agents.portfolio.reasoning import ReasoningError
from app.discovery.orchestrator import DiscoveryError
from app.models.common import AnalysisConfidence, RiskLevel, UserRequest
from app.models.discovery import Candidate, MarketFilter
from app.models.market import MarketAnalysis, MarketRegime
from app.models.portfolio import InvestorProfile
from app.models.stock import StockAnalysis
from app.models.strategy import InvestmentAction, PositionRecommendation, StrategyResult
from app.services.kiwoom import KiwoomAccountBalance, KiwoomAccountPosition
from app.services.llm import LLMResponse, LLMService
from app.supervisor.orchestrator import SupervisorError, SupervisorOrchestrator
from app.supervisor.routing import RoutingError


class _FakeMarketOrchestrator:
    def __init__(self, result: MarketAnalysis | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def run(self, as_of_date: str) -> MarketAnalysis:
        self.calls.append(as_of_date)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class _FakeStockResearchOrchestrator:
    def __init__(
        self,
        results: dict[str, StockAnalysis] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.results = results or {}
        self.errors = errors or {}
        self.calls: list[str] = []

    async def run(
        self, stock_code: str, business_year: str, report_code: str = "11011"
    ) -> StockAnalysis:
        self.calls.append(stock_code)
        if stock_code in self.errors:
            raise self.errors[stock_code]
        return self.results[stock_code]


class _FakePortfolioStrategyOrchestrator:
    def __init__(self, result: StrategyResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[list[StockAnalysis]] = []

    async def run(self, market_analysis, stock_analyses, portfolio_context, investor_profile) -> StrategyResult:
        self.calls.append(stock_analyses)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class _FakeKiwoomTools:
    def __init__(self, balance: KiwoomAccountBalance) -> None:
        self.balance = balance

    async def get_account_balance(self, query_type: str = "1", exchange_type: str = "KRX") -> KiwoomAccountBalance:
        return self.balance


class _FakeOpenDartTools:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self.mapping = mapping or {}

    async def find_stock_code_by_name(self, company_name: str) -> str | None:
        return self.mapping.get(company_name)


class _FakeDiscoveryOrchestrator:
    def __init__(
        self,
        result: list[Candidate] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def run(self, question: str, *, portfolio_context=None) -> list[Candidate] | None:
        self.calls.append(question)
        if self.error is not None:
            raise self.error
        return self.result


def _routing_json(intent: str, mentioned_stock_terms: list[str] | None = None) -> str:
    return json.dumps(
        {
            "intent": intent,
            "mentioned_stock_terms": mentioned_stock_terms or [],
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


def _market_analysis() -> MarketAnalysis:
    return MarketAnalysis(
        regime=MarketRegime.NEUTRAL,
        risk_level=RiskLevel.MEDIUM,
        summary="테스트 시장 요약",
        confidence=AnalysisConfidence.MEDIUM,
    )


def _stock_analysis(symbol: str = "005930", name: str = "삼성전자") -> StockAnalysis:
    return StockAnalysis(
        symbol=symbol,
        name=name,
        investment_thesis="테스트 투자 논지",
        risk_level=RiskLevel.MEDIUM,
        confidence=AnalysisConfidence.MEDIUM,
    )


def _strategy_result() -> StrategyResult:
    return StrategyResult(
        summary="테스트 전략 요약",
        recommendations=[
            PositionRecommendation(
                symbol="005930",
                name="삼성전자",
                action=InvestmentAction.HOLD,
                rationale="테스트 근거",
            )
        ],
        portfolio_risk=RiskLevel.MEDIUM,
        confidence=AnalysisConfidence.MEDIUM,
    )


def _investor_profile() -> InvestorProfile:
    return InvestorProfile(risk_tolerance=RiskLevel.MEDIUM)


def _candidate(
    symbol: str = "000660",
    name: str = "SK하이닉스",
    market: MarketFilter = MarketFilter.KOSPI,
    sector: str = "반도체와반도체장비",
) -> Candidate:
    return Candidate(
        symbol=symbol,
        name=name,
        market=market,
        sector=sector,
        matched_filters={"sector": sector},
    )


def _position(symbol: str, name: str) -> KiwoomAccountPosition:
    return KiwoomAccountPosition(
        stock_code=symbol,
        stock_name=name,
        quantity=10,
        tradable_quantity=10,
        average_price=1000,
        current_price=1200,
        purchase_amount=10000,
        evaluation_amount=12000,
        profit_loss=2000,
        return_rate=20.0,
        portfolio_weight=50.0,
    )


def _balance(positions: list[KiwoomAccountPosition]) -> KiwoomAccountBalance:
    return KiwoomAccountBalance(
        total_purchase_amount=10000 * max(len(positions), 1),
        total_evaluation_amount=12000 * max(len(positions), 1),
        total_profit_loss=2000 * len(positions),
        total_return_rate=20.0,
        estimated_asset_amount=None,
        total_loan_amount=None,
        total_credit_loan_amount=None,
        total_credit_short_amount=None,
        positions=positions,
    )


def _build_supervisor(
    *,
    llm_contents: list[str],
    market: _FakeMarketOrchestrator | None = None,
    stock: _FakeStockResearchOrchestrator | None = None,
    portfolio: _FakePortfolioStrategyOrchestrator | None = None,
    discovery: _FakeDiscoveryOrchestrator | None = None,
    balance: KiwoomAccountBalance | None = None,
    name_map: dict[str, str] | None = None,
) -> SupervisorOrchestrator:
    return SupervisorOrchestrator(
        llm_service=_llm_with_responses(llm_contents),
        market_orchestrator=market or _FakeMarketOrchestrator(result=_market_analysis()),
        stock_research_orchestrator=stock or _FakeStockResearchOrchestrator(),
        portfolio_orchestrator=portfolio or _FakePortfolioStrategyOrchestrator(),
        # 기본값은 "조건 없는 요청"(None) — 기존 PORTFOLIO_STRATEGY 테스트들이
        # 전부 discovery 없이 보유종목 전체로 폴백하던 기존 동작을 그대로
        # 유지한다.
        discovery_orchestrator=discovery or _FakeDiscoveryOrchestrator(result=None),
        kiwoom_tools=_FakeKiwoomTools(balance or _balance([])),
        opendart_tools=_FakeOpenDartTools(name_map or {}),
    )


@pytest.mark.anyio
async def test_market_only_returns_market_analysis() -> None:
    market = _FakeMarketOrchestrator(result=_market_analysis())
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("market_only")], market=market
    )

    result = await supervisor.run(UserRequest(question="시장 상황 알려줘"))

    assert result.intent.value == "market_only"
    assert result.market_analysis is not None
    assert result.stock_analyses == []
    assert len(market.calls) == 1


@pytest.mark.anyio
async def test_market_only_propagates_market_agent_failure() -> None:
    market = _FakeMarketOrchestrator(error=RuntimeError("ECOS down"))
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("market_only")], market=market
    )

    with pytest.raises(RuntimeError):
        await supervisor.run(UserRequest(question="시장 상황 알려줘"))


@pytest.mark.anyio
async def test_stock_research_resolves_symbol_from_user_request() -> None:
    stock = _FakeStockResearchOrchestrator(results={"005930": _stock_analysis()})
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("stock_research")], stock=stock
    )

    result = await supervisor.run(
        UserRequest(question="이 종목 분석해줘", symbols=["005930"])
    )

    assert result.intent.value == "stock_research"
    assert result.resolved_symbols == ["005930"]
    assert len(result.stock_analyses) == 1
    assert stock.calls == ["005930"]


@pytest.mark.anyio
async def test_stock_research_resolves_symbol_from_company_name() -> None:
    stock = _FakeStockResearchOrchestrator(results={"005930": _stock_analysis()})
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("stock_research", ["삼성전자"])],
        stock=stock,
        name_map={"삼성전자": "005930"},
    )

    result = await supervisor.run(UserRequest(question="삼성전자 분석해줘"))

    assert result.resolved_symbols == ["005930"]
    assert stock.calls == ["005930"]


@pytest.mark.anyio
async def test_stock_research_raises_when_symbol_unresolvable() -> None:
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("stock_research", ["알수없는회사"])],
        name_map={},
    )

    with pytest.raises(SupervisorError):
        await supervisor.run(UserRequest(question="알수없는회사 분석해줘"))


@pytest.mark.anyio
async def test_stock_research_propagates_failure() -> None:
    stock = _FakeStockResearchOrchestrator(
        errors={"005930": RuntimeError("OpenDART down")}
    )
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("stock_research")], stock=stock
    )

    with pytest.raises(RuntimeError):
        await supervisor.run(
            UserRequest(question="이 종목 분석해줘", symbols=["005930"])
        )


@pytest.mark.anyio
async def test_portfolio_strategy_requires_investor_profile() -> None:
    supervisor = _build_supervisor(llm_contents=[_routing_json("portfolio_strategy")])

    with pytest.raises(SupervisorError):
        await supervisor.run(UserRequest(question="내 포트폴리오 분석해줘"))


@pytest.mark.anyio
async def test_portfolio_strategy_whole_portfolio_researches_only_held_symbols() -> None:
    positions = [_position("005930", "삼성전자"), _position("000660", "SK하이닉스")]
    stock = _FakeStockResearchOrchestrator(
        results={
            "005930": _stock_analysis("005930", "삼성전자"),
            "000660": _stock_analysis("000660", "SK하이닉스"),
        }
    )
    portfolio = _FakePortfolioStrategyOrchestrator(result=_strategy_result())
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy")],
        stock=stock,
        portfolio=portfolio,
        balance=_balance(positions),
    )

    result = await supervisor.run(
        UserRequest(question="내 포트폴리오 분석해줘"),
        investor_profile=_investor_profile(),
    )

    assert result.intent.value == "portfolio_strategy"
    assert result.resolved_symbols == []
    assert sorted(stock.calls) == ["000660", "005930"]
    assert len(result.stock_analyses) == 2
    assert result.strategy_result is not None
    assert result.skipped == []


@pytest.mark.anyio
async def test_portfolio_strategy_whole_portfolio_skips_failed_symbol() -> None:
    positions = [_position("233740", "ETF"), _position("005930", "삼성전자")]
    stock = _FakeStockResearchOrchestrator(
        results={"005930": _stock_analysis()},
        errors={"233740": ValueError("OpenDART corporation not found: 233740")},
    )
    portfolio = _FakePortfolioStrategyOrchestrator(result=_strategy_result())
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy")],
        stock=stock,
        portfolio=portfolio,
        balance=_balance(positions),
    )

    result = await supervisor.run(
        UserRequest(question="내 포트폴리오 분석해줘"),
        investor_profile=_investor_profile(),
    )

    assert len(result.stock_analyses) == 1
    assert result.stock_analyses[0].symbol == "005930"
    assert len(result.skipped) == 1
    assert "233740" in result.skipped[0]
    assert result.strategy_result is not None


@pytest.mark.anyio
async def test_portfolio_strategy_explicit_symbol_only_researches_that_symbol() -> None:
    # 보유종목이 20개여도, 특정 종목을 물어봤다면 그 종목만 Stock Research를
    # 실행해야 한다(비용 절감 정책).
    positions = [_position(f"{i:06d}", f"종목{i}") for i in range(20)]
    positions.append(_position("005930", "삼성전자"))
    stock = _FakeStockResearchOrchestrator(results={"005930": _stock_analysis()})
    portfolio = _FakePortfolioStrategyOrchestrator(result=_strategy_result())
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy", ["삼성전자"])],
        stock=stock,
        portfolio=portfolio,
        balance=_balance(positions),
        name_map={"삼성전자": "005930"},
    )

    result = await supervisor.run(
        UserRequest(question="내가 삼성전자를 더 사도 될까?"),
        investor_profile=_investor_profile(),
    )

    assert result.resolved_symbols == ["005930"]
    assert stock.calls == ["005930"]
    assert len(result.stock_analyses) == 1
    # 그러나 portfolio_context 자체는 전체 보유종목을 여전히 반영한다.
    assert result.portfolio_context is not None
    assert len(result.portfolio_context.positions) == 21


@pytest.mark.anyio
async def test_portfolio_strategy_explicit_symbol_failure_fails_whole_request() -> None:
    stock = _FakeStockResearchOrchestrator(
        errors={"005930": RuntimeError("Kiwoom down")}
    )
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy", ["삼성전자"])],
        stock=stock,
        balance=_balance([_position("005930", "삼성전자")]),
        name_map={"삼성전자": "005930"},
    )

    with pytest.raises(RuntimeError):
        await supervisor.run(
            UserRequest(question="내가 삼성전자를 더 사도 될까?"),
            investor_profile=_investor_profile(),
        )


@pytest.mark.anyio
async def test_portfolio_strategy_market_agent_failure_propagates() -> None:
    market = _FakeMarketOrchestrator(error=RuntimeError("ECOS down"))
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy")],
        market=market,
        balance=_balance([_position("005930", "삼성전자")]),
    )

    with pytest.raises(RuntimeError):
        await supervisor.run(
            UserRequest(question="내 포트폴리오 분석해줘"),
            investor_profile=_investor_profile(),
        )


@pytest.mark.anyio
async def test_portfolio_strategy_reasoning_failure_returns_partial_result() -> None:
    positions = [_position("005930", "삼성전자")]
    stock = _FakeStockResearchOrchestrator(results={"005930": _stock_analysis()})
    portfolio = _FakePortfolioStrategyOrchestrator(
        error=ReasoningError("근거 부족으로 실패")
    )
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy")],
        stock=stock,
        portfolio=portfolio,
        balance=_balance(positions),
    )

    result = await supervisor.run(
        UserRequest(question="내 포트폴리오 분석해줘"),
        investor_profile=_investor_profile(),
    )

    # market_analysis/stock_analyses/portfolio_context는 그대로 반환되고,
    # strategy_result만 없이 부분 결과가 반환되어야 한다.
    assert result.market_analysis is not None
    assert len(result.stock_analyses) == 1
    assert result.portfolio_context is not None
    assert result.strategy_result is None
    assert any("portfolio_strategy" in note for note in result.skipped)


@pytest.mark.anyio
async def test_routing_error_propagates() -> None:
    supervisor = _build_supervisor(
        llm_contents=["이건 JSON이 아닙니다", "여전히 아닙니다"]
    )

    with pytest.raises(RoutingError):
        await supervisor.run(UserRequest(question="아무 질문"))


@pytest.mark.anyio
async def test_candidate_discovery_runs_stock_research_for_found_candidates() -> None:
    candidates = [_candidate(symbol="000660", name="SK하이닉스")]
    discovery = _FakeDiscoveryOrchestrator(result=candidates)
    stock = _FakeStockResearchOrchestrator(
        results={"000660": _stock_analysis("000660", "SK하이닉스")}
    )
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("candidate_discovery")],
        discovery=discovery,
        stock=stock,
    )

    result = await supervisor.run(UserRequest(question="반도체 종목 중 후보 찾아줘"))

    assert result.intent.value == "candidate_discovery"
    assert result.resolved_symbols == ["000660"]
    assert result.candidates == candidates
    assert len(result.stock_analyses) == 1
    assert result.strategy_result is None


@pytest.mark.anyio
async def test_candidate_discovery_fails_when_no_active_constraint() -> None:
    # discovery_filter가 완전히 비어 있으면(None) open-ended 요청으로
    # 간주해 실패시킨다 — v1 범위 밖.
    discovery = _FakeDiscoveryOrchestrator(result=None)
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("candidate_discovery")],
        discovery=discovery,
    )

    with pytest.raises(SupervisorError):
        await supervisor.run(UserRequest(question="좋은 종목 추천해줘"))


@pytest.mark.anyio
async def test_candidate_discovery_propagates_error_and_runs_no_stock_research() -> None:
    # 후보 과다 등으로 DiscoveryError가 나면 Stock Research를 아예 실행하지
    # 않아야 한다(0건 호출 검증).
    discovery = _FakeDiscoveryOrchestrator(
        error=DiscoveryError("조건에 맞는 종목이 50건입니다")
    )
    stock = _FakeStockResearchOrchestrator()
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("candidate_discovery")],
        discovery=discovery,
        stock=stock,
    )

    with pytest.raises(DiscoveryError):
        await supervisor.run(UserRequest(question="반도체 종목 중 후보 찾아줘"))

    assert stock.calls == []


@pytest.mark.anyio
async def test_portfolio_strategy_uses_discovery_sourced_symbols_when_no_explicit_symbol() -> None:
    candidates = [_candidate(symbol="000660", name="SK하이닉스")]
    discovery = _FakeDiscoveryOrchestrator(result=candidates)
    stock = _FakeStockResearchOrchestrator(
        results={"000660": _stock_analysis("000660", "SK하이닉스")}
    )
    portfolio = _FakePortfolioStrategyOrchestrator(result=_strategy_result())
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy")],
        discovery=discovery,
        stock=stock,
        portfolio=portfolio,
        balance=_balance([_position("005930", "삼성전자")]),
    )

    result = await supervisor.run(
        UserRequest(question="내 포트폴리오에 없는 반도체 후보 찾아줘"),
        investor_profile=_investor_profile(),
    )

    assert result.intent.value == "portfolio_strategy"
    assert result.resolved_symbols == ["000660"]
    assert result.candidates == candidates
    assert stock.calls == ["000660"]
    assert result.strategy_result is not None


@pytest.mark.anyio
async def test_portfolio_strategy_discovery_individual_failure_is_skipped() -> None:
    # discovery로 찾은 종목 집합은 명시적으로 이름을 부른 종목이 아니라
    # 시스템이 찾아낸 후보이므로, 보유종목 fan-out과 동일하게 개별 실패를
    # skip 허용해야 한다.
    candidates = [
        _candidate(symbol="000660", name="SK하이닉스"),
        _candidate(symbol="005930", name="삼성전자"),
    ]
    discovery = _FakeDiscoveryOrchestrator(result=candidates)
    stock = _FakeStockResearchOrchestrator(
        results={"005930": _stock_analysis()},
        errors={"000660": RuntimeError("OpenDART down")},
    )
    portfolio = _FakePortfolioStrategyOrchestrator(result=_strategy_result())
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy")],
        discovery=discovery,
        stock=stock,
        portfolio=portfolio,
        balance=_balance([]),
    )

    result = await supervisor.run(
        UserRequest(question="내 포트폴리오에 없는 반도체 후보 찾아줘"),
        investor_profile=_investor_profile(),
    )

    assert len(result.stock_analyses) == 1
    assert result.stock_analyses[0].symbol == "005930"
    assert len(result.skipped) == 1
    assert "000660" in result.skipped[0]


@pytest.mark.anyio
async def test_portfolio_strategy_discovery_error_fails_whole_request_not_fallback() -> None:
    # discovery 조건은 있었으나 실행 불가(DiscoveryError)면, 조용히 "전체
    # 포트폴리오"로 대체하지 않고 요청 전체를 실패시켜야 한다.
    discovery = _FakeDiscoveryOrchestrator(
        error=DiscoveryError("조건에 맞는 종목이 50건입니다")
    )
    stock = _FakeStockResearchOrchestrator()
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy")],
        discovery=discovery,
        stock=stock,
        balance=_balance([_position("005930", "삼성전자")]),
    )

    with pytest.raises(DiscoveryError):
        await supervisor.run(
            UserRequest(question="내 포트폴리오에 없는 반도체 후보 찾아줘"),
            investor_profile=_investor_profile(),
        )

    assert stock.calls == []


@pytest.mark.anyio
async def test_portfolio_strategy_falls_back_to_held_symbols_when_discovery_empty() -> None:
    # explicit_symbols도 없고 discovery_filter도 비어 있으면(None), 기존
    # "보유종목 전체" 경로로 폴백해야 한다 — 새 기능이 기존 동작을 바꾸지
    # 않는다.
    positions = [_position("005930", "삼성전자")]
    discovery = _FakeDiscoveryOrchestrator(result=None)
    stock = _FakeStockResearchOrchestrator(results={"005930": _stock_analysis()})
    portfolio = _FakePortfolioStrategyOrchestrator(result=_strategy_result())
    supervisor = _build_supervisor(
        llm_contents=[_routing_json("portfolio_strategy")],
        discovery=discovery,
        stock=stock,
        portfolio=portfolio,
        balance=_balance(positions),
    )

    result = await supervisor.run(
        UserRequest(question="내 포트폴리오 분석해줘"),
        investor_profile=_investor_profile(),
    )

    # 보유종목 전체 경로(기존 동작)이므로 resolved_symbols는 채워지지 않고
    # stock_analyses로만 보유종목 분석 결과가 담긴다.
    assert result.resolved_symbols == []
    assert len(result.stock_analyses) == 1
    assert result.stock_analyses[0].symbol == "005930"
    assert result.candidates == []

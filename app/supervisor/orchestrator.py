import asyncio
from datetime import UTC, datetime

from app.agents.market.orchestrator import MarketOrchestrator
from app.agents.portfolio.orchestrator import PortfolioStrategyOrchestrator
from app.agents.portfolio.reasoning import ReasoningError
from app.agents.stock_research.orchestrator import StockResearchOrchestrator
from app.mcp.kiwoom_tools import KiwoomTools
from app.mcp.opendart_tools import OpenDartTools
from app.models.common import UserRequest
from app.models.portfolio import InvestorProfile, PortfolioContext
from app.models.stock import StockAnalysis
from app.models.supervisor import Intent, SupervisorResult
from app.services.llm import LLMService
from app.services.portfolio_adapter import PortfolioAdapter
from app.supervisor.routing import RoutingResult, classify


class SupervisorError(Exception):
    """Raised when a required dependency for the routed intent fails and no
    safe partial SupervisorResult can be produced."""


# 보유종목 전체 fan-out을 제한 없이 asyncio.gather로 한 번에 실행하면, 종목마다
# KiwoomTools가 매번 새 OAuth 토큰을 발급받으면서 Kiwoom 인증 서버가
# 동시 요청을 429(Too Many Requests)로 거부하는 것을 실제 E2E에서 확인했다.
# Stock Research Agent/KiwoomService 자체를 바꾸지 않고, Supervisor가 새로
# 도입한 동시성만 안전한 수준으로 제한한다.
MAX_CONCURRENT_STOCK_RESEARCH = 3


class SupervisorOrchestrator:
    def __init__(
        self,
        llm_service: LLMService,
        market_orchestrator: MarketOrchestrator,
        stock_research_orchestrator: StockResearchOrchestrator,
        portfolio_orchestrator: PortfolioStrategyOrchestrator,
        kiwoom_tools: KiwoomTools,
        opendart_tools: OpenDartTools,
        max_concurrent_stock_research: int = MAX_CONCURRENT_STOCK_RESEARCH,
    ) -> None:
        self.llm_service = llm_service
        self.market_orchestrator = market_orchestrator
        self.stock_research_orchestrator = stock_research_orchestrator
        self.portfolio_orchestrator = portfolio_orchestrator
        self.kiwoom_tools = kiwoom_tools
        self.opendart_tools = opendart_tools
        self._stock_research_semaphore = asyncio.Semaphore(
            max_concurrent_stock_research
        )

    async def run(
        self,
        request: UserRequest,
        *,
        as_of_date: str | None = None,
        business_year: str | None = None,
        investor_profile: InvestorProfile | None = None,
    ) -> SupervisorResult:
        as_of_date = as_of_date or _default_as_of_date()
        business_year = business_year or _default_business_year()

        # RoutingError는 여기서 삼키지 않고 그대로 전파한다. 근거 없는
        # fallback intent를 임의로 고르지 않는다.
        routing_result = await classify(self.llm_service, request)

        if routing_result.intent == Intent.MARKET_ONLY:
            return await self._run_market_only(as_of_date)

        if routing_result.intent == Intent.STOCK_RESEARCH:
            return await self._run_stock_research(
                request, routing_result, business_year
            )

        return await self._run_portfolio_strategy(
            request, routing_result, as_of_date, business_year, investor_profile
        )

    async def _run_market_only(self, as_of_date: str) -> SupervisorResult:
        # Market Agent는 이 intent의 유일한 root 의존성이다. 실패하면 근거
        # 없는 MarketAnalysis를 만들지 않고 그대로 전파한다.
        market_analysis = await self.market_orchestrator.run(as_of_date=as_of_date)

        return SupervisorResult(
            intent=Intent.MARKET_ONLY,
            market_analysis=market_analysis,
        )

    async def _run_stock_research(
        self,
        request: UserRequest,
        routing_result: RoutingResult,
        business_year: str,
    ) -> SupervisorResult:
        resolved_symbols = await self._resolve_symbols(
            request.symbols, routing_result.mentioned_stock_terms
        )

        if not resolved_symbols:
            raise SupervisorError(
                "stock_research intent인데 특정할 수 있는 종목이 없습니다"
            )

        # 사용자가 명시적으로 물어본 종목이므로 필수 dependency로 취급한다.
        # 하나라도 실패하면 이 요청 전체를 실패시킨다(skip하지 않음).
        stock_analyses = [
            await self.stock_research_orchestrator.run(
                stock_code=symbol, business_year=business_year
            )
            for symbol in resolved_symbols
        ]

        return SupervisorResult(
            intent=Intent.STOCK_RESEARCH,
            resolved_symbols=resolved_symbols,
            stock_analyses=stock_analyses,
        )

    async def _run_portfolio_strategy(
        self,
        request: UserRequest,
        routing_result: RoutingResult,
        as_of_date: str,
        business_year: str,
        investor_profile: InvestorProfile | None,
    ) -> SupervisorResult:
        if investor_profile is None:
            raise SupervisorError(
                "portfolio_strategy intent에는 investor_profile이 필요합니다"
            )

        balance = await self.kiwoom_tools.get_account_balance()
        portfolio_context: PortfolioContext = PortfolioAdapter.from_kiwoom_balance(
            balance
        )

        # Market Agent는 여기서도 root 의존성이다 — 실패 시 전파.
        market_analysis = await self.market_orchestrator.run(as_of_date=as_of_date)

        explicit_symbols = await self._resolve_symbols(
            request.symbols, routing_result.mentioned_stock_terms
        )

        if explicit_symbols:
            # 특정 종목 질문: 그 종목만 분석한다(보유종목 전체를 매번 다시
            # 분석하는 비용을 피함). 사용자가 명시적으로 물어본 종목이므로
            # 필수 dependency로 취급하고, 실패하면 그 종목에 대한 판단을
            # 만들지 않기 위해 이 요청 전체를 실패시킨다(skip하지 않음).
            stock_analyses = [
                await self.stock_research_orchestrator.run(
                    stock_code=symbol, business_year=business_year
                )
                for symbol in explicit_symbols
            ]
            skipped: list[str] = []
        else:
            # 전체 포트폴리오 질문: 보유 종목 전체를 분석하되, 개별 종목의
            # 실패는 skip하고 나머지로 계속 진행한다(예: ETF처럼 Stock
            # Research Agent가 지원하지 않는 종목).
            held_symbols = [
                position.symbol for position in portfolio_context.positions
            ]
            stock_analyses, skipped = await self._run_stock_research_fanout(
                held_symbols, business_year
            )

        strategy_result = None
        try:
            strategy_result = await self.portfolio_orchestrator.run(
                market_analysis=market_analysis,
                stock_analyses=stock_analyses,
                portfolio_context=portfolio_context,
                investor_profile=investor_profile,
            )
        except ReasoningError as error:
            # Portfolio Strategy는 이 그래프의 sink다 — 아무것도 이 결과에
            # 의존하지 않으므로, 이미 확보한 market_analysis/stock_analyses/
            # portfolio_context는 그대로 반환하고 strategy_result만 없이
            # 부분 결과를 허용한다. 근거 없는 StrategyResult를 임의로 만들지
            # 않는다. 원인 진단을 위해 재시도에서 최종적으로 실패한 검증
            # 오류(__cause__)도 함께 기록한다.
            detail = f" ({error.__cause__})" if error.__cause__ else ""
            skipped = [*skipped, f"portfolio_strategy: {error}{detail}"]

        return SupervisorResult(
            intent=Intent.PORTFOLIO_STRATEGY,
            resolved_symbols=explicit_symbols,
            market_analysis=market_analysis,
            stock_analyses=stock_analyses,
            portfolio_context=portfolio_context,
            strategy_result=strategy_result,
            skipped=skipped,
        )

    async def _run_stock_research_fanout(
        self,
        symbols: list[str],
        business_year: str,
    ) -> tuple[list[StockAnalysis], list[str]]:
        outcomes = await asyncio.gather(
            *[
                self._run_stock_research_safe(symbol, business_year)
                for symbol in symbols
            ]
        )

        stock_analyses = [
            outcome for outcome in outcomes if isinstance(outcome, StockAnalysis)
        ]
        skipped = [outcome for outcome in outcomes if isinstance(outcome, str)]

        return stock_analyses, skipped

    async def _run_stock_research_safe(
        self,
        symbol: str,
        business_year: str,
    ) -> StockAnalysis | str:
        # 동시 실행 개수를 제한한다(MAX_CONCURRENT_STOCK_RESEARCH 참고) — 종목
        # 수가 많아도 Kiwoom OAuth 토큰 발급이 한꺼번에 몰리지 않게 한다.
        async with self._stock_research_semaphore:
            try:
                return await self.stock_research_orchestrator.run(
                    stock_code=symbol, business_year=business_year
                )
            except Exception as error:  # noqa: BLE001 - 보유종목 전체 fan-out의
                # 개별 실패 경계. ETF처럼 Stock Research Agent가 지원하지 않는
                # 종목이나 일시적 네트워크 오류 등 어떤 이유로든 실패하면 이
                # 종목만 건너뛰고 나머지로 계속 진행한다(전체 포트폴리오 질문
                # 한정 — 특정 종목 질문은 이 경로를 타지 않는다).
                return f"{symbol}: {error}"

    async def _resolve_symbols(
        self,
        user_symbols: list[str],
        mentioned_terms: list[str],
    ) -> list[str]:
        resolved: list[str] = []

        for term in [*user_symbols, *mentioned_terms]:
            code = await self._resolve_one_symbol(term)

            if code is not None and code not in resolved:
                resolved.append(code)

        return resolved

    async def _resolve_one_symbol(self, term: str) -> str | None:
        term = term.strip()

        if not term:
            return None

        if term.isdigit() and len(term) == 6:
            return term

        # 종목명은 OpenDART 회사 목록과 정확히 일치할 때만 종목코드로
        # 채택한다(모호하거나 없으면 None) — LLM이 종목코드를 스스로
        # 만들어내는 경로를 원천적으로 만들지 않는다.
        return await self.opendart_tools.find_stock_code_by_name(term)


def _default_as_of_date() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _default_business_year() -> str:
    # OpenDART 사업보고서는 해당 연도 다음 해에 공시되므로, 특별히 지정하지
    # 않으면 전년도를 기본값으로 사용한다(기존 데모 스크립트들의 관행과 동일).
    return str(datetime.now(UTC).year - 1)

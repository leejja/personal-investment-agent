from app.discovery.filter_intent import DiscoveryFilter, classify
from app.mcp.kiwoom_tools import KiwoomTools
from app.models.discovery import Candidate, MarketFilter
from app.models.portfolio import PortfolioContext
from app.services.kiwoom import KiwoomStockListItem
from app.services.llm import LLMService

# 이 값은 투자 threshold나 "top N을 고른다"는 선택 기준이 아니다.
# Candidate Discovery가 찾은 후보 전체를 Stock Research Agent(Kiwoom +
# OpenDART + LLM 호출)에 넘기는 fan-out의 실행/비용 안전 한도일 뿐이다.
# 이 한도를 넘으면 후보 중 일부를 임의로 골라내지 않고 Stock Research를
# 0건 실행한 뒤 조건을 더 좁혀달라고 요청한다.
MAX_STOCK_RESEARCH_FANOUT = 10


class DiscoveryError(Exception):
    """Raised when a filter has active constraints but cannot be safely
    turned into a bounded set of candidates for Stock Research."""


class DiscoveryOrchestrator:
    def __init__(
        self,
        kiwoom_tools: KiwoomTools,
        llm_service: LLMService,
    ) -> None:
        self.kiwoom_tools = kiwoom_tools
        self.llm_service = llm_service

    async def run(
        self,
        question: str,
        *,
        portfolio_context: PortfolioContext | None = None,
    ) -> list[Candidate] | None:
        """조건 없는 요청은 None을 반환한다(호출자가 각자의 정책대로
        처리한다 — CANDIDATE_DISCOVERY는 이를 실패로, PORTFOLIO_STRATEGY는
        held-symbols 폴백으로 다룬다). 조건은 있으나 후보가
        MAX_STOCK_RESEARCH_FANOUT을 초과하면 DiscoveryError를 raise한다.
        FilterIntentError(구조화 실패/grounding 실패)는 여기서 삼키지 않고
        그대로 전파한다."""
        universe = await self._fetch_universe()

        known_sectors = sorted(
            {item.sector_name for item, _ in universe if item.sector_name}
        )
        known_sizes = sorted({item.size_name for item, _ in universe if item.size_name})

        discovery_filter = await classify(
            self.llm_service,
            question,
            known_sectors=known_sectors,
            known_sizes=known_sizes,
        )

        if not _has_active_constraint(discovery_filter):
            return None

        held_symbols = (
            {position.symbol for position in portfolio_context.positions}
            if portfolio_context is not None
            else set()
        )

        matched = _apply_filters(universe, discovery_filter, held_symbols)

        if len(matched) > MAX_STOCK_RESEARCH_FANOUT:
            raise DiscoveryError(
                f"조건에 맞는 종목이 {len(matched)}건입니다 "
                f"(Stock Research 실행 한도 {MAX_STOCK_RESEARCH_FANOUT}건 초과). "
                "market/sector/size 조건을 더 좁혀주세요."
            )

        return [
            Candidate(
                symbol=item.symbol,
                name=item.name,
                market=market,
                sector=item.sector_name,
                matched_filters=matched_filters,
            )
            for item, market, matched_filters in matched
        ]

    async def _fetch_universe(
        self,
    ) -> list[tuple[KiwoomStockListItem, MarketFilter]]:
        kospi = await self.kiwoom_tools.get_kospi_stock_list()
        kosdaq = await self.kiwoom_tools.get_kosdaq_stock_list()

        return [(item, MarketFilter.KOSPI) for item in kospi] + [
            (item, MarketFilter.KOSDAQ) for item in kosdaq
        ]


def _has_active_constraint(discovery_filter: DiscoveryFilter) -> bool:
    return bool(
        discovery_filter.market
        or discovery_filter.sector_terms
        or discovery_filter.size_terms
        or discovery_filter.exclude_owned
    )


def _apply_filters(
    universe: list[tuple[KiwoomStockListItem, MarketFilter]],
    discovery_filter: DiscoveryFilter,
    held_symbols: set[str],
) -> list[tuple[KiwoomStockListItem, MarketFilter, dict[str, str]]]:
    matched: list[tuple[KiwoomStockListItem, MarketFilter, dict[str, str]]] = []

    for item, market in universe:
        if not item.symbol or not item.name:
            continue

        matched_filters: dict[str, str] = {}

        if discovery_filter.market is not None:
            if market != discovery_filter.market:
                continue
            matched_filters["market"] = market.value

        if discovery_filter.sector_terms:
            if item.sector_name not in discovery_filter.sector_terms:
                continue
            matched_filters["sector"] = item.sector_name

        if discovery_filter.size_terms:
            if item.size_name not in discovery_filter.size_terms:
                continue
            matched_filters["size"] = item.size_name

        if discovery_filter.exclude_owned:
            if item.symbol in held_symbols:
                continue
            matched_filters["exclude_owned"] = "true"

        matched.append((item, market, matched_filters))

    return matched

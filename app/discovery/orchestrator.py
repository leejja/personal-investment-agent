import asyncio

from app.discovery.filter_intent import DiscoveryFilter, ThemeRequest, classify
from app.mcp.kiwoom_tools import KiwoomTools
from app.models.discovery import Candidate, MarketFilter
from app.models.portfolio import PortfolioContext
from app.services.kiwoom import KiwoomStockListItem, KiwoomThemeGroup
from app.services.llm import LLMService

# 이 값은 투자 threshold나 "top N을 고른다"는 선택 기준이 아니다.
# Candidate Discovery가 찾은 후보 전체를 Stock Research Agent(Kiwoom +
# OpenDART + LLM 호출)에 넘기는 fan-out의 실행/비용 안전 한도일 뿐이다.
# 이 한도를 넘으면 후보 중 일부를 임의로 골라내지 않고 Stock Research를
# 0건 실행한 뒤 조건을 더 좁혀달라고 요청한다.
MAX_STOCK_RESEARCH_FANOUT = 10

# UX-01 실제 E2E 중 ka90002(테마구성종목요청) 연속 호출에서 실제 HTTP 429를
# 관측했다(2026-08-28 dev-log 참고) — 한 concept이 여러 세부 테마로
# grounding되면(예: "반도체" → 8개) _resolve_theme_membership()이 그만큼
# ka90002를 연속 호출하기 때문이다. 정확한 Kiwoom rate limit 수치는
# 확인하지 못했으므로 추측하지 않는다. 대신 Kiwoom 공식 REST API 예제
# 저장소(Kiwoom-Securities/Kiwoom-REST-API)의 연속조회 예제 코드 자체가
# 동일한 목적으로 쓰는 값(REQUEST_DELAY_SECONDS = 0.2)을 그대로 채택해,
# 같은 요청 안에서 서로 다른 테마를 연속 조회할 때만 최소한의 간격을
# 둔다. 이는 retry/backoff가 아니다 — 429가 실제로 발생해도 이 지연은
# 그 실패를 흡수하지 못하고 그대로 예외가 전파된다(의도적으로 이 v1
# 범위에서 retry는 추가하지 않았다 — dev-log Known Issue 참고).
_THEME_MEMBERSHIP_REQUEST_DELAY_SECONDS = 0.2


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
        그대로 전파한다.

        UX-01(Semantic Industry + Grounded Theme): sector_terms는 여전히
        ka10099.upName 기반 Industry axis다(ka10101이 upName보다 세분화돼
        있지 않음을 실측 확인해 별도 연동을 추가하지 않았다 — 2026-08-28
        dev-log 참고). theme_requests는 ka90001/ka90002 기반의 별도 Theme
        axis이며, 사용자가 언급한 세부 테마 개념 중 하나라도 실제
        카탈로그에 대응하는 테마가 없으면(matched_themes가 빈 채로 grounding
        통과) 조용히 나머지 조건만으로 좁히지 않고 DiscoveryError로
        명시적으로 실패시킨다."""
        universe = await self._fetch_universe()
        theme_catalog = await self.kiwoom_tools.get_theme_groups()

        known_sectors = sorted(
            {item.sector_name for item, _ in universe if item.sector_name}
        )
        known_sizes = sorted({item.size_name for item, _ in universe if item.size_name})
        known_themes = sorted(
            {group.theme_name for group in theme_catalog if group.theme_name}
        )

        discovery_filter = await classify(
            self.llm_service,
            question,
            known_sectors=known_sectors,
            known_sizes=known_sizes,
            known_themes=known_themes,
        )

        if not _has_active_constraint(discovery_filter):
            return None

        unsupported_concepts = [
            theme_request.concept
            for theme_request in discovery_filter.theme_requests
            if not theme_request.matched_themes
        ]
        if unsupported_concepts:
            raise DiscoveryError(
                "현재 지원하지 않는 테마 조건입니다: "
                f"{', '.join(unsupported_concepts)}. 다른 조건으로 다시 시도해주세요."
            )

        held_symbols = (
            {position.symbol for position in portfolio_context.positions}
            if portfolio_context is not None
            else set()
        )

        stock_theme_membership, theme_name_concepts = await self._resolve_theme_membership(
            discovery_filter.theme_requests, theme_catalog
        )

        matched = _apply_filters(
            universe,
            discovery_filter,
            held_symbols,
            stock_theme_membership,
            theme_name_concepts,
        )

        if len(matched) > MAX_STOCK_RESEARCH_FANOUT:
            raise DiscoveryError(
                f"조건에 맞는 종목이 {len(matched)}건입니다 "
                f"(Stock Research 실행 한도 {MAX_STOCK_RESEARCH_FANOUT}건 초과). "
                "market/sector/size/theme 조건을 더 좁혀주세요."
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

    async def _resolve_theme_membership(
        self,
        theme_requests: list[ThemeRequest],
        theme_catalog: list[KiwoomThemeGroup],
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """theme_requests가 비어 있으면(Theme axis 미사용) 빈 dict 2개를
        그대로 반환한다 — 호출자는 이를 "Theme 제약 없음"으로 해석한다.

        Theme membership은 사전 구축하지 않는다: 실제로 grounding을
        통과한(=실제 카탈로그에 존재하는) 테마 이름에 대해서만, 그것도
        전체 카탈로그가 아니라 이번 요청에 필요한 테마만 ka90002로 lazy
        조회한다(전체 카탈로그를 대상으로 한 사전 구축은 하지 않는다).

        반환값:
        - stock_theme_membership: 종목코드 -> 이 종목이 속한 매칭된 테마명
          집합(여러 concept이 같은 종목을 가리켜도 한 번만 조회한다 —
          같은 테마 이름이 여러 concept에서 겹쳐도 ka90002는 테마당 1회만
          호출한다).
        - theme_name_to_concepts: 테마명 -> 그 테마를 요청하게 만든
          concept 집합(evidence/traceability용, Candidate.matched_filters
          구성에 사용).
        """
        if not theme_requests:
            return {}, {}

        theme_code_by_name = {group.theme_name: group.theme_code for group in theme_catalog}

        theme_name_to_concepts: dict[str, set[str]] = {}
        for theme_request in theme_requests:
            for theme_name in theme_request.matched_themes:
                theme_name_to_concepts.setdefault(theme_name, set()).add(
                    theme_request.concept
                )

        stock_theme_membership: dict[str, set[str]] = {}
        for index, theme_name in enumerate(theme_name_to_concepts):
            if index > 0:
                # 이전 테마 조회 직후에만 대기한다(첫 호출 전에는 대기하지
                # 않음) — 서로 다른 테마를 연속 호출할 때만 간격을 둔다.
                await asyncio.sleep(_THEME_MEMBERSHIP_REQUEST_DELAY_SECONDS)

            theme_code = theme_code_by_name[theme_name]
            members = await self.kiwoom_tools.get_theme_stocks(theme_code)
            for member in members:
                stock_theme_membership.setdefault(member.stock_code, set()).add(theme_name)

        return stock_theme_membership, theme_name_to_concepts


def _has_active_constraint(discovery_filter: DiscoveryFilter) -> bool:
    return bool(
        discovery_filter.market
        or discovery_filter.sector_terms
        or discovery_filter.size_terms
        or discovery_filter.theme_requests
        or discovery_filter.exclude_owned
    )


def _apply_filters(
    universe: list[tuple[KiwoomStockListItem, MarketFilter]],
    discovery_filter: DiscoveryFilter,
    held_symbols: set[str],
    stock_theme_membership: dict[str, set[str]],
    theme_name_to_concepts: dict[str, set[str]],
) -> list[tuple[KiwoomStockListItem, MarketFilter, dict[str, str]]]:
    # Theme axis는 "같은 concept의 여러 테마 = UNION"이 이미
    # stock_theme_membership에 반영돼 있다(어떤 matched theme에든 속하면
    # 포함) — 서로 다른 axis(market/size/industry/theme/ownership) 사이는
    # 이 함수 전체가 매 axis를 순차 continue로 걸러내는 INTERSECTION이다.
    theme_axis_active = bool(discovery_filter.theme_requests)

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

        if theme_axis_active:
            matched_theme_names = stock_theme_membership.get(item.symbol)
            if not matched_theme_names:
                continue
            matched_filters["theme"] = ",".join(sorted(matched_theme_names))
            matched_concepts = {
                concept
                for theme_name in matched_theme_names
                for concept in theme_name_to_concepts.get(theme_name, set())
            }
            matched_filters["theme_concept"] = ",".join(sorted(matched_concepts))

        if discovery_filter.exclude_owned:
            if item.symbol in held_symbols:
                continue
            matched_filters["exclude_owned"] = "true"

        matched.append((item, market, matched_filters))

    return matched

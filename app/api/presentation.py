from app.models.discovery import Candidate
from app.models.market import MarketAnalysis
from app.models.presentation import (
    DiscoverySummary,
    MarketSummary,
    PortfolioSummary,
    PresentationResult,
    RecommendationSummary,
    StockSummary,
)
from app.models.stock import StockAnalysis
from app.models.strategy import StrategyResult
from app.models.supervisor import Intent, SupervisorResult

# build_presentation()은 순수 함수다 — LLM이나 어떤 외부 API/Service도
# 인자로 받지 않는다(함수 시그니처 자체가 SupervisorResult -> PresentationResult
# 뿐이라 새 사실/판단을 만들 수단이 없다). 여기서 하는 일은 SupervisorResult에
# 이미 존재하는 값을 그대로 옮기거나(pass-through) 개수를 세는 것뿐이며,
# action/rationale 같은 투자 판단 필드는 절대 재계산하지 않는다.


def build_presentation(result: SupervisorResult) -> PresentationResult:
    market = (
        _build_market_summary(result.market_analysis)
        if result.market_analysis is not None
        else None
    )

    # PORTFOLIO_STRATEGY도 stock_analyses를 갖고 있지만(보유종목 fan-out
    # 결과), 그 종목별 상세는 PortfolioSummary.recommendations(간결한
    # RecommendationSummary)로만 노출한다 — 여기서 StockSummary까지 함께
    # 채우면 원래 문제였던 "응답이 너무 길다"가 그대로 재현된다.
    stocks = (
        [_build_stock_summary(stock_analysis) for stock_analysis in result.stock_analyses]
        if result.intent in (Intent.STOCK_RESEARCH, Intent.CANDIDATE_DISCOVERY)
        else []
    )

    discovery = (
        _build_discovery_summary(result.candidates)
        if result.intent == Intent.CANDIDATE_DISCOVERY
        else None
    )

    portfolio = (
        _build_portfolio_summary(result.strategy_result)
        if result.intent == Intent.PORTFOLIO_STRATEGY
        and result.strategy_result is not None
        else None
    )

    return PresentationResult(
        intent=result.intent,
        headline=_build_headline(result),
        market=market,
        stocks=stocks,
        discovery=discovery,
        portfolio=portfolio,
        skipped=result.skipped,
    )


def _build_headline(result: SupervisorResult) -> str | None:
    # 새 문장을 생성하지 않는다 — 각 Agent가 이미 만든 grounded summary/
    # thesis를 그대로 재사용하거나(대부분), 값만 채우는 템플릿 문자열
    # (candidate 개수) 정도만 예외로 허용한다.
    if result.intent == Intent.MARKET_ONLY:
        return result.market_analysis.summary if result.market_analysis else None

    if result.intent == Intent.STOCK_RESEARCH:
        # 여러 종목을 하나의 문장으로 합치는 것 자체가 새로운 종합 판단이
        # 될 수 있으므로, 단일 종목일 때만 그 investment_thesis를 그대로
        # 쓴다. 종목별 thesis는 어차피 각 StockSummary에 그대로 남는다.
        if len(result.stock_analyses) == 1:
            return result.stock_analyses[0].investment_thesis
        return None

    if result.intent == Intent.CANDIDATE_DISCOVERY:
        return f"{len(result.candidates)}건의 후보를 찾았습니다"

    if result.intent == Intent.PORTFOLIO_STRATEGY:
        return result.strategy_result.summary if result.strategy_result else None

    return None


def _build_market_summary(market_analysis: MarketAnalysis) -> MarketSummary:
    return MarketSummary(
        regime=market_analysis.regime,
        risk_level=market_analysis.risk_level,
        summary=market_analysis.summary,
        confidence=market_analysis.confidence,
    )


def _build_stock_summary(stock_analysis: StockAnalysis) -> StockSummary:
    price = stock_analysis.price

    return StockSummary(
        symbol=stock_analysis.symbol,
        name=stock_analysis.name,
        price=price.price if price is not None else None,
        change_pct=price.change_pct if price is not None else None,
        investment_thesis=stock_analysis.investment_thesis,
        risks=stock_analysis.risks,
        catalysts=stock_analysis.catalysts,
        risk_level=stock_analysis.risk_level,
        confidence=stock_analysis.confidence,
    )


def _build_discovery_summary(candidates: list[Candidate]) -> DiscoverySummary:
    return DiscoverySummary(
        candidate_count=len(candidates),
        candidates=candidates,
    )


def _build_portfolio_summary(strategy_result: StrategyResult) -> PortfolioSummary:
    recommendations = [
        RecommendationSummary(
            symbol=recommendation.symbol,
            name=recommendation.name,
            action=recommendation.action,
            current_weight=recommendation.current_weight,
            rationale=recommendation.rationale,
            conditions=recommendation.conditions,
        )
        for recommendation in strategy_result.recommendations
    ]

    return PortfolioSummary(
        portfolio_risk=strategy_result.portfolio_risk,
        confidence=strategy_result.confidence,
        summary=strategy_result.summary,
        recommendation_count=len(recommendations),
        recommendations=recommendations,
    )

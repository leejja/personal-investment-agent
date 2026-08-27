from pydantic import BaseModel

from app.models.common import AnalysisConfidence
from app.models.market import MarketAnalysis
from app.models.portfolio import InvestorProfile, PortfolioContext, PortfolioPosition
from app.models.stock import StockAnalysis
from app.models.strategy import InvestmentAction

# 미보유 종목에는 "새로 사거나(BUY) 진입을 피한다(AVOID)"만 물리적으로 말이 된다.
# 보유 종목에는 그 반대로 "이미 있는 포지션을 어떻게 다룰지"만 말이 된다.
# 이 매핑은 시장/재무 판단이 아니라 순수한 구조적 사실이므로 deterministic
# layer에서 고정하고, reasoning.py가 이 집합 밖의 action을 반환하면 검증
# 실패로 처리한다.
_UNHELD_ACTIONS: frozenset[InvestmentAction] = frozenset(
    {InvestmentAction.BUY, InvestmentAction.AVOID}
)
_HELD_ACTIONS: frozenset[InvestmentAction] = frozenset(
    {
        InvestmentAction.ADD,
        InvestmentAction.HOLD,
        InvestmentAction.REDUCE,
        InvestmentAction.SELL,
    }
)


class DeterministicFact(BaseModel):
    id: str
    description: str
    source: str


class SymbolContext(BaseModel):
    symbol: str
    name: str
    current_weight: float | None
    allowed_actions: list[InvestmentAction]


class PortfolioDeterministicAnalysisResult(BaseModel):
    symbol_contexts: list[SymbolContext]
    facts: list[DeterministicFact]
    max_confidence: AnalysisConfidence


def analyze(
    market_analysis: MarketAnalysis,
    stock_analyses: list[StockAnalysis],
    portfolio_context: PortfolioContext,
    investor_profile: InvestorProfile,
) -> PortfolioDeterministicAnalysisResult:
    positions_by_symbol = {
        position.symbol: position for position in portfolio_context.positions
    }

    facts = _build_portfolio_facts(market_analysis, portfolio_context, investor_profile)

    symbol_contexts: list[SymbolContext] = []
    for stock in stock_analyses:
        position = positions_by_symbol.get(stock.symbol)

        symbol_contexts.append(
            SymbolContext(
                symbol=stock.symbol,
                name=stock.name,
                current_weight=position.weight if position is not None else None,
                allowed_actions=sorted(
                    _HELD_ACTIONS if position is not None else _UNHELD_ACTIONS,
                    key=lambda action: action.value,
                ),
            )
        )
        facts.extend(_build_symbol_facts(stock, position))

    return PortfolioDeterministicAnalysisResult(
        symbol_contexts=symbol_contexts,
        facts=facts,
        max_confidence=_max_confidence(stock_analyses),
    )


def _build_portfolio_facts(
    market_analysis: MarketAnalysis,
    portfolio_context: PortfolioContext,
    investor_profile: InvestorProfile,
) -> list[DeterministicFact]:
    # 평가(과도하다/적절하다 등)를 담지 않고 수치·라벨 사실만 남긴다.
    # 이 값들을 어떻게 해석할지는 reasoning 단계(LLM)의 몫이다.
    facts: list[DeterministicFact] = [
        DeterministicFact(
            id="market_regime",
            description=f"현재 시장 regime은 {market_analysis.regime.value}",
            source="MarketAnalysis",
        ),
        DeterministicFact(
            id="market_risk_level",
            description=f"현재 시장 risk_level은 {market_analysis.risk_level.value}",
            source="MarketAnalysis",
        ),
        DeterministicFact(
            id="investor_risk_tolerance",
            description=f"사용자 risk_tolerance는 {investor_profile.risk_tolerance.value}",
            source="InvestorProfile",
        ),
    ]

    cash_weight = _cash_weight(portfolio_context)
    if cash_weight is not None:
        facts.append(
            DeterministicFact(
                id="portfolio_cash_weight",
                description=f"현금 비중은 {cash_weight * 100:.1f}%",
                source="PortfolioContext",
            )
        )
        facts.append(
            DeterministicFact(
                id="portfolio_equity_exposure",
                description=f"주식(현금 제외) 노출 비중은 {(1 - cash_weight) * 100:.1f}%",
                source="PortfolioContext",
            )
        )

    top1_weight = _top_n_weight(portfolio_context.positions, 1)
    if top1_weight is not None:
        facts.append(
            DeterministicFact(
                id="portfolio_top1_weight",
                description=f"단일 최대 비중 종목의 비중은 {top1_weight * 100:.1f}%",
                source="PortfolioContext",
            )
        )

    top3_weight = _top_n_weight(portfolio_context.positions, 3)
    if top3_weight is not None:
        top3_count = min(3, len(portfolio_context.positions))
        facts.append(
            DeterministicFact(
                id="portfolio_top3_weight",
                description=f"상위 {top3_count}종목 합산 비중은 {top3_weight * 100:.1f}%",
                source="PortfolioContext",
            )
        )

    if investor_profile.investment_horizon_months is not None:
        facts.append(
            DeterministicFact(
                id="investor_horizon",
                description=(
                    f"사용자 투자 기간은 {investor_profile.investment_horizon_months}개월"
                ),
                source="InvestorProfile",
            )
        )

    if investor_profile.objectives:
        facts.append(
            DeterministicFact(
                id="investor_objectives",
                description=f"사용자 투자 목표: {', '.join(investor_profile.objectives)}",
                source="InvestorProfile",
            )
        )

    if investor_profile.constraints:
        facts.append(
            DeterministicFact(
                id="investor_constraints",
                description=f"사용자 제약 조건: {', '.join(investor_profile.constraints)}",
                source="InvestorProfile",
            )
        )

    return facts


def _build_symbol_facts(
    stock: StockAnalysis,
    position: PortfolioPosition | None,
) -> list[DeterministicFact]:
    label = f"{stock.name}({stock.symbol})"

    facts = [
        DeterministicFact(
            id=f"{stock.symbol}_stock_risk_level",
            description=f"{label}의 종목 risk_level은 {stock.risk_level.value}",
            source="StockAnalysis",
        ),
        DeterministicFact(
            id=f"{stock.symbol}_stock_confidence",
            description=f"{label} 분석의 confidence는 {stock.confidence.value}",
            source="StockAnalysis",
        ),
    ]

    if position is not None:
        facts.append(
            DeterministicFact(
                id=f"{stock.symbol}_current_weight",
                description=f"{label}의 현재 포트폴리오 비중은 {position.weight * 100:.1f}%",
                source="PortfolioContext",
            )
        )
        facts.append(
            DeterministicFact(
                id=f"{stock.symbol}_profit_loss_pct",
                description=f"{label}의 평가손익률은 {position.profit_loss_pct:+.1f}%",
                source="PortfolioContext",
            )
        )
    else:
        facts.append(
            DeterministicFact(
                id=f"{stock.symbol}_not_held",
                description=f"{label}은 현재 미보유",
                source="PortfolioContext",
            )
        )

    return facts


def _cash_weight(portfolio_context: PortfolioContext) -> float | None:
    if portfolio_context.total_value <= 0:
        return None

    return portfolio_context.cash / portfolio_context.total_value


def _top_n_weight(positions: list[PortfolioPosition], n: int) -> float | None:
    if not positions:
        return None

    sorted_weights = sorted((position.weight for position in positions), reverse=True)
    return sum(sorted_weights[:n])


def _max_confidence(stock_analyses: list[StockAnalysis]) -> AnalysisConfidence:
    # MarketAnalysis/PortfolioContext/InvestorProfile은 함수 시그니처상 항상
    # 필수 입력이라 호출 시점에 이미 존재가 보장된다. 유일한 가변 요소는
    # 판단 대상 종목(StockAnalysis)이 하나라도 주어졌는지 여부다.
    # v1은 공시/뉴스/포지션 사이징 근거가 없으므로 HIGH를 절대 반환하지
    # 않는다(Stock Research Agent / Market Agent와 동일 원칙).
    if stock_analyses:
        return AnalysisConfidence.MEDIUM

    return AnalysisConfidence.LOW

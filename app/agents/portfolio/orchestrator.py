from app.agents.portfolio import analysis
from app.agents.portfolio.reasoning import ReasoningResult, generate_reasoning
from app.models.common import AnalysisConfidence, Evidence
from app.models.market import MarketAnalysis
from app.models.portfolio import InvestorProfile, PortfolioContext
from app.models.stock import StockAnalysis
from app.models.strategy import PositionRecommendation, StrategyResult
from app.services.llm import LLMService

_CONFIDENCE_RANK: dict[AnalysisConfidence, int] = {
    AnalysisConfidence.LOW: 0,
    AnalysisConfidence.MEDIUM: 1,
    AnalysisConfidence.HIGH: 2,
}


class PortfolioStrategyOrchestrator:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    async def run(
        self,
        market_analysis: MarketAnalysis,
        stock_analyses: list[StockAnalysis],
        portfolio_context: PortfolioContext,
        investor_profile: InvestorProfile,
    ) -> StrategyResult:
        analysis_result = analysis.analyze(
            market_analysis=market_analysis,
            stock_analyses=stock_analyses,
            portfolio_context=portfolio_context,
            investor_profile=investor_profile,
        )

        # symbol / fact-id / allowed-action 검증은 모두 reasoning.py의 재시도
        # 루프 안에서 이미 끝난 상태로 돌아온다. 여기서 다시 검증하지 않는다.
        # ReasoningError는 여기서 삼키지 않고 그대로 전파한다. 근거 없는
        # fallback StrategyResult를 임의로 만들지 않는다.
        reasoning_result = await generate_reasoning(
            self.llm_service,
            analysis_result,
        )

        confidence = _min_confidence(
            reasoning_result.suggested_confidence,
            analysis_result.max_confidence,
        )

        return StrategyResult(
            summary=reasoning_result.portfolio_summary,
            recommendations=_build_recommendations(analysis_result, reasoning_result),
            portfolio_risk=reasoning_result.suggested_portfolio_risk,
            confidence=confidence,
            evidence=_build_evidence(analysis_result),
        )


def _min_confidence(
    suggested: AnalysisConfidence,
    max_allowed: AnalysisConfidence,
) -> AnalysisConfidence:
    if _CONFIDENCE_RANK[suggested] <= _CONFIDENCE_RANK[max_allowed]:
        return suggested

    return max_allowed


def _build_recommendations(
    analysis_result: analysis.PortfolioDeterministicAnalysisResult,
    reasoning_result: ReasoningResult,
) -> list[PositionRecommendation]:
    current_weight_by_symbol = {
        context.symbol: context.current_weight
        for context in analysis_result.symbol_contexts
    }
    name_by_symbol = {
        context.symbol: context.name for context in analysis_result.symbol_contexts
    }

    return [
        PositionRecommendation(
            symbol=recommendation.symbol,
            name=name_by_symbol[recommendation.symbol],
            action=recommendation.suggested_action,
            current_weight=current_weight_by_symbol[recommendation.symbol],
            # v1에는 포지션 사이징 근거(리스크 버짓, 밸류에이션 모델 등)가
            # 없다. reasoning.py의 응답 스키마 자체에 숫자 필드가 없어 LLM이
            # 애초에 값을 만들 통로가 없지만, 최종 조립 지점인 여기서도
            # 명시적으로 None을 강제해 어떤 경로로도 근거 없는 숫자가 섞이지
            # 않도록 한다(Stock Research Agent의 target_price와 동일 원칙).
            target_weight=None,
            rationale=recommendation.rationale,
            conditions=recommendation.conditions,
        )
        for recommendation in reasoning_result.recommendations
    ]


def _build_evidence(
    analysis_result: analysis.PortfolioDeterministicAnalysisResult,
) -> list[Evidence]:
    return [
        Evidence(source=fact.source, description=fact.description)
        for fact in analysis_result.facts
    ]

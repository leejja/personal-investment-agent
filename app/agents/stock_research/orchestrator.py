from app.agents.stock_research import analysis
from app.agents.stock_research.reasoning import generate_reasoning
from app.mcp.kiwoom_tools import KiwoomTools
from app.mcp.opendart_tools import KeyFinancials, OpenDartTools
from app.models.common import AnalysisConfidence, Evidence
from app.models.stock import StockAnalysis
from app.services.llm import LLMService

_CONFIDENCE_RANK: dict[AnalysisConfidence, int] = {
    AnalysisConfidence.LOW: 0,
    AnalysisConfidence.MEDIUM: 1,
    AnalysisConfidence.HIGH: 2,
}


class StockResearchOrchestrator:
    def __init__(
        self,
        kiwoom_tools: KiwoomTools,
        opendart_tools: OpenDartTools,
        llm_service: LLMService,
    ) -> None:
        self.kiwoom_tools = kiwoom_tools
        self.opendart_tools = opendart_tools
        self.llm_service = llm_service

    async def run(
        self,
        stock_code: str,
        business_year: str,
        report_code: str = "11011",
    ) -> StockAnalysis:
        stock_info = await self.kiwoom_tools.get_stock_info(
            stock_code=stock_code,
        )

        key_financials = await self.opendart_tools.get_key_financials(
            stock_code=stock_code,
            business_year=business_year,
            report_code=report_code,
        )

        analysis_result = analysis.analyze(stock_info, key_financials)

        # ReasoningError는 여기서 삼키지 않고 그대로 전파한다.
        # 근거 없는 fallback StockAnalysis를 임의로 만들지 않는다.
        reasoning_result = await generate_reasoning(
            self.llm_service,
            analysis_result,
        )

        confidence = _min_confidence(
            reasoning_result.suggested_confidence,
            analysis_result.max_confidence,
        )

        return StockAnalysis(
            symbol=analysis_result.price.symbol,
            name=analysis_result.price.name,
            price=analysis_result.price,
            financials=analysis_result.financials,
            investment_thesis=reasoning_result.investment_thesis,
            catalysts=reasoning_result.catalysts,
            risks=reasoning_result.risks,
            scenarios=reasoning_result.scenarios,
            # risk_level은 analysis.py(deterministic) 결과만 사용한다.
            # reasoning_result에는 risk_level 필드 자체가 없으므로
            # LLM이 이 값을 바꿀 수 없다.
            risk_level=analysis_result.risk_level,
            confidence=confidence,
            evidence=_build_evidence(analysis_result, key_financials),
        )


def _min_confidence(
    suggested: AnalysisConfidence,
    max_allowed: AnalysisConfidence,
) -> AnalysisConfidence:
    if _CONFIDENCE_RANK[suggested] <= _CONFIDENCE_RANK[max_allowed]:
        return suggested

    return max_allowed


def _build_evidence(
    analysis_result: analysis.DeterministicAnalysisResult,
    key_financials: KeyFinancials,
) -> list[Evidence]:
    evidence = [
        Evidence(source=fact.source, description=fact.description)
        for fact in analysis_result.facts
    ]

    evidence.append(
        Evidence(
            source="Kiwoom",
            description="Kiwoom 주식 기본정보 조회 (get_stock_info)",
            reference=analysis_result.price.symbol,
        )
    )

    evidence.append(
        Evidence(
            source="OpenDART",
            description="OpenDART 핵심 재무정보 조회 (get_key_financials)",
            reference=key_financials.corp_code,
        )
    )

    return evidence

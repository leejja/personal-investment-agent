from datetime import UTC, datetime, timedelta

from app.agents.market import analysis
from app.agents.market.reasoning import generate_reasoning
from app.mcp.ecos_tools import EcosTools
from app.models.common import AnalysisConfidence, Evidence
from app.models.market import MarketAnalysis, MarketIndicator
from app.services.llm import LLMService

# 60거래일(약 84일) 대비 여유를 두고 넉넉히 데이터를 확보한다. 국내 공휴일이
# 몰리는 구간(설/추석 연휴 등)에서도 60거래일치 데이터가 충분히 들어오도록
# 하기 위함이며, 정확히 어느 지점이 20/60일 전인지는 analysis.py가 판단한다.
LOOKBACK_DAYS = 100

_CONFIDENCE_RANK: dict[AnalysisConfidence, int] = {
    AnalysisConfidence.LOW: 0,
    AnalysisConfidence.MEDIUM: 1,
    AnalysisConfidence.HIGH: 2,
}


class MarketOrchestrator:
    def __init__(
        self,
        ecos_tools: EcosTools,
        llm_service: LLMService,
    ) -> None:
        self.ecos_tools = ecos_tools
        self.llm_service = llm_service

    async def run(self, as_of_date: str) -> MarketAnalysis:
        start_date = _date_minus(as_of_date, LOOKBACK_DAYS)

        base_rate_points = await self.ecos_tools.get_base_rate(
            start_date=start_date,
            end_date=as_of_date,
        )
        exchange_rate_points = await self.ecos_tools.get_exchange_rate(
            start_date=start_date,
            end_date=as_of_date,
        )
        kospi_points = await self.ecos_tools.get_kospi_index(
            start_date=start_date,
            end_date=as_of_date,
        )
        kosdaq_points = await self.ecos_tools.get_kosdaq_index(
            start_date=start_date,
            end_date=as_of_date,
        )

        analysis_result = analysis.analyze(
            as_of_date=as_of_date,
            base_rate_points=base_rate_points,
            exchange_rate_points=exchange_rate_points,
            kospi_points=kospi_points,
            kosdaq_points=kosdaq_points,
        )

        # ReasoningError(구조화 실패 및 grounding 검증 실패 포함)는 여기서
        # 삼키지 않고 그대로 전파한다. 근거 없는 fallback MarketAnalysis를
        # 임의로 만들지 않는다.
        reasoning_result = await generate_reasoning(
            self.llm_service,
            analysis_result,
        )

        confidence = _min_confidence(
            reasoning_result.suggested_confidence,
            analysis_result.max_confidence,
        )

        return MarketAnalysis(
            regime=reasoning_result.suggested_regime,
            risk_level=reasoning_result.suggested_risk_level,
            summary=reasoning_result.summary,
            indicators=_build_indicators(analysis_result),
            confidence=confidence,
            evidence=_build_evidence(analysis_result, start_date, as_of_date),
        )


def _date_minus(date_str: str, days: int) -> str:
    parsed = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=UTC)
    return (parsed - timedelta(days=days)).strftime("%Y%m%d")


def _min_confidence(
    suggested: AnalysisConfidence,
    max_allowed: AnalysisConfidence,
) -> AnalysisConfidence:
    if _CONFIDENCE_RANK[suggested] <= _CONFIDENCE_RANK[max_allowed]:
        return suggested

    return max_allowed


def _build_indicators(
    result: analysis.MarketDeterministicAnalysisResult,
) -> list[MarketIndicator]:
    indicators: list[MarketIndicator] = []

    if result.base_rate_latest is not None:
        indicators.append(
            MarketIndicator(
                name="한국 기준금리",
                value=result.base_rate_latest,
                unit="%",
                change=result.base_rate_change_bp,
                description="변경폭 단위: bp, 최근 60일 대비" if result.base_rate_change_bp is not None else None,
            )
        )

    if result.usd_krw_latest is not None:
        indicators.append(
            MarketIndicator(
                name="USD/KRW",
                value=result.usd_krw_latest,
                unit="원",
                change=result.usd_krw_change_20d_pct,
                description="변화율 단위: %, 최근 20거래일 대비" if result.usd_krw_change_20d_pct is not None else None,
            )
        )

    if result.kospi_latest is not None:
        indicators.append(
            MarketIndicator(
                name="KOSPI",
                value=result.kospi_latest,
                unit="포인트",
                change=result.kospi_change_20d_pct,
                description="변화율 단위: %, 최근 20거래일 대비" if result.kospi_change_20d_pct is not None else None,
            )
        )

    if result.kosdaq_latest is not None:
        indicators.append(
            MarketIndicator(
                name="KOSDAQ",
                value=result.kosdaq_latest,
                unit="포인트",
                change=result.kosdaq_change_20d_pct,
                description="변화율 단위: %, 최근 20거래일 대비" if result.kosdaq_change_20d_pct is not None else None,
            )
        )

    return indicators


def _build_evidence(
    result: analysis.MarketDeterministicAnalysisResult,
    start_date: str,
    end_date: str,
) -> list[Evidence]:
    evidence = [
        Evidence(source=fact.source, description=fact.description)
        for fact in result.facts
    ]

    evidence.append(
        Evidence(
            source="ECOS",
            description=(
                "ECOS 기준금리/환율/KOSPI/KOSDAQ 조회 "
                "(get_base_rate/get_exchange_rate/get_kospi_index/get_kosdaq_index)"
            ),
            reference=f"{start_date}~{end_date}",
        )
    )

    return evidence

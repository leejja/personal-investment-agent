import argparse
import asyncio

from app.agents.market.orchestrator import MarketOrchestrator
from app.agents.portfolio.orchestrator import PortfolioStrategyOrchestrator
from app.agents.stock_research.orchestrator import StockResearchOrchestrator
from app.config import settings
from app.discovery.orchestrator import DiscoveryOrchestrator
from app.mcp.ecos_tools import EcosTools
from app.mcp.kiwoom_tools import KiwoomTools
from app.mcp.opendart_tools import OpenDartTools
from app.models.common import RiskLevel, UserRequest
from app.models.portfolio import InvestorProfile
from app.services.ecos import EcosService
from app.services.kiwoom import KiwoomService
from app.services.llm import LLMService
from app.services.opendart import OpenDartService
from app.supervisor.orchestrator import SupervisorOrchestrator

_SCENARIOS = {
    "market": UserRequest(question="요즘 시장 상황 어때?"),
    "stock": UserRequest(question="삼성전자 어때?"),
    "portfolio": UserRequest(question="내 포트폴리오 분석해줘"),
    "portfolio-stock": UserRequest(question="내가 삼성전자를 더 사도 될까?"),
    "discovery": UserRequest(question="반도체 종목 중 후보 찾아줘"),
    "personalized-discovery": UserRequest(
        question="내 포트폴리오에 없는 반도체 후보 찾아줘"
    ),
}

# InvestorProfile은 아직 데이터 소스가 없다(Portfolio Strategy Agent 데모와
# 동일한 이유). Supervisor 데모에서도 고정된 예시 프로필을 사용한다.
_DEMO_INVESTOR_PROFILE = InvestorProfile(
    risk_tolerance=RiskLevel.MEDIUM,
    investment_horizon_months=12,
    target_return_pct=15.0,
    objectives=["장기 자산 증식"],
    constraints=[],
)


async def main(scenario: str) -> None:
    kiwoom_service = KiwoomService(
        app_key=settings.kiwoom_app_key,
        secret_key=settings.kiwoom_secret_key,
    )
    kiwoom_tools = KiwoomTools(service=kiwoom_service)

    opendart_service = OpenDartService(api_key=settings.opendart_api_key)
    opendart_tools = OpenDartTools(service=opendart_service)

    ecos_service = EcosService(api_key=settings.ecos_api_key)
    ecos_tools = EcosTools(service=ecos_service)

    # Supervisor 경로는 routing LLM 호출 + 최대 3개 Agent의 LLM 호출까지
    # 이어질 수 있어 Portfolio Strategy Agent 데모와 동일한 이유로 기본
    # 30초보다 넉넉한 timeout을 사용한다.
    llm_service = LLMService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout=90.0,
    )

    supervisor = SupervisorOrchestrator(
        llm_service=llm_service,
        market_orchestrator=MarketOrchestrator(
            ecos_tools=ecos_tools, llm_service=llm_service
        ),
        stock_research_orchestrator=StockResearchOrchestrator(
            kiwoom_tools=kiwoom_tools,
            opendart_tools=opendart_tools,
            llm_service=llm_service,
        ),
        portfolio_orchestrator=PortfolioStrategyOrchestrator(
            llm_service=llm_service
        ),
        discovery_orchestrator=DiscoveryOrchestrator(
            kiwoom_tools=kiwoom_tools, llm_service=llm_service
        ),
        kiwoom_tools=kiwoom_tools,
        opendart_tools=opendart_tools,
    )

    request = _SCENARIOS[scenario]
    print(f"=== Supervisor v1: scenario={scenario} ===")
    print(f"question: {request.question}\n")

    result = await supervisor.run(
        request,
        investor_profile=_DEMO_INVESTOR_PROFILE,
    )

    print(f"intent           : {result.intent.value}")
    print(f"resolved_symbols : {result.resolved_symbols}\n")

    if result.candidates:
        print("--- Candidates ---")
        for candidate in result.candidates:
            print(
                f"[{candidate.market.value}] {candidate.name}({candidate.symbol}) "
                f"sector={candidate.sector} matched_filters={candidate.matched_filters}"
            )
        print()

    if result.market_analysis is not None:
        m = result.market_analysis
        print("--- MarketAnalysis ---")
        print(f"regime={m.regime.value} risk_level={m.risk_level.value} confidence={m.confidence.value}")
        print(m.summary)
        print()

    if result.stock_analyses:
        print("--- StockAnalysis ---")
        for stock in result.stock_analyses:
            print(f"[{stock.symbol}] {stock.name} risk_level={stock.risk_level.value} confidence={stock.confidence.value}")
            print(f"  {stock.investment_thesis}")
        print()

    if result.portfolio_context is not None:
        pc = result.portfolio_context
        print("--- PortfolioContext ---")
        print(f"positions={len(pc.positions)} total_value={pc.total_value:,.0f} cash={pc.cash:,.0f}")
        print()

    if result.strategy_result is not None:
        s = result.strategy_result
        print("--- StrategyResult ---")
        print(f"portfolio_risk={s.portfolio_risk.value} confidence={s.confidence.value}")
        print(s.summary)
        for rec in s.recommendations:
            current = f"{rec.current_weight:.1%}" if rec.current_weight is not None else "미보유"
            target = f"{rec.target_weight:.1%}" if rec.target_weight is not None else "-"
            print(f"[{rec.action.value.upper()}] {rec.name}({rec.symbol}) current={current} target={target}")
            print(f"  {rec.rationale}")
        print()

    if result.skipped:
        print("--- Skipped ---")
        for note in result.skipped:
            print(f"- {note}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "scenario",
        choices=sorted(_SCENARIOS),
        help="which UserRequest scenario to run",
    )
    args = parser.parse_args()

    asyncio.run(main(args.scenario))

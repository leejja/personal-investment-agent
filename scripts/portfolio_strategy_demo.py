import asyncio
from datetime import UTC, datetime

from app.agents.market.orchestrator import MarketOrchestrator
from app.agents.portfolio.orchestrator import PortfolioStrategyOrchestrator
from app.agents.stock_research.orchestrator import StockResearchOrchestrator
from app.config import settings
from app.mcp.ecos_tools import EcosTools
from app.mcp.kiwoom_tools import KiwoomTools
from app.mcp.opendart_tools import OpenDartTools
from app.models.common import RiskLevel
from app.models.portfolio import InvestorProfile
from app.services.ecos import EcosService
from app.services.kiwoom import KiwoomService
from app.services.llm import LLMService
from app.services.opendart import OpenDartService
from app.services.portfolio_adapter import PortfolioAdapter

# 보유 종목이 없거나 부족할 때 "미보유 종목 BUY 후보" 경로를 함께 보여주기
# 위한 데모 전용 후보. 실제 서비스에서는 Recommendation Engine이 이 후보를
# 대신 채운다(README "미보유 종목" 정책 참고).
_DEMO_UNHELD_CANDIDATE = "005930"

# InvestorProfile은 아직 데이터 소스가 없다(사용자가 직접 입력해야 하는
# 값). 데모에서는 고정된 예시 프로필을 사용한다.
_DEMO_INVESTOR_PROFILE = InvestorProfile(
    risk_tolerance=RiskLevel.MEDIUM,
    investment_horizon_months=12,
    target_return_pct=15.0,
    objectives=["장기 자산 증식"],
    constraints=[],
)


async def main() -> None:
    kiwoom_service = KiwoomService(
        app_key=settings.kiwoom_app_key,
        secret_key=settings.kiwoom_secret_key,
    )
    kiwoom_tools = KiwoomTools(service=kiwoom_service)

    opendart_service = OpenDartService(api_key=settings.opendart_api_key)
    opendart_tools = OpenDartTools(service=opendart_service)

    ecos_service = EcosService(api_key=settings.ecos_api_key)
    ecos_tools = EcosTools(service=ecos_service)

    # Portfolio Strategy Agent의 프롬프트는 포트폴리오/시장/종목 fact를 모두
    # 합친 만큼 Market Agent/Stock Research Agent보다 길다. 기본 30초
    # timeout으로는 reasoning 모델 응답이 종종 시간 내에 끝나지 않는 것을
    # 실제 E2E에서 확인해 데모 한정으로 넉넉하게 늘린다.
    llm_service = LLMService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout=90.0,
    )

    balance = await kiwoom_tools.get_account_balance()
    portfolio_context = PortfolioAdapter.from_kiwoom_balance(balance)

    target_symbols = [position.symbol for position in portfolio_context.positions]
    if _DEMO_UNHELD_CANDIDATE not in target_symbols:
        target_symbols.append(_DEMO_UNHELD_CANDIDATE)

    stock_research_orchestrator = StockResearchOrchestrator(
        kiwoom_tools=kiwoom_tools,
        opendart_tools=opendart_tools,
        llm_service=llm_service,
    )

    stock_analyses = []
    for symbol in target_symbols:
        try:
            stock_analyses.append(
                await stock_research_orchestrator.run(
                    stock_code=symbol, business_year="2025"
                )
            )
        except Exception as error:  # noqa: BLE001 - 데모 스크립트의 최상위 경계
            # ETF/ETN처럼 OpenDART에 기업 재무가 없는 종목 등, Stock Research
            # Agent가 분석할 수 없는 보유 종목이 섞여 있을 수 있다. 이런
            # 종목은 StockAnalysis 없이 넘어가고(Portfolio Strategy Agent
            # 설계상 "핵심 분석 근거가 없는 종목은 recommendation을 생성하지
            # 않는다"), 나머지 종목으로 데모를 계속 진행한다.
            print(f"[skip] {symbol}: Stock Research Agent 분석 실패 ({error})")

    market_orchestrator = MarketOrchestrator(ecos_tools=ecos_tools, llm_service=llm_service)
    as_of_date = datetime.now(UTC).strftime("%Y%m%d")
    market_analysis = await market_orchestrator.run(as_of_date=as_of_date)

    portfolio_orchestrator = PortfolioStrategyOrchestrator(llm_service=llm_service)
    result = await portfolio_orchestrator.run(
        market_analysis=market_analysis,
        stock_analyses=stock_analyses,
        portfolio_context=portfolio_context,
        investor_profile=_DEMO_INVESTOR_PROFILE,
    )

    print("=== Portfolio Strategy Agent v1 ===\n")

    print(f"portfolio_risk : {result.portfolio_risk.value}")
    print(f"confidence     : {result.confidence.value}\n")

    print("--- Summary ---")
    print(result.summary)
    print()

    print("--- Recommendations ---")
    if not result.recommendations:
        print("(없음)")
    for recommendation in result.recommendations:
        current = (
            f"{recommendation.current_weight:.1%}"
            if recommendation.current_weight is not None
            else "미보유"
        )
        target = (
            f"{recommendation.target_weight:.1%}"
            if recommendation.target_weight is not None
            else "-"
        )
        print(
            f"[{recommendation.action.value.upper()}] "
            f"{recommendation.name}({recommendation.symbol}) "
            f"current={current} target={target}"
        )
        print(f"  {recommendation.rationale}")
        for condition in recommendation.conditions:
            print(f"  조건: {condition}")
    print()

    print("--- Evidence ---")
    for evidence in result.evidence:
        print(f"- [{evidence.source}] {evidence.description}")


if __name__ == "__main__":
    asyncio.run(main())

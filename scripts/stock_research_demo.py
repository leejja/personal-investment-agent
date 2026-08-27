import asyncio

from app.agents.stock_research.orchestrator import StockResearchOrchestrator
from app.config import settings
from app.mcp.kiwoom_tools import KiwoomTools
from app.mcp.opendart_tools import OpenDartTools
from app.services.kiwoom import KiwoomService
from app.services.llm import LLMService
from app.services.opendart import OpenDartService


async def main() -> None:
    kiwoom_service = KiwoomService(
        app_key=settings.kiwoom_app_key,
        secret_key=settings.kiwoom_secret_key,
    )
    kiwoom_tools = KiwoomTools(service=kiwoom_service)

    opendart_service = OpenDartService(api_key=settings.opendart_api_key)
    opendart_tools = OpenDartTools(service=opendart_service)

    llm_service = LLMService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )

    orchestrator = StockResearchOrchestrator(
        kiwoom_tools=kiwoom_tools,
        opendart_tools=opendart_tools,
        llm_service=llm_service,
    )

    result = await orchestrator.run(
        stock_code="005930",
        business_year="2025",
    )

    print(f"=== Stock Research Agent v1: {result.name} ({result.symbol}) ===\n")

    print(f"risk_level : {result.risk_level.value}")
    print(f"confidence : {result.confidence.value}\n")

    if result.price is not None:
        price = result.price
        print("--- Price ---")
        print(f"현재가    : {price.price:,.0f}")
        if price.change_pct is not None:
            print(f"등락률    : {price.change_pct:+.2f}%")
        if price.volume is not None:
            print(f"거래량    : {price.volume:,}")
        if price.high_250d is not None and price.low_250d is not None:
            print(f"52주 고/저: {price.high_250d:,.0f} / {price.low_250d:,.0f}")
        print()

    if result.financials is not None:
        f = result.financials
        print("--- Financials ---")
        _print_if_present("매출액", f.revenue)
        _print_if_present("영업이익", f.operating_profit)
        _print_if_present("순이익", f.net_income)
        _print_if_present("자산총계", f.total_assets)
        _print_if_present("부채총계", f.total_liabilities)
        _print_if_present("자본총계", f.total_equity)
        _print_if_present("PER", f.per)
        _print_if_present("PBR", f.pbr)
        _print_if_present("ROE", f.roe)
        print()

    if result.financial_history:
        print("--- Financial History (오래된 연도 → 최신 연도) ---")
        for snapshot in result.financial_history:
            print(f"[{snapshot.business_year}]")
            _print_if_present("  매출액", snapshot.revenue)
            _print_if_present("  영업이익", snapshot.operating_profit)
            _print_if_present("  순이익", snapshot.net_income)
            _print_if_present("  자산총계", snapshot.total_assets)
            _print_if_present("  부채총계", snapshot.total_liabilities)
            _print_if_present("  자본총계", snapshot.total_equity)
            _print_if_present("  PER", snapshot.per)
            _print_if_present("  PBR", snapshot.pbr)
            _print_if_present("  ROE", snapshot.roe)
        print()

    print("--- Investment Thesis ---")
    print(result.investment_thesis)
    print()

    print("--- Catalysts ---")
    _print_list(result.catalysts)
    print()

    print("--- Risks ---")
    _print_list(result.risks)
    print()

    print("--- Scenarios ---")
    for scenario in result.scenarios:
        target = (
            f"{scenario.target_price:,.0f}"
            if scenario.target_price is not None
            else "-"
        )
        probability = (
            f"{scenario.probability:.0%}"
            if scenario.probability is not None
            else "-"
        )
        print(f"[{scenario.scenario.value}] target={target} probability={probability}")
        print(f"  {scenario.thesis}")
    print()

    print("--- Evidence ---")
    for evidence in result.evidence:
        reference = f" (ref: {evidence.reference})" if evidence.reference else ""
        print(f"- [{evidence.source}] {evidence.description}{reference}")


def _print_if_present(label: str, value: float | None) -> None:
    if value is None:
        return
    print(f"{label:8s}: {value:,.2f}")


def _print_list(items: list[str]) -> None:
    if not items:
        print("(없음)")
        return
    for item in items:
        print(f"- {item}")


if __name__ == "__main__":
    asyncio.run(main())

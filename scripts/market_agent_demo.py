import asyncio
from datetime import UTC, datetime

from app.agents.market.orchestrator import MarketOrchestrator
from app.config import settings
from app.mcp.ecos_tools import EcosTools
from app.services.ecos import EcosService
from app.services.llm import LLMService


async def main() -> None:
    ecos_service = EcosService(api_key=settings.ecos_api_key)
    ecos_tools = EcosTools(service=ecos_service)

    llm_service = LLMService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )

    orchestrator = MarketOrchestrator(
        ecos_tools=ecos_tools,
        llm_service=llm_service,
    )

    as_of_date = datetime.now(UTC).strftime("%Y%m%d")
    result = await orchestrator.run(as_of_date=as_of_date)

    print(f"=== Market Agent v1: as of {as_of_date} ===\n")

    print(f"regime     : {result.regime.value}")
    print(f"risk_level : {result.risk_level.value}")
    print(f"confidence : {result.confidence.value}\n")

    print("--- Summary ---")
    print(result.summary)
    print()

    print("--- Indicators ---")
    for indicator in result.indicators:
        unit = f" {indicator.unit}" if indicator.unit else ""
        change = f" (change={indicator.change:+.2f})" if indicator.change is not None else ""
        description = f" — {indicator.description}" if indicator.description else ""
        print(f"- {indicator.name}: {indicator.value:,.2f}{unit}{change}{description}")
    print()

    print("--- Evidence ---")
    for evidence in result.evidence:
        reference = f" (ref: {evidence.reference})" if evidence.reference else ""
        print(f"- [{evidence.source}] {evidence.description}{reference}")


if __name__ == "__main__":
    asyncio.run(main())

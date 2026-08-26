import json
from unittest.mock import AsyncMock

import pytest

from app.agents.stock_research.orchestrator import StockResearchOrchestrator
from app.agents.stock_research.reasoning import ReasoningError
from app.mcp.kiwoom_tools import KiwoomTools
from app.mcp.opendart_tools import KeyFinancials, OpenDartTools
from app.models.common import RiskLevel
from app.services.kiwoom import KiwoomService, KiwoomStockInfo
from app.services.llm import LLMResponse, LLMService
from app.services.opendart import OpenDartService


def _stock_info(**overrides: object) -> KiwoomStockInfo:
    defaults: dict[object, object] = {
        "stock_code": "005930",
        "stock_name": "삼성전자",
        "current_price": 281500,
        "change": 10500,
        "change_rate": 3.87,
        "trading_volume": 15000000,
        "per": 42.89,
        "pbr": 4.4,
        "roe": 10.9,
        "eps": 6564,
        "bps": 63976,
        "high_250d": 374500,
        "low_250d": 67500,
    }
    defaults.update(overrides)
    return KiwoomStockInfo(**defaults)


def _key_financials(**overrides: object) -> KeyFinancials:
    defaults: dict[object, object] = {
        "stock_code": "005930",
        "corp_code": "00126380",
        "business_year": "2025",
        "report_code": "11011",
        "fs_div": "CFS",
        "revenue": 333605938000000,
        "operating_profit": 43601051000000,
        "net_income": 45206805000000,
        "total_assets": 566942110000000,
        "total_liabilities": 130621773000000,
        "total_equity": 436320337000000,
    }
    defaults.update(overrides)
    return KeyFinancials(**defaults)


def _valid_llm_json(
    suggested_confidence: str = "high",
    catalysts: list[str] | None = None,
    risks: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "investment_thesis": "안정적인 수익성을 바탕으로 한 valuation 매력",
            "catalysts": catalysts if catalysts is not None else [],
            "risks": risks if risks is not None else [],
            "scenarios": [
                {
                    "scenario": "base",
                    "thesis": "현재 추세가 유지되는 시나리오",
                    "target_price": 300000,
                    "probability": 0.5,
                }
            ],
            "suggested_confidence": suggested_confidence,
        },
        ensure_ascii=False,
    )


def _build_orchestrator(
    *,
    stock_info: KiwoomStockInfo | None = None,
    key_financials: KeyFinancials | None = None,
    llm_contents: list[str] | None = None,
) -> StockResearchOrchestrator:
    kiwoom_tools = KiwoomTools(
        service=KiwoomService(app_key="test-app-key", secret_key="test-secret-key")
    )
    kiwoom_tools.get_stock_info = AsyncMock(
        return_value=stock_info if stock_info is not None else _stock_info()
    )

    opendart_tools = OpenDartTools(service=OpenDartService(api_key="test-key"))
    opendart_tools.get_key_financials = AsyncMock(
        return_value=(
            key_financials if key_financials is not None else _key_financials()
        )
    )

    llm_service = LLMService(api_key="test-key", model="test-model")
    contents = llm_contents if llm_contents is not None else [_valid_llm_json()]
    llm_service.complete = AsyncMock(
        side_effect=[
            LLMResponse(content=content, model="test-model", finish_reason="stop")
            for content in contents
        ]
    )

    return StockResearchOrchestrator(
        kiwoom_tools=kiwoom_tools,
        opendart_tools=opendart_tools,
        llm_service=llm_service,
    )


@pytest.mark.anyio
async def test_run_assembles_stock_analysis() -> None:
    orchestrator = _build_orchestrator()

    result = await orchestrator.run(stock_code="005930", business_year="2025")

    assert result.symbol == "005930"
    assert result.name == "삼성전자"
    assert result.price is not None
    assert result.price.price == 281500.0
    assert result.financials is not None
    assert result.financials.revenue == 333605938000000.0
    assert result.investment_thesis == "안정적인 수익성을 바탕으로 한 valuation 매력"
    assert len(result.scenarios) == 1


@pytest.mark.anyio
async def test_run_calls_tools_with_expected_arguments() -> None:
    orchestrator = _build_orchestrator()

    await orchestrator.run(
        stock_code="005930",
        business_year="2025",
        report_code="11012",
    )

    orchestrator.kiwoom_tools.get_stock_info.assert_awaited_once_with(
        stock_code="005930",
    )
    orchestrator.opendart_tools.get_key_financials.assert_awaited_once_with(
        stock_code="005930",
        business_year="2025",
        report_code="11012",
    )


@pytest.mark.anyio
async def test_run_caps_confidence_to_analysis_max() -> None:
    # 핵심 재무 데이터를 비워 max_confidence가 LOW로 캡되도록 만든다.
    orchestrator = _build_orchestrator(
        key_financials=_key_financials(
            revenue=None,
            operating_profit=None,
            net_income=None,
        ),
        llm_contents=[_valid_llm_json(suggested_confidence="high")],
    )

    result = await orchestrator.run(stock_code="005930", business_year="2025")

    assert result.confidence.value == "low"


@pytest.mark.anyio
async def test_run_uses_lower_llm_confidence_when_lower_than_max() -> None:
    orchestrator = _build_orchestrator(
        llm_contents=[_valid_llm_json(suggested_confidence="low")],
    )

    result = await orchestrator.run(stock_code="005930", business_year="2025")

    # analysis_result.max_confidence는 MEDIUM이지만 LLM이 LOW를 제안했으므로
    # 더 낮은 쪽(LOW)을 그대로 따른다.
    assert result.confidence.value == "low"


@pytest.mark.anyio
async def test_run_risk_level_comes_only_from_analysis() -> None:
    # v1의 analysis.py는 risk_level을 항상 MEDIUM으로 고정한다.
    # debt_ratio가 매우 높아도(300%) 이 값이 바뀌지 않아야 하고,
    # reasoning_result에는 애초에 risk_level 필드가 없으므로
    # LLM이 이 값에 영향을 줄 수 없음을 함께 확인한다.
    orchestrator = _build_orchestrator(
        key_financials=_key_financials(total_liabilities=300, total_equity=100),
        llm_contents=[_valid_llm_json()],
    )

    result = await orchestrator.run(stock_code="005930", business_year="2025")

    assert result.risk_level == RiskLevel.MEDIUM


@pytest.mark.anyio
async def test_run_evidence_includes_facts_and_tool_sources() -> None:
    orchestrator = _build_orchestrator()

    result = await orchestrator.run(stock_code="005930", business_year="2025")

    sources = [evidence.source for evidence in result.evidence]

    assert "Kiwoom" in sources
    assert "OpenDART" in sources

    descriptions = [evidence.description for evidence in result.evidence]
    assert any("250거래일" in description for description in descriptions)
    assert any("부채비율" in description for description in descriptions)
    assert any("현재가는" in description for description in descriptions)
    assert any("get_stock_info" in description for description in descriptions)
    assert any("get_key_financials" in description for description in descriptions)

    kiwoom_tool_evidence = next(
        evidence
        for evidence in result.evidence
        if evidence.source == "Kiwoom" and "get_stock_info" in evidence.description
    )
    assert kiwoom_tool_evidence.reference == "005930"

    opendart_tool_evidence = next(
        evidence
        for evidence in result.evidence
        if evidence.source == "OpenDART"
        and "get_key_financials" in evidence.description
    )
    assert opendart_tool_evidence.reference == "00126380"


@pytest.mark.anyio
async def test_run_propagates_reasoning_error_without_fallback() -> None:
    orchestrator = _build_orchestrator(
        llm_contents=["이건 JSON이 아닙니다", "여전히 JSON이 아닙니다"],
    )

    with pytest.raises(ReasoningError):
        await orchestrator.run(stock_code="005930", business_year="2025")

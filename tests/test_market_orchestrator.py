import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.agents.market.orchestrator import LOOKBACK_DAYS, MarketOrchestrator
from app.agents.market.reasoning import ReasoningError
from app.mcp.ecos_tools import EcosTools
from app.models.common import AnalysisConfidence
from app.services.ecos import EcosService, EcosStatisticPoint
from app.services.llm import LLMResponse, LLMService

AS_OF = "20260827"


def _dates_ending_at(end_date: str, count: int) -> list[str]:
    end = datetime.strptime(end_date, "%Y%m%d").replace(tzinfo=UTC)
    return [
        (end - timedelta(days=count - 1 - i)).strftime("%Y%m%d") for i in range(count)
    ]


def _points(values: list[float], *, end_date: str = AS_OF) -> list[EcosStatisticPoint]:
    dates = _dates_ending_at(end_date, len(values))
    return [
        EcosStatisticPoint(
            statistic_code="TEST",
            statistic_name="test",
            item_code1="TEST",
            item_name1="test",
            unit=None,
            time=date,
            value=value,
        )
        for date, value in zip(dates, values)
    ]


def _flat(value: float, count: int) -> list[float]:
    return [value] * count


def _linear(start: float, step: float, count: int) -> list[float]:
    return [start + step * i for i in range(count)]


def _valid_llm_json(*, suggested_confidence: str = "high") -> str:
    return json.dumps(
        {
            "summary": "기준금리 인상과 원화 약세가 동시에 관찰됨",
            "suggested_regime": "neutral",
            "suggested_risk_level": "medium",
            "suggested_confidence": suggested_confidence,
            "regime_fact_ids": ["base_rate_change"],
            "risk_fact_ids": ["usd_krw_change_20d"],
        },
        ensure_ascii=False,
    )


def _build_orchestrator(
    *,
    base_rate_values: list[float] | None = None,
    fx_values: list[float] | None = None,
    kospi_values: list[float] | None = None,
    kosdaq_values: list[float] | None = None,
    llm_contents: list[str] | None = None,
) -> MarketOrchestrator:
    ecos_tools = EcosTools(service=EcosService(api_key="test-key"))
    ecos_tools.get_base_rate = AsyncMock(
        return_value=_points(
            base_rate_values if base_rate_values is not None else _flat(2.75, 65)
        )
    )
    ecos_tools.get_exchange_rate = AsyncMock(
        return_value=_points(
            fx_values if fx_values is not None else _linear(1400.0, -1.0, 65)
        )
    )
    ecos_tools.get_kospi_index = AsyncMock(
        return_value=_points(
            kospi_values if kospi_values is not None else _linear(6700.0, 2.0, 65)
        )
    )
    ecos_tools.get_kosdaq_index = AsyncMock(
        return_value=_points(
            kosdaq_values if kosdaq_values is not None else _linear(800.0, 1.0, 65)
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

    return MarketOrchestrator(ecos_tools=ecos_tools, llm_service=llm_service)


@pytest.mark.anyio
async def test_run_assembles_market_analysis() -> None:
    orchestrator = _build_orchestrator()

    result = await orchestrator.run(as_of_date=AS_OF)

    assert result.summary
    assert result.regime.value == "neutral"
    assert result.risk_level.value == "medium"
    assert len(result.indicators) == 4


@pytest.mark.anyio
async def test_run_calls_tools_with_expected_date_range() -> None:
    orchestrator = _build_orchestrator()

    await orchestrator.run(as_of_date=AS_OF)

    expected_start = (
        datetime.strptime(AS_OF, "%Y%m%d").replace(tzinfo=UTC)
        - timedelta(days=LOOKBACK_DAYS)
    ).strftime("%Y%m%d")

    orchestrator.ecos_tools.get_base_rate.assert_awaited_once_with(
        start_date=expected_start, end_date=AS_OF
    )
    orchestrator.ecos_tools.get_exchange_rate.assert_awaited_once_with(
        start_date=expected_start, end_date=AS_OF
    )
    orchestrator.ecos_tools.get_kospi_index.assert_awaited_once_with(
        start_date=expected_start, end_date=AS_OF
    )
    orchestrator.ecos_tools.get_kosdaq_index.assert_awaited_once_with(
        start_date=expected_start, end_date=AS_OF
    )


@pytest.mark.anyio
async def test_run_caps_confidence_to_analysis_max() -> None:
    # KOSPI 데이터를 비워 max_confidence가 LOW로 캡되도록 만든다.
    orchestrator = _build_orchestrator(
        kospi_values=[],
        llm_contents=[_valid_llm_json(suggested_confidence="high")],
    )

    result = await orchestrator.run(as_of_date=AS_OF)

    assert result.confidence == AnalysisConfidence.LOW


@pytest.mark.anyio
async def test_run_uses_lower_llm_confidence_when_lower_than_max() -> None:
    orchestrator = _build_orchestrator(
        llm_contents=[_valid_llm_json(suggested_confidence="low")],
    )

    result = await orchestrator.run(as_of_date=AS_OF)

    # analysis_result.max_confidence는 MEDIUM이지만 LLM이 LOW를 제안했으므로
    # 더 낮은 쪽(LOW)을 그대로 따른다.
    assert result.confidence == AnalysisConfidence.LOW


@pytest.mark.anyio
async def test_run_evidence_includes_facts_and_tool_call_source() -> None:
    orchestrator = _build_orchestrator()

    result = await orchestrator.run(as_of_date=AS_OF)

    sources = [evidence.source for evidence in result.evidence]
    assert "ECOS" in sources

    descriptions = [evidence.description for evidence in result.evidence]
    assert any("기준금리" in description for description in descriptions)
    assert any("get_base_rate" in description for description in descriptions)


@pytest.mark.anyio
async def test_run_propagates_reasoning_error_without_fallback() -> None:
    orchestrator = _build_orchestrator(
        llm_contents=["이건 JSON이 아닙니다", "여전히 JSON이 아닙니다"],
    )

    with pytest.raises(ReasoningError):
        await orchestrator.run(as_of_date=AS_OF)


@pytest.mark.anyio
async def test_run_propagates_reasoning_error_on_ungrounded_regime() -> None:
    ungrounded_json = json.dumps(
        {
            "summary": "근거 없는 판단",
            "suggested_regime": "risk_off",
            "suggested_risk_level": "high",
            "suggested_confidence": "high",
            "regime_fact_ids": [],
            "risk_fact_ids": ["usd_krw_change_20d"],
        },
        ensure_ascii=False,
    )
    orchestrator = _build_orchestrator(llm_contents=[ungrounded_json, ungrounded_json])

    with pytest.raises(ReasoningError):
        await orchestrator.run(as_of_date=AS_OF)

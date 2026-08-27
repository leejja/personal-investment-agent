import json
from unittest.mock import AsyncMock

import pytest

from app.agents.portfolio.orchestrator import PortfolioStrategyOrchestrator
from app.agents.portfolio.reasoning import ReasoningError
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.market import MarketAnalysis, MarketRegime
from app.models.portfolio import InvestorProfile, PortfolioContext, PortfolioPosition
from app.models.stock import StockAnalysis
from app.services.llm import LLMResponse, LLMService


def _market_analysis() -> MarketAnalysis:
    return MarketAnalysis(
        regime=MarketRegime.NEUTRAL,
        risk_level=RiskLevel.MEDIUM,
        summary="테스트 시장 요약",
        confidence=AnalysisConfidence.MEDIUM,
    )


def _investor_profile() -> InvestorProfile:
    return InvestorProfile(risk_tolerance=RiskLevel.MEDIUM)


def _position(
    symbol: str = "005930",
    name: str = "삼성전자",
    weight: float = 0.50,
) -> PortfolioPosition:
    return PortfolioPosition(
        symbol=symbol,
        name=name,
        quantity=100,
        average_price=80000,
        current_price=100000,
        market_value=10000000,
        profit_loss=2000000,
        profit_loss_pct=25.0,
        weight=weight,
    )


def _portfolio_context() -> PortfolioContext:
    return PortfolioContext(
        total_value=10000000,
        cash=5000000,
        positions=[_position()],
    )


def _stock_analysis(
    symbol: str = "005930",
    name: str = "삼성전자",
) -> StockAnalysis:
    return StockAnalysis(
        symbol=symbol,
        name=name,
        investment_thesis="테스트 투자 논지",
        risk_level=RiskLevel.MEDIUM,
        confidence=AnalysisConfidence.MEDIUM,
    )


def _valid_llm_json(
    *,
    suggested_confidence: str = "high",
    target_weight: float | None = None,
) -> str:
    recommendation = {
        "symbol": "005930",
        "suggested_action": "reduce",
        "rationale": "비중이 높아 축소를 검토",
        "conditions": [],
        "fact_ids": ["005930_current_weight"],
    }
    if target_weight is not None:
        # LLM이 스키마에 없는 필드를 억지로 끼워 넣어도(예: 프롬프트 무시)
        # ReasoningResult가 이를 무시하고, 최종 조립에서도 orchestrator가
        # target_weight를 None으로 강제하는지 확인하기 위한 테스트용 값.
        recommendation["target_weight"] = target_weight

    return json.dumps(
        {
            "portfolio_summary": "삼성전자 비중이 높아 축소를 검토할 시점",
            "recommendations": [recommendation],
            "suggested_portfolio_risk": "medium",
            "portfolio_risk_fact_ids": ["portfolio_top1_weight"],
            "suggested_confidence": suggested_confidence,
        },
        ensure_ascii=False,
    )


def _build_orchestrator(
    *,
    llm_contents: list[str] | None = None,
) -> PortfolioStrategyOrchestrator:
    llm_service = LLMService(api_key="test-key", model="test-model")
    contents = llm_contents if llm_contents is not None else [_valid_llm_json()]
    llm_service.complete = AsyncMock(
        side_effect=[
            LLMResponse(content=content, model="test-model", finish_reason="stop")
            for content in contents
        ]
    )
    return PortfolioStrategyOrchestrator(llm_service=llm_service)


@pytest.mark.anyio
async def test_run_assembles_strategy_result() -> None:
    orchestrator = _build_orchestrator()

    result = await orchestrator.run(
        market_analysis=_market_analysis(),
        stock_analyses=[_stock_analysis()],
        portfolio_context=_portfolio_context(),
        investor_profile=_investor_profile(),
    )

    assert result.summary
    assert len(result.recommendations) == 1

    recommendation = result.recommendations[0]
    assert recommendation.symbol == "005930"
    assert recommendation.name == "삼성전자"
    assert recommendation.action.value == "reduce"
    assert recommendation.current_weight == 0.50


@pytest.mark.anyio
async def test_run_forces_target_weight_none_even_if_llm_supplies_one() -> None:
    orchestrator = _build_orchestrator(
        llm_contents=[_valid_llm_json(target_weight=0.25)],
    )

    result = await orchestrator.run(
        market_analysis=_market_analysis(),
        stock_analyses=[_stock_analysis()],
        portfolio_context=_portfolio_context(),
        investor_profile=_investor_profile(),
    )

    assert result.recommendations[0].target_weight is None


@pytest.mark.anyio
async def test_run_caps_confidence_to_analysis_max() -> None:
    # stock_analyses가 비어 있으면 max_confidence가 LOW로 캡된다.
    orchestrator = _build_orchestrator(
        llm_contents=[
            json.dumps(
                {
                    "portfolio_summary": "판단 대상 종목 없음",
                    "recommendations": [],
                    "suggested_portfolio_risk": "medium",
                    "portfolio_risk_fact_ids": ["market_regime"],
                    "suggested_confidence": "high",
                },
                ensure_ascii=False,
            )
        ],
    )

    result = await orchestrator.run(
        market_analysis=_market_analysis(),
        stock_analyses=[],
        portfolio_context=_portfolio_context(),
        investor_profile=_investor_profile(),
    )

    assert result.confidence == AnalysisConfidence.LOW


@pytest.mark.anyio
async def test_run_uses_lower_llm_confidence_when_lower_than_max() -> None:
    orchestrator = _build_orchestrator(
        llm_contents=[_valid_llm_json(suggested_confidence="low")],
    )

    result = await orchestrator.run(
        market_analysis=_market_analysis(),
        stock_analyses=[_stock_analysis()],
        portfolio_context=_portfolio_context(),
        investor_profile=_investor_profile(),
    )

    # analysis_result.max_confidence는 MEDIUM이지만 LLM이 LOW를 제안했으므로
    # 더 낮은 쪽(LOW)을 그대로 따른다.
    assert result.confidence == AnalysisConfidence.LOW


@pytest.mark.anyio
async def test_run_never_returns_high_confidence() -> None:
    orchestrator = _build_orchestrator(
        llm_contents=[_valid_llm_json(suggested_confidence="high")],
    )

    result = await orchestrator.run(
        market_analysis=_market_analysis(),
        stock_analyses=[_stock_analysis()],
        portfolio_context=_portfolio_context(),
        investor_profile=_investor_profile(),
    )

    assert result.confidence == AnalysisConfidence.MEDIUM


@pytest.mark.anyio
async def test_run_evidence_built_from_deterministic_facts_only() -> None:
    orchestrator = _build_orchestrator()

    result = await orchestrator.run(
        market_analysis=_market_analysis(),
        stock_analyses=[_stock_analysis()],
        portfolio_context=_portfolio_context(),
        investor_profile=_investor_profile(),
    )

    sources = {evidence.source for evidence in result.evidence}
    assert "PortfolioContext" in sources
    assert "MarketAnalysis" in sources
    assert "StockAnalysis" in sources

    descriptions = [evidence.description for evidence in result.evidence]
    assert any("포트폴리오 비중" in description for description in descriptions)


@pytest.mark.anyio
async def test_run_propagates_reasoning_error_without_fallback() -> None:
    orchestrator = _build_orchestrator(
        llm_contents=["이건 JSON이 아닙니다", "여전히 JSON이 아닙니다"],
    )

    with pytest.raises(ReasoningError):
        await orchestrator.run(
            market_analysis=_market_analysis(),
            stock_analyses=[_stock_analysis()],
            portfolio_context=_portfolio_context(),
            investor_profile=_investor_profile(),
        )


@pytest.mark.anyio
async def test_run_propagates_reasoning_error_on_disallowed_action() -> None:
    # 005930은 보유 종목이라 BUY가 허용되지 않는다 — reasoning.py 재시도
    # 루프 안에서 구조적으로 걸러지고, 최종 실패하면 ReasoningError로
    # 전파되어야 한다.
    invalid_json = json.dumps(
        {
            "portfolio_summary": "근거 없는 판단",
            "recommendations": [
                {
                    "symbol": "005930",
                    "suggested_action": "buy",
                    "rationale": "신규 매수",
                    "conditions": [],
                    "fact_ids": ["005930_current_weight"],
                }
            ],
            "suggested_portfolio_risk": "medium",
            "portfolio_risk_fact_ids": ["portfolio_top1_weight"],
            "suggested_confidence": "medium",
        },
        ensure_ascii=False,
    )
    orchestrator = _build_orchestrator(llm_contents=[invalid_json, invalid_json])

    with pytest.raises(ReasoningError):
        await orchestrator.run(
            market_analysis=_market_analysis(),
            stock_analyses=[_stock_analysis()],
            portfolio_context=_portfolio_context(),
            investor_profile=_investor_profile(),
        )

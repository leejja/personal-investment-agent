import pytest
from pydantic import ValidationError

from app.models.common import AnalysisConfidence, RiskLevel, UserRequest
from app.models.market import MarketAnalysis, MarketRegime
from app.models.portfolio import InvestorProfile, PortfolioPosition
from app.models.stock import ScenarioType, StockScenario
from app.models.strategy import (
    InvestmentAction,
    PositionRecommendation,
    StrategyResult,
)


def test_user_request():
    request = UserRequest(
        question="삼성전자 투자전략을 분석해줘",
        symbols=["005930"],
    )

    assert request.question == "삼성전자 투자전략을 분석해줘"
    assert request.symbols == ["005930"]


def test_market_analysis():
    analysis = MarketAnalysis(
        regime=MarketRegime.RISK_ON,
        risk_level=RiskLevel.MEDIUM,
        summary="위험자산 선호 환경",
        confidence=AnalysisConfidence.HIGH,
    )

    assert analysis.regime == MarketRegime.RISK_ON
    assert analysis.risk_level == RiskLevel.MEDIUM
    assert analysis.indicators == []
    assert analysis.evidence == []


def test_stock_scenario():
    scenario = StockScenario(
        scenario=ScenarioType.BASE,
        thesis="실적 개선이 예상 수준으로 진행",
        target_price=110000,
        probability=0.55,
    )

    assert scenario.scenario == ScenarioType.BASE
    assert scenario.probability == 0.55


def test_portfolio_position():
    position = PortfolioPosition(
        symbol="005930",
        name="삼성전자",
        quantity=100,
        average_price=80000,
        current_price=100000,
        market_value=10000000,
        profit_loss=2000000,
        profit_loss_pct=25.0,
        weight=0.20,
    )

    assert position.quantity == 100
    assert position.weight == 0.20


def test_investor_profile():
    profile = InvestorProfile(
        risk_tolerance=RiskLevel.HIGH,
        investment_horizon_months=36,
        target_return_pct=20.0,
    )

    assert profile.risk_tolerance == RiskLevel.HIGH
    assert profile.investment_horizon_months == 36


def test_strategy_result():
    strategy = StrategyResult(
        summary="현재 포지션 유지",
        recommendations=[
            PositionRecommendation(
                symbol="005930",
                name="삼성전자",
                action=InvestmentAction.HOLD,
                current_weight=0.20,
                target_weight=0.20,
                rationale="현재 비중이 적정 수준",
            )
        ],
        portfolio_risk=RiskLevel.MEDIUM,
        confidence=AnalysisConfidence.HIGH,
    )

    assert len(strategy.recommendations) == 1
    assert strategy.recommendations[0].action == InvestmentAction.HOLD


def test_empty_question_rejected():
    with pytest.raises(ValidationError):
        UserRequest(question="")


def test_probability_over_one_rejected():
    with pytest.raises(ValidationError):
        StockScenario(
            scenario=ScenarioType.BULL,
            thesis="강한 실적 성장",
            probability=1.1,
        )


def test_portfolio_weight_over_one_rejected():
    with pytest.raises(ValidationError):
        PortfolioPosition(
            symbol="005930",
            name="삼성전자",
            quantity=100,
            average_price=80000,
            current_price=100000,
            market_value=10000000,
            profit_loss=2000000,
            profit_loss_pct=25.0,
            weight=1.1,
        )


def test_negative_quantity_rejected():
    with pytest.raises(ValidationError):
        PortfolioPosition(
            symbol="005930",
            name="삼성전자",
            quantity=-1,
            average_price=80000,
            current_price=100000,
            market_value=10000000,
            profit_loss=2000000,
            profit_loss_pct=25.0,
            weight=0.20,
        )

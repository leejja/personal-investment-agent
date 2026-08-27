from app.agents.portfolio.analysis import analyze
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.market import MarketAnalysis, MarketRegime
from app.models.portfolio import InvestorProfile, PortfolioContext, PortfolioPosition
from app.models.stock import StockAnalysis
from app.models.strategy import InvestmentAction


def _market_analysis(
    regime: MarketRegime = MarketRegime.NEUTRAL,
    risk_level: RiskLevel = RiskLevel.MEDIUM,
) -> MarketAnalysis:
    return MarketAnalysis(
        regime=regime,
        risk_level=risk_level,
        summary="테스트 시장 요약",
        confidence=AnalysisConfidence.MEDIUM,
    )


def _investor_profile(**overrides: object) -> InvestorProfile:
    defaults = {"risk_tolerance": RiskLevel.MEDIUM}
    defaults.update(overrides)
    return InvestorProfile(**defaults)


def _position(
    symbol: str = "005930",
    name: str = "삼성전자",
    weight: float = 0.20,
    profit_loss_pct: float = 25.0,
) -> PortfolioPosition:
    return PortfolioPosition(
        symbol=symbol,
        name=name,
        quantity=100,
        average_price=80000,
        current_price=100000,
        market_value=10000000,
        profit_loss=2000000,
        profit_loss_pct=profit_loss_pct,
        weight=weight,
    )


def _stock_analysis(
    symbol: str = "005930",
    name: str = "삼성전자",
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    confidence: AnalysisConfidence = AnalysisConfidence.MEDIUM,
) -> StockAnalysis:
    return StockAnalysis(
        symbol=symbol,
        name=name,
        investment_thesis="테스트 투자 논지",
        risk_level=risk_level,
        confidence=confidence,
    )


def test_held_symbol_gets_current_weight_and_held_actions() -> None:
    portfolio = PortfolioContext(
        total_value=10000000,
        cash=0,
        positions=[_position(weight=0.20)],
    )

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[_stock_analysis()],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    context = result.symbol_contexts[0]
    assert context.current_weight == 0.20
    assert set(context.allowed_actions) == {
        InvestmentAction.ADD,
        InvestmentAction.HOLD,
        InvestmentAction.REDUCE,
        InvestmentAction.SELL,
    }


def test_unheld_symbol_has_no_current_weight_and_unheld_actions() -> None:
    portfolio = PortfolioContext(total_value=10000000, cash=10000000, positions=[])

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[_stock_analysis(symbol="000660", name="SK하이닉스")],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    context = result.symbol_contexts[0]
    assert context.current_weight is None
    assert set(context.allowed_actions) == {
        InvestmentAction.BUY,
        InvestmentAction.AVOID,
    }


def test_portfolio_level_facts_computed_from_context() -> None:
    portfolio = PortfolioContext(
        total_value=10000000,
        cash=2000000,
        positions=[
            _position(symbol="005930", weight=0.50),
            _position(symbol="000660", name="SK하이닉스", weight=0.30),
        ],
    )

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    cash_weight_fact = next(f for f in result.facts if f.id == "portfolio_cash_weight")
    assert "20.0%" in cash_weight_fact.description

    equity_exposure_fact = next(
        f for f in result.facts if f.id == "portfolio_equity_exposure"
    )
    assert "80.0%" in equity_exposure_fact.description

    top1_fact = next(f for f in result.facts if f.id == "portfolio_top1_weight")
    assert "50.0%" in top1_fact.description

    top3_fact = next(f for f in result.facts if f.id == "portfolio_top3_weight")
    assert "80.0%" in top3_fact.description


def test_cash_weight_facts_omitted_when_total_value_zero() -> None:
    portfolio = PortfolioContext(total_value=0, cash=0, positions=[])

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    assert all(f.id != "portfolio_cash_weight" for f in result.facts)
    assert all(f.id != "portfolio_equity_exposure" for f in result.facts)


def test_investor_profile_optional_facts_included_only_when_present() -> None:
    portfolio = PortfolioContext(total_value=10000000, cash=10000000, positions=[])

    result_with = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(
            investment_horizon_months=36,
            objectives=["은퇴 자금 마련"],
            constraints=["레버리지 금지"],
        ),
    )
    ids_with = {f.id for f in result_with.facts}
    assert "investor_horizon" in ids_with
    assert "investor_objectives" in ids_with
    assert "investor_constraints" in ids_with

    result_without = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )
    ids_without = {f.id for f in result_without.facts}
    assert "investor_horizon" not in ids_without
    assert "investor_objectives" not in ids_without
    assert "investor_constraints" not in ids_without


def test_symbol_facts_reflect_held_vs_unheld() -> None:
    portfolio = PortfolioContext(
        total_value=10000000,
        cash=5000000,
        positions=[_position(symbol="005930", weight=0.50, profit_loss_pct=25.0)],
    )

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[
            _stock_analysis(symbol="005930", name="삼성전자"),
            _stock_analysis(symbol="000660", name="SK하이닉스"),
        ],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    held_weight_fact = next(f for f in result.facts if f.id == "005930_current_weight")
    assert "50.0%" in held_weight_fact.description

    held_pl_fact = next(f for f in result.facts if f.id == "005930_profit_loss_pct")
    assert "+25.0%" in held_pl_fact.description

    unheld_fact = next(f for f in result.facts if f.id == "000660_not_held")
    assert "미보유" in unheld_fact.description
    assert all(f.id != "000660_current_weight" for f in result.facts)


def test_symbol_facts_contain_no_evaluative_language() -> None:
    portfolio = PortfolioContext(
        total_value=10000000,
        cash=5000000,
        positions=[_position(weight=0.50)],
    )

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[_stock_analysis()],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    evaluative_terms = ["높다", "낮다", "양호", "부진", "과도", "적절"]
    for fact in result.facts:
        for term in evaluative_terms:
            assert term not in fact.description


def test_max_confidence_medium_when_stock_analyses_present() -> None:
    portfolio = PortfolioContext(total_value=10000000, cash=10000000, positions=[])

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[_stock_analysis()],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    assert result.max_confidence == AnalysisConfidence.MEDIUM


def test_max_confidence_low_when_no_stock_analyses() -> None:
    portfolio = PortfolioContext(total_value=10000000, cash=10000000, positions=[])

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    assert result.max_confidence == AnalysisConfidence.LOW


def test_max_confidence_never_high() -> None:
    portfolio = PortfolioContext(
        total_value=10000000,
        cash=5000000,
        positions=[_position()],
    )

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[
            _stock_analysis(confidence=AnalysisConfidence.HIGH),
        ],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    # 개별 StockAnalysis의 confidence가 HIGH여도 v1 포트폴리오 판단의
    # max_confidence는 HIGH를 반환하지 않는다.
    assert result.max_confidence == AnalysisConfidence.MEDIUM


def test_fact_ids_are_unique() -> None:
    portfolio = PortfolioContext(
        total_value=10000000,
        cash=5000000,
        positions=[_position(symbol="005930", weight=0.50)],
    )

    result = analyze(
        market_analysis=_market_analysis(),
        stock_analyses=[
            _stock_analysis(symbol="005930", name="삼성전자"),
            _stock_analysis(symbol="000660", name="SK하이닉스"),
        ],
        portfolio_context=portfolio,
        investor_profile=_investor_profile(),
    )

    ids = [fact.id for fact in result.facts]
    assert len(ids) == len(set(ids))

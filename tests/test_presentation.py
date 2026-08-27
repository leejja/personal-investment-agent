import inspect

from app.api.presentation import build_presentation
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.discovery import Candidate, MarketFilter
from app.models.market import MarketAnalysis, MarketRegime
from app.models.presentation import (
    PortfolioSummary,
    PresentationResult,
    RecommendationSummary,
    StockSummary,
)
from app.models.stock import StockAnalysis, StockPriceSnapshot
from app.models.strategy import InvestmentAction, PositionRecommendation, StrategyResult
from app.models.supervisor import Intent, SupervisorResult


def _market_analysis(**overrides: object) -> MarketAnalysis:
    defaults: dict[object, object] = {
        "regime": MarketRegime.NEUTRAL,
        "risk_level": RiskLevel.MEDIUM,
        "summary": "시장은 중립 국면입니다",
        "confidence": AnalysisConfidence.MEDIUM,
    }
    defaults.update(overrides)
    return MarketAnalysis(**defaults)


def _stock_analysis(**overrides: object) -> StockAnalysis:
    defaults: dict[object, object] = {
        "symbol": "005930",
        "name": "삼성전자",
        "price": StockPriceSnapshot(
            symbol="005930", name="삼성전자", price=266000, change_pct=1.72
        ),
        "financials": None,
        "financial_history": [],
        "investment_thesis": "다년 매출/이익이 연속 상승했습니다",
        "catalysts": [],
        "risks": ["부채비율 상승 추세"],
        "scenarios": [],
        "risk_level": RiskLevel.MEDIUM,
        "confidence": AnalysisConfidence.MEDIUM,
        "evidence": [],
    }
    defaults.update(overrides)
    return StockAnalysis(**defaults)


def _candidate(**overrides: object) -> Candidate:
    defaults: dict[object, object] = {
        "symbol": "000660",
        "name": "SK하이닉스",
        "market": MarketFilter.KOSPI,
        "sector": "전기전자",
        "matched_filters": {"sector": "전기전자"},
    }
    defaults.update(overrides)
    return Candidate(**defaults)


def _recommendation(**overrides: object) -> PositionRecommendation:
    defaults: dict[object, object] = {
        "symbol": "005930",
        "name": "삼성전자",
        "action": InvestmentAction.ADD,
        "current_weight": 0.12,
        "rationale": "다년 이익 개선 추세와 낮은 부채비율",
        "conditions": [],
    }
    defaults.update(overrides)
    return PositionRecommendation(**defaults)


def _strategy_result(**overrides: object) -> StrategyResult:
    defaults: dict[object, object] = {
        "summary": "전반적으로 안정적인 포트폴리오입니다",
        "recommendations": [_recommendation()],
        "portfolio_risk": RiskLevel.MEDIUM,
        "confidence": AnalysisConfidence.MEDIUM,
        "evidence": [],
    }
    defaults.update(overrides)
    return StrategyResult(**defaults)


# ---------------------------------------------------------------------------
# 순수 함수 시그니처 검증 — build_presentation은 SupervisorResult 하나만
# 받는다. LLMService/Tools 등 어떤 외부 의존성도 파라미터로 받을 수 없다는
# 것을 구조적으로 확인한다(10번 요구사항).
# ---------------------------------------------------------------------------


def test_build_presentation_signature_has_no_external_dependency() -> None:
    parameters = list(inspect.signature(build_presentation).parameters)

    assert parameters == ["result"]
    assert not inspect.iscoroutinefunction(build_presentation)


# ---------------------------------------------------------------------------
# MARKET_ONLY
# ---------------------------------------------------------------------------


def test_market_only_presentation() -> None:
    result = SupervisorResult(
        intent=Intent.MARKET_ONLY,
        market_analysis=_market_analysis(),
    )

    presentation = build_presentation(result)

    assert presentation.intent == Intent.MARKET_ONLY
    assert presentation.headline == "시장은 중립 국면입니다"
    assert presentation.market is not None
    assert presentation.market.regime == MarketRegime.NEUTRAL
    assert presentation.market.risk_level == RiskLevel.MEDIUM
    assert presentation.market.summary == "시장은 중립 국면입니다"
    assert presentation.market.confidence == AnalysisConfidence.MEDIUM
    assert presentation.stocks == []
    assert presentation.discovery is None
    assert presentation.portfolio is None


# ---------------------------------------------------------------------------
# STOCK_RESEARCH
# ---------------------------------------------------------------------------


def test_stock_research_presentation_single_symbol_uses_thesis_as_headline() -> None:
    stock = _stock_analysis()
    result = SupervisorResult(
        intent=Intent.STOCK_RESEARCH,
        resolved_symbols=["005930"],
        stock_analyses=[stock],
    )

    presentation = build_presentation(result)

    assert presentation.headline == stock.investment_thesis
    assert len(presentation.stocks) == 1

    summary = presentation.stocks[0]
    assert summary.symbol == "005930"
    assert summary.name == "삼성전자"
    assert summary.price == 266000.0
    assert summary.change_pct == 1.72
    assert summary.investment_thesis == stock.investment_thesis
    assert summary.risks == stock.risks
    assert summary.catalysts == stock.catalysts
    assert summary.risk_level == stock.risk_level
    assert summary.confidence == stock.confidence


def test_stock_research_presentation_multiple_symbols_has_no_headline() -> None:
    # 여러 종목의 investment_thesis를 하나로 합치는 것 자체가 새로운
    # 종합 판단이 될 수 있으므로, 단일 headline을 만들지 않는다 — 각 종목의
    # thesis는 stocks[].investment_thesis에 그대로 남는다.
    result = SupervisorResult(
        intent=Intent.STOCK_RESEARCH,
        resolved_symbols=["005930", "000660"],
        stock_analyses=[
            _stock_analysis(),
            _stock_analysis(symbol="000660", name="SK하이닉스"),
        ],
    )

    presentation = build_presentation(result)

    assert presentation.headline is None
    assert len(presentation.stocks) == 2


def test_stock_summary_never_carries_financial_history_or_evidence_fields() -> None:
    # StockSummary 모델 자체에 financial_history/evidence 필드가 없어야
    # 한다 — 실수로도 detail 데이터를 summary에 채울 수 없게 한다.
    assert "financial_history" not in StockSummary.model_fields
    assert "evidence" not in StockSummary.model_fields
    assert "financials" not in StockSummary.model_fields
    assert "scenarios" not in StockSummary.model_fields


# ---------------------------------------------------------------------------
# CANDIDATE_DISCOVERY
# ---------------------------------------------------------------------------


def test_candidate_discovery_presentation() -> None:
    candidates = [_candidate(), _candidate(symbol="005380", name="현대차")]
    stock_analyses = [
        _stock_analysis(symbol="000660", name="SK하이닉스"),
        _stock_analysis(symbol="005380", name="현대차"),
    ]
    result = SupervisorResult(
        intent=Intent.CANDIDATE_DISCOVERY,
        resolved_symbols=[c.symbol for c in candidates],
        candidates=candidates,
        stock_analyses=stock_analyses,
        skipped=["005380: 일시적 오류"],
    )

    presentation = build_presentation(result)

    assert presentation.headline == "2건의 후보를 찾았습니다"
    assert presentation.discovery is not None
    assert presentation.discovery.candidate_count == 2
    # Candidate 자체를 그대로 재사용한다 — matched_filters를 포함해 필터링
    # 근거가 그대로 남는다.
    assert presentation.discovery.candidates == candidates
    # 후보에 대한 짧은 분석 요약도 함께 노출한다(기존 stocks 필드 재사용).
    assert len(presentation.stocks) == 2
    assert presentation.skipped == ["005380: 일시적 오류"]


# ---------------------------------------------------------------------------
# PORTFOLIO_STRATEGY
# ---------------------------------------------------------------------------


def test_portfolio_strategy_presentation() -> None:
    strategy_result = _strategy_result(
        recommendations=[
            _recommendation(
                symbol="005930",
                name="삼성전자",
                action=InvestmentAction.ADD,
                current_weight=0.12,
                rationale="다년 이익 개선 추세",
                conditions=["추가 하락 시 분할 매수"],
            ),
            _recommendation(
                symbol="000660",
                name="SK하이닉스",
                action=InvestmentAction.HOLD,
                current_weight=0.08,
                rationale="현재 비중 유지가 적절",
                conditions=[],
            ),
        ]
    )
    # PORTFOLIO_STRATEGY도 stock_analyses를 갖지만(보유종목 fan-out),
    # presentation.stocks에는 반영되지 않아야 한다 — 원래 문제(응답 과다)가
    # 재현되지 않도록 한다.
    stock_analyses = [
        _stock_analysis(symbol="005930", name="삼성전자"),
        _stock_analysis(symbol="000660", name="SK하이닉스"),
    ]
    result = SupervisorResult(
        intent=Intent.PORTFOLIO_STRATEGY,
        resolved_symbols=["005930", "000660"],
        market_analysis=_market_analysis(),
        stock_analyses=stock_analyses,
        strategy_result=strategy_result,
        skipped=[],
    )

    presentation = build_presentation(result)

    assert presentation.headline == strategy_result.summary
    assert presentation.market is not None  # 시장 환경도 함께 노출
    assert presentation.stocks == []  # 종목별 raw StockAnalysis는 노출 안 함

    portfolio = presentation.portfolio
    assert portfolio is not None
    assert portfolio.portfolio_risk == strategy_result.portfolio_risk
    assert portfolio.confidence == strategy_result.confidence
    assert portfolio.summary == strategy_result.summary
    assert portfolio.recommendation_count == 2
    assert len(portfolio.recommendations) == 2


def test_portfolio_summary_recommendation_action_and_rationale_match_original() -> None:
    # 7번 요구사항의 핵심 회귀 테스트: presentation layer가 action/rationale을
    # 재해석하거나 값을 바꾸면 안 된다 — 원본과 정확히 동일해야 한다.
    original = _recommendation(
        symbol="005930",
        action=InvestmentAction.REDUCE,
        rationale="원본 rationale 문장 그대로",
        conditions=["조건 A", "조건 B"],
        current_weight=0.25,
    )
    strategy_result = _strategy_result(recommendations=[original])
    result = SupervisorResult(
        intent=Intent.PORTFOLIO_STRATEGY,
        market_analysis=_market_analysis(),
        strategy_result=strategy_result,
    )

    presentation = build_presentation(result)

    summary = presentation.portfolio.recommendations[0]
    assert summary.symbol == original.symbol
    assert summary.name == original.name
    assert summary.action == original.action
    assert summary.rationale == original.rationale
    assert summary.conditions == original.conditions
    assert summary.current_weight == original.current_weight


def test_portfolio_strategy_presentation_omitted_when_strategy_result_missing() -> None:
    # Portfolio reasoning이 부분 실패해 strategy_result가 None인 경우
    # (ReasoningError로 skip된 경우) portfolio 섹션 자체를 만들지 않는다 —
    # 근거 없는 PortfolioSummary를 임의로 채우지 않는다.
    result = SupervisorResult(
        intent=Intent.PORTFOLIO_STRATEGY,
        market_analysis=_market_analysis(),
        strategy_result=None,
        skipped=["portfolio_strategy: ReasoningError(...)"],
    )

    presentation = build_presentation(result)

    assert presentation.portfolio is None
    assert presentation.headline is None
    assert presentation.skipped == ["portfolio_strategy: ReasoningError(...)"]


def test_recommendation_summary_and_portfolio_summary_have_no_forbidden_fields() -> (
    None
):
    # 5/7번 요구사항: target_weight/target_price 같은 새 판단 필드와,
    # raw StockAnalysis/evidence를 담는 필드 자체가 모델에 없어야 한다.
    assert "target_weight" not in RecommendationSummary.model_fields
    assert "target_price" not in RecommendationSummary.model_fields

    assert "evidence" not in PortfolioSummary.model_fields
    assert "stock_analyses" not in PortfolioSummary.model_fields
    assert "portfolio_context" not in PortfolioSummary.model_fields


# ---------------------------------------------------------------------------
# skipped pass-through (모든 intent 공통)
# ---------------------------------------------------------------------------


def test_skipped_is_passed_through_unchanged() -> None:
    result = SupervisorResult(
        intent=Intent.STOCK_RESEARCH,
        stock_analyses=[_stock_analysis()],
        skipped=["000660: 일시적 오류", "005380: Stock Research 미지원"],
    )

    presentation = build_presentation(result)

    assert presentation.skipped == [
        "000660: 일시적 오류",
        "005380: Stock Research 미지원",
    ]


def test_presentation_result_has_no_forbidden_top_level_fields() -> None:
    # PresentationResult 자체에도 raw evidence/portfolio_context 같은
    # detail 전용 필드가 없어야 한다.
    assert "evidence" not in PresentationResult.model_fields
    assert "portfolio_context" not in PresentationResult.model_fields

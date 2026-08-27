import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.portfolio.reasoning import ReasoningError as PortfolioReasoningError
from app.api.main import app
from app.api.routes import get_supervisor
from app.discovery.orchestrator import DiscoveryError
from app.models.common import AnalysisConfidence, RiskLevel, UserRequest
from app.models.discovery import Candidate, MarketFilter
from app.models.market import MarketAnalysis, MarketRegime
from app.models.stock import StockAnalysis, StockPriceSnapshot
from app.models.strategy import InvestmentAction, PositionRecommendation, StrategyResult
from app.models.supervisor import Intent, SupervisorResult
from app.supervisor.orchestrator import SupervisorError
from app.supervisor.routing import RoutingError


class _FakeSupervisor:
    def __init__(
        self,
        result: SupervisorResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple] = []

    async def run(self, request, *, as_of_date=None, business_year=None, investor_profile=None):
        self.calls.append((request, investor_profile))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


@pytest.fixture
def override_supervisor():
    overridden: list[_FakeSupervisor] = []

    def _apply(fake: _FakeSupervisor) -> None:
        overridden.append(fake)
        app.dependency_overrides[get_supervisor] = lambda: fake

    yield _apply
    app.dependency_overrides.pop(get_supervisor, None)


def _market_analysis() -> MarketAnalysis:
    return MarketAnalysis(
        regime=MarketRegime.NEUTRAL,
        risk_level=RiskLevel.MEDIUM,
        summary="테스트 시장 요약",
        confidence=AnalysisConfidence.MEDIUM,
    )


def _stock_analysis(symbol: str = "005930", name: str = "삼성전자") -> StockAnalysis:
    return StockAnalysis(
        symbol=symbol,
        name=name,
        price=StockPriceSnapshot(symbol=symbol, name=name, price=100000),
        investment_thesis="테스트 investment thesis",
        risk_level=RiskLevel.MEDIUM,
        confidence=AnalysisConfidence.MEDIUM,
    )


def _strategy_result() -> StrategyResult:
    return StrategyResult(
        summary="테스트 전략 요약",
        recommendations=[
            PositionRecommendation(
                symbol="005930",
                name="삼성전자",
                action=InvestmentAction.ADD,
                current_weight=0.1,
                rationale="테스트 rationale",
            )
        ],
        portfolio_risk=RiskLevel.MEDIUM,
        confidence=AnalysisConfidence.MEDIUM,
    )


def test_health_returns_ok_without_calling_supervisor(override_supervisor) -> None:
    fake = _FakeSupervisor(result=SupervisorResult(intent=Intent.MARKET_ONLY))
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake.calls == []


def test_analysis_market_only_returns_supervisor_result(override_supervisor) -> None:
    fake = _FakeSupervisor(
        result=SupervisorResult(
            intent=Intent.MARKET_ONLY, market_analysis=_market_analysis()
        )
    )
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post("/analysis", json={"question": "요즘 시장 상황 어때?"})

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "market_only"
    assert body["market_analysis"]["regime"] == "neutral"
    assert body["market_analysis"]["risk_level"] == "medium"

    user_request, investor_profile = fake.calls[0]
    assert isinstance(user_request, UserRequest)
    assert user_request.question == "요즘 시장 상황 어때?"
    assert investor_profile is None


def test_analysis_passes_investor_profile_separately_from_user_request(
    override_supervisor,
) -> None:
    # UserRequest 자체에는 investor_profile 필드가 없어야 한다 — Core
    # domain model을 HTTP transport 편의를 위해 바꾸지 않는다는 설계
    # 제약을 검증한다.
    assert "investor_profile" not in UserRequest.model_fields

    fake = _FakeSupervisor(result=SupervisorResult(intent=Intent.PORTFOLIO_STRATEGY))
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post(
            "/analysis",
            json={
                "question": "내 포트폴리오 분석해줘",
                "investor_profile": {"risk_tolerance": "medium"},
            },
        )

    assert response.status_code == 200

    user_request, investor_profile = fake.calls[0]
    assert isinstance(user_request, UserRequest)
    assert investor_profile is not None
    assert investor_profile.risk_tolerance.value == "medium"


def test_analysis_invalid_request_returns_422(override_supervisor) -> None:
    fake = _FakeSupervisor(result=SupervisorResult(intent=Intent.MARKET_ONLY))
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post("/analysis", json={"question": ""})

    assert response.status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (RoutingError("분류 실패"), 502),
        (SupervisorError("investor_profile이 필요합니다"), 400),
        (DiscoveryError("조건에 맞는 종목이 50건입니다"), 400),
        (PortfolioReasoningError("근거 있는 결과를 얻지 못했습니다"), 502),
    ],
)
def test_analysis_core_exceptions_map_to_expected_status(
    override_supervisor, error, expected_status
) -> None:
    fake = _FakeSupervisor(error=error)
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post("/analysis", json={"question": "질문"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_analysis_unhandled_exception_returns_500_without_leaking_message(
    override_supervisor,
) -> None:
    secret_marker = "SECRET_ECOS_KEY_DO_NOT_LEAK"
    fake = _FakeSupervisor(
        error=RuntimeError(
            f"boom: https://ecos.bok.or.kr/api/StatisticSearch/{secret_marker}/json"
        )
    )
    override_supervisor(fake)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/analysis", json={"question": "질문"})

    assert response.status_code == 500
    body_text = response.text

    assert secret_marker not in body_text
    assert "RuntimeError" not in body_text
    assert "boom" not in body_text
    assert response.json() == {
        "detail": "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    }


def test_analysis_httpx_exception_does_not_leak_url_with_api_key(
    override_supervisor,
) -> None:
    # ECOS/OpenDART는 API key가 URL 경로/쿼리 파라미터에 그대로 포함된다
    # (app/services/ecos.py, app/services/opendart.py 확인). httpx 예외의
    # 기본 str()에는 request URL이 들어가므로, 이런 예외가 그대로 client에
    # 전달되지 않는지 실제 httpx 예외 형태로 검증한다.
    secret_key = "FAKE_ECOS_API_KEY_12345"
    request = httpx.Request(
        "GET",
        f"https://ecos.bok.or.kr/api/StatisticSearch/{secret_key}/json/kr/1/100/722Y001",
    )
    http_response = httpx.Response(500, request=request)
    exc = httpx.HTTPStatusError("Server error", request=request, response=http_response)

    fake = _FakeSupervisor(error=exc)
    override_supervisor(fake)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/analysis", json={"question": "질문"})

    assert response.status_code == 500
    assert secret_key not in response.text
    assert "ecos.bok.or.kr" not in response.text


def test_analysis_no_investor_profile_field_leaks_to_user_request_when_absent(
    override_supervisor,
) -> None:
    fake = _FakeSupervisor(result=SupervisorResult(intent=Intent.STOCK_RESEARCH))
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post(
            "/analysis", json={"question": "삼성전자 분석해줘", "symbols": ["005930"]}
        )

    assert response.status_code == 200
    user_request, investor_profile = fake.calls[0]
    assert user_request.symbols == ["005930"]
    assert investor_profile is None


# ============================== view=summary ==============================


def test_analysis_view_summary_market_only(override_supervisor) -> None:
    fake = _FakeSupervisor(
        result=SupervisorResult(
            intent=Intent.MARKET_ONLY, market_analysis=_market_analysis()
        )
    )
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post(
            "/analysis?view=summary", json={"question": "요즘 시장 상황 어때?"}
        )

    assert response.status_code == 200
    body = response.json()

    assert body["intent"] == "market_only"
    assert body["headline"] == "테스트 시장 요약"
    assert body["market"]["regime"] == "neutral"
    # detail 전용 필드는 summary 응답에 존재하지 않는다.
    assert "evidence" not in body
    assert "portfolio_context" not in body


def test_analysis_view_summary_stock_research(override_supervisor) -> None:
    fake = _FakeSupervisor(
        result=SupervisorResult(
            intent=Intent.STOCK_RESEARCH,
            resolved_symbols=["005930"],
            stock_analyses=[_stock_analysis()],
        )
    )
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post(
            "/analysis?view=summary", json={"question": "삼성전자 어때?"}
        )

    assert response.status_code == 200
    body = response.json()

    assert body["intent"] == "stock_research"
    assert len(body["stocks"]) == 1
    stock = body["stocks"][0]
    assert stock["symbol"] == "005930"
    assert stock["investment_thesis"] == "테스트 investment thesis"
    # financial_history/evidence 같은 raw 상세 필드는 summary에 없다.
    assert "financial_history" not in stock
    assert "evidence" not in stock


def test_analysis_view_summary_candidate_discovery(override_supervisor) -> None:
    candidate = Candidate(
        symbol="000660",
        name="SK하이닉스",
        market=MarketFilter.KOSPI,
        sector="전기전자",
        matched_filters={"sector": "전기전자"},
    )
    fake = _FakeSupervisor(
        result=SupervisorResult(
            intent=Intent.CANDIDATE_DISCOVERY,
            resolved_symbols=["000660"],
            candidates=[candidate],
            stock_analyses=[_stock_analysis(symbol="000660", name="SK하이닉스")],
        )
    )
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post(
            "/analysis?view=summary", json={"question": "반도체 업종 후보 찾아줘"}
        )

    assert response.status_code == 200
    body = response.json()

    assert body["intent"] == "candidate_discovery"
    assert body["discovery"]["candidate_count"] == 1
    assert body["discovery"]["candidates"][0]["symbol"] == "000660"
    assert len(body["stocks"]) == 1


def test_analysis_view_summary_portfolio_strategy(override_supervisor) -> None:
    fake = _FakeSupervisor(
        result=SupervisorResult(
            intent=Intent.PORTFOLIO_STRATEGY,
            resolved_symbols=["005930"],
            market_analysis=_market_analysis(),
            stock_analyses=[_stock_analysis()],
            strategy_result=_strategy_result(),
        )
    )
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post(
            "/analysis?view=summary",
            json={
                "question": "내 포트폴리오 분석해줘",
                "investor_profile": {"risk_tolerance": "medium"},
            },
        )

    assert response.status_code == 200
    body = response.json()

    assert body["intent"] == "portfolio_strategy"
    assert body["portfolio"]["recommendation_count"] == 1
    recommendation = body["portfolio"]["recommendations"][0]
    assert recommendation["action"] == "add"
    assert recommendation["rationale"] == "테스트 rationale"
    # target_weight/target_price 같은 새 판단 필드는 존재하지 않는다.
    assert "target_weight" not in recommendation
    assert "target_price" not in recommendation
    # 종목별 raw StockAnalysis는 summary에 노출되지 않는다(PortfolioSummary
    # 안의 간결한 recommendation으로만 표현).
    assert body["stocks"] == []


def test_analysis_view_detail_default_matches_existing_response_shape(
    override_supervisor,
) -> None:
    # view를 생략하면 기존 SupervisorResult 응답 shape과 완전히 동일해야
    # 한다 — 기존 client와의 호환성 확인.
    fake = _FakeSupervisor(
        result=SupervisorResult(
            intent=Intent.MARKET_ONLY, market_analysis=_market_analysis()
        )
    )
    override_supervisor(fake)

    with TestClient(app) as client:
        default_response = client.post(
            "/analysis", json={"question": "요즘 시장 상황 어때?"}
        )
        explicit_detail_response = client.post(
            "/analysis?view=detail", json={"question": "요즘 시장 상황 어때?"}
        )

    assert default_response.status_code == 200
    assert default_response.json() == explicit_detail_response.json()
    # summary 전용 필드(headline 등)는 detail 응답에 없다.
    assert "headline" not in default_response.json()


def test_analysis_invalid_view_returns_422_without_calling_supervisor(
    override_supervisor,
) -> None:
    fake = _FakeSupervisor(result=SupervisorResult(intent=Intent.MARKET_ONLY))
    override_supervisor(fake)

    with TestClient(app) as client:
        response = client.post(
            "/analysis?view=both", json={"question": "요즘 시장 상황 어때?"}
        )

    assert response.status_code == 422
    assert fake.calls == []

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agents.market.orchestrator import MarketOrchestrator
from app.agents.market.reasoning import ReasoningError as MarketReasoningError
from app.agents.portfolio.orchestrator import PortfolioStrategyOrchestrator
from app.agents.portfolio.reasoning import ReasoningError as PortfolioReasoningError
from app.agents.stock_research.orchestrator import StockResearchOrchestrator
from app.agents.stock_research.reasoning import ReasoningError as StockReasoningError
from app.api.routes import router
from app.config import settings
from app.discovery.filter_intent import FilterIntentError
from app.discovery.orchestrator import DiscoveryError, DiscoveryOrchestrator
from app.mcp.ecos_tools import EcosTools
from app.mcp.kiwoom_tools import KiwoomTools
from app.mcp.opendart_tools import OpenDartTools
from app.services.ecos import EcosService
from app.services.kiwoom import KiwoomService
from app.services.llm import LLMService
from app.services.opendart import OpenDartService
from app.supervisor.orchestrator import SupervisorError, SupervisorOrchestrator
from app.supervisor.routing import RoutingError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 이 프로세스가 살아있는 동안 재사용할 의존성 그래프를 1회만 생성한다
    # (scripts/supervisor_demo.py와 동일한 구성). 요청마다 새로 만들면
    # KiwoomService의 access token instance-level 캐싱이 의미가 없어진다.
    #
    # 여기서 만드는 각 Service는 생성 시점에 실제 네트워크 호출을 하지
    # 않는다(자격증명을 속성으로 저장할 뿐) — 이후 v1 범위에서 다루지 않는
    # multi-worker 배포에서는 워커마다 별도 프로세스라 이 그래프도 워커마다
    # 따로 생성되며, token 캐시도 워커별로 분리된다(공유 캐시 없음 — 원칙
    # 상 Redis 등을 미리 넣지 않음).
    kiwoom_service = KiwoomService(
        app_key=settings.kiwoom_app_key,
        secret_key=settings.kiwoom_secret_key,
    )
    kiwoom_tools = KiwoomTools(service=kiwoom_service)

    opendart_service = OpenDartService(api_key=settings.opendart_api_key)
    opendart_tools = OpenDartTools(service=opendart_service)

    ecos_service = EcosService(api_key=settings.ecos_api_key)
    ecos_tools = EcosTools(service=ecos_service)

    # Supervisor 경로는 routing + 최대 3개 Agent(+ Discovery)의 LLM 호출까지
    # 이어질 수 있어, 데모 스크립트들과 동일한 이유로 기본 30초보다 넉넉한
    # timeout을 쓴다.
    llm_service = LLMService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout=90.0,
    )

    app.state.supervisor = SupervisorOrchestrator(
        llm_service=llm_service,
        market_orchestrator=MarketOrchestrator(
            ecos_tools=ecos_tools, llm_service=llm_service
        ),
        stock_research_orchestrator=StockResearchOrchestrator(
            kiwoom_tools=kiwoom_tools,
            opendart_tools=opendart_tools,
            llm_service=llm_service,
        ),
        portfolio_orchestrator=PortfolioStrategyOrchestrator(
            llm_service=llm_service
        ),
        discovery_orchestrator=DiscoveryOrchestrator(
            kiwoom_tools=kiwoom_tools, llm_service=llm_service
        ),
        kiwoom_tools=kiwoom_tools,
        opendart_tools=opendart_tools,
    )

    yield


app = FastAPI(
    title="Personal Investment Multi-Agent System API",
    lifespan=lifespan,
)
app.include_router(router)


# ============================== Error mapping ==============================
#
# 502: routing/filter-intent/reasoning 등 이 프로젝트의 LLM 기반 dependency를
# 통해 요청을 정상 완료하지 못한 경우를 뜻하는 API 정책이다. 일반적인
# "네트워크 게이트웨이 오류"라는 의미가 아니라, "LLM이 근거 있는 결과를
# 만들지 못해 재시도까지 실패한 상태"를 가리킨다는 점을 문서로 남긴다
# (자세한 내용은 README/dev-log 참고).
async def _external_dependency_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


# 400: 요청 자체를 클라이언트가 고치면 해결 가능한 실패(예: investor_profile
# 누락, 후보 과다로 인한 discovery 거부, 종목 특정 불가).
async def _client_correctable_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# 500: 그 외 전부. ECOS는 API key가 URL 경로에(app/services/ecos.py), OpenDART는
# 쿼리 파라미터에(app/services/opendart.py) 그대로 포함되므로, 이런 예외의
# 원문(str(exc))을 client에 그대로 전달하면 credential이 유출될 수 있다.
# 서버 로그에는 전체 내용을 남기고 client에는 고정된 일반 메시지만
# 반환한다 — 실패를 숨기는 게 아니라(500은 정직하게 알림), 실패의 원문
# 내용만 감춘다.
async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception while handling %s", request.url.path)

    return JSONResponse(
        status_code=500,
        content={"detail": "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."},
    )


app.add_exception_handler(RoutingError, _external_dependency_error_handler)
app.add_exception_handler(FilterIntentError, _external_dependency_error_handler)
app.add_exception_handler(MarketReasoningError, _external_dependency_error_handler)
app.add_exception_handler(StockReasoningError, _external_dependency_error_handler)
app.add_exception_handler(PortfolioReasoningError, _external_dependency_error_handler)
app.add_exception_handler(SupervisorError, _client_correctable_error_handler)
app.add_exception_handler(DiscoveryError, _client_correctable_error_handler)
app.add_exception_handler(Exception, _unhandled_error_handler)

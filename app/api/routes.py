from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.presentation import build_presentation
from app.api.snapshot_store import AnalysisSnapshotStore
from app.models.common import UserRequest
from app.models.portfolio import InvestorProfile
from app.models.presentation import PresentationResult
from app.models.supervisor import SupervisorResult
from app.supervisor.orchestrator import SupervisorOrchestrator

router = APIRouter()

# GET /analysis/{analysis_id}에서 snapshot이 없거나 만료됐을 때 반환하는
# 고정 메시지 — 내부 정보(존재했었는지/TTL 값 등)를 노출하지 않는다.
# 과거에 존재했던 id와 애초에 존재하지 않았던 id를 store가 구분해 보관하지
# 않으므로 410 Gone은 쓰지 않는다(둘 다 "지금은 없음"이라는 404가 정확하다).
_ANALYSIS_SNAPSHOT_NOT_FOUND_DETAIL = "Analysis snapshot not found or expired."


class AnalysisRequest(BaseModel):
    # HTTP transport 편의를 위한 API 레이어 전용 DTO다. Core의 domain model인
    # UserRequest에는 investor_profile을 추가하지 않는다 —
    # SupervisorOrchestrator.run(request, investor_profile=...)이 이미 이
    # 둘을 의도적으로 분리하고 있으므로 그 경계를 그대로 유지하고, 이
    # endpoint에서만 다시 둘로 나눠 넘긴다.
    question: str = Field(min_length=1)
    symbols: list[str] = Field(default_factory=list)
    investor_profile: InvestorProfile | None = None


def get_supervisor(request: Request) -> SupervisorOrchestrator:
    # lifespan(app/api/main.py)에서 프로세스 생애주기 동안 1회만 생성해
    # app.state에 저장해둔 인스턴스를 그대로 반환한다 — 요청마다 새로
    # 만들지 않아야 KiwoomService의 access token 캐싱이 의미가 있다.
    return request.app.state.supervisor


def get_snapshot_store(request: Request) -> AnalysisSnapshotStore:
    # get_supervisor()와 동일한 패턴 — lifespan에서 1회 생성된 인스턴스를
    # 그대로 반환한다. 요청마다 새로 만들면 다른 요청이 저장한 snapshot을
    # 조회할 수 없다(UX-04의 핵심 전제).
    return request.app.state.snapshot_store


@router.get("/health")
async def health() -> dict[str, str]:
    # 외부 API(Kiwoom/OpenAI/ECOS/OpenDART)를 호출하지 않는다 — 이 프로세스
    # 자체가 살아있는지만 확인한다.
    return {"status": "ok"}


@router.post("/analysis", response_model=None)
async def analyze(
    payload: AnalysisRequest,
    response: Response,
    # view 생략(기본값 "detail")은 기존 SupervisorResult 응답 shape을 그대로
    # 유지한다 — 기존 client와 100% 호환. "summary"만 PresentationResult로
    # 바꿔 반환한다. Literal 타입이라 그 외 값은 FastAPI가 자동으로 422를
    # 반환한다(both는 v1 범위 밖 — payload를 줄이는 게 목적인데 요약+상세를
    # 함께 반환하면 원래 문제가 그대로 남는다. 실제 Flutter 사용에서
    # summary→detail 재요청 latency가 문제가 되면 그때 caching과 함께
    # 재검토한다).
    view: Literal["detail", "summary"] = "detail",
    supervisor: SupervisorOrchestrator = Depends(get_supervisor),  # noqa: B008
    snapshot_store: AnalysisSnapshotStore = Depends(get_snapshot_store),  # noqa: B008
) -> SupervisorResult | PresentationResult:
    user_request = UserRequest(question=payload.question, symbols=payload.symbols)

    result = await supervisor.run(
        user_request, investor_profile=payload.investor_profile
    )

    # UX-04: 이번 실행으로 만들어진 SupervisorResult를 snapshot으로 저장해
    # analysis_id를 발급한다. body shape은 기존과 완전히 동일하게 유지하고
    # (response_model 변경 없음), analysis_id는 header로만 전달해 기존
    # client의 backward compatibility를 깨지 않는다.
    analysis_id = snapshot_store.put(result)
    response.headers["X-Analysis-ID"] = analysis_id

    if view == "summary":
        # build_presentation()은 순수 함수다 — LLM/외부 API를 호출하지
        # 않고 이미 계산된 result만 읽어 옮긴다(app/api/presentation.py 참고).
        return build_presentation(result)

    return result


@router.get("/analysis/{analysis_id}", response_model=None)
async def get_analysis(
    analysis_id: str,
    view: Literal["detail", "summary"] = "detail",
    snapshot_store: AnalysisSnapshotStore = Depends(get_snapshot_store),  # noqa: B008
) -> SupervisorResult | PresentationResult:
    # UX-04 핵심 invariant: 이 endpoint는 Supervisor.run()을 절대 호출하지
    # 않는다 — POST /analysis로 이미 만들어진 SupervisorResult snapshot을
    # 그대로 조회하거나(detail), 그 snapshot에 build_presentation()이라는
    # 순수 projection만 적용해(summary) 반환한다. 즉 refresh/재분석이
    # 아니라 이미 생성된 분석의 조회다 — 새 시장 데이터/reasoning이
    # 필요하면 client가 다시 POST해야 한다.
    result = snapshot_store.get(analysis_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=_ANALYSIS_SNAPSHOT_NOT_FOUND_DETAIL
        )

    if view == "summary":
        return build_presentation(result)

    return result

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.models.common import UserRequest
from app.models.portfolio import InvestorProfile
from app.models.supervisor import SupervisorResult
from app.supervisor.orchestrator import SupervisorOrchestrator

router = APIRouter()


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


@router.get("/health")
async def health() -> dict[str, str]:
    # 외부 API(Kiwoom/OpenAI/ECOS/OpenDART)를 호출하지 않는다 — 이 프로세스
    # 자체가 살아있는지만 확인한다.
    return {"status": "ok"}


@router.post("/analysis", response_model=SupervisorResult)
async def analyze(
    payload: AnalysisRequest,
    supervisor: SupervisorOrchestrator = Depends(get_supervisor),  # noqa: B008
) -> SupervisorResult:
    user_request = UserRequest(question=payload.question, symbols=payload.symbols)

    return await supervisor.run(user_request, investor_profile=payload.investor_profile)

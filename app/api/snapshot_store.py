import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models.supervisor import SupervisorResult

# API/snapshot lifecycle을 위한 임시 보관 기간이지 투자 판단의 금융적
# 유효기간이 아니다 — TTL이 지나면 "동일 analysis_id 재조회가 보장되지
# 않는다"는 의미일 뿐, 그 시점의 분석이 틀렸다는 뜻이 아니다. 이 값은
# 이 프로젝트의 기존 관례(app/discovery/orchestrator.py의
# MAX_STOCK_RESEARCH_FANOUT)를 따라 모듈 상수로 둔다 — config.py에 넣거나
# 환경변수로 노출하지 않는다(아직 관측되지 않은 확장 가능성만으로
# 미리 설정 가능하게 만들지 않는다).
DEFAULT_ANALYSIS_SNAPSHOT_TTL = timedelta(minutes=30)


@dataclass
class _Entry:
    result: SupervisorResult
    expires_at: datetime


class AnalysisSnapshotStore:
    """`SupervisorResult`를 analysis_id로 임시 보관하는 in-memory TTL store.

    UX-04의 목표는 summary/detail 조회가 동일 `SupervisorResult` snapshot을
    공유해 Supervisor/Agent/LLM/외부 API를 재실행하지 않게 하는 것뿐이다.
    그 이상의 책임(영속성, multi-worker 공유, 분석 history)은 의도적으로
    갖지 않는다 — DB/Redis/background job은 v1 범위 밖이다.

    FastAPI lifespan(app/api/main.py)에서 프로세스 생애주기 동안 1회만
    생성해 `app.state`에 저장하고, 요청마다 재사용해야 한다(요청마다 새로
    만들면 다른 요청이 저장한 snapshot을 조회할 수 없다).

    Concurrency: `put()`/`get()` 모두 `await` 지점이 없는 순수 동기 dict
    연산이다 — 이벤트 루프는 `await` 지점에서만 다른 task로 넘어가므로,
    이 메서드들이 실행되는 동안 다른 코루틴이 끼어들 수 없다(atomic).
    따라서 race condition이 발생할 지점 자체가 없어 `asyncio.Lock`을
    예방적으로 추가하지 않는다 — 현재 `--workers 1` 단일 프로세스
    전제에서만 유효한 판단이며, multi-worker로 확장하면(v1 범위 밖) 이
    in-memory dict 자체가 worker마다 분리되는 더 근본적인 한계에 먼저
    부딪힌다(Kiwoom access token 캐시와 동일한 성격의 제약).
    """

    def __init__(
        self,
        ttl: timedelta = DEFAULT_ANALYSIS_SNAPSHOT_TTL,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._snapshots: dict[str, _Entry] = {}

    def put(self, result: SupervisorResult) -> str:
        # 별도 background cleanup task를 두지 않는 대신, 쓰기 시점마다
        # 만료된 항목을 함께 정리한다 — 아무도 만료된 id를 다시 get()하지
        # 않아도 store가 무한히 커지지 않도록 하는 최소한의 lazy cleanup.
        self._evict_expired()

        analysis_id = str(uuid.uuid4())
        self._snapshots[analysis_id] = _Entry(
            result=result, expires_at=self._clock() + self._ttl
        )
        return analysis_id

    def get(self, analysis_id: str) -> SupervisorResult | None:
        entry = self._snapshots.get(analysis_id)
        if entry is None:
            return None

        if entry.expires_at <= self._clock():
            del self._snapshots[analysis_id]
            return None

        return entry.result

    def _evict_expired(self) -> None:
        now = self._clock()
        expired_ids = [
            analysis_id
            for analysis_id, entry in self._snapshots.items()
            if entry.expires_at <= now
        ]
        for analysis_id in expired_ids:
            del self._snapshots[analysis_id]

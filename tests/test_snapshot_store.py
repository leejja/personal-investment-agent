from datetime import UTC, datetime, timedelta

from app.api.snapshot_store import AnalysisSnapshotStore
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.market import MarketAnalysis, MarketRegime
from app.models.supervisor import Intent, SupervisorResult


def _result(summary: str = "테스트 시장 요약") -> SupervisorResult:
    return SupervisorResult(
        intent=Intent.MARKET_ONLY,
        market_analysis=MarketAnalysis(
            regime=MarketRegime.NEUTRAL,
            risk_level=RiskLevel.MEDIUM,
            summary=summary,
            confidence=AnalysisConfidence.MEDIUM,
        ),
    )


class _FakeClock:
    """`AnalysisSnapshotStore`에 주입해 실제 sleep 없이 시간 경과를
    결정론적으로 시뮬레이션하기 위한 테스트 전용 clock. 실제 datetime.now()
    호출은 하지 않고 테스트가 명시적으로 advance()한 시각만 반환한다."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def test_put_returns_analysis_id() -> None:
    store = AnalysisSnapshotStore()

    analysis_id = store.put(_result())

    assert isinstance(analysis_id, str)
    assert analysis_id


def test_get_immediately_after_put_returns_same_result() -> None:
    store = AnalysisSnapshotStore()
    result = _result()

    analysis_id = store.put(result)

    assert store.get(analysis_id) is result


def test_different_puts_produce_different_ids() -> None:
    store = AnalysisSnapshotStore()

    id1 = store.put(_result("첫 번째"))
    id2 = store.put(_result("두 번째"))

    assert id1 != id2
    assert store.get(id1).market_analysis.summary == "첫 번째"
    assert store.get(id2).market_analysis.summary == "두 번째"


def test_get_unknown_id_returns_none() -> None:
    store = AnalysisSnapshotStore()

    assert store.get("존재하지-않는-id") is None


def test_get_before_ttl_expiry_returns_result() -> None:
    clock = _FakeClock(datetime(2026, 8, 29, 10, 0, tzinfo=UTC))
    store = AnalysisSnapshotStore(ttl=timedelta(minutes=30), clock=clock)
    result = _result()

    analysis_id = store.put(result)
    clock.advance(timedelta(minutes=29, seconds=59))

    assert store.get(analysis_id) is result


def test_get_after_ttl_expiry_returns_none() -> None:
    clock = _FakeClock(datetime(2026, 8, 29, 10, 0, tzinfo=UTC))
    store = AnalysisSnapshotStore(ttl=timedelta(minutes=30), clock=clock)

    analysis_id = store.put(_result())
    clock.advance(timedelta(minutes=30, seconds=1))

    assert store.get(analysis_id) is None


def test_get_at_exact_ttl_boundary_returns_none() -> None:
    # expires_at <= now를 만료로 판정하는 경계값을 명시적으로 검증한다.
    clock = _FakeClock(datetime(2026, 8, 29, 10, 0, tzinfo=UTC))
    store = AnalysisSnapshotStore(ttl=timedelta(minutes=30), clock=clock)

    analysis_id = store.put(_result())
    clock.advance(timedelta(minutes=30))

    assert store.get(analysis_id) is None


def test_expired_snapshot_is_evicted_lazily_on_get() -> None:
    clock = _FakeClock(datetime(2026, 8, 29, 10, 0, tzinfo=UTC))
    store = AnalysisSnapshotStore(ttl=timedelta(minutes=30), clock=clock)

    analysis_id = store.put(_result())
    clock.advance(timedelta(minutes=31))
    store.get(analysis_id)  # 만료 판정과 함께 내부 dict에서 제거되어야 함

    assert analysis_id not in store._snapshots


def test_expired_snapshot_is_evicted_lazily_on_put() -> None:
    clock = _FakeClock(datetime(2026, 8, 29, 10, 0, tzinfo=UTC))
    store = AnalysisSnapshotStore(ttl=timedelta(minutes=30), clock=clock)

    old_id = store.put(_result("오래된 분석"))
    clock.advance(timedelta(minutes=31))
    store.put(_result("새 분석"))  # put() 시점에 만료된 항목을 함께 정리

    assert old_id not in store._snapshots


def test_get_returns_none_after_lazy_cleanup_from_put() -> None:
    clock = _FakeClock(datetime(2026, 8, 29, 10, 0, tzinfo=UTC))
    store = AnalysisSnapshotStore(ttl=timedelta(minutes=30), clock=clock)

    old_id = store.put(_result())
    clock.advance(timedelta(minutes=31))
    store.put(_result())

    assert store.get(old_id) is None

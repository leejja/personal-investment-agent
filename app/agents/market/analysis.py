from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from app.models.common import AnalysisConfidence
from app.services.ecos import EcosStatisticPoint

TRADING_DAY_LOOKBACK_20 = 20
TRADING_DAY_LOOKBACK_60 = 60
CALENDAR_DAY_LOOKBACK_60 = 60


class DeterministicFact(BaseModel):
    id: str
    description: str
    source: str


class MarketDeterministicAnalysisResult(BaseModel):
    base_rate_latest: float | None = None
    base_rate_change_bp: float | None = None

    usd_krw_latest: float | None = None
    usd_krw_change_20d_pct: float | None = None
    usd_krw_change_60d_pct: float | None = None

    kospi_latest: float | None = None
    kospi_change_20d_pct: float | None = None
    kospi_change_60d_pct: float | None = None

    kosdaq_latest: float | None = None
    kosdaq_change_20d_pct: float | None = None
    kosdaq_change_60d_pct: float | None = None

    facts: list[DeterministicFact]
    max_confidence: AnalysisConfidence


def analyze(
    as_of_date: str,
    base_rate_points: list[EcosStatisticPoint],
    exchange_rate_points: list[EcosStatisticPoint],
    kospi_points: list[EcosStatisticPoint],
    kosdaq_points: list[EcosStatisticPoint],
) -> MarketDeterministicAnalysisResult:
    base_rate_sorted = _sorted_by_time(base_rate_points)
    exchange_rate_sorted = _sorted_by_time(exchange_rate_points)
    kospi_sorted = _sorted_by_time(kospi_points)
    kosdaq_sorted = _sorted_by_time(kosdaq_points)

    base_rate_latest = _latest_value(base_rate_sorted)
    # 기준금리는 주말을 포함해 매일 값이 채워지므로(정책 변경이 없는 날도
    # 직전 값이 반복 기록됨) "60일 전"은 달력일 기준으로 찾는다.
    base_rate_60d_ago = _value_on_or_before(
        base_rate_sorted,
        _date_minus(as_of_date, CALENDAR_DAY_LOOKBACK_60),
    )
    base_rate_change_bp = _bp_change(base_rate_latest, base_rate_60d_ago)

    # 환율/지수는 영업일에만 값이 존재하므로(주말·휴장일 없음) "N일 전"은
    # 달력일이 아니라 최신값 기준 리스트 위치(N거래일 전)로 찾는다.
    usd_krw_latest = _latest_value(exchange_rate_sorted)
    usd_krw_20d_ago = _value_n_trading_days_ago(
        exchange_rate_sorted, TRADING_DAY_LOOKBACK_20
    )
    usd_krw_60d_ago = _value_n_trading_days_ago(
        exchange_rate_sorted, TRADING_DAY_LOOKBACK_60
    )
    usd_krw_change_20d_pct = _pct_change(usd_krw_latest, usd_krw_20d_ago)
    usd_krw_change_60d_pct = _pct_change(usd_krw_latest, usd_krw_60d_ago)

    kospi_latest = _latest_value(kospi_sorted)
    kospi_20d_ago = _value_n_trading_days_ago(kospi_sorted, TRADING_DAY_LOOKBACK_20)
    kospi_60d_ago = _value_n_trading_days_ago(kospi_sorted, TRADING_DAY_LOOKBACK_60)
    kospi_change_20d_pct = _pct_change(kospi_latest, kospi_20d_ago)
    kospi_change_60d_pct = _pct_change(kospi_latest, kospi_60d_ago)

    kosdaq_latest = _latest_value(kosdaq_sorted)
    kosdaq_20d_ago = _value_n_trading_days_ago(kosdaq_sorted, TRADING_DAY_LOOKBACK_20)
    kosdaq_60d_ago = _value_n_trading_days_ago(kosdaq_sorted, TRADING_DAY_LOOKBACK_60)
    kosdaq_change_20d_pct = _pct_change(kosdaq_latest, kosdaq_20d_ago)
    kosdaq_change_60d_pct = _pct_change(kosdaq_latest, kosdaq_60d_ago)

    facts = _build_facts(
        base_rate_latest=base_rate_latest,
        base_rate_60d_ago=base_rate_60d_ago,
        base_rate_change_bp=base_rate_change_bp,
        usd_krw_latest=usd_krw_latest,
        usd_krw_change_20d_pct=usd_krw_change_20d_pct,
        usd_krw_change_60d_pct=usd_krw_change_60d_pct,
        kospi_latest=kospi_latest,
        kospi_change_20d_pct=kospi_change_20d_pct,
        kospi_change_60d_pct=kospi_change_60d_pct,
        kosdaq_latest=kosdaq_latest,
        kosdaq_change_20d_pct=kosdaq_change_20d_pct,
        kosdaq_change_60d_pct=kosdaq_change_60d_pct,
    )

    max_confidence = _max_confidence(
        base_rate_latest=base_rate_latest,
        usd_krw_change_20d_pct=usd_krw_change_20d_pct,
        kospi_change_20d_pct=kospi_change_20d_pct,
    )

    return MarketDeterministicAnalysisResult(
        base_rate_latest=base_rate_latest,
        base_rate_change_bp=base_rate_change_bp,
        usd_krw_latest=usd_krw_latest,
        usd_krw_change_20d_pct=usd_krw_change_20d_pct,
        usd_krw_change_60d_pct=usd_krw_change_60d_pct,
        kospi_latest=kospi_latest,
        kospi_change_20d_pct=kospi_change_20d_pct,
        kospi_change_60d_pct=kospi_change_60d_pct,
        kosdaq_latest=kosdaq_latest,
        kosdaq_change_20d_pct=kosdaq_change_20d_pct,
        kosdaq_change_60d_pct=kosdaq_change_60d_pct,
        facts=facts,
        max_confidence=max_confidence,
    )


def _sorted_by_time(points: list[EcosStatisticPoint]) -> list[EcosStatisticPoint]:
    return sorted(points, key=lambda point: point.time)


def _latest_value(points_sorted_asc: list[EcosStatisticPoint]) -> float | None:
    if not points_sorted_asc:
        return None

    return points_sorted_asc[-1].value


def _value_on_or_before(
    points_sorted_asc: list[EcosStatisticPoint],
    target_date: str,
) -> float | None:
    candidates = [point for point in points_sorted_asc if point.time <= target_date]

    if not candidates:
        return None

    return candidates[-1].value


def _value_n_trading_days_ago(
    points_sorted_asc: list[EcosStatisticPoint],
    n: int,
) -> float | None:
    if len(points_sorted_asc) <= n:
        return None

    return points_sorted_asc[-(n + 1)].value


def _date_minus(date_str: str, days: int) -> str:
    parsed = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=UTC)
    return (parsed - timedelta(days=days)).strftime("%Y%m%d")


def _pct_change(latest: float | None, past: float | None) -> float | None:
    if latest is None or past is None or past == 0:
        return None

    return (latest - past) / past * 100


def _bp_change(latest: float | None, past: float | None) -> float | None:
    if latest is None or past is None:
        return None

    return (latest - past) * 100


def _build_facts(
    *,
    base_rate_latest: float | None,
    base_rate_60d_ago: float | None,
    base_rate_change_bp: float | None,
    usd_krw_latest: float | None,
    usd_krw_change_20d_pct: float | None,
    usd_krw_change_60d_pct: float | None,
    kospi_latest: float | None,
    kospi_change_20d_pct: float | None,
    kospi_change_60d_pct: float | None,
    kosdaq_latest: float | None,
    kosdaq_change_20d_pct: float | None,
    kosdaq_change_60d_pct: float | None,
) -> list[DeterministicFact]:
    # 평가(긴축적/완화적, 위험/안전 등)를 담지 않고 수치 사실만 남긴다.
    # 이 값들을 어떻게 해석할지는 reasoning 단계의 몫이다.
    facts: list[DeterministicFact] = []

    if base_rate_latest is not None:
        facts.append(
            DeterministicFact(
                id="base_rate_level",
                description=f"한국 기준금리는 현재 {base_rate_latest:.2f}%",
                source="ECOS",
            )
        )

    facts.append(
        _rate_change_fact(
            fact_id="base_rate_change",
            label="한국 기준금리",
            window_label="60일",
            latest=base_rate_latest,
            past=base_rate_60d_ago,
            change_bp=base_rate_change_bp,
        )
    )

    level_entries: list[tuple[str, str, float | None, str]] = [
        ("usd_krw_level", "USD/KRW 환율은 현재", usd_krw_latest, "원"),
        ("kospi_level", "KOSPI지수는 현재", kospi_latest, "포인트"),
        ("kosdaq_level", "KOSDAQ지수는 현재", kosdaq_latest, "포인트"),
    ]
    facts.extend(
        DeterministicFact(
            id=fact_id,
            description=f"{label} {value:,.2f}{unit}",
            source="ECOS",
        )
        for fact_id, label, value, unit in level_entries
        if value is not None
    )

    change_entries: list[tuple[str, str, str, float | None, float | None]] = [
        ("usd_krw_change_20d", "USD/KRW 환율은", "20거래일", usd_krw_latest, usd_krw_change_20d_pct),
        ("usd_krw_change_60d", "USD/KRW 환율은", "60거래일", usd_krw_latest, usd_krw_change_60d_pct),
        ("kospi_change_20d", "KOSPI지수는", "20거래일", kospi_latest, kospi_change_20d_pct),
        ("kospi_change_60d", "KOSPI지수는", "60거래일", kospi_latest, kospi_change_60d_pct),
        ("kosdaq_change_20d", "KOSDAQ지수는", "20거래일", kosdaq_latest, kosdaq_change_20d_pct),
        ("kosdaq_change_60d", "KOSDAQ지수는", "60거래일", kosdaq_latest, kosdaq_change_60d_pct),
    ]
    facts.extend(
        fact
        for fact_id, label, window_label, latest, change_pct in change_entries
        if (fact := _pct_change_fact(fact_id, label, window_label, latest, change_pct))
        is not None
    )

    return [fact for fact in facts if fact is not None]


def _rate_change_fact(
    *,
    fact_id: str,
    label: str,
    window_label: str,
    latest: float | None,
    past: float | None,
    change_bp: float | None,
) -> DeterministicFact | None:
    if latest is None or past is None or change_bp is None:
        return None

    if change_bp == 0:
        description = f"{label}는 최근 {window_label}간 변동 없음 ({latest:.2f}% 유지)"
    else:
        direction = "상승" if change_bp > 0 else "하락"
        description = (
            f"{label}는 최근 {window_label}간 {past:.2f}% → {latest:.2f}%로 "
            f"{abs(change_bp):.0f}bp {direction}"
        )

    return DeterministicFact(id=fact_id, description=description, source="ECOS")


def _pct_change_fact(
    fact_id: str,
    label: str,
    window_label: str,
    latest: float | None,
    change_pct: float | None,
) -> DeterministicFact | None:
    if latest is None or change_pct is None:
        return None

    sign = "+" if change_pct >= 0 else ""

    return DeterministicFact(
        id=fact_id,
        description=f"{label} 최근 {window_label} {sign}{change_pct:.1f}% 변동",
        source="ECOS",
    )


def _max_confidence(
    *,
    base_rate_latest: float | None,
    usd_krw_change_20d_pct: float | None,
    kospi_change_20d_pct: float | None,
) -> AnalysisConfidence:
    core_present = (
        base_rate_latest is not None
        and usd_krw_change_20d_pct is not None
        and kospi_change_20d_pct is not None
    )

    if core_present:
        return AnalysisConfidence.MEDIUM

    return AnalysisConfidence.LOW

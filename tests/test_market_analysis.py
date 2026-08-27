from datetime import UTC, datetime, timedelta

import pytest

from app.agents.market.analysis import analyze
from app.models.common import AnalysisConfidence
from app.services.ecos import EcosStatisticPoint

AS_OF = "20260827"


def _dates_ending_at(end_date: str, count: int) -> list[str]:
    end = datetime.strptime(end_date, "%Y%m%d").replace(tzinfo=UTC)
    return [
        (end - timedelta(days=count - 1 - i)).strftime("%Y%m%d") for i in range(count)
    ]


def _points(
    values: list[float],
    *,
    item_code1: str = "TEST",
    end_date: str = AS_OF,
) -> list[EcosStatisticPoint]:
    dates = _dates_ending_at(end_date, len(values))
    return [
        EcosStatisticPoint(
            statistic_code="TEST",
            statistic_name="test",
            item_code1=item_code1,
            item_name1="test",
            unit=None,
            time=date,
            value=value,
        )
        for date, value in zip(dates, values)
    ]


def _flat(value: float, count: int) -> list[float]:
    return [value] * count


def _linear(start: float, step: float, count: int) -> list[float]:
    return [start + step * i for i in range(count)]


def test_analyze_computes_base_rate_change_bp() -> None:
    values = _flat(2.50, 70) + _flat(2.75, 20)  # 90 calendar days total
    result = analyze(
        as_of_date=AS_OF,
        base_rate_points=_points(values),
        exchange_rate_points=[],
        kospi_points=[],
        kosdaq_points=[],
    )

    assert result.base_rate_latest == 2.75
    assert result.base_rate_change_bp is not None
    assert result.base_rate_change_bp == pytest.approx(25.0)

    change_fact = next(f for f in result.facts if f.id == "base_rate_change")
    assert "상승" in change_fact.description
    assert "25bp" in change_fact.description


def test_analyze_reports_no_change_when_base_rate_flat() -> None:
    values = _flat(2.50, 90)
    result = analyze(
        as_of_date=AS_OF,
        base_rate_points=_points(values),
        exchange_rate_points=[],
        kospi_points=[],
        kosdaq_points=[],
    )

    assert result.base_rate_change_bp == 0

    change_fact = next(f for f in result.facts if f.id == "base_rate_change")
    assert "변동 없음" in change_fact.description


def test_analyze_computes_pct_changes_for_fx_and_index() -> None:
    fx_values = _linear(1400.0, -1.0, 70)  # latest is index -1 => smallest value
    kospi_values = _linear(6700.0, 2.0, 70)

    result = analyze(
        as_of_date=AS_OF,
        base_rate_points=[],
        exchange_rate_points=_points(fx_values),
        kospi_points=_points(kospi_values),
        kosdaq_points=[],
    )

    latest_fx = fx_values[-1]
    fx_20d_ago = fx_values[-21]
    fx_60d_ago = fx_values[-61]
    expected_20d_pct = (latest_fx - fx_20d_ago) / fx_20d_ago * 100
    expected_60d_pct = (latest_fx - fx_60d_ago) / fx_60d_ago * 100

    assert result.usd_krw_latest == latest_fx
    assert result.usd_krw_change_20d_pct == pytest.approx(expected_20d_pct)
    assert result.usd_krw_change_60d_pct == pytest.approx(expected_60d_pct)

    latest_kospi = kospi_values[-1]
    kospi_20d_ago = kospi_values[-21]
    expected_kospi_20d_pct = (latest_kospi - kospi_20d_ago) / kospi_20d_ago * 100

    assert result.kospi_latest == latest_kospi
    assert result.kospi_change_20d_pct == pytest.approx(expected_kospi_20d_pct)


def test_analyze_omits_change_fact_when_lookback_insufficient() -> None:
    # 20거래일치(21개 포인트)에 못 미치는 데이터만 제공
    fx_values = _linear(1400.0, -1.0, 15)

    result = analyze(
        as_of_date=AS_OF,
        base_rate_points=[],
        exchange_rate_points=_points(fx_values),
        kospi_points=[],
        kosdaq_points=[],
    )

    assert result.usd_krw_latest == fx_values[-1]
    assert result.usd_krw_change_20d_pct is None
    assert result.usd_krw_change_60d_pct is None
    assert all(f.id != "usd_krw_change_20d" for f in result.facts)
    assert all(f.id != "usd_krw_change_60d" for f in result.facts)


def test_max_confidence_medium_when_core_data_present() -> None:
    result = analyze(
        as_of_date=AS_OF,
        base_rate_points=_points(_flat(2.75, 65)),
        exchange_rate_points=_points(_linear(1400.0, -1.0, 25)),
        kospi_points=_points(_linear(6700.0, 2.0, 25)),
        kosdaq_points=[],
    )

    assert result.max_confidence == AnalysisConfidence.MEDIUM


def test_max_confidence_low_when_core_indicator_missing() -> None:
    result = analyze(
        as_of_date=AS_OF,
        base_rate_points=_points(_flat(2.75, 65)),
        exchange_rate_points=_points(_linear(1400.0, -1.0, 25)),
        kospi_points=[],  # KOSPI 데이터 자체가 없음
        kosdaq_points=[],
    )

    assert result.max_confidence == AnalysisConfidence.LOW


def test_raw_facts_contain_no_evaluative_language() -> None:
    result = analyze(
        as_of_date=AS_OF,
        base_rate_points=_points(_flat(2.50, 70) + _flat(2.75, 20)),
        exchange_rate_points=_points(_linear(1400.0, -1.0, 65)),
        kospi_points=_points(_linear(6700.0, 2.0, 65)),
        kosdaq_points=_points(_linear(800.0, 1.0, 65)),
    )

    evaluative_terms = ["높다", "낮다", "양호", "부진", "고평가", "저평가", "긴축적", "완화적"]

    for fact in result.facts:
        for term in evaluative_terms:
            assert term not in fact.description


def test_fact_ids_are_unique() -> None:
    result = analyze(
        as_of_date=AS_OF,
        base_rate_points=_points(_flat(2.50, 70) + _flat(2.75, 20)),
        exchange_rate_points=_points(_linear(1400.0, -1.0, 65)),
        kospi_points=_points(_linear(6700.0, 2.0, 65)),
        kosdaq_points=_points(_linear(800.0, 1.0, 65)),
    )

    ids = [fact.id for fact in result.facts]
    assert len(ids) == len(set(ids))

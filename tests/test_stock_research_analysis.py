from app.agents.stock_research.analysis import analyze
from app.mcp.opendart_tools import KeyFinancials
from app.models.common import AnalysisConfidence, RiskLevel
from app.services.kiwoom import KiwoomStockInfo


def _stock_info(**overrides: object) -> KiwoomStockInfo:
    defaults: dict[object, object] = {
        "stock_code": "005930",
        "stock_name": "삼성전자",
        "current_price": 281500,
        "change": 10500,
        "change_rate": 3.87,
        "trading_volume": 15000000,
        "per": 42.89,
        "pbr": 4.4,
        "roe": 10.9,
        "eps": 6564,
        "bps": 63976,
        "high_250d": 374500,
        "low_250d": 67500,
    }
    defaults.update(overrides)
    return KiwoomStockInfo(**defaults)


def _key_financials(**overrides: object) -> KeyFinancials:
    defaults: dict[object, object] = {
        "stock_code": "005930",
        "corp_code": "00126380",
        "business_year": "2025",
        "report_code": "11011",
        "fs_div": "CFS",
        "revenue": 333605938000000,
        "operating_profit": 43601051000000,
        "net_income": 45206805000000,
        "total_assets": 566942110000000,
        "total_liabilities": 130621773000000,
        "total_equity": 436320337000000,
    }
    defaults.update(overrides)
    return KeyFinancials(**defaults)


def test_analyze_maps_price_snapshot_without_loss() -> None:
    result = analyze(_stock_info(), _key_financials())

    assert result.price.symbol == "005930"
    assert result.price.name == "삼성전자"
    assert result.price.price == 281500.0
    assert result.price.change_pct == 3.87
    assert result.price.volume == 15000000
    assert result.price.high_250d == 374500.0
    assert result.price.low_250d == 67500.0


def test_analyze_maps_financial_snapshot_without_loss() -> None:
    result = analyze(_stock_info(), _key_financials())

    assert result.financials.revenue == 333605938000000.0
    assert result.financials.operating_profit == 43601051000000.0
    assert result.financials.net_income == 45206805000000.0
    assert result.financials.total_assets == 566942110000000.0
    assert result.financials.total_liabilities == 130621773000000.0
    assert result.financials.total_equity == 436320337000000.0
    assert result.financials.per == 42.89
    assert result.financials.pbr == 4.4
    assert result.financials.roe == 10.9


def test_analyze_produces_price_position_fact() -> None:
    result = analyze(_stock_info(), _key_financials())

    descriptions = [fact.description for fact in result.facts]
    price_fact = next(
        description for description in descriptions if "위치" in description
    )
    assert "250거래일" in price_fact
    assert "52주" not in price_fact


def test_analyze_produces_debt_ratio_fact() -> None:
    result = analyze(_stock_info(), _key_financials())

    descriptions = [fact.description for fact in result.facts]
    assert any("부채비율" in description for description in descriptions)


def test_analyze_skips_price_position_fact_when_high_low_missing() -> None:
    result = analyze(
        _stock_info(high_250d=None, low_250d=None),
        _key_financials(),
    )

    descriptions = [fact.description for fact in result.facts]
    assert not any("위치" in description for description in descriptions)


def test_analyze_skips_debt_ratio_fact_when_equity_missing() -> None:
    result = analyze(
        _stock_info(),
        _key_financials(total_liabilities=None, total_equity=None),
    )

    descriptions = [fact.description for fact in result.facts]
    assert not any("부채비율" in description for description in descriptions)
    # 부채비율 fact만 빠지고, 다른 OpenDART 원본 수치 fact는 남아 있어야 한다.
    assert any(fact.source == "OpenDART" for fact in result.facts)


def test_analyze_skips_debt_ratio_fact_when_equity_is_zero_or_negative() -> None:
    result = analyze(
        _stock_info(),
        _key_financials(total_equity=0),
    )

    descriptions = [fact.description for fact in result.facts]
    assert not any("부채비율" in description for description in descriptions)


def test_max_confidence_is_medium_when_core_data_complete() -> None:
    result = analyze(_stock_info(), _key_financials())

    assert result.max_confidence == AnalysisConfidence.MEDIUM


def test_max_confidence_is_low_when_core_financials_missing() -> None:
    result = analyze(
        _stock_info(),
        _key_financials(
            revenue=None,
            operating_profit=None,
            net_income=None,
        ),
    )

    assert result.max_confidence == AnalysisConfidence.LOW


def test_max_confidence_is_low_when_partial_financials_missing() -> None:
    result = analyze(
        _stock_info(),
        _key_financials(net_income=None),
    )

    assert result.max_confidence == AnalysisConfidence.LOW


def test_max_confidence_never_returns_high() -> None:
    result = analyze(_stock_info(), _key_financials())

    assert result.max_confidence != AnalysisConfidence.HIGH


def test_risk_level_is_always_medium_in_v1() -> None:
    # v1은 부채비율 등 단일 지표만으로 종목 전체 RiskLevel을
    # LOW/HIGH로 판단하지 않고 중립값(MEDIUM)으로 고정한다.
    result = analyze(_stock_info(), _key_financials())

    assert result.risk_level == RiskLevel.MEDIUM


def test_risk_level_is_medium_even_with_very_high_debt_ratio() -> None:
    result = analyze(
        _stock_info(),
        _key_financials(total_liabilities=300, total_equity=100),  # 300%
    )

    assert result.risk_level == RiskLevel.MEDIUM


def test_risk_level_is_medium_when_debt_ratio_unavailable() -> None:
    result = analyze(
        _stock_info(),
        _key_financials(total_liabilities=None, total_equity=None),
    )

    assert result.risk_level == RiskLevel.MEDIUM


def test_risk_level_is_medium_when_core_financials_incomplete() -> None:
    result = analyze(
        _stock_info(),
        _key_financials(
            revenue=None,
            operating_profit=None,
            net_income=None,
        ),
    )

    assert result.max_confidence == AnalysisConfidence.LOW
    assert result.risk_level == RiskLevel.MEDIUM


def test_analyze_produces_raw_value_facts_for_all_available_fields() -> None:
    result = analyze(_stock_info(), _key_financials())

    descriptions = [fact.description for fact in result.facts]

    assert "현재가는 281,500원" in descriptions
    assert "PER는 42.89배" in descriptions
    assert "PBR는 4.40배" in descriptions
    assert "ROE는 10.90%" in descriptions
    assert "매출액는 333,605,938,000,000원" in descriptions
    assert "영업이익는 43,601,051,000,000원" in descriptions
    assert "순이익는 45,206,805,000,000원" in descriptions
    assert "자산총계는 566,942,110,000,000원" in descriptions
    assert "부채총계는 130,621,773,000,000원" in descriptions
    assert "자본총계는 436,320,337,000,000원" in descriptions


def test_raw_value_facts_use_correct_sources() -> None:
    result = analyze(_stock_info(), _key_financials())

    facts_by_description = {fact.description: fact.source for fact in result.facts}

    assert facts_by_description["현재가는 281,500원"] == "Kiwoom"
    assert facts_by_description["PER는 42.89배"] == "Kiwoom"
    assert facts_by_description["PBR는 4.40배"] == "Kiwoom"
    assert facts_by_description["ROE는 10.90%"] == "Kiwoom"
    assert facts_by_description["매출액는 333,605,938,000,000원"] == "OpenDART"
    assert facts_by_description["자본총계는 436,320,337,000,000원"] == "OpenDART"


def test_raw_value_facts_skip_missing_optional_price_fields() -> None:
    result = analyze(
        _stock_info(per=None, pbr=None, roe=None),
        _key_financials(),
    )

    descriptions = [fact.description for fact in result.facts]

    assert not any(description.startswith("PER는") for description in descriptions)
    assert not any(description.startswith("PBR는") for description in descriptions)
    assert not any(description.startswith("ROE는") for description in descriptions)
    # 다른 필드는 여전히 포함되어야 한다.
    assert "현재가는 281,500원" in descriptions


def test_raw_value_facts_skip_missing_financial_fields() -> None:
    result = analyze(
        _stock_info(),
        _key_financials(
            revenue=None,
            operating_profit=None,
            net_income=None,
            total_assets=None,
            total_liabilities=None,
            total_equity=None,
        ),
    )

    descriptions = [fact.description for fact in result.facts]

    assert not any("매출액는" in description for description in descriptions)
    assert not any("영업이익는" in description for description in descriptions)
    assert not any("순이익는" in description for description in descriptions)
    assert not any("자산총계는" in description for description in descriptions)
    assert not any("부채총계는" in description for description in descriptions)
    assert not any("자본총계는" in description for description in descriptions)
    # 가격 관련 raw value fact는 영향을 받지 않는다.
    assert "현재가는 281,500원" in descriptions


def test_analyze_without_financial_history_returns_empty_list() -> None:
    result = analyze(_stock_info(), _key_financials())

    assert result.financial_history == []


def test_analyze_with_single_year_history_returns_empty_list() -> None:
    # history 길이가 1(당기만 있음)이면 추세라 부를 근거가 없으므로 빈
    # 리스트로 둔다.
    result = analyze(_stock_info(), _key_financials(), [_key_financials()])

    assert result.financial_history == []


def test_analyze_builds_financial_history_oldest_first() -> None:
    current = _key_financials(
        business_year="2025", revenue=300, operating_profit=40, net_income=35
    )
    previous = _key_financials(
        business_year="2024", revenue=280, operating_profit=30, net_income=25
    )
    before_previous = _key_financials(
        business_year="2023", revenue=250, operating_profit=20, net_income=15
    )

    result = analyze(
        _stock_info(), current, [current, previous, before_previous]
    )

    assert [snap.business_year for snap in result.financial_history] == [
        "2023",
        "2024",
        "2025",
    ]
    assert result.financial_history[-1].revenue == 300.0
    assert result.financial_history[0].revenue == 250.0


def test_financial_history_snapshots_never_carry_historical_valuation_ratios() -> (
    None
):
    # 과거 연도 스냅샷에는 PER/PBR/ROE를 만들어내지 않는다 — OpenDART는
    # 과거 시점의 시가총액/주가를 제공하지 않으므로 계산 근거가 없다.
    current = _key_financials(business_year="2025")
    previous = _key_financials(business_year="2024")

    result = analyze(_stock_info(), current, [current, previous])

    for snapshot in result.financial_history:
        assert snapshot.per is None
        assert snapshot.pbr is None
        assert snapshot.roe is None


def test_trend_facts_include_normal_yoy_percentage() -> None:
    current = _key_financials(
        business_year="2025", revenue=330, operating_profit=44, net_income=45
    )
    previous = _key_financials(
        business_year="2024", revenue=300, operating_profit=40, net_income=40
    )

    result = analyze(_stock_info(), current, [current, previous])

    descriptions = [fact.description for fact in result.facts]
    assert "매출액는 2024년 대비 2025년 +10.0% 변동" in descriptions


def test_trend_facts_omit_yoy_when_past_value_is_zero() -> None:
    current = _key_financials(business_year="2025", net_income=10)
    previous = _key_financials(business_year="2024", net_income=0)

    result = analyze(_stock_info(), current, [current, previous])

    descriptions = [fact.description for fact in result.facts]
    assert not any(
        "순이익" in d and ("변동" in d or "전환" in d or "규모" in d)
        for d in descriptions
    )


def test_trend_facts_mark_loss_to_profit_transition() -> None:
    current = _key_financials(business_year="2025", net_income=50)
    previous = _key_financials(business_year="2024", net_income=-30)

    result = analyze(_stock_info(), current, [current, previous])

    descriptions = [fact.description for fact in result.facts]
    assert "순이익는 2024년 적자에서 2025년 흑자로 전환" in descriptions


def test_trend_facts_mark_profit_to_loss_transition() -> None:
    current = _key_financials(business_year="2025", net_income=-20)
    previous = _key_financials(business_year="2024", net_income=40)

    result = analyze(_stock_info(), current, [current, previous])

    descriptions = [fact.description for fact in result.facts]
    assert "순이익는 2024년 흑자에서 2025년 적자로 전환" in descriptions


def test_trend_facts_describe_loss_widening_without_percentage_distortion() -> None:
    current = _key_financials(business_year="2025", net_income=-60)
    previous = _key_financials(business_year="2024", net_income=-30)

    result = analyze(_stock_info(), current, [current, previous])

    descriptions = [fact.description for fact in result.facts]
    assert "순이익는 2024년 대비 2025년 적자 규모가 확대" in descriptions
    # 부호가 둘 다 음수인 경우 왜곡된 백분율 변동 표현이 나오면 안 된다.
    assert not any(
        d.startswith("순이익는 2024년 대비 2025년") and "%" in d
        for d in descriptions
    )


def test_trend_facts_describe_loss_narrowing() -> None:
    current = _key_financials(business_year="2025", net_income=-10)
    previous = _key_financials(business_year="2024", net_income=-30)

    result = analyze(_stock_info(), current, [current, previous])

    descriptions = [fact.description for fact in result.facts]
    assert "순이익는 2024년 대비 2025년 적자 규모가 축소" in descriptions


def test_trend_facts_include_margin_and_debt_ratio_per_year() -> None:
    current = _key_financials(
        business_year="2025",
        revenue=300,
        operating_profit=30,
        net_income=15,
        total_liabilities=100,
        total_equity=200,
    )
    previous = _key_financials(
        business_year="2024",
        revenue=250,
        operating_profit=20,
        net_income=10,
        total_liabilities=90,
        total_equity=180,
    )

    result = analyze(_stock_info(), current, [current, previous])

    descriptions = [fact.description for fact in result.facts]
    assert "2025년 영업이익률은 약 10.0%" in descriptions
    assert "2025년 순이익률은 약 5.0%" in descriptions
    assert "2025년 부채비율은 약 50.0%" in descriptions
    assert "2024년 영업이익률은 약 8.0%" in descriptions


def test_trend_facts_mark_three_year_consecutive_increase() -> None:
    current = _key_financials(business_year="2025", revenue=330)
    previous = _key_financials(business_year="2024", revenue=300)
    before_previous = _key_financials(business_year="2023", revenue=270)

    result = analyze(
        _stock_info(), current, [current, previous, before_previous]
    )

    descriptions = [fact.description for fact in result.facts]
    assert "매출액는 최근 3개 연도 연속 상승" in descriptions


def test_trend_facts_skip_direction_fact_when_only_two_years() -> None:
    current = _key_financials(business_year="2025", revenue=330)
    previous = _key_financials(business_year="2024", revenue=300)

    result = analyze(_stock_info(), current, [current, previous])

    descriptions = [fact.description for fact in result.facts]
    assert not any("연속" in d for d in descriptions)


def test_trend_facts_skip_direction_fact_when_not_monotonic() -> None:
    current = _key_financials(business_year="2025", revenue=300)
    previous = _key_financials(business_year="2024", revenue=330)
    before_previous = _key_financials(business_year="2023", revenue=270)

    result = analyze(
        _stock_info(), current, [current, previous, before_previous]
    )

    descriptions = [fact.description for fact in result.facts]
    assert not any("매출액는 최근" in d and "연속" in d for d in descriptions)


def test_raw_value_facts_contain_no_evaluative_language() -> None:
    result = analyze(_stock_info(), _key_financials())

    evaluative_words = [
        "높다",
        "낮다",
        "높은",
        "낮은",
        "양호",
        "부진",
        "고평가",
        "저평가",
        "우수",
        "위험",
    ]

    for fact in result.facts:
        for word in evaluative_words:
            assert word not in fact.description, (
                f"평가성 표현 '{word}'이(가) fact에 포함됨: {fact.description}"
            )

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

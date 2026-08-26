from pydantic import BaseModel

from app.mcp.opendart_tools import KeyFinancials
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.stock import FinancialSnapshot, StockPriceSnapshot
from app.services.kiwoom import KiwoomStockInfo


class DeterministicFact(BaseModel):
    description: str
    source: str


class DeterministicAnalysisResult(BaseModel):
    price: StockPriceSnapshot
    financials: FinancialSnapshot
    facts: list[DeterministicFact]
    max_confidence: AnalysisConfidence
    risk_level: RiskLevel


def analyze(
    stock_info: KiwoomStockInfo,
    key_financials: KeyFinancials,
) -> DeterministicAnalysisResult:
    price = _map_price_snapshot(stock_info)
    financials = _map_financial_snapshot(stock_info, key_financials)
    debt_ratio = _debt_ratio(key_financials)
    max_confidence = _max_confidence(price, financials)

    facts = [
        fact
        for fact in (
            _price_position_fact(stock_info),
            _debt_ratio_fact(debt_ratio),
        )
        if fact is not None
    ] + _raw_value_facts(stock_info, key_financials)

    return DeterministicAnalysisResult(
        price=price,
        financials=financials,
        facts=facts,
        max_confidence=max_confidence,
        risk_level=_risk_level(),
    )


def _map_price_snapshot(stock_info: KiwoomStockInfo) -> StockPriceSnapshot:
    return StockPriceSnapshot(
        symbol=stock_info.stock_code,
        name=stock_info.stock_name,
        price=float(stock_info.current_price),
        change_pct=stock_info.change_rate,
        volume=stock_info.trading_volume,
        high_250d=_to_float(stock_info.high_250d),
        low_250d=_to_float(stock_info.low_250d),
    )


def _map_financial_snapshot(
    stock_info: KiwoomStockInfo,
    key_financials: KeyFinancials,
) -> FinancialSnapshot:
    return FinancialSnapshot(
        revenue=_to_float(key_financials.revenue),
        operating_profit=_to_float(key_financials.operating_profit),
        net_income=_to_float(key_financials.net_income),
        total_assets=_to_float(key_financials.total_assets),
        total_liabilities=_to_float(key_financials.total_liabilities),
        total_equity=_to_float(key_financials.total_equity),
        per=stock_info.per,
        pbr=stock_info.pbr,
        roe=stock_info.roe,
    )


def _price_position_fact(
    stock_info: KiwoomStockInfo,
) -> DeterministicFact | None:
    high = stock_info.high_250d
    low = stock_info.low_250d

    if high is None or low is None or high <= low:
        return None

    position_pct = (stock_info.current_price - low) / (high - low) * 100

    return DeterministicFact(
        description=(
            f"현재가는 250거래일 최저 {low:,}원 ~ 최고 {high:,}원 구간에서 "
            f"약 {position_pct:.1f}% 위치"
        ),
        source="Kiwoom",
    )


def _debt_ratio(key_financials: KeyFinancials) -> float | None:
    liabilities = key_financials.total_liabilities
    equity = key_financials.total_equity

    if liabilities is None or equity is None or equity <= 0:
        return None

    return liabilities / equity * 100


def _debt_ratio_fact(debt_ratio: float | None) -> DeterministicFact | None:
    if debt_ratio is None:
        return None

    return DeterministicFact(
        description=f"부채비율(부채총계/자본총계)은 약 {debt_ratio:.1f}%",
        source="OpenDART",
    )


def _raw_value_facts(
    stock_info: KiwoomStockInfo,
    key_financials: KeyFinancials,
) -> list[DeterministicFact]:
    # 평가(고평가/저평가, 양호/부진 등)를 담지 않고 원본 수치 자체만
    # fact로 남긴다. 이 값들을 어떻게 해석할지는 reasoning 단계의 몫이다.
    entries: list[tuple[str, str, float | int | None, str]] = [
        ("현재가", "Kiwoom", stock_info.current_price, "원"),
        ("PER", "Kiwoom", stock_info.per, "배"),
        ("PBR", "Kiwoom", stock_info.pbr, "배"),
        ("ROE", "Kiwoom", stock_info.roe, "%"),
        ("매출액", "OpenDART", key_financials.revenue, "원"),
        ("영업이익", "OpenDART", key_financials.operating_profit, "원"),
        ("순이익", "OpenDART", key_financials.net_income, "원"),
        ("자산총계", "OpenDART", key_financials.total_assets, "원"),
        ("부채총계", "OpenDART", key_financials.total_liabilities, "원"),
        ("자본총계", "OpenDART", key_financials.total_equity, "원"),
    ]

    return [
        DeterministicFact(
            description=f"{label}는 {_format_raw_value(value)}{unit}",
            source=source,
        )
        for label, source, value, unit in entries
        if value is not None
    ]


def _format_raw_value(value: float) -> str:
    if isinstance(value, int):
        return f"{value:,}"

    return f"{value:,.2f}"


def _max_confidence(
    price: StockPriceSnapshot,
    financials: FinancialSnapshot,
) -> AnalysisConfidence:
    core_financials_present = (
        financials.revenue is not None
        and financials.operating_profit is not None
        and financials.net_income is not None
    )

    if price.price > 0 and core_financials_present:
        return AnalysisConfidence.MEDIUM

    return AnalysisConfidence.LOW


def _risk_level() -> RiskLevel:
    # v1은 가격 + 단일연도 재무 데이터만으로 종목 전체의 투자 RiskLevel을
    # LOW/HIGH로 판단하지 않는다. 부채비율 같은 단일 지표만으로는 근거가
    # 부족하고 업종별 자본구조 차이도 반영하지 못하기 때문이다.
    # 충분한 risk 데이터와 업종 상대기준이 확보되기 전까지는 중립값으로
    # 고정한다. 부채비율 자체는 DeterministicFact로는 계속 남아
    # reasoning 단계의 risks 서술 근거로 쓰인다.
    return RiskLevel.MEDIUM


def _to_float(value: int | None) -> float | None:
    return float(value) if value is not None else None

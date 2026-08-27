from pydantic import BaseModel, Field

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
    # 오래된 연도 → 최신 연도 순. 입력으로 받은 financial_history가 2개
    # 미만이면(추세라 부를 근거가 없으면) 빈 리스트로 둔다.
    financial_history: list[FinancialSnapshot] = Field(default_factory=list)
    facts: list[DeterministicFact]
    max_confidence: AnalysisConfidence
    risk_level: RiskLevel


def analyze(
    stock_info: KiwoomStockInfo,
    key_financials: KeyFinancials,
    financial_history: list[KeyFinancials] | None = None,
) -> DeterministicAnalysisResult:
    price = _map_price_snapshot(stock_info)
    financials = _map_financial_snapshot(stock_info, key_financials)
    debt_ratio = _debt_ratio(key_financials)
    max_confidence = _max_confidence(price, financials)

    # financial_history는 최신 연도 → 과거 연도 순으로 들어온다고 가정한다
    # (OpenDartTools.get_key_financials_history()와 동일한 순서, history[0]는
    # key_financials와 동일). 2개 미만이면 YoY/추세를 계산할 근거가 없다.
    history = financial_history or []
    has_trend = len(history) >= 2

    financial_snapshots = (
        [_map_history_snapshot(kf) for kf in reversed(history)] if has_trend else []
    )

    facts = [
        fact
        for fact in (
            _price_position_fact(stock_info),
            _debt_ratio_fact(debt_ratio),
        )
        if fact is not None
    ] + _raw_value_facts(stock_info, key_financials)

    if has_trend:
        facts += _trend_facts(history)

    return DeterministicAnalysisResult(
        price=price,
        financials=financials,
        financial_history=financial_snapshots,
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
        business_year=key_financials.business_year,
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


def _map_history_snapshot(key_financials: KeyFinancials) -> FinancialSnapshot:
    # 과거 연도 스냅샷에는 PER/PBR/ROE를 채우지 않는다 — Kiwoom은 "현재
    # 시점" valuation만 제공하고, OpenDART는 과거 시점의 시가총액/주가를
    # 함께 주지 않으므로 과거 PER/PBR/ROE는 계산할 근거가 없다(8번 정책).
    return FinancialSnapshot(
        business_year=key_financials.business_year,
        revenue=_to_float(key_financials.revenue),
        operating_profit=_to_float(key_financials.operating_profit),
        net_income=_to_float(key_financials.net_income),
        total_assets=_to_float(key_financials.total_assets),
        total_liabilities=_to_float(key_financials.total_liabilities),
        total_equity=_to_float(key_financials.total_equity),
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


def _operating_margin(key_financials: KeyFinancials) -> float | None:
    revenue = key_financials.revenue
    operating_profit = key_financials.operating_profit

    if revenue is None or operating_profit is None or revenue == 0:
        return None

    return operating_profit / revenue * 100


def _net_margin(key_financials: KeyFinancials) -> float | None:
    revenue = key_financials.revenue
    net_income = key_financials.net_income

    if revenue is None or net_income is None or revenue == 0:
        return None

    return net_income / revenue * 100


def _yoy_change_fact(
    label: str,
    latest_year: str,
    latest: float | None,
    past_year: str,
    past: float | None,
) -> DeterministicFact | None:
    # 손익 항목은 부호가 바뀌거나(흑자↔적자) 기준값이 0/음수일 수 있어
    # 단순 백분율 계산이 왜곡되거나 정의되지 않는다. 케이스별로 안전하게
    # 표현한다.
    if latest is None or past is None:
        return None

    if past == 0:
        # 0 대비 변동률은 정의할 수 없으므로 조용히 생략한다.
        return None

    if (latest >= 0) != (past >= 0):
        if past < 0 <= latest:
            description = (
                f"{label}는 {past_year}년 적자에서 {latest_year}년 흑자로 전환"
            )
        else:
            description = (
                f"{label}는 {past_year}년 흑자에서 {latest_year}년 적자로 전환"
            )
        return DeterministicFact(description=description, source="OpenDART")

    if latest < 0 and past < 0:
        if abs(latest) > abs(past):
            direction = "확대"
        elif abs(latest) < abs(past):
            direction = "축소"
        else:
            direction = "유지"
        description = (
            f"{label}는 {past_year}년 대비 {latest_year}년 적자 규모가 {direction}"
        )
        return DeterministicFact(description=description, source="OpenDART")

    change_pct = (latest - past) / past * 100
    sign = "+" if change_pct >= 0 else ""
    description = (
        f"{label}는 {past_year}년 대비 {latest_year}년 {sign}{change_pct:.1f}% 변동"
    )
    return DeterministicFact(description=description, source="OpenDART")


def _consecutive_direction_fact(
    label: str,
    values_newest_first: list[float | None],
) -> DeterministicFact | None:
    # 결측 없이 3개 연도가 모두 있을 때만 "연속 상승/하락"을 말한다 —
    # 일부 연도가 비어 있으면 방향성을 단정할 근거가 부족하다.
    if len(values_newest_first) < 3 or any(
        value is None for value in values_newest_first
    ):
        return None

    values = [value for value in values_newest_first if value is not None]
    chronological = list(reversed(values))

    if all(
        chronological[i] < chronological[i + 1]
        for i in range(len(chronological) - 1)
    ):
        direction = "상승"
    elif all(
        chronological[i] > chronological[i + 1]
        for i in range(len(chronological) - 1)
    ):
        direction = "하락"
    else:
        return None

    return DeterministicFact(
        description=f"{label}는 최근 {len(chronological)}개 연도 연속 {direction}",
        source="OpenDART",
    )


def _trend_facts(history: list[KeyFinancials]) -> list[DeterministicFact]:
    # history는 최신 → 과거 순(history[0]이 당기).
    facts: list[DeterministicFact] = []

    metric_getters = [
        ("매출액", lambda kf: _to_float(kf.revenue)),
        ("영업이익", lambda kf: _to_float(kf.operating_profit)),
        ("순이익", lambda kf: _to_float(kf.net_income)),
    ]

    for label, getter in metric_getters:
        for i in range(len(history) - 1):
            latest_kf, past_kf = history[i], history[i + 1]
            fact = _yoy_change_fact(
                label,
                latest_kf.business_year,
                getter(latest_kf),
                past_kf.business_year,
                getter(past_kf),
            )
            if fact is not None:
                facts.append(fact)

    for key_financials in history:
        year = key_financials.business_year

        operating_margin = _operating_margin(key_financials)
        if operating_margin is not None:
            facts.append(
                DeterministicFact(
                    description=f"{year}년 영업이익률은 약 {operating_margin:.1f}%",
                    source="OpenDART",
                )
            )

        net_margin = _net_margin(key_financials)
        if net_margin is not None:
            facts.append(
                DeterministicFact(
                    description=f"{year}년 순이익률은 약 {net_margin:.1f}%",
                    source="OpenDART",
                )
            )

        year_debt_ratio = _debt_ratio(key_financials)
        if year_debt_ratio is not None:
            facts.append(
                DeterministicFact(
                    description=f"{year}년 부채비율은 약 {year_debt_ratio:.1f}%",
                    source="OpenDART",
                )
            )

    direction_series: list[tuple[str, list[float | None]]] = [
        ("영업이익률", [_operating_margin(kf) for kf in history]),
        ("순이익률", [_net_margin(kf) for kf in history]),
        ("매출액", [_to_float(kf.revenue) for kf in history]),
        ("영업이익", [_to_float(kf.operating_profit) for kf in history]),
        ("순이익", [_to_float(kf.net_income) for kf in history]),
    ]
    for label, series in direction_series:
        fact = _consecutive_direction_fact(label, series)
        if fact is not None:
            facts.append(fact)

    return facts


def _to_float(value: int | None) -> float | None:
    return float(value) if value is not None else None

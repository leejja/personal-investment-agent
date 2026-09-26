from collections.abc import Callable

from pydantic import BaseModel, Field

from app.mcp.opendart_tools import KeyFinancials
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.evidence import (
    MEASURE_DEBT_RATIO,
    MEASURE_NET_INCOME,
    MEASURE_NET_MARGIN,
    MEASURE_OPERATING_MARGIN,
    MEASURE_OPERATING_PROFIT,
    MEASURE_PBR,
    MEASURE_PER,
    MEASURE_REVENUE,
    MEASURE_ROE,
    MEASURE_TOTAL_EQUITY,
    MEASURE_TOTAL_LIABILITIES,
    DerivationLineage,
    EvidenceItemIdentity,
    EvidenceOrigin,
    EvidenceReference,
    FinancialFactsEvidence,
)
from app.models.stock import (
    AnnualFinancialFeatures,
    FinancialFeatures,
    FinancialMetric,
    FinancialSnapshot,
    FinancialTransition,
    FinancialTrendDirection,
    FinancialTrendEntry,
    FinancialYoYChange,
    StockPriceSnapshot,
)
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
    # RE-01: financial_history와 별개의 gate를 쓴다 — 최소 1개 연도(당기)만
    # 있어도 annual은 채워진다(margin/debt_ratio는 단일 연도로 계산
    # 가능한 기존 공식이라 financial_history의 "2개 연도 이상" 요건과
    # 묶일 이유가 없다). yoy/trends는 각각 기존 semantics 그대로 2개/
    # 3개 연도 이상을 요구한다. analyze()는 항상 실제 값을 채워 반환한다
    # — 기본값은 이 internal result를 직접 생성하는 기존 테스트 fixture가
    # (reasoning.py 테스트 등) 이 필드를 몰라도 깨지지 않게 하기 위함이다.
    financial_features: FinancialFeatures = Field(default_factory=FinancialFeatures)
    # Evidence Identity Preservation(first slice): 6개 evaluator 경로의 evidence
    # reference. v1 StockAnalysis / reasoning 경로는 이 값을 쓰지 않으므로 optional이다
    # — evaluation pipeline(build_normalized_research_data)은 None이면 fail-fast한다.
    evidence: FinancialFactsEvidence | None = None


class AnalysisEvidenceInput(BaseModel):
    """analyze()에 전달하는 source evidence(measure key → reference).

    `stock_info`: Kiwoom ROE / PER / PBR reference.
    `latest_financials`: 최신 연도(`financial_history[0]`, 없으면 `key_financials`) —
    annual[-1] margin / debt_ratio가 계산되는 바로 그 KeyFinancials의 measure reference.
    """

    stock_info: dict[str, EvidenceReference]
    latest_financials: dict[str, EvidenceReference]


def analyze(
    stock_info: KiwoomStockInfo,
    key_financials: KeyFinancials,
    financial_history: list[KeyFinancials] | None = None,
    *,
    evidence: AnalysisEvidenceInput | None = None,
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

    # annual은 financial_history와 독립적인 gate를 쓴다: financial_history
    # 인자가 아예 주어지지 않은 호출(예: 일부 단위 테스트)도 최소
    # key_financials(당기) 하나만으로 annual 1건은 만들 수 있다 — 이미
    # 존재하는 단일연도 deterministic formula(margin/debt_ratio)를
    # 구조화하는 것뿐이라 새로운 판단이 아니다.
    annual_source = history if history else [key_financials]
    annual_features_newest_first = _build_annual_features(annual_source)

    yoy_features: list[FinancialYoYChange] = []
    trend_features: list[FinancialTrendEntry] = []

    if has_trend:
        trend_facts, yoy_features, trend_features = _trend_facts(
            history, annual_features_newest_first
        )
        facts += trend_facts

    financial_features = FinancialFeatures(
        annual=list(reversed(annual_features_newest_first)),
        yoy=yoy_features,
        trends=trend_features,
    )

    return DeterministicAnalysisResult(
        price=price,
        financials=financials,
        financial_history=financial_snapshots,
        facts=facts,
        max_confidence=max_confidence,
        risk_level=_risk_level(),
        financial_features=financial_features,
        evidence=(
            _build_evaluator_evidence(
                financials, annual_features_newest_first[0], annual_source[0], evidence
            )
            if evidence is not None
            else None
        ),
    )


# ============================== Evidence Identity Preservation ==============================
#
# 아래 formula 식별자는 이 모듈의 _operating_margin / _net_margin / _debt_ratio가 현재
# 실행하는 deterministic formula를 가리킨다. lineage를 derivation이 현재 일어나는 위치에서
# 기록할 뿐이며, 이 모듈이 canonical Derived Feature Value Ownership을 가진다는 뜻이
# 아니다(ownership OPEN). numeric calibration semantics는 없다.
_DERIVED_FORMULAS: dict[str, tuple[str, tuple[str, ...]]] = {
    # measure: (formula_id, required input measures — formula의 입력 순서)
    MEASURE_OPERATING_MARGIN: ("operating_margin", (MEASURE_REVENUE, MEASURE_OPERATING_PROFIT)),
    MEASURE_NET_MARGIN: ("net_margin", (MEASURE_REVENUE, MEASURE_NET_INCOME)),
    MEASURE_DEBT_RATIO: ("debt_ratio", (MEASURE_TOTAL_LIABILITIES, MEASURE_TOTAL_EQUITY)),
}
_FORMULA_VERSION = "1"


def _build_evaluator_evidence(
    financials: FinancialSnapshot,
    latest_annual: AnnualFinancialFeatures,
    latest_financials: KeyFinancials,
    evidence: AnalysisEvidenceInput,
) -> FinancialFactsEvidence:
    # 값이 있는데 reference가 없으면 pipeline 안에서 identity가 소실된 것이다 — fail-fast.
    return FinancialFactsEvidence(
        roe=_required_source_reference(financials.roe, MEASURE_ROE, evidence.stock_info),
        per=_required_source_reference(financials.per, MEASURE_PER, evidence.stock_info),
        pbr=_required_source_reference(financials.pbr, MEASURE_PBR, evidence.stock_info),
        operating_margin=_derived_reference(
            latest_annual.operating_margin,
            MEASURE_OPERATING_MARGIN,
            latest_financials.stock_code,
            evidence.latest_financials,
        ),
        net_margin=_derived_reference(
            latest_annual.net_margin,
            MEASURE_NET_MARGIN,
            latest_financials.stock_code,
            evidence.latest_financials,
        ),
        debt_ratio=_derived_reference(
            latest_annual.debt_ratio,
            MEASURE_DEBT_RATIO,
            latest_financials.stock_code,
            evidence.latest_financials,
        ),
    )


def _required_source_reference(
    value: float | None,
    measure: str,
    references: dict[str, EvidenceReference],
) -> EvidenceReference | None:
    if value is None:
        return None
    reference = references.get(measure)
    if reference is None:
        raise ValueError(f"evidence reference for '{measure}' was lost: value present, reference missing")
    return reference


def _derived_reference(
    value: float | None,
    measure: str,
    entity: str,
    references: dict[str, EvidenceReference],
) -> EvidenceReference | None:
    if value is None:
        return None
    formula_id, input_measures = _DERIVED_FORMULAS[measure]
    inputs: list[EvidenceReference] = []
    for input_measure in input_measures:
        reference = references.get(input_measure)
        if reference is None:
            raise ValueError(
                f"input evidence '{input_measure}' for derived '{measure}' was lost: "
                "derived value present, input reference missing"
            )
        inputs.append(reference)

    return EvidenceReference(
        identity=EvidenceItemIdentity(
            entity=entity,
            measure=measure,
            origin=EvidenceOrigin.DERIVED,
            derivation=DerivationLineage(
                formula_id=formula_id,
                formula_version=_FORMULA_VERSION,
                inputs=tuple(reference.identity for reference in inputs),
            ),
        ),
        input_references=tuple(inputs),
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


# ============================== RE-01: single source of truth ==============================
#
# 아래 _classify_yoy/_classify_direction은 순수 계산만 하고(텍스트 생성
# 없음), _format_yoy_description/_format_direction_description은 그
# 계산 결과로부터 기존과 동일한 문자열만 만든다(포맷 자체는 한 글자도
# 바꾸지 않았다). _trend_facts()가 이 계산 결과를 Evidence
# 텍스트(DeterministicFact)와 구조화 값(FinancialYoYChange/
# FinancialTrendEntry) 양쪽에 그대로 사용해, 같은 계산이 두 번 실행되지
# 않는다.


def _classify_yoy(
    latest: float | None,
    past: float | None,
) -> tuple[float | None, FinancialTransition | None] | None:
    """단일 지표의 YoY 변화를 분류한다. None을 반환하면 fact/entry를 만들지
    않는다(latest/past 결측 또는 past==0 — 0 대비 변동률은 정의할 수
    없어 조용히 생략한다는 기존 semantics를 그대로 따른다). 그 외에는
    (growth_pct, transition) 튜플을 반환하며 둘 중 정확히 하나만
    non-None이다. 분기 조건은 기존 _yoy_change_fact와 동일하다."""
    if latest is None or past is None:
        return None

    if past == 0:
        return None

    if (latest >= 0) != (past >= 0):
        if past < 0 <= latest:
            return None, FinancialTransition.LOSS_TO_PROFIT
        return None, FinancialTransition.PROFIT_TO_LOSS

    if latest < 0 and past < 0:
        if abs(latest) > abs(past):
            return None, FinancialTransition.LOSS_WIDENING
        if abs(latest) < abs(past):
            return None, FinancialTransition.LOSS_NARROWING
        return None, FinancialTransition.LOSS_UNCHANGED

    change_pct = (latest - past) / past * 100
    return change_pct, None


def _format_yoy_description(
    label: str,
    latest_year: str,
    past_year: str,
    growth_pct: float | None,
    transition: FinancialTransition | None,
) -> str:
    if transition == FinancialTransition.LOSS_TO_PROFIT:
        return f"{label}는 {past_year}년 적자에서 {latest_year}년 흑자로 전환"
    if transition == FinancialTransition.PROFIT_TO_LOSS:
        return f"{label}는 {past_year}년 흑자에서 {latest_year}년 적자로 전환"
    if transition == FinancialTransition.LOSS_WIDENING:
        return f"{label}는 {past_year}년 대비 {latest_year}년 적자 규모가 확대"
    if transition == FinancialTransition.LOSS_NARROWING:
        return f"{label}는 {past_year}년 대비 {latest_year}년 적자 규모가 축소"
    if transition == FinancialTransition.LOSS_UNCHANGED:
        return f"{label}는 {past_year}년 대비 {latest_year}년 적자 규모가 유지"

    assert growth_pct is not None
    sign = "+" if growth_pct >= 0 else ""
    return f"{label}는 {past_year}년 대비 {latest_year}년 {sign}{growth_pct:.1f}% 변동"


def _classify_direction(
    values_newest_first: list[float | None],
) -> FinancialTrendDirection | None:
    # 결측 없이 3개 연도가 모두 있을 때만 방향을 판단한다 — 일부 연도가
    # 비어 있으면 방향성을 단정할 근거가 부족하다(기존 semantics 그대로).
    if len(values_newest_first) < 3 or any(
        value is None for value in values_newest_first
    ):
        return None

    chronological = list(reversed(values_newest_first))

    if all(
        chronological[i] < chronological[i + 1]
        for i in range(len(chronological) - 1)
    ):
        return FinancialTrendDirection.INCREASING

    if all(
        chronological[i] > chronological[i + 1]
        for i in range(len(chronological) - 1)
    ):
        return FinancialTrendDirection.DECREASING

    # 비단조(예: 100→80→110)면 방향을 만들지 않는다 — "MIXED" 같은 새
    # 판단을 추가하지 않는다.
    return None


def _format_direction_description(
    label: str,
    count: int,
    direction: FinancialTrendDirection,
) -> str:
    word = "상승" if direction == FinancialTrendDirection.INCREASING else "하락"
    return f"{label}는 최근 {count}개 연도 연속 {word}"


def _build_annual_features(
    key_financials_newest_first: list[KeyFinancials],
) -> list[AnnualFinancialFeatures]:
    # 입력 순서를 그대로 보존한다(호출부에서 필요한 순서로 뒤집는다).
    # margin/debt_ratio 계산은 기존 함수를 그대로 재사용한다 — 새 공식
    # 없음. 값이 전부 None이어도 해당 연도의 entry 자체는 만든다
    # (missing != 항목 생략, "이 연도는 시도했으나 데이터가 없다"를
    # 명시적으로 표현한다).
    return [
        AnnualFinancialFeatures(
            business_year=kf.business_year,
            operating_margin=_operating_margin(kf),
            net_margin=_net_margin(kf),
            debt_ratio=_debt_ratio(kf),
        )
        for kf in key_financials_newest_first
    ]


def _trend_facts(
    history: list[KeyFinancials],
    annual_features_newest_first: list[AnnualFinancialFeatures],
) -> tuple[list[DeterministicFact], list[FinancialYoYChange], list[FinancialTrendEntry]]:
    # history/annual_features_newest_first는 둘 다 최신 → 과거 순이며
    # 길이/순서가 서로 정확히 대응한다(호출부에서 동일한 history로부터
    # 만들었기 때문). 연도별 margin/debt_ratio는 여기서 다시 계산하지
    # 않고 annual_features_newest_first에 이미 계산된 값을 그대로 쓴다.
    facts: list[DeterministicFact] = []
    yoy_features: list[FinancialYoYChange] = []

    metric_getters: list[
        tuple[str, FinancialMetric, Callable[[KeyFinancials], float | None]]
    ] = [
        ("매출액", FinancialMetric.REVENUE, lambda kf: _to_float(kf.revenue)),
        (
            "영업이익",
            FinancialMetric.OPERATING_PROFIT,
            lambda kf: _to_float(kf.operating_profit),
        ),
        ("순이익", FinancialMetric.NET_INCOME, lambda kf: _to_float(kf.net_income)),
    ]

    for label, metric, getter in metric_getters:
        for i in range(len(history) - 1):
            latest_kf, past_kf = history[i], history[i + 1]
            classified = _classify_yoy(getter(latest_kf), getter(past_kf))
            if classified is None:
                continue

            growth_pct, transition = classified
            facts.append(
                DeterministicFact(
                    description=_format_yoy_description(
                        label,
                        latest_kf.business_year,
                        past_kf.business_year,
                        growth_pct,
                        transition,
                    ),
                    source="OpenDART",
                )
            )
            yoy_features.append(
                FinancialYoYChange(
                    metric=metric,
                    latest_year=latest_kf.business_year,
                    previous_year=past_kf.business_year,
                    growth_pct=growth_pct,
                    transition=transition,
                )
            )

    for annual in annual_features_newest_first:
        year = annual.business_year

        if annual.operating_margin is not None:
            facts.append(
                DeterministicFact(
                    description=f"{year}년 영업이익률은 약 {annual.operating_margin:.1f}%",
                    source="OpenDART",
                )
            )

        if annual.net_margin is not None:
            facts.append(
                DeterministicFact(
                    description=f"{year}년 순이익률은 약 {annual.net_margin:.1f}%",
                    source="OpenDART",
                )
            )

        if annual.debt_ratio is not None:
            facts.append(
                DeterministicFact(
                    description=f"{year}년 부채비율은 약 {annual.debt_ratio:.1f}%",
                    source="OpenDART",
                )
            )

    direction_series: list[tuple[str, FinancialMetric, list[float | None]]] = [
        (
            "영업이익률",
            FinancialMetric.OPERATING_MARGIN,
            [annual.operating_margin for annual in annual_features_newest_first],
        ),
        (
            "순이익률",
            FinancialMetric.NET_MARGIN,
            [annual.net_margin for annual in annual_features_newest_first],
        ),
        ("매출액", FinancialMetric.REVENUE, [_to_float(kf.revenue) for kf in history]),
        (
            "영업이익",
            FinancialMetric.OPERATING_PROFIT,
            [_to_float(kf.operating_profit) for kf in history],
        ),
        (
            "순이익",
            FinancialMetric.NET_INCOME,
            [_to_float(kf.net_income) for kf in history],
        ),
    ]
    trend_features: list[FinancialTrendEntry] = []
    for label, metric, series in direction_series:
        direction = _classify_direction(series)
        if direction is None:
            continue

        facts.append(
            DeterministicFact(
                description=_format_direction_description(label, len(series), direction),
                source="OpenDART",
            )
        )
        trend_features.append(FinancialTrendEntry(metric=metric, direction=direction))

    return facts, yoy_features, trend_features


def _to_float(value: int | None) -> float | None:
    return float(value) if value is not None else None

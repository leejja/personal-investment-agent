import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.models.common import AnalysisConfidence
from app.models.stock import StockScenario
from app.services.llm import LLMService

DEFAULT_MAX_ATTEMPTS = 2

_SYSTEM_PROMPT = (
    "당신은 한국 주식 시장을 다루는 애널리스트입니다.\n"
    "아래 사용자 메시지에 주어진 가격/재무 데이터와 사실(facts)만을 근거로 "
    "분석하세요.\n"
    "주어지지 않은 뉴스, 공시, 산업 동향, 시장 상황 등 외부 정보를 "
    "추측하거나 지어내지 마세요.\n"
    "\n"
    "PER, PBR, ROE 등 비율 지표에는 업종 평균, 과거 평균, 동종 기업 비교 "
    "같은 비교 기준(benchmark)이 함께 제공되지 않았습니다. 비교 기준이 "
    "없는 값에 대해 '높다/낮다/양호하다/부진하다/고평가/저평가' 같은 "
    "평가를 하지 마세요. 그런 지표는 수치 사실만 언급하세요.\n"
    "\n"
    "catalysts는 향후 주가·실적·기업가치에 영향을 줄 수 있는 구체적인 "
    "변화나 이벤트만을 의미합니다. 다음은 그 자체로는 catalyst가 "
    "아닙니다:\n"
    "- 단순 매출 규모\n"
    "- 단순 순이익 규모\n"
    "- 자산/자본 규모\n"
    "- PER/PBR/ROE 수치\n"
    "- 부채비율\n"
    "- 현재 가격 위치\n"
    "- 과거 재무 추세 개선/악화 자체(예: 매출 증가 추세)\n"
    "주어진 facts 안에 이런 미래 지향적 이벤트나 변화의 근거가 없다면 "
    "catalysts는 반드시 빈 리스트 []를 반환하세요. 근거 없이 catalyst를 "
    "만들지 마세요.\n"
    "\n"
    "risks의 각 항목도 반드시 주어진 facts 중 하나 이상에 직접 근거해야 "
    "합니다. 근거가 없는 risk는 만들지 말고, 근거가 없으면 빈 리스트를 "
    "반환하세요.\n"
    "\n"
    "업종 평균이나 과거 평균 같은 비교 기준 없이 단일 시점 수치만 있는 "
    "PER, PBR, ROE, 거래량, 부채비율 등은 그 자체만으로 고평가/저평가나 "
    "위험/안전 여부를 단정하는 근거로 쓰지 마세요. 이런 수치는 사실로만 "
    "언급하세요. 반면 다년간 재무 추세나 흑자/적자 전환 같은 fact가 함께 "
    "제공된 경우, 이는 단일 시점 수치보다 더 강한 risk 판단 근거가 될 수 "
    "있습니다(예: 영업이익률이 여러 해 연속 하락, 순이익이 흑자에서 "
    "적자로 전환 등). 그런 추세 fact가 있다면 risks 서술에 적극 "
    "활용하세요. 핵심은 단순 사실(fact)과 위험 판단(risk)을 혼동하지 "
    "않는 것입니다.\n"
    "\n"
    "여러 사업연도의 재무 추세(financial_history)가 함께 제공된 경우, "
    "investment_thesis는 최근 한 해 수치만 나열하지 말고 이 추세를 "
    "적극적으로 활용해 서술하세요. 다만 과거 추세가 존재하더라도 이를 "
    "근거로 미래 실적이나 주가를 단정하지 마세요 — 추세는 어디까지나 "
    "과거에 있었던 사실로만 서술하세요.\n"
    "\n"
    "v1에는 목표주가를 산정할 근거(밸류에이션 모델, 애널리스트 컨센서스, "
    "backtest 등)가 없습니다. target_price와 probability는 항상 null로 "
    "두세요. 절대 임의의 숫자를 만들지 마세요.\n"
    "\n"
    "현재 데이터만으로 서로 구분되는 시나리오를 정당화할 수 없다면 "
    "scenarios를 빈 배열 []로 반환해도 됩니다. 근거 없이 시나리오를 "
    "억지로 만들지 마세요.\n"
    "\n"
    "반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트를 덧붙이지 마세요.\n"
    "{\n"
    '  "investment_thesis": string,\n'
    '  "catalysts": string[],\n'
    '  "risks": string[],\n'
    '  "scenarios": [\n'
    "    {\n"
    '      "scenario": "bull" | "base" | "bear",\n'
    '      "thesis": string,\n'
    '      "target_price": null,\n'
    '      "probability": null\n'
    "    }\n"
    "  ],\n"
    '  "suggested_confidence": "low" | "medium" | "high"\n'
    "}"
)


class ReasoningResult(BaseModel):
    investment_thesis: str = Field(min_length=1)
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    scenarios: list[StockScenario] = Field(default_factory=list)
    suggested_confidence: AnalysisConfidence


class ReasoningError(Exception):
    """Raised when no valid ReasoningResult could be obtained from the LLM."""


async def generate_reasoning(
    llm_service: LLMService,
    analysis: DeterministicAnalysisResult,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> ReasoningResult:
    messages = _build_messages(analysis)

    last_error: Exception | None = None

    for _ in range(max_attempts):
        response = await llm_service.complete(
            messages=messages,
            response_format={"type": "json_object"},
        )

        try:
            result = _parse_response(response.content)
        except (ValueError, ValidationError) as error:
            last_error = error
            continue

        return _strip_unsupported_projections(result)

    raise ReasoningError(
        f"Failed to obtain a valid reasoning result after {max_attempts} attempts"
    ) from last_error


def _parse_response(content: str) -> ReasoningResult:
    data = json.loads(content)
    return ReasoningResult.model_validate(data)


def _strip_unsupported_projections(result: ReasoningResult) -> ReasoningResult:
    # v1에는 목표주가/확률을 산정할 근거(밸류에이션 모델, backtest 등)가
    # 없다. 프롬프트로 지시해도 LLM이 숫자를 만들어낼 수 있으므로,
    # 여기서 항상 제거해 근거 없는 숫자가 절대 결과에 남지 않게 한다.
    if not result.scenarios:
        return result

    sanitized_scenarios = [
        scenario.model_copy(update={"target_price": None, "probability": None})
        for scenario in result.scenarios
    ]

    return result.model_copy(update={"scenarios": sanitized_scenarios})


def _build_messages(
    analysis: DeterministicAnalysisResult,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _format_analysis(analysis)},
    ]


def _format_analysis(analysis: DeterministicAnalysisResult) -> str:
    price = analysis.price
    financials = analysis.financials

    lines = [
        f"종목: {price.name} ({price.symbol})",
        f"현재가: {price.price:,.0f}원",
    ]

    _append_if_present(lines, "등락률", price.change_pct, suffix="%")
    _append_if_present(lines, "거래량", price.volume)

    if price.high_250d is not None and price.low_250d is not None:
        lines.append(
            f"250거래일 최고/최저: {price.high_250d:,.0f}원 / "
            f"{price.low_250d:,.0f}원"
        )

    _append_if_present(lines, "매출액", financials.revenue, suffix="원")
    _append_if_present(lines, "영업이익", financials.operating_profit, suffix="원")
    _append_if_present(lines, "순이익", financials.net_income, suffix="원")
    _append_if_present(lines, "자산총계", financials.total_assets, suffix="원")
    _append_if_present(
        lines, "부채총계", financials.total_liabilities, suffix="원"
    )
    _append_if_present(lines, "자본총계", financials.total_equity, suffix="원")
    _append_if_present(lines, "PER", financials.per)
    _append_if_present(lines, "PBR", financials.pbr)
    _append_if_present(lines, "ROE", financials.roe, suffix="%")

    if analysis.financial_history:
        lines.append("")
        lines.append("다년 재무 추세(사업보고서 기준, 오래된 연도 → 최신 연도):")
        for snapshot in analysis.financial_history:
            year_label = snapshot.business_year or "?"
            parts = [f"{year_label}년"]
            if snapshot.revenue is not None:
                parts.append(f"매출액 {snapshot.revenue:,.0f}원")
            if snapshot.operating_profit is not None:
                parts.append(f"영업이익 {snapshot.operating_profit:,.0f}원")
            if snapshot.net_income is not None:
                parts.append(f"순이익 {snapshot.net_income:,.0f}원")
            lines.append("- " + ", ".join(parts))

    if analysis.facts:
        lines.append("추가로 확인된 사실:")
        lines.extend(
            f"- {fact.description} (출처: {fact.source})"
            for fact in analysis.facts
        )
    else:
        lines.append("추가로 확인된 사실 없음.")

    return "\n".join(lines)


def _append_if_present(
    lines: list[str],
    label: str,
    value: Any,
    suffix: str = "",
) -> None:
    if value is None:
        return

    if isinstance(value, float):
        lines.append(f"{label}: {value:,.2f}{suffix}")
    else:
        lines.append(f"{label}: {value:,}{suffix}")

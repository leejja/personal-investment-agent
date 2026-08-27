import json

from pydantic import BaseModel, Field, ValidationError

from app.agents.market.analysis import MarketDeterministicAnalysisResult
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.market import MarketRegime
from app.services.llm import LLMService

DEFAULT_MAX_ATTEMPTS = 2

_SYSTEM_PROMPT = (
    "당신은 한국 시장 환경을 다루는 거시 분석가입니다.\n"
    "아래 사용자 메시지에 주어진 시장 지표 사실(facts)만을 근거로 분석하세요.\n"
    "주어지지 않은 뉴스, 수급, 해외 지수, 산업 동향 등 외부 정보를 추측하거나 "
    "지어내지 마세요.\n"
    "\n"
    "각 fact 앞에는 대괄호로 표시된 고유 id가 있습니다(예: [base_rate_change]). "
    "regime_fact_ids와 risk_fact_ids에는 실제로 판단의 근거로 삼은 fact의 id만 "
    "대괄호 없이 정확히 그대로 적으세요. 주어진 목록에 없는 id를 만들어 적으면 "
    "안 됩니다.\n"
    "\n"
    "regime_fact_ids와 risk_fact_ids는 각각 반드시 최소 1개 이상의 id를 "
    "포함해야 합니다. 이 필드를 빈 배열로 남기는 것은 허용되지 않습니다. 근거로 "
    "삼을 fact가 마땅치 않다고 느껴지더라도, 주어진 fact 중 가장 관련이 깊은 "
    "것을 최소 1개 선택해 반드시 포함하세요.\n"
    "\n"
    "regime은 risk_on/neutral/risk_off 중 하나, risk_level은 low/medium/high "
    "중 하나로만 답하세요. 확신이 서지 않는다면 neutral/medium을 사용하고, 그 "
    "불확실성은 suggested_confidence를 낮추는 것으로 표현하세요.\n"
    "\n"
    "반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트를 덧붙이지 마세요.\n"
    "{\n"
    '  "summary": string,\n'
    '  "suggested_regime": "risk_on" | "neutral" | "risk_off",\n'
    '  "suggested_risk_level": "low" | "medium" | "high",\n'
    '  "suggested_confidence": "low" | "medium" | "high",\n'
    '  "regime_fact_ids": string[],\n'
    '  "risk_fact_ids": string[]\n'
    "}"
)


class ReasoningResult(BaseModel):
    summary: str = Field(min_length=1)
    suggested_regime: MarketRegime
    suggested_risk_level: RiskLevel
    suggested_confidence: AnalysisConfidence
    regime_fact_ids: list[str] = Field(default_factory=list)
    risk_fact_ids: list[str] = Field(default_factory=list)


class ReasoningError(Exception):
    """Raised when no valid, grounded ReasoningResult could be obtained from the LLM."""


async def generate_reasoning(
    llm_service: LLMService,
    analysis: MarketDeterministicAnalysisResult,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> ReasoningResult:
    messages = _build_messages(analysis)
    known_fact_ids = {fact.id for fact in analysis.facts}

    last_error: Exception | None = None

    for _ in range(max_attempts):
        response = await llm_service.complete(
            messages=messages,
            response_format={"type": "json_object"},
        )

        try:
            result = _parse_response(response.content)
            _validate_grounding(result, known_fact_ids)
        except (ValueError, ValidationError) as error:
            last_error = error
            continue

        return result

    raise ReasoningError(
        f"Failed to obtain a grounded reasoning result after {max_attempts} attempts"
    ) from last_error


def _parse_response(content: str) -> ReasoningResult:
    data = json.loads(content)
    return ReasoningResult.model_validate(data)


def _validate_grounding(result: ReasoningResult, known_fact_ids: set[str]) -> None:
    # regime/risk_level은 Market Agent의 핵심 판단이라 Python 상수로 고정할 수
    # 없다(stock의 risk_level처럼 고정할 근거가 없음). 대신 "실제 존재하는
    # fact에 근거했는지"를 엄격하게 검증한다 — 일부만 유효해도 조용히 걸러내고
    # 통과시키지 않는다. 검증에 실패하면 재시도하고, 재시도까지 실패하면
    # ReasoningError로 전파한다(근거 없는 결과를 반환하지 않는다).
    if not result.regime_fact_ids:
        raise ValueError("regime_fact_ids must not be empty")

    if not result.risk_fact_ids:
        raise ValueError("risk_fact_ids must not be empty")

    unknown_regime_ids = [
        fact_id for fact_id in result.regime_fact_ids if fact_id not in known_fact_ids
    ]
    if unknown_regime_ids:
        raise ValueError(f"regime_fact_ids contains unknown fact ids: {unknown_regime_ids}")

    unknown_risk_ids = [
        fact_id for fact_id in result.risk_fact_ids if fact_id not in known_fact_ids
    ]
    if unknown_risk_ids:
        raise ValueError(f"risk_fact_ids contains unknown fact ids: {unknown_risk_ids}")


def _build_messages(
    analysis: MarketDeterministicAnalysisResult,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _format_analysis(analysis)},
    ]


def _format_analysis(analysis: MarketDeterministicAnalysisResult) -> str:
    lines = ["시장 지표 사실:"]

    if analysis.facts:
        lines.extend(f"- [{fact.id}] {fact.description}" for fact in analysis.facts)
    else:
        lines.append("확인된 사실 없음.")

    return "\n".join(lines)

import json

from pydantic import BaseModel, Field, ValidationError

from app.agents.portfolio.analysis import PortfolioDeterministicAnalysisResult
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.strategy import InvestmentAction
from app.services.llm import LLMService

DEFAULT_MAX_ATTEMPTS = 2

_SYSTEM_PROMPT = (
    "당신은 개인 투자자의 포트폴리오 전략을 다루는 애널리스트입니다.\n"
    "아래 사용자 메시지에 주어진 시장/포트폴리오/종목 사실(facts)과 \"판단 대상 "
    "종목\" 목록만을 근거로 판단하세요. 주어지지 않은 뉴스, 공시, 산업 동향, "
    "종목 등 외부 정보를 추측하거나 지어내지 마세요.\n"
    "\n"
    "가장 중요한 규칙: recommendations의 symbol은 반드시 아래 \"판단 대상 "
    "종목\" 목록에 있는 종목이어야 합니다. 목록에 없는 종목은 당신이 실제로 "
    "알고 있는 유명하거나 관련성 높은 종목이라도 절대 언급하거나 추천하지 "
    "마세요 — 이 시스템은 새로운 종목을 발굴하는 도구가 아니라, 이미 주어진 "
    "종목에 대해서만 판단하는 도구입니다. 목록에 없는 종목을 하나라도 포함하면 "
    "응답 전체가 무효 처리되고 재시도됩니다.\n"
    "\n"
    "symbol 필드에는 반드시 종목코드만 정확히 그대로 적으세요(예: "
    "\"005930\"). 종목명을 적거나, \"삼성전자(005930)\"처럼 이름과 코드를 "
    "합쳐 적으면 안 됩니다 — 그런 형식도 목록에 없는 값으로 취급되어 "
    "무효 처리됩니다. \"판단 대상 종목\" 목록의 symbol= 뒤에 오는 값만 "
    "그대로 사용하세요.\n"
    "\n"
    "각 fact 앞에는 대괄호로 표시된 고유 id가 있습니다(예: [portfolio_cash_weight]). "
    "recommendations의 각 항목과 portfolio_risk_fact_ids에는 실제로 판단의 "
    "근거로 삼은 fact의 id만 대괄호 없이 정확히 그대로 적으세요. 주어진 목록에 "
    "없는 id를 만들어 적으면 안 됩니다. 각 recommendation의 fact_ids와 "
    "portfolio_risk_fact_ids는 각각 반드시 최소 1개 이상의 id를 포함해야 "
    "합니다.\n"
    "\n"
    "\"판단 대상 종목\" 목록에는 종목별로 보유 여부와 그에 따라 허용된 action이 "
    "함께 주어집니다. suggested_action은 반드시 그 종목에 허용된 action 중 "
    "하나여야 합니다. 허용되지 않은 action(예: 미보유 종목에 "
    "sell/reduce/add/hold, 보유 종목에 buy/avoid)을 사용하면 안 됩니다.\n"
    "\n"
    "특정 종목에 대해 판단할 근거가 충분치 않다면 그 종목은 recommendations에서 "
    "제외해도 됩니다 — 억지로 모든 종목을 판단할 필요는 없습니다. 근거가 없으면 "
    "만들지 마세요. recommendations를 빈 배열로 반환하는 것이, 목록에 없는 "
    "종목을 지어내는 것보다 항상 낫습니다.\n"
    "\n"
    "v1에는 목표 비중(target weight)이나 매매 수량/금액을 산정할 근거(포지션 "
    "사이징 모델, 리스크 버짓 등)가 없습니다. 이 응답 형식에는 그런 숫자 필드가 "
    "아예 없습니다 — 방향(action)과 이유(rationale)만 제공하세요.\n"
    "\n"
    "conditions에는 \"만약 ~하면\" 형태의 조건부 대응을 적을 수 있습니다. 근거가 "
    "없으면 빈 리스트로 두세요.\n"
    "\n"
    "portfolio_risk는 low/medium/high 중 하나로만 답하세요.\n"
    "\n"
    "반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트를 덧붙이지 마세요.\n"
    "{\n"
    '  "portfolio_summary": string,\n'
    '  "recommendations": [\n'
    "    {\n"
    '      "symbol": string,\n'
    '      "suggested_action": "buy" | "add" | "hold" | "reduce" | "sell" | "avoid",\n'
    '      "rationale": string,\n'
    '      "conditions": string[],\n'
    '      "fact_ids": string[]\n'
    "    }\n"
    "  ],\n"
    '  "suggested_portfolio_risk": "low" | "medium" | "high",\n'
    '  "portfolio_risk_fact_ids": string[],\n'
    '  "suggested_confidence": "low" | "medium" | "high"\n'
    "}"
)


class SuggestedRecommendation(BaseModel):
    symbol: str = Field(min_length=1)
    suggested_action: InvestmentAction
    rationale: str = Field(min_length=1)
    conditions: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


class ReasoningResult(BaseModel):
    portfolio_summary: str = Field(min_length=1)
    recommendations: list[SuggestedRecommendation] = Field(default_factory=list)
    suggested_portfolio_risk: RiskLevel
    portfolio_risk_fact_ids: list[str] = Field(default_factory=list)
    suggested_confidence: AnalysisConfidence


class ReasoningError(Exception):
    """Raised when no valid, grounded ReasoningResult could be obtained from the LLM."""


async def generate_reasoning(
    llm_service: LLMService,
    analysis: PortfolioDeterministicAnalysisResult,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> ReasoningResult:
    messages = _build_messages(analysis)

    known_symbols = {context.symbol for context in analysis.symbol_contexts}
    known_fact_ids = {fact.id for fact in analysis.facts}
    allowed_actions_by_symbol = {
        context.symbol: set(context.allowed_actions)
        for context in analysis.symbol_contexts
    }

    last_error: Exception | None = None

    for _ in range(max_attempts):
        response = await llm_service.complete(
            messages=messages,
            response_format={"type": "json_object"},
        )

        try:
            result = _parse_response(response.content)
            _validate_result(
                result,
                known_symbols=known_symbols,
                known_fact_ids=known_fact_ids,
                allowed_actions_by_symbol=allowed_actions_by_symbol,
            )
        except (ValueError, ValidationError) as error:
            last_error = error
            continue

        return result

    raise ReasoningError(
        f"Failed to obtain a valid, grounded reasoning result after {max_attempts} attempts"
    ) from last_error


def _parse_response(content: str) -> ReasoningResult:
    data = json.loads(content)
    return ReasoningResult.model_validate(data)


def _validate_result(
    result: ReasoningResult,
    *,
    known_symbols: set[str],
    known_fact_ids: set[str],
    allowed_actions_by_symbol: dict[str, set[InvestmentAction]],
) -> None:
    # portfolio_risk는 regime/risk_level(Market Agent)과 동일하게 이 Agent의
    # 핵심 판단이라 Python 상수로 고정할 수 없다. 대신 fact-id grounding으로
    # "실제 존재하는 fact에 근거했는지"를 엄격하게 검증한다 — 일부만 유효해도
    # 조용히 걸러내고 통과시키지 않는다.
    if not result.portfolio_risk_fact_ids:
        raise ValueError("portfolio_risk_fact_ids must not be empty")

    unknown_portfolio_risk_ids = [
        fact_id
        for fact_id in result.portfolio_risk_fact_ids
        if fact_id not in known_fact_ids
    ]
    if unknown_portfolio_risk_ids:
        raise ValueError(
            f"portfolio_risk_fact_ids contains unknown fact ids: {unknown_portfolio_risk_ids}"
        )

    for recommendation in result.recommendations:
        _validate_recommendation(
            recommendation,
            known_symbols=known_symbols,
            known_fact_ids=known_fact_ids,
            allowed_actions_by_symbol=allowed_actions_by_symbol,
        )


def _validate_recommendation(
    recommendation: SuggestedRecommendation,
    *,
    known_symbols: set[str],
    known_fact_ids: set[str],
    allowed_actions_by_symbol: dict[str, set[InvestmentAction]],
) -> None:
    # symbol grounding: 주어진 판단 대상 종목 밖의 새 종목을 지어내는 것을
    # 원천 차단한다.
    if recommendation.symbol not in known_symbols:
        raise ValueError(
            f"recommendation references unknown symbol: {recommendation.symbol}"
        )

    # action grounding: 보유 여부에 물리적으로 맞지 않는 action(예: 미보유
    # 종목에 SELL)을 구조적으로 차단한다. 시장/재무 판단이 아니라 순수한
    # 사실 검증이다.
    allowed_actions = allowed_actions_by_symbol[recommendation.symbol]
    if recommendation.suggested_action not in allowed_actions:
        allowed_values = sorted(action.value for action in allowed_actions)
        raise ValueError(
            f"recommendation for {recommendation.symbol} suggests disallowed "
            f"action {recommendation.suggested_action.value}: "
            f"allowed={allowed_values}"
        )

    # fact-id grounding: regime/risk_level(Market Agent)과 동일한 정책.
    if not recommendation.fact_ids:
        raise ValueError(
            f"recommendation for {recommendation.symbol} has empty fact_ids"
        )

    unknown_fact_ids = [
        fact_id for fact_id in recommendation.fact_ids if fact_id not in known_fact_ids
    ]
    if unknown_fact_ids:
        raise ValueError(
            f"recommendation for {recommendation.symbol} references unknown "
            f"fact ids: {unknown_fact_ids}"
        )


def _build_messages(
    analysis: PortfolioDeterministicAnalysisResult,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _format_analysis(analysis)},
    ]


def _format_analysis(analysis: PortfolioDeterministicAnalysisResult) -> str:
    lines = ["포트폴리오/시장/종목 사실:"]

    if analysis.facts:
        lines.extend(f"- [{fact.id}] {fact.description}" for fact in analysis.facts)
    else:
        lines.append("확인된 사실 없음.")

    lines.append("")
    lines.append("판단 대상 종목:")

    if analysis.symbol_contexts:
        for context in analysis.symbol_contexts:
            held = "보유" if context.current_weight is not None else "미보유"
            allowed = ", ".join(action.value for action in context.allowed_actions)
            # symbol과 name을 별도 필드로 명확히 분리해 표기한다. "이름(코드)"
            # 형태로 붙여 쓰면 LLM이 recommendations[].symbol에 "이름(코드)"
            # 문자열 전체를 그대로 넣는 경우가 실제 E2E에서 관찰됐다(예:
            # "에코프로비엠(247540)") — symbol grounding이 이를 정확히
            # 차단하지만, 애초에 그런 혼동이 생기지 않도록 포맷 자체를
            # 분리한다.
            lines.append(
                f"- symbol={context.symbol}, name={context.name}, {held}, "
                f"허용 action=[{allowed}]"
            )
    else:
        lines.append("판단 대상 종목 없음.")

    return "\n".join(lines)

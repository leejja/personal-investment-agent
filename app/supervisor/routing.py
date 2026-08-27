import json

from pydantic import BaseModel, Field, ValidationError

from app.models.common import UserRequest
from app.models.supervisor import Intent
from app.services.llm import LLMService

DEFAULT_MAX_ATTEMPTS = 2

_SYSTEM_PROMPT = (
    "당신은 개인 투자 시스템의 요청 분류기입니다.\n"
    "사용자의 질문을 아래 세 가지 intent 중 정확히 하나로 분류하세요.\n"
    "\n"
    "- market_only: 시장 전반(금리/환율/지수 등)에 대한 질문. 특정 종목이나 "
    "사용자의 보유 포트폴리오와 무관합니다.\n"
    "- stock_research: 특정 종목 자체에 대한 분석 요청이되, 사용자의 보유 "
    "여부나 포트폴리오 맥락과는 무관한 질문입니다(예: \"삼성전자 어때?\").\n"
    "- portfolio_strategy: 사용자의 실제 보유 포트폴리오를 고려해야 하는 "
    "질문입니다. 전체 포트폴리오에 대한 질문(예: \"내 포트폴리오 분석해줘\")과 "
    "특정 종목을 사용자가 사도/팔아도 되는지 묻는 질문(예: \"삼성전자 더 "
    "사도 될까?\") 모두 여기 포함됩니다 — 후자도 사용자의 현재 보유 여부와 "
    "비중을 고려해야 하므로 stock_research가 아니라 portfolio_strategy로 "
    "분류하세요.\n"
    "\n"
    "mentioned_stock_terms에는 질문에서 언급된 종목명이나 종목코드를 원문 "
    "그대로(번역·수정하지 말고) 추출해 담으세요. 언급된 종목이 없으면 빈 "
    "배열로 두세요. 이 필드는 종목 코드를 새로 만들어내는 곳이 아닙니다 — "
    "질문에 실제로 등장한 텍스트만 담으세요.\n"
    "\n"
    "반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트를 덧붙이지 마세요.\n"
    "{\n"
    '  "intent": "market_only" | "stock_research" | "portfolio_strategy",\n'
    '  "mentioned_stock_terms": string[]\n'
    "}"
)


class RoutingResult(BaseModel):
    intent: Intent
    mentioned_stock_terms: list[str] = Field(default_factory=list)


class RoutingError(Exception):
    """Raised when no valid RoutingResult could be obtained from the LLM."""


async def classify(
    llm_service: LLMService,
    request: UserRequest,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> RoutingResult:
    messages = _build_messages(request)

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

        return result

    raise RoutingError(
        f"Failed to classify request after {max_attempts} attempts"
    ) from last_error


def _parse_response(content: str) -> RoutingResult:
    data = json.loads(content)
    return RoutingResult.model_validate(data)


def _build_messages(request: UserRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _format_request(request)},
    ]


def _format_request(request: UserRequest) -> str:
    lines = [f"질문: {request.question}"]

    if request.symbols:
        lines.append(f"이미 알려진 종목코드: {', '.join(request.symbols)}")

    return "\n".join(lines)

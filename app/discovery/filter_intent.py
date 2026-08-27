import json

from pydantic import BaseModel, Field, ValidationError

from app.models.discovery import MarketFilter
from app.services.llm import LLMService

DEFAULT_MAX_ATTEMPTS = 2

_SYSTEM_PROMPT = (
    "당신은 종목 후보 검색 조건을 구조화하는 파서입니다.\n"
    "사용자 메시지에 주어진 질문과 \"사용 가능한 업종명\"/\"사용 가능한 "
    "규모 구분\" 목록만 근거로 판단하세요. 절대 종목명이나 종목코드를 "
    "직접 언급하거나 만들어내지 마세요 — 이 시스템은 조건만 구조화하고, "
    "실제 종목 선택은 Python이 실제 데이터로 수행합니다.\n"
    "\n"
    "market: 코스피/코스닥 중 하나로 명시적으로 한정하는 질문에만 "
    "\"kospi\" 또는 \"kosdaq\"를 쓰고, 특별한 언급이 없으면 null을 "
    "반환하세요.\n"
    "\n"
    "sector_terms: 반드시 주어진 \"사용 가능한 업종명\" 목록에 실제로 "
    "존재하는 값 중에서만, 그것도 원문 그대로 정확히 선택하세요. 목록에 "
    "없는 업종명을 만들어내거나 비슷한 이름으로 대체하면 안 됩니다. "
    "사용자가 업종을 언급하지 않았거나 목록에서 대응하는 값을 찾을 수 "
    "없으면 빈 배열로 두세요.\n"
    "\n"
    "size_terms: 반드시 주어진 \"사용 가능한 규모 구분\" 목록에 실제로 "
    "존재하는 값 중에서만 선택하세요. sector_terms와 동일한 규칙입니다.\n"
    "\n"
    "exclude_owned: 사용자의 문장이 실제로 \"보유하지 않은\", \"내 "
    "포트폴리오에 없는\", \"새로 추가할\", \"미보유\"처럼 기존 보유 "
    "종목을 제외해달라는 의미를 명시하거나 강하게 암시할 때만 true로 "
    "설정하세요. 이 결과가 나중에 포트폴리오 판단에 쓰일 수 있다는 "
    "사실만으로 true로 설정하지 마세요 — 반드시 문장 자체에 제외 의도가 "
    "있어야 합니다.\n"
    "\n"
    "반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트를 덧붙이지 "
    "마세요.\n"
    "{\n"
    '  "market": "kospi" | "kosdaq" | null,\n'
    '  "sector_terms": string[],\n'
    '  "size_terms": string[],\n'
    '  "exclude_owned": boolean\n'
    "}"
)


class DiscoveryFilter(BaseModel):
    market: MarketFilter | None = None
    sector_terms: list[str] = Field(default_factory=list)
    size_terms: list[str] = Field(default_factory=list)
    exclude_owned: bool = False


class FilterIntentError(Exception):
    """Raised when no valid, grounded DiscoveryFilter could be obtained from the LLM."""


async def classify(
    llm_service: LLMService,
    question: str,
    *,
    known_sectors: list[str],
    known_sizes: list[str],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> DiscoveryFilter:
    messages = _build_messages(question, known_sectors, known_sizes)
    known_sector_set = set(known_sectors)
    known_size_set = set(known_sizes)

    last_error: Exception | None = None

    for _ in range(max_attempts):
        response = await llm_service.complete(
            messages=messages,
            response_format={"type": "json_object"},
        )

        try:
            result = _parse_response(response.content)
            _validate(result, known_sector_set, known_size_set)
        except (ValueError, ValidationError) as error:
            last_error = error
            continue

        return result

    raise FilterIntentError(
        f"Failed to obtain a valid, grounded discovery filter after {max_attempts} attempts"
    ) from last_error


def _parse_response(content: str) -> DiscoveryFilter:
    data = json.loads(content)
    return DiscoveryFilter.model_validate(data)


def _validate(
    result: DiscoveryFilter,
    known_sectors: set[str],
    known_sizes: set[str],
) -> None:
    # fact-id grounding과 달리 sector_terms/size_terms가 비어 있는 것은
    # 정상이다(사용자가 그 조건을 언급하지 않았다는 뜻) — 여기서는 "실제로
    # 제안된 값이 존재하는 것인지"만 검증한다.
    unknown_sectors = [term for term in result.sector_terms if term not in known_sectors]
    if unknown_sectors:
        raise ValueError(f"sector_terms contains unknown values: {unknown_sectors}")

    unknown_sizes = [term for term in result.size_terms if term not in known_sizes]
    if unknown_sizes:
        raise ValueError(f"size_terms contains unknown values: {unknown_sizes}")


def _build_messages(
    question: str,
    known_sectors: list[str],
    known_sizes: list[str],
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _format_request(question, known_sectors, known_sizes)},
    ]


def _format_request(
    question: str,
    known_sectors: list[str],
    known_sizes: list[str],
) -> str:
    lines = [f"질문: {question}", "", "사용 가능한 업종명:"]
    lines.extend(f"- {sector}" for sector in known_sectors)
    if not known_sectors:
        lines.append("(없음)")

    lines.extend(["", "사용 가능한 규모 구분:"])
    lines.extend(f"- {size}" for size in known_sizes)
    if not known_sizes:
        lines.append("(없음)")

    return "\n".join(lines)

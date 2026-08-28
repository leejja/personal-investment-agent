import json

from pydantic import BaseModel, Field, ValidationError

from app.models.discovery import MarketFilter
from app.services.llm import LLMService

DEFAULT_MAX_ATTEMPTS = 2

_SYSTEM_PROMPT = (
    "당신은 종목 후보 검색 조건을 구조화하는 파서입니다.\n"
    "sector_terms/size_terms는 주어진 \"사용 가능한 업종명\"/\"사용 "
    "가능한 규모 구분\" 목록만 근거로 판단하세요. 절대 종목명이나 "
    "종목코드를 직접 언급하거나 만들어내지 마세요 — 이 시스템은 조건만 "
    "구조화하고, 실제 종목 선택과 테마 매칭은 Python이 실제 데이터로 "
    "수행합니다.\n"
    "\n"
    "market: 코스피/코스닥 중 하나로 명시적으로 한정하는 질문에만 "
    "\"kospi\" 또는 \"kosdaq\"를 쓰고, 특별한 언급이 없으면 null을 "
    "반환하세요.\n"
    "\n"
    "sector_terms: 업종(broad industry) 조건입니다. 반드시 주어진 "
    "\"사용 가능한 업종명\" 목록에 실제로 존재하는 값 중에서만, 그것도 "
    "원문 그대로 정확히 선택하세요. 목록에 없는 업종명을 만들어내거나 "
    "비슷한 이름으로 대체하면 안 됩니다. 사용자가 업종을 언급하지 "
    "않았거나 목록에서 대응하는 값을 찾을 수 없으면 빈 배열로 두세요. "
    "\"통신\", \"전기/전자\"처럼 굵직한 업종 대분류를 가리키는 표현에만 "
    "쓰고, \"반도체\", \"2차전지\", \"로봇\", \"원전\"처럼 더 구체적인 "
    "투자 테마는 sector_terms가 아니라 아래 theme_requests로 표현하세요 "
    "— 이 목록에는 그런 세부 테마가 애초에 존재하지 않습니다.\n"
    "\n"
    "size_terms: 반드시 주어진 \"사용 가능한 규모 구분\" 목록에 실제로 "
    "존재하는 값 중에서만 선택하세요. sector_terms와 동일한 규칙입니다.\n"
    "\n"
    "theme_requests: 사용자가 언급한 세부 투자 테마/산업 개념(예: "
    "\"반도체\", \"2차전지\", \"로봇\", \"원전\", \"AI\")마다 하나씩 "
    "항목을 만드세요. \"A와 B\", \"A, B\"처럼 서로 다른 개념이 명확히 "
    "나열된 경우 각각 별도 항목으로 분리하세요 — 하나로 합쳐서 "
    "\"A B\" concept를 만들면 안 됩니다(예: \"AI와 반도체 관련주\"는 "
    "concept \"AI\" 항목과 concept \"반도체\" 항목 두 개로 분리해야지, "
    "\"AI 반도체\"라는 새 concept 하나로 합치면 안 됩니다). 다만 "
    "\"AI 반도체\"처럼 띄어쓰기만으로 이어져 있고 그 자체가 이미 하나의 "
    "고유한 대상(예: AI 연산 전용 반도체)을 가리키는 것이 명백한 "
    "합성어라면 하나의 concept으로 유지해도 됩니다 — 애매하면 분리하는 "
    "쪽을 우선하세요.\n"
    "각 항목의 concept에는 사용자가 의도한 개념을 그대로 쓰세요. "
    "실제 테마 카탈로그에서 어떤 값이 이 concept과 매칭되는지는 "
    "당신이 판단하지 않습니다 — 그 매칭은 시스템이 정확한 문자열 "
    "규칙으로 결정론적으로 수행합니다. 당신의 역할은 오직 "
    "normalized_concepts를 제안하는 것뿐입니다: concept이 한국 "
    "주식시장에서 통용되는 다른 공식/일반 표현이 있다면(예: \"원전\"의 "
    "통용 표현인 \"원자력\") 최대 2~3개까지 자유롭게 제안하세요. "
    "이 제안이 실제로 맞는지 확신할 필요는 없습니다 — 틀린 제안은 "
    "시스템이 문자열 매칭 단계에서 자동으로 걸러냅니다. 확신이 없으면 "
    "빈 배열로 두어도 됩니다. concept 자체에 뚜렷한 동의어가 없으면 "
    "normalized_concepts는 생략(빈 배열)해도 됩니다 — concept 항목 "
    "자체는 매칭 여부와 무관하게 반드시 남기세요(생략하지 마세요), "
    "매칭 결과가 없으면 이후 시스템이 이 항목을 보고 \"현재 지원하지 "
    "않는 개념\"으로 판단합니다. 사용자가 세부 테마/산업 개념을 전혀 "
    "언급하지 않았으면 theme_requests를 빈 배열로 두세요.\n"
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
    '  "theme_requests": [{"concept": string, "normalized_concepts": string[]}],\n'
    '  "exclude_owned": boolean\n'
    "}"
)


class ThemeRequest(BaseModel):
    # concept은 사용자가 언급한 원래 개념(예: "반도체", "원전")을 그대로
    # 담는 evidence/traceability 목적의 필드다 — 최종 필터링에는
    # matched_themes만 쓰인다(concept 자체로 매칭하지 않는다).
    concept: str = Field(min_length=1)
    # ka90001 실제 관측 카탈로그에 존재하는 테마명만 담긴다. 이 필드는
    # LLM이 직접 채우지 않는다 — _match_theme_names()가 concept과
    # _RawThemeRequest.normalized_concepts를 실제 카탈로그에 대해
    # 결정론적 문자열 매칭(exact/prefix)한 결과로만 채워진다(아래
    # "Theme grounding responsibility" 참고). 그래서 이 필드는 항상
    # known_themes의 부분집합이도록 **구조적으로 보장**된다 — LLM이
    # 카탈로그에 실제로 존재하지만 concept과 무관한 테마를 골라 담는
    # 경로 자체가 없다. 빈 배열은 "이 개념에 대응하는 실제 테마가
    # 없다"는 정상적인 결과다. 이 개념이 사용자 요청에서 필수였는지는
    # DiscoveryOrchestrator가 판단한다(빈 매칭 = unsupported classification
    # 정책).
    matched_themes: list[str] = Field(default_factory=list)


class DiscoveryFilter(BaseModel):
    market: MarketFilter | None = None
    # Industry axis. ka10099.upName(=ka10101 업종코드) 기반의 굵직한
    # KRX 대분류만 담는다 — 실측(2026-08-28 UX-01 조사) 결과 ka10101이
    # upName보다 세분화돼 있지 않아, 별도 Industry API 연동 없이 기존
    # upName 값을 그대로 semantic Industry axis로 재사용한다.
    sector_terms: list[str] = Field(default_factory=list)
    size_terms: list[str] = Field(default_factory=list)
    # Theme axis(ka90001/ka90002). Industry와 의도적으로 분리된 별도
    # 필드다 — 같은 필드에 섞으면 "전기/전자"(Industry, 84종목)와
    # "반도체_생산"(Theme, 3종목)처럼 granularity가 전혀 다른 값이
    # 뒤섞인다.
    theme_requests: list[ThemeRequest] = Field(default_factory=list)
    exclude_owned: bool = False


class _RawThemeRequest(BaseModel):
    """LLM 응답의 theme_requests 원소를 그대로 받는 내부 전용 파싱
    모델이다. LLM은 실제 테마명이 아니라 concept과(선택적으로)
    normalized_concepts만 제안한다 — 최종 matched_themes는 절대 LLM이
    채우지 않고 _match_theme_names()가 계산한다(아래 참고)."""

    concept: str = Field(min_length=1)
    normalized_concepts: list[str] = Field(default_factory=list)


class FilterIntentError(Exception):
    """Raised when no valid, grounded DiscoveryFilter could be obtained from the LLM."""


async def classify(
    llm_service: LLMService,
    question: str,
    *,
    known_sectors: list[str],
    known_sizes: list[str],
    known_themes: list[str] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> DiscoveryFilter:
    # known_themes 기본값 None → []는 호출자가 Theme axis를 아예 모르는
    # 경우(예: 기존 테스트)도 기존과 동일하게 동작하도록 하기 위함이다 —
    # 빈 카탈로그를 주면 어떤 concept도 매칭될 수 없어 theme_requests가
    # 항상 매칭 없는 상태로만 유효하게 통과한다.
    known_themes = known_themes or []

    messages = _build_messages(question, known_sectors, known_sizes)
    known_sector_set = set(known_sectors)
    known_size_set = set(known_sizes)
    known_theme_set = set(known_themes)

    last_error: Exception | None = None

    for _ in range(max_attempts):
        response = await llm_service.complete(
            messages=messages,
            response_format={"type": "json_object"},
        )

        try:
            result = _parse_response(response.content, known_theme_set)
            _validate(result, known_sector_set, known_size_set)
        except (ValueError, ValidationError) as error:
            last_error = error
            continue

        return result

    raise FilterIntentError(
        f"Failed to obtain a valid, grounded discovery filter after {max_attempts} attempts"
    ) from last_error


def _parse_response(content: str, known_themes: set[str]) -> DiscoveryFilter:
    data = json.loads(content)

    # theme_requests는 DiscoveryFilter.model_validate()에 그대로 넘기지
    # 않는다 — LLM이 보낸 원본 구조(concept + normalized_concepts)를
    # _RawThemeRequest로 먼저 파싱하고, 실제 matched_themes는 아래에서
    # Python이 결정론적으로 계산해 별도로 구성한다.
    raw_theme_requests_data = data.get("theme_requests", []) if isinstance(data, dict) else []
    filter_data = {
        key: value for key, value in data.items() if key != "theme_requests"
    }

    discovery_filter = DiscoveryFilter.model_validate(filter_data)

    raw_theme_requests = [
        _RawThemeRequest.model_validate(item) for item in raw_theme_requests_data
    ]
    discovery_filter.theme_requests = [
        ThemeRequest(
            concept=raw.concept,
            matched_themes=_match_theme_names(
                [raw.concept, *raw.normalized_concepts], known_themes
            ),
        )
        for raw in raw_theme_requests
    ]

    return discovery_filter


def _match_theme_names(candidate_terms: list[str], known_themes: set[str]) -> list[str]:
    """Theme grounding responsibility: 실제 카탈로그 매칭은 항상 Python이
    결정론적 문자열 규칙으로 수행한다 — LLM이 카탈로그에서 직접 테마를
    고르지 않는다. candidate_terms(concept 자신 + LLM이 제안한
    normalized_concepts)를 순서대로 시도해 첫 번째로 매칭되는 term의
    결과를 그대로 반환한다(먼저 매칭되면 이후 term은 시도하지 않는다 —
    서로 다른 term의 결과를 합치지 않는다).

    매칭 규칙은 두 가지뿐이다:
    - exact: term이 테마명과 완전히 같음(예: "화장품" == "화장품")
    - prefix: 테마명이 "{term}_"로 시작함 — Kiwoom 테마 카탈로그가 실제로
      쓰는 "카테고리_세부항목" 명명 규칙이다(예: "반도체_생산",
      "2차전지_완제품", "원자력_기자재" — 2026-08-28 UX-01 조사에서
      실측 확인).

    fuzzy/semantic 매칭이나 하드코딩된 동의어 사전은 쓰지 않는다 — LLM이
    제안한 normalized_concepts가 틀리거나 카탈로그에 없는 값이어도 그냥
    매칭되지 않을 뿐 에러가 아니다(이게 안전한 이유: 최종 결과는 항상
    known_themes의 부분집합이도록 이 함수가 구조적으로 보장한다)."""
    for term in candidate_terms:
        if not term:
            continue

        matches = sorted(
            name
            for name in known_themes
            if name == term or name.startswith(f"{term}_")
        )
        if matches:
            return matches

    return []


def _validate(
    result: DiscoveryFilter,
    known_sectors: set[str],
    known_sizes: set[str],
) -> None:
    # fact-id grounding과 달리 sector_terms/size_terms가 비어 있는 것은
    # 정상이다(사용자가 그 조건을 언급하지 않았다는 뜻) — 여기서는 "실제로
    # 제안된 값이 존재하는 것인지"만 검증한다. theme_requests는 여기서
    # 검증하지 않는다 — _parse_response()의 _match_theme_names()가 이미
    # known_themes의 부분집합만 만들어내도록 구조적으로 보장하므로
    # hallucination 자체가 발생할 수 없다.
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
        {
            "role": "user",
            "content": _format_request(question, known_sectors, known_sizes),
        },
    ]


def _format_request(
    question: str,
    known_sectors: list[str],
    known_sizes: list[str],
) -> str:
    # 테마명 카탈로그는 더 이상 프롬프트에 렌더링하지 않는다 — LLM의
    # 역할이 "카탈로그에서 실제 테마를 고르는 것"에서 "concept과 그
    # 동의어를 자유롭게 제안하는 것"으로 바뀌어(위 _match_theme_names
    # 참고) 카탈로그를 볼 필요가 없어졌다. 142개 테마명을 매 요청마다
    # 프롬프트에 싣던 토큰 비용도 함께 줄었다.
    lines = [f"질문: {question}", "", "사용 가능한 업종명:"]
    lines.extend(f"- {sector}" for sector in known_sectors)
    if not known_sectors:
        lines.append("(없음)")

    lines.extend(["", "사용 가능한 규모 구분:"])
    lines.extend(f"- {size}" for size in known_sizes)
    if not known_sizes:
        lines.append("(없음)")

    return "\n".join(lines)

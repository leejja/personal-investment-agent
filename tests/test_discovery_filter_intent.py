import json
from unittest.mock import AsyncMock

import pytest

from app.discovery.filter_intent import FilterIntentError, _match_theme_names, classify
from app.models.discovery import MarketFilter
from app.services.llm import LLMResponse, LLMService

_KNOWN_SECTORS = ["반도체와반도체장비", "제약", "운송장비/부품"]
_KNOWN_SIZES = ["대형주", "중형주", "소형주"]
_KNOWN_THEMES = [
    "반도체_생산",
    "반도체_설계(fabless)",
    "반도체_전공정장비",
    "2차전지_완제품",
    "2차전지_소재(양극화물질등)",
    "로봇_지능형",
    "원자력_기자재",
    "원자력_설계시공",
    "화장품",  # 언더스코어 없는 flat/단일 테마명(exact match 케이스 커버용)
]


def _valid_json(
    *,
    market: str | None = None,
    sector_terms: list[str] | None = None,
    size_terms: list[str] | None = None,
    theme_requests: list[dict] | None = None,
    exclude_owned: bool = False,
) -> str:
    return json.dumps(
        {
            "market": market,
            "sector_terms": sector_terms or [],
            "size_terms": size_terms or [],
            "theme_requests": theme_requests or [],
            "exclude_owned": exclude_owned,
        },
        ensure_ascii=False,
    )


def _llm_with_responses(contents: list[str]) -> LLMService:
    llm_service = LLMService(api_key="test-key", model="test-model")
    llm_service.complete = AsyncMock(
        side_effect=[
            LLMResponse(content=content, model="test-model", finish_reason="stop")
            for content in contents
        ]
    )
    return llm_service


@pytest.mark.anyio
async def test_classify_returns_valid_filter() -> None:
    llm_service = _llm_with_responses(
        [_valid_json(sector_terms=["반도체와반도체장비"])]
    )

    result = await classify(
        llm_service,
        "반도체 종목 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.sector_terms == ["반도체와반도체장비"]
    assert result.market is None
    assert result.exclude_owned is False


@pytest.mark.anyio
async def test_classify_allows_empty_filter() -> None:
    llm_service = _llm_with_responses([_valid_json()])

    result = await classify(
        llm_service,
        "아무 조건도 없는 질문",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.market is None
    assert result.sector_terms == []
    assert result.size_terms == []
    assert result.exclude_owned is False


@pytest.mark.anyio
async def test_classify_market_enum_validated_structurally() -> None:
    llm_service = _llm_with_responses([_valid_json(market="kospi")])

    result = await classify(
        llm_service,
        "코스피 종목 중에서 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.market == MarketFilter.KOSPI


@pytest.mark.anyio
async def test_classify_retries_when_market_is_unknown_enum_value() -> None:
    bad_json = json.dumps(
        {
            "market": "nasdaq",
            "sector_terms": [],
            "size_terms": [],
            "exclude_owned": False,
        }
    )
    llm_service = _llm_with_responses([bad_json, _valid_json()])

    result = await classify(
        llm_service,
        "질문",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.market is None
    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_classify_raises_when_sector_term_not_in_known_set() -> None:
    # 일부만 유효한 값이어도(예: 두 개 중 하나만 실재) 전체를 실패로
    # 처리해야 한다(부분 valid만 남겨 통과시키지 않음).
    bad_json = _valid_json(sector_terms=["반도체와반도체장비", "존재하지않는업종"])
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(FilterIntentError):
        await classify(
            llm_service,
            "질문",
            known_sectors=_KNOWN_SECTORS,
            known_sizes=_KNOWN_SIZES,
        )


@pytest.mark.anyio
async def test_classify_raises_when_size_term_not_in_known_set() -> None:
    bad_json = _valid_json(size_terms=["초대형주"])
    llm_service = _llm_with_responses([bad_json, bad_json])

    with pytest.raises(FilterIntentError):
        await classify(
            llm_service,
            "질문",
            known_sectors=_KNOWN_SECTORS,
            known_sizes=_KNOWN_SIZES,
        )


@pytest.mark.anyio
async def test_classify_recovers_from_unknown_sector_on_retry() -> None:
    llm_service = _llm_with_responses(
        [
            _valid_json(sector_terms=["존재하지않는업종"]),
            _valid_json(sector_terms=["제약"]),
        ]
    )

    result = await classify(
        llm_service,
        "질문",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.sector_terms == ["제약"]


@pytest.mark.anyio
async def test_classify_exclude_owned_true_when_llm_says_so() -> None:
    llm_service = _llm_with_responses([_valid_json(exclude_owned=True)])

    result = await classify(
        llm_service,
        "내 포트폴리오에 없는 반도체 후보 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.exclude_owned is True


@pytest.mark.anyio
async def test_classify_raises_after_max_attempts_on_invalid_json() -> None:
    llm_service = _llm_with_responses(["이건 JSON이 아닙니다", "여전히 아닙니다"])

    with pytest.raises(FilterIntentError):
        await classify(
            llm_service,
            "질문",
            known_sectors=_KNOWN_SECTORS,
            known_sizes=_KNOWN_SIZES,
        )


# ============================== UX-01: _match_theme_names (pure function) ==============================
#
# Theme grounding responsibility: 실제 카탈로그 매칭은 항상 이 함수(순수
# 문자열 비교)가 결정하고, LLM은 concept + normalized_concepts만
# 제안한다. 아래는 그 매칭 규칙 자체에 대한 단위 테스트다.


def test_match_theme_names_prefix_match() -> None:
    # Kiwoom 테마 카탈로그의 "카테고리_세부항목" 명명 규칙(예: "반도체_생산")에
    # 대한 prefix 매칭.
    result = _match_theme_names(["반도체"], set(_KNOWN_THEMES))

    assert result == sorted(
        ["반도체_생산", "반도체_설계(fabless)", "반도체_전공정장비"]
    )


def test_match_theme_names_exact_match() -> None:
    # 언더스코어로 세분화되지 않은 단일/flat 테마명은 exact match로 잡힌다.
    result = _match_theme_names(["화장품"], set(_KNOWN_THEMES))

    assert result == ["화장품"]


def test_match_theme_names_no_match_returns_empty() -> None:
    result = _match_theme_names(["AI"], set(_KNOWN_THEMES))

    assert result == []


def test_match_theme_names_falls_back_to_next_candidate_term() -> None:
    # concept 자체("원전")로는 매칭되지 않고, normalized_concepts의
    # "원자력"으로 매칭되는 경우 — 첫 매칭에서 멈추고 그 결과만 반환한다.
    result = _match_theme_names(["원전", "원자력"], set(_KNOWN_THEMES))

    assert result == sorted(["원자력_기자재", "원자력_설계시공"])


def test_match_theme_names_first_matching_term_wins_no_merge() -> None:
    # concept 자체가 이미 매칭되면 이후 candidate term은 시도하지 않는다
    # (서로 다른 term의 결과를 합치지 않음).
    result = _match_theme_names(["반도체", "전자"], set(_KNOWN_THEMES))

    assert result == sorted(
        ["반도체_생산", "반도체_설계(fabless)", "반도체_전공정장비"]
    )


def test_match_theme_names_arbitrary_normalized_concept_is_harmless() -> None:
    # LLM이 완전히 근거 없는 normalized_concepts를 제안해도(hallucination이
    # 아니라 그냥 틀린 추측) 결과는 항상 known_themes의 부분집합이도록
    # 구조적으로 보장된다 — 에러가 아니라 그냥 매칭되지 않을 뿐이다.
    result = _match_theme_names(["존재하지않는개념", "이것도없음"], set(_KNOWN_THEMES))

    assert result == []


# ============================== UX-01: classify() theme_requests ==============================


@pytest.mark.anyio
async def test_classify_grounds_theme_requests_for_semiconductor_via_concept_itself() -> None:
    # "반도체" concept 자체가 이미 실제 카탈로그의 여러 세부 테마에
    # prefix 매칭된다 — LLM은 normalized_concepts 없이 concept만
    # 제안해도 된다.
    llm_service = _llm_with_responses(
        [_valid_json(theme_requests=[{"concept": "반도체", "normalized_concepts": []}])]
    )

    result = await classify(
        llm_service,
        "반도체 관련 종목 후보 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
        known_themes=_KNOWN_THEMES,
    )

    assert len(result.theme_requests) == 1
    assert result.theme_requests[0].concept == "반도체"
    assert result.theme_requests[0].matched_themes == sorted(
        ["반도체_생산", "반도체_설계(fabless)", "반도체_전공정장비"]
    )


@pytest.mark.anyio
async def test_classify_normalizes_colloquial_concept_to_actual_theme_names() -> None:
    # "원전"이라는 사용자 표현 자체로는 카탈로그에 매칭되지 않고, LLM이
    # 제안한 normalized_concepts("원자력")를 통해 실제 카탈로그의
    # "원자력_*" 테마로 대응하는 정상화(normalization) 케이스. 최종
    # matched_themes는 LLM이 아니라 Python의 결정론적 매칭 결과다.
    llm_service = _llm_with_responses(
        [
            _valid_json(
                theme_requests=[
                    {"concept": "원전", "normalized_concepts": ["원자력"]}
                ]
            )
        ]
    )

    result = await classify(
        llm_service,
        "원전 관련주 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
        known_themes=_KNOWN_THEMES,
    )

    assert result.theme_requests[0].concept == "원전"
    assert result.theme_requests[0].matched_themes == sorted(
        ["원자력_기자재", "원자력_설계시공"]
    )


@pytest.mark.anyio
async def test_classify_allows_unsupported_concept_with_empty_matched_themes() -> None:
    # "AI"처럼 카탈로그에 대응하는 테마가 전혀 없는 concept은 grounding
    # 실패가 아니다 — classify() 자체는 정상적으로 성공하고
    # matched_themes만 빈 배열이 된다. "필수 개념인데 매칭이 없다"는
    # 판단은 DiscoveryOrchestrator의 몫이다.
    llm_service = _llm_with_responses(
        [_valid_json(theme_requests=[{"concept": "AI", "normalized_concepts": []}])]
    )

    result = await classify(
        llm_service,
        "AI 관련주 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
        known_themes=_KNOWN_THEMES,
    )

    assert len(result.theme_requests) == 1
    assert result.theme_requests[0].concept == "AI"
    assert result.theme_requests[0].matched_themes == []


@pytest.mark.anyio
async def test_classify_ai_stays_unsupported_even_if_llm_suggests_unrelated_normalized_concepts() -> None:
    # 핵심 회귀 방지 테스트: 실제 E2E에서 관측됐던 "AI가 클라우드컴퓨팅/
    # 보안_인터넷 등 실제로 존재하지만 무관한 테마에 과다 매칭되는" 문제.
    # 이제는 LLM이 무엇을 normalized_concepts로 제안하든(설령 그것이
    # 실제 카탈로그와 무관한 추측이어도) Python의 결정론적 매칭이 최종
    # 권한을 가지므로, 존재하지 않는 접두사와 매칭되는 한 결과는 항상
    # 빈 배열이다.
    llm_service = _llm_with_responses(
        [
            _valid_json(
                theme_requests=[
                    {
                        "concept": "AI",
                        "normalized_concepts": ["인공지능", "클라우드", "빅데이터"],
                    }
                ]
            )
        ]
    )

    result = await classify(
        llm_service,
        "AI 관련주 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
        known_themes=_KNOWN_THEMES,
    )

    assert result.theme_requests[0].matched_themes == []


@pytest.mark.anyio
async def test_classify_theme_requests_never_contains_unknown_theme_names() -> None:
    # LLM이 JSON 스키마 자체를 어기고 과거 스키마의 matched_themes 키를
    # 보내거나 임의 값을 넣어도(예: 구버전 프롬프트를 따르는 실수),
    # _RawThemeRequest가 그 키를 무시하므로 최종 matched_themes는 여전히
    # concept/normalized_concepts 기반 매칭 결과만 담긴다 — 존재하지
    # 않는 테마명이 섞여 들어갈 구조적 경로 자체가 없다.
    raw = json.dumps(
        {
            "market": None,
            "sector_terms": [],
            "size_terms": [],
            "theme_requests": [
                {
                    "concept": "반도체",
                    "matched_themes": ["존재하지않는테마"],  # 구버전 스키마 키, 무시됨
                }
            ],
            "exclude_owned": False,
        },
        ensure_ascii=False,
    )
    llm_service = _llm_with_responses([raw])

    result = await classify(
        llm_service,
        "질문",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
        known_themes=_KNOWN_THEMES,
    )

    # normalized_concepts가 없으니 concept("반도체") 자체로 매칭된다 —
    # "존재하지않는테마"는 어디에도 나타나지 않는다.
    assert "존재하지않는테마" not in result.theme_requests[0].matched_themes
    assert result.theme_requests[0].matched_themes == sorted(
        ["반도체_생산", "반도체_설계(fabless)", "반도체_전공정장비"]
    )


@pytest.mark.anyio
async def test_classify_handles_multiple_theme_concepts_independently() -> None:
    # "AI 반도체 관련주"처럼 concept 두 개가 동시에 요청되고, 하나는
    # 지원되지 않는 경우 — 두 항목 모두 그대로 결과에 남아야 orchestrator가
    # 어떤 concept이 unsupported인지 판단할 수 있다(조용히 하나를
    # 누락시키면 안 됨).
    llm_service = _llm_with_responses(
        [
            _valid_json(
                theme_requests=[
                    {"concept": "AI", "normalized_concepts": []},
                    {"concept": "반도체", "normalized_concepts": []},
                ]
            )
        ]
    )

    result = await classify(
        llm_service,
        "AI 반도체 관련주 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
        known_themes=_KNOWN_THEMES,
    )

    assert len(result.theme_requests) == 2
    concepts = {tr.concept: tr.matched_themes for tr in result.theme_requests}
    assert concepts["AI"] == []
    assert concepts["반도체"] == sorted(
        ["반도체_생산", "반도체_설계(fabless)", "반도체_전공정장비"]
    )


@pytest.mark.anyio
async def test_classify_theme_requests_empty_when_not_mentioned() -> None:
    llm_service = _llm_with_responses([_valid_json(sector_terms=["제약"])])

    result = await classify(
        llm_service,
        "제약 종목 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
        known_themes=_KNOWN_THEMES,
    )

    assert result.theme_requests == []


@pytest.mark.anyio
async def test_classify_without_known_themes_argument_still_works() -> None:
    # known_themes를 아예 안 넘기는 기존 호출부(과거 시그니처)와의 호환성
    # — theme_requests를 다루지 않는 한 기존과 동일하게 동작해야 한다.
    llm_service = _llm_with_responses([_valid_json(sector_terms=["제약"])])

    result = await classify(
        llm_service,
        "제약 종목 찾아줘",
        known_sectors=_KNOWN_SECTORS,
        known_sizes=_KNOWN_SIZES,
    )

    assert result.sector_terms == ["제약"]
    assert result.theme_requests == []

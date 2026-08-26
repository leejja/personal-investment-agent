import json
from unittest.mock import AsyncMock

import pytest

from app.agents.stock_research.analysis import (
    DeterministicAnalysisResult,
    DeterministicFact,
)
from app.agents.stock_research.reasoning import (
    ReasoningError,
    generate_reasoning,
)
from app.models.common import AnalysisConfidence, RiskLevel
from app.models.stock import FinancialSnapshot, StockPriceSnapshot
from app.services.llm import LLMResponse, LLMService


def _analysis_result(
    facts: list[DeterministicFact] | None = None,
) -> DeterministicAnalysisResult:
    return DeterministicAnalysisResult(
        price=StockPriceSnapshot(
            symbol="005930",
            name="삼성전자",
            price=281500,
            change_pct=3.87,
            volume=15000000,
            high_250d=374500,
            low_250d=67500,
        ),
        financials=FinancialSnapshot(
            revenue=333605938000000,
            operating_profit=43601051000000,
            net_income=45206805000000,
            total_assets=566942110000000,
            total_liabilities=130621773000000,
            total_equity=436320337000000,
            per=42.89,
            pbr=4.4,
            roe=10.9,
        ),
        facts=facts if facts is not None else [],
        max_confidence=AnalysisConfidence.MEDIUM,
        risk_level=RiskLevel.LOW,
    )


def _valid_llm_json(
    catalysts: list[str] | None = None,
    risks: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "investment_thesis": "안정적인 수익성을 바탕으로 한 valuation 매력",
            "catalysts": catalysts if catalysts is not None else [],
            "risks": risks if risks is not None else [],
            "scenarios": [
                {
                    "scenario": "base",
                    "thesis": "현재 추세가 유지되는 시나리오",
                    "target_price": 300000,
                    "probability": 0.5,
                }
            ],
            "suggested_confidence": "medium",
        },
        ensure_ascii=False,
    )


def _llm_service_returning(*contents: str) -> LLMService:
    service = LLMService(api_key="test-key", model="test-model")
    service.complete = AsyncMock(
        side_effect=[
            LLMResponse(content=content, model="test-model", finish_reason="stop")
            for content in contents
        ]
    )
    return service


@pytest.mark.anyio
async def test_generate_reasoning_returns_parsed_result() -> None:
    llm_service = _llm_service_returning(_valid_llm_json())
    analysis = _analysis_result(
        facts=[DeterministicFact(description="테스트 사실", source="Kiwoom")]
    )

    result = await generate_reasoning(llm_service, analysis)

    assert result.investment_thesis == "안정적인 수익성을 바탕으로 한 valuation 매력"
    assert result.catalysts == []
    assert result.risks == []
    assert len(result.scenarios) == 1
    # v1에는 목표주가 산정 근거가 없으므로 LLM이 값을 보냈어도 제거된다.
    assert result.scenarios[0].target_price is None
    assert result.scenarios[0].probability is None
    assert result.suggested_confidence.value == "medium"

    llm_service.complete.assert_awaited_once()


@pytest.mark.anyio
async def test_generate_reasoning_only_uses_analysis_data_in_prompt() -> None:
    llm_service = _llm_service_returning(_valid_llm_json())
    analysis = _analysis_result(
        facts=[DeterministicFact(description="부채비율은 약 30.0%", source="OpenDART")]
    )

    await generate_reasoning(llm_service, analysis)

    _, kwargs = llm_service.complete.call_args
    user_message = kwargs["messages"][1]["content"]

    assert "삼성전자" in user_message
    assert "부채비율은 약 30.0%" in user_message
    assert "출처: OpenDART" in user_message
    # 외부 정보(뉴스/공시 원문 등)를 프롬프트에 추가하지 않는다.
    assert "뉴스" not in user_message


@pytest.mark.anyio
async def test_generate_reasoning_sends_json_object_response_format() -> None:
    llm_service = _llm_service_returning(_valid_llm_json())
    analysis = _analysis_result()

    await generate_reasoning(llm_service, analysis)

    _, kwargs = llm_service.complete.call_args
    assert kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.anyio
async def test_generate_reasoning_allows_empty_catalysts_and_risks() -> None:
    llm_service = _llm_service_returning(_valid_llm_json(catalysts=[], risks=[]))
    analysis = _analysis_result()

    result = await generate_reasoning(llm_service, analysis)

    assert result.catalysts == []
    assert result.risks == []


@pytest.mark.anyio
async def test_generate_reasoning_keeps_non_empty_catalysts_and_risks() -> None:
    llm_service = _llm_service_returning(
        _valid_llm_json(
            catalysts=["부채비율은 약 30.0%로 재무 부담이 낮은 편"],
            risks=["52주 고점 대비 낮은 위치"],
        )
    )
    analysis = _analysis_result()

    result = await generate_reasoning(llm_service, analysis)

    assert result.catalysts == ["부채비율은 약 30.0%로 재무 부담이 낮은 편"]
    assert result.risks == ["52주 고점 대비 낮은 위치"]


@pytest.mark.anyio
async def test_generate_reasoning_retries_once_on_invalid_json() -> None:
    llm_service = _llm_service_returning(
        "이건 JSON이 아닙니다",
        _valid_llm_json(),
    )
    analysis = _analysis_result()

    result = await generate_reasoning(llm_service, analysis)

    assert result.investment_thesis
    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_generate_reasoning_retries_once_on_schema_violation() -> None:
    invalid_schema = json.dumps({"investment_thesis": ""})  # min_length=1 위반

    llm_service = _llm_service_returning(invalid_schema, _valid_llm_json())
    analysis = _analysis_result()

    result = await generate_reasoning(llm_service, analysis)

    assert result.investment_thesis
    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_generate_reasoning_raises_after_exhausting_attempts() -> None:
    llm_service = _llm_service_returning(
        "이건 JSON이 아닙니다",
        "여전히 JSON이 아닙니다",
    )
    analysis = _analysis_result()

    with pytest.raises(ReasoningError):
        await generate_reasoning(llm_service, analysis, max_attempts=2)

    assert llm_service.complete.await_count == 2


@pytest.mark.anyio
async def test_generate_reasoning_strips_target_price_and_probability() -> None:
    # LLM이 프롬프트 지시를 어기고 임의의 숫자를 보내더라도
    # generate_reasoning은 항상 None으로 되돌린다.
    llm_service = _llm_service_returning(
        json.dumps(
            {
                "investment_thesis": "임의의 밸류에이션 근거 없이 작성된 thesis",
                "catalysts": [],
                "risks": [],
                "scenarios": [
                    {
                        "scenario": "bull",
                        "thesis": "낙관적 시나리오",
                        "target_price": 999999,
                        "probability": 0.9,
                    },
                    {
                        "scenario": "bear",
                        "thesis": "비관적 시나리오",
                        "target_price": 1,
                        "probability": 0.1,
                    },
                ],
                "suggested_confidence": "high",
            },
            ensure_ascii=False,
        )
    )
    analysis = _analysis_result()

    result = await generate_reasoning(llm_service, analysis)

    assert len(result.scenarios) == 2
    for scenario in result.scenarios:
        assert scenario.target_price is None
        assert scenario.probability is None
        assert scenario.thesis  # 서술 자체는 그대로 유지된다.


@pytest.mark.anyio
async def test_generate_reasoning_allows_empty_scenarios() -> None:
    llm_content = json.dumps(
        {
            "investment_thesis": "현재 데이터만으로는 뚜렷한 시나리오를 구분하기 어려움",
            "catalysts": [],
            "risks": [],
            "scenarios": [],
            "suggested_confidence": "low",
        },
        ensure_ascii=False,
    )
    llm_service = _llm_service_returning(llm_content)
    analysis = _analysis_result()

    result = await generate_reasoning(llm_service, analysis)

    assert result.scenarios == []
    # 빈 시나리오는 검증 실패가 아니므로 재시도가 발생하지 않는다.
    llm_service.complete.assert_awaited_once()


@pytest.mark.anyio
async def test_prompt_instructs_no_evaluation_without_benchmark() -> None:
    llm_service = _llm_service_returning(_valid_llm_json())
    analysis = _analysis_result()

    await generate_reasoning(llm_service, analysis)

    _, kwargs = llm_service.complete.call_args
    system_message = kwargs["messages"][0]["content"]

    assert "비교 기준" in system_message
    assert "고평가" in system_message
    assert "저평가" in system_message


@pytest.mark.anyio
async def test_prompt_instructs_null_target_price_and_probability() -> None:
    llm_service = _llm_service_returning(_valid_llm_json())
    analysis = _analysis_result()

    await generate_reasoning(llm_service, analysis)

    _, kwargs = llm_service.complete.call_args
    system_message = kwargs["messages"][0]["content"]

    assert "target_price" in system_message
    assert "probability" in system_message
    assert "null" in system_message


@pytest.mark.anyio
async def test_prompt_allows_empty_scenarios() -> None:
    llm_service = _llm_service_returning(_valid_llm_json())
    analysis = _analysis_result()

    await generate_reasoning(llm_service, analysis)

    _, kwargs = llm_service.complete.call_args
    system_message = kwargs["messages"][0]["content"]

    assert "빈 배열" in system_message


@pytest.mark.anyio
async def test_prompt_defines_catalyst_narrowly() -> None:
    llm_service = _llm_service_returning(_valid_llm_json())
    analysis = _analysis_result()

    await generate_reasoning(llm_service, analysis)

    _, kwargs = llm_service.complete.call_args
    system_message = kwargs["messages"][0]["content"]

    assert "향후 주가" in system_message
    assert "이벤트" in system_message

    # 명시적으로 catalyst가 아니라고 규정한 항목들이 프롬프트에 있어야 한다.
    excluded_examples = [
        "매출 규모",
        "순이익 규모",
        "자산/자본 규모",
        "PER/PBR/ROE",
        "부채비율",
        "현재 가격 위치",
    ]
    for example in excluded_examples:
        assert example in system_message


@pytest.mark.anyio
async def test_generate_reasoning_accepts_empty_catalysts_with_only_magnitude_facts() -> (
    None
):
    # 매출/순이익/자산 등 정적인 규모 facts만 있고 이벤트성 근거가
    # 전혀 없는 상황을 가정한다. 이 경우 catalysts=[]가 정상 출력이다.
    llm_content = json.dumps(
        {
            "investment_thesis": "제공된 재무 규모 사실에 근거한 요약",
            "catalysts": [],
            "risks": ["PER 39.84배 (비교 기준 없음)"],
            "scenarios": [],
            "suggested_confidence": "low",
        },
        ensure_ascii=False,
    )
    llm_service = _llm_service_returning(llm_content)
    analysis = _analysis_result(
        facts=[
            DeterministicFact(description="매출액는 333,605,938,000,000원", source="OpenDART"),
            DeterministicFact(description="순이익는 45,206,805,000,000원", source="OpenDART"),
            DeterministicFact(description="자산총계는 566,942,110,000,000원", source="OpenDART"),
            DeterministicFact(description="PER는 39.84배", source="Kiwoom"),
        ]
    )

    result = await generate_reasoning(llm_service, analysis)

    assert result.catalysts == []
    llm_service.complete.assert_awaited_once()

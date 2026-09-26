"""§33.1 Option A: `NormalizedResearchData`의 canonical builder.

`app/agents/stock_research/analysis.py`의 `analyze()`가 만드는
`DeterministicAnalysisResult`(vendor 데이터의 deterministic normalization
결과, LLM 호출 **이전** 단계)에서만 `NormalizedResearchData`를 조립한다.

이 모듈이 하지 않는 것:
- `StockAnalysis`를 입력으로 받지 않는다(canonical path가 아님, §33.1).
- LLM output(투자 논지/촉매/리스크/시나리오)을 입력으로 받지 않는다.
- vendor API를 호출하지 않는다 -- `DeterministicAnalysisResult`는 이미
  호출자가 만들어 넘겨준다.
- attractiveness 판단/normalization formula가 없다 -- deterministic
  factual mapping만 한다(존재하는 값을 그대로 옮기고, 그 값의 availability
  status만 결정한다).
"""

from datetime import datetime

from app.agents.stock_research.analysis import DeterministicAnalysisResult
from app.models.recommendation import AvailabilityStatus
from app.models.research_context import (
    BenchmarkReference,
    FinancialFacts,
    FlowFacts,
    ForwardFacts,
    NormalizedResearchData,
    PriceHistoryReference,
    ResearchIdentity,
    ValuationFacts,
)


def build_normalized_research_data(
    result: DeterministicAnalysisResult,
    *,
    as_of: datetime,
) -> NormalizedResearchData:
    """`DeterministicAnalysisResult` -> `NormalizedResearchData`.

    Fundamental facts(financial_facts)만 실제로 채운다 -- Valuation(market
    cap 등)/Flow/OHLCV historical/Benchmark/Forward는 이 pipeline에
    아직 연결된 source가 없으므로(dev-log §26/§28의 Implementation Gap,
    §29 V1 Feature Set) 전부 `AvailabilityStatus.UNAVAILABLE`로 정직하게
    표시한다 -- 값을 추정하거나 0/None 이상의 의미를 부여하지 않는다.

    `financial_facts.status`는 `AvailabilityStatus.AVAILABLE`로 고정한다
    -- `DeterministicAnalysisResult`가 이 함수에 전달됐다는 것 자체가
    `analyze()`가 이미 성공했다는 뜻이기 때문이다(OpenDART/Kiwoom 호출
    자체가 실패했다면 `analyze()` 호출 전 단계에서 exception이 전파되고
    이 함수까지 도달하지 않는다 -- root-level 실패는 exception, 이 함수는
    그 이후의 성공 경로만 다룬다, §32.18). 개별 필드(예: `roe`)가 비어있는
    것은 이 bundle-level status와 별개로 각 feature evaluator가
    개별적으로 판단한다.
    """
    # Evidence Identity Preservation: evidence 없는 evaluation fallback은 없다. 값별 evidence
    # 완결성은 FinancialFacts가 생성 시 스스로 검사한다(downstream에서 재구성하지 않는다).
    if result.evidence is None:
        raise ValueError(
            "DeterministicAnalysisResult.evidence is required for evaluation "
            "(analyze(..., evidence=...)); evidence identity was not provided"
        )

    financial_facts = FinancialFacts(
        status=AvailabilityStatus.AVAILABLE,
        current=result.financials,
        history=result.financial_history,
        features=result.financial_features,
        evidence=result.evidence,
    )

    return NormalizedResearchData(
        identity=ResearchIdentity(
            symbol=result.price.symbol,
            name=result.price.name,
        ),
        market_snapshot=result.price,
        financial_facts=financial_facts,
        valuation_facts=ValuationFacts(status=AvailabilityStatus.UNAVAILABLE),
        flow_facts=FlowFacts(status=AvailabilityStatus.UNAVAILABLE),
        price_history=PriceHistoryReference(status=AvailabilityStatus.UNAVAILABLE),
        benchmark=BenchmarkReference(status=AvailabilityStatus.UNAVAILABLE),
        forward_facts=ForwardFacts(),
        as_of=as_of,
    )

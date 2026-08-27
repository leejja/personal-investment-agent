from enum import Enum

from pydantic import BaseModel, Field


class MarketFilter(str, Enum):
    KOSPI = "kospi"
    KOSDAQ = "kosdaq"


class Candidate(BaseModel):
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)
    market: MarketFilter
    sector: str

    # 어떤 필터 조건 때문에 이 종목이 후보에 포함됐는지 추적하기 위한
    # 최소 구조. 점수/매력도 값은 절대 담지 않는다 — Candidate Discovery는
    # "분석 대상으로 올릴 것인가"만 판단하고 투자 판단을 하지 않는다.
    matched_filters: dict[str, str] = Field(default_factory=dict)

"""RE-05 Evidence Identity Preservation — provider-neutral evidence identity.

`docs/ARCHITECTURE.md` §7.10(Calibration Evidence Identity & Persistence Contract)의
identity-only 구현 slice다(§7.3 Post-§7.10 selection). 이 모듈은 값이 어떤 evidence를
나타내는지, 언제 조회됐는지, source-reported인지 derived인지를 downstream이 truthful하게
식별할 수 있게 하는 **식별 정보만** 담는다.

두 개념을 분리한다(§7.10 E3/E6):

- `EvidenceItemIdentity` — semantic identity. 같은 filing / measure / observation /
  source term을 다른 시각에 조회해도 같은 identity다. `retrieved_at`은 equality/hash에
  참여하지 않는다.
- `EvidenceReference` — 이번 runtime에서 사용한 evidence에 대한 in-memory reference.
  identity + retrieval fact(`retrieved_at`) + derived 값의 input reference를 담는다.
  저장된 record / persisted object / captured evidence / reproducible snapshot이 아니다.

이 모듈이 하지 않는 것: vendor model import, 값(content) 보관, persistent ID / content
hash / snapshot ID, evidence capture, reproducibility 상태 표현(§7.10 아래 OPEN),
`available_at` / `published_at` 도출, revision order / original-correction 관계 추론.
`version_anchor=None`은 "provider/interface가 version anchor를 제공하지 않았다"만 뜻한다
— recoverable / not recoverable / latest / original / corrected를 뜻하지 않는다.

derived lineage는 derivation이 현재 일어나는 위치에서 기록되지만, 그 위치가 canonical
Derived Feature Value Ownership을 뜻하지 않는다(ownership OPEN).
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

# provider-neutral measure key — evaluator 경로(first slice)와 derived input에 필요한 것만.
MEASURE_REVENUE = "revenue"
MEASURE_OPERATING_PROFIT = "operating_profit"
MEASURE_NET_INCOME = "net_income"
MEASURE_TOTAL_ASSETS = "total_assets"
MEASURE_TOTAL_LIABILITIES = "total_liabilities"
MEASURE_TOTAL_EQUITY = "total_equity"
MEASURE_ROE = "roe"
MEASURE_PER = "per"
MEASURE_PBR = "pbr"
MEASURE_OPERATING_MARGIN = "operating_margin"
MEASURE_NET_MARGIN = "net_margin"
MEASURE_DEBT_RATIO = "debt_ratio"


class EvidenceOrigin(str, Enum):
    """이 시스템 관점의 origin. provider가 내부적으로 계산한 비율(예: Kiwoom PER)도
    이 시스템이 그 derivation을 모르면 SOURCE_REPORTED다."""

    SOURCE_REPORTED = "source_reported"
    DERIVED = "derived"


class EvidenceSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    interface: str = Field(min_length=1)


class ObservationIdentity(BaseModel):
    """source가 실제로 제공한 observation 식별 정보. 전부 source 표기 그대로 보존하며
    파싱/정규화하지 않는다."""

    model_config = ConfigDict(frozen=True)

    period_notation: str | None = None
    period_label: str | None = None
    source_term: str | None = None
    report_type: str | None = None
    reporting_basis: str | None = None
    statement: str | None = None


class DerivationLineage(BaseModel):
    """derived 값의 deterministic formula 식별 + required input의 semantic identity.
    input의 retrieval fact는 여기 들어가지 않는다(`EvidenceReference.input_references`)."""

    model_config = ConfigDict(frozen=True)

    formula_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    inputs: tuple["EvidenceItemIdentity", ...] = Field(min_length=1)


class EvidenceItemIdentity(BaseModel):
    """semantic evidence identity. frozen/hashable — equality는 아래 필드로만 결정된다."""

    model_config = ConfigDict(frozen=True)

    entity: str = Field(min_length=1)
    measure: str = Field(min_length=1)
    origin: EvidenceOrigin
    source: EvidenceSource | None = None
    observation: ObservationIdentity | None = None
    version_anchor: str | None = None
    derivation: DerivationLineage | None = None

    @model_validator(mode="after")
    def _origin_invariant(self) -> "EvidenceItemIdentity":
        if self.origin == EvidenceOrigin.SOURCE_REPORTED:
            if self.source is None:
                raise ValueError("SOURCE_REPORTED evidence requires a source")
            if self.derivation is not None:
                raise ValueError("SOURCE_REPORTED evidence must not carry a derivation")
        else:
            if self.derivation is None:
                raise ValueError("DERIVED evidence requires a derivation lineage")
            if self.source is not None:
                raise ValueError("DERIVED evidence must not carry a provider source")
        return self


DerivationLineage.model_rebuild()


class EvidenceReference(BaseModel):
    """이번 runtime에서 사용한 evidence에 대한 reference. `retrieved_at`은 runtime
    retrieval 시각이다 — published_at / available_at / provider event time /
    historical availability가 아니다. DERIVED는 자체 retrieval event가 없다."""

    model_config = ConfigDict(frozen=True)

    identity: EvidenceItemIdentity
    retrieved_at: datetime | None = None
    input_references: tuple["EvidenceReference", ...] = ()

    @model_validator(mode="after")
    def _retrieval_invariant(self) -> "EvidenceReference":
        if self.identity.origin == EvidenceOrigin.SOURCE_REPORTED:
            if self.retrieved_at is None:
                raise ValueError("SOURCE_REPORTED evidence requires retrieved_at")
            if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
                raise ValueError("retrieved_at must be timezone-aware")
            if self.input_references:
                raise ValueError("SOURCE_REPORTED evidence must not carry input references")
            return self

        if self.retrieved_at is not None:
            raise ValueError("DERIVED evidence has no retrieval event; retrieved_at must be None")
        derivation = self.identity.derivation
        assert derivation is not None  # EvidenceItemIdentity가 보장
        if not self.input_references:
            raise ValueError("DERIVED evidence requires input references")
        if tuple(ref.identity for ref in self.input_references) != derivation.inputs:
            raise ValueError(
                "DERIVED input references must match the derivation's semantic input identities"
            )
        return self


EvidenceReference.model_rebuild()


class FinancialFactsEvidence(BaseModel):
    """first slice의 6개 evaluator 경로에 필요한 evidence reference.

    `roe` / `per` / `pbr`는 `FinancialFacts.current`의 값, `operating_margin` /
    `net_margin` / `debt_ratio`는 `FinancialFacts.features.annual[-1]`의 값에 대응한다.
    "값이 있으면 reference가 있어야 한다"는 규칙은 값과 함께 검사된다
    (`build_normalized_research_data`). history / YoY / trends는 이 slice 범위 밖이다.
    """

    model_config = ConfigDict(frozen=True)

    roe: EvidenceReference | None = None
    per: EvidenceReference | None = None
    pbr: EvidenceReference | None = None
    operating_margin: EvidenceReference | None = None
    net_margin: EvidenceReference | None = None
    debt_ratio: EvidenceReference | None = None

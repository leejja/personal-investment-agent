from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.models.annual_evidence import (
    AnnualEvidenceOutcome,
    AnnualSelectionFailure,
    AnnualSelectionStatus,
)
from app.models.evidence import (
    MEASURE_NET_INCOME,
    MEASURE_OPERATING_PROFIT,
    MEASURE_REVENUE,
    MEASURE_TOTAL_ASSETS,
    MEASURE_TOTAL_EQUITY,
    MEASURE_TOTAL_LIABILITIES,
    EvidenceItemIdentity,
    EvidenceOrigin,
    EvidenceReference,
    EvidenceSource,
    ObservationIdentity,
)
from app.services.opendart import (
    ANNUAL_REPORT_CODE,
    OpenDartAnnualRetrieval,
    OpenDartFinancialAccount,
    OpenDartService,
)

# OpenDART 공식 문서(단일회사 주요계정): bsns_year "사업연도(4자리) ※ 2015년 이후 부터 정보제공".
# provider 사실이며, 후보 탐색의 하한이다.
OPENDART_FINANCIAL_DATA_LOWER_BOUND_YEAR = 2015

_OPENDART_SOURCE = EvidenceSource(provider="OpenDART", interface="fnlttSinglAcnt")

# KeyFinancials 필드 / provider-neutral measure key / 매칭할 OpenDART 계정명.
# _extract_key_financials와 _extract_measure_evidence가 같은 표를 써서, evidence가
# 항상 값이 실제로 선택된 row와 같은 row에서 만들어지게 한다.
_KEY_MEASURES: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("revenue", MEASURE_REVENUE, frozenset({"매출액"})),
    ("operating_profit", MEASURE_OPERATING_PROFIT, frozenset({"영업이익"})),
    ("net_income", MEASURE_NET_INCOME, frozenset({"당기순이익", "당기순이익(손실)"})),
    ("total_assets", MEASURE_TOTAL_ASSETS, frozenset({"자산총계"})),
    ("total_liabilities", MEASURE_TOTAL_LIABILITIES, frozenset({"부채총계"})),
    ("total_equity", MEASURE_TOTAL_EQUITY, frozenset({"자본총계"})),
)

_TERM_AMOUNT_ATTR = {
    "current": "current_term_amount",
    "previous": "previous_term_amount",
    "before_previous": "before_previous_term_amount",
}
_TERM_DATE_ATTR = {
    "current": "current_term_date",
    "previous": "previous_term_date",
    "before_previous": "before_previous_term_date",
}


class CompanyFinancials(BaseModel):
    stock_code: str
    corp_code: str
    business_year: str
    report_code: str
    accounts: list[OpenDartFinancialAccount]


class KeyFinancials(BaseModel):
    stock_code: str
    corp_code: str
    business_year: str
    report_code: str
    fs_div: str
    revenue: int | None
    operating_profit: int | None
    net_income: int | None
    total_assets: int | None
    total_liabilities: int | None
    total_equity: int | None


class KeyFinancialsWithEvidence(BaseModel):
    """internal carrier(MCP tool이 반환하지 않는다). `evidence`는 값이 None이 아닌
    measure마다 그 값을 실제로 제공한 row에서 만든 reference다(measure key →
    reference). 비교 컬럼(previous / before_previous)은 나중 filing의 `rcept_no`와
    `source_term`을 그대로 가진다 — 해당 연도 original filing과 구별된다."""

    key_financials: KeyFinancials
    evidence: dict[str, EvidenceReference]


class AnnualCandidate(BaseModel):
    """연간 보고서 후보(요청 identity). 후보 순서는 탐색 순서일 뿐 latest / corrected /
    original / final / best filing을 뜻하지 않는다. 순서는 `AnnualEvidenceSelection.candidates`의
    tuple 위치가 표현한다(별도 ordinal 없음)."""

    model_config = ConfigDict(frozen=True)

    business_year: str
    report_code: str = Field(pattern=f"^{ANNUAL_REPORT_CODE}$")


class AnnualSelectionTraceEntry(BaseModel):
    """시도한 후보 하나와 그 분류된 조회 결과(provider status / message, failure reason /
    detail, EVIDENCE_RETURNED의 accounts / retrieved_at)를 그대로 담는다."""

    model_config = ConfigDict(frozen=True)

    candidate: AnnualCandidate
    retrieval: OpenDartAnnualRetrieval

    @model_validator(mode="after")
    def _retrieval_matches_candidate(self) -> "AnnualSelectionTraceEntry":
        if (
            self.retrieval.business_year != self.candidate.business_year
            or self.retrieval.report_code != self.candidate.report_code
        ):
            raise ValueError("trace retrieval does not match its candidate")
        return self


class AnnualEvidenceSelection(BaseModel):
    """positive-only fallback selection의 결과(Implementation Contract rev.1).

    탐색 범위(`candidate_basis_instant` · `lookback_years` · `candidates`)와 시도한 후보의
    `trace`를 기록한다. `NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES`는 기록된 후보 집합
    안의 결과일 뿐 전역 부재가 아니다. `evaluation_as_of`를 만들거나 정의하지 않는다(§7.11.3)."""

    model_config = ConfigDict(frozen=True)

    corp_code: str
    candidate_basis_instant: datetime
    lookback_years: StrictInt = Field(ge=1)
    candidates: tuple[AnnualCandidate, ...]
    trace: tuple[AnnualSelectionTraceEntry, ...]
    status: AnnualSelectionStatus
    failure: AnnualSelectionFailure | None = None

    @model_validator(mode="after")
    def _selection_invariant(self) -> "AnnualEvidenceSelection":
        if self.candidates != _annual_candidates(
            self.candidate_basis_instant, lookback_years=self.lookback_years
        ):
            raise ValueError("candidates do not match the recorded search universe")

        if len(self.trace) > len(self.candidates) or any(
            entry.candidate != candidate
            for entry, candidate in zip(self.trace, self.candidates, strict=False)
        ):
            raise ValueError("trace must follow the candidate order, each candidate at most once")

        if any(entry.retrieval.corp_code != self.corp_code for entry in self.trace):
            raise ValueError("trace retrieval corp_code does not match the selection")

        outcomes = [entry.retrieval.outcome for entry in self.trace]
        # fallback은 positive UNAVAILABLE 다음에만 — 마지막을 제외한 entry는 모두 UNAVAILABLE이다.
        if any(
            outcome != AnnualEvidenceOutcome.REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE
            for outcome in outcomes[:-1]
        ):
            raise ValueError("only a positive unavailability may be followed by another candidate")

        last = outcomes[-1] if outcomes else None

        if self.status == AnnualSelectionStatus.SELECTED:
            valid = last == AnnualEvidenceOutcome.EVIDENCE_RETURNED and self.failure is None
        elif self.status == AnnualSelectionStatus.FAILED:
            if self.failure == AnnualSelectionFailure.NO_CANDIDATES:
                valid = not self.candidates and not self.trace
            else:
                valid = (
                    self.failure == AnnualSelectionFailure.CANDIDATE_FAILURE
                    and last == AnnualEvidenceOutcome.FAILURE
                )
        else:
            valid = (
                bool(self.candidates)
                and len(self.trace) == len(self.candidates)
                and last == AnnualEvidenceOutcome.REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE
                and self.failure is None
            )

        if not valid:
            raise ValueError(f"trace is inconsistent with selection status {self.status.value}")
        return self

    @property
    def selected(self) -> OpenDartAnnualRetrieval | None:
        """SELECTED일 때 선택된 retrieval(= 마지막 trace entry). 그 외에는 None."""
        if self.status != AnnualSelectionStatus.SELECTED:
            return None
        return self.trace[-1].retrieval


def _annual_candidates(
    candidate_basis_instant: datetime,
    *,
    lookback_years: int,
) -> tuple[AnnualCandidate, ...]:
    """Bounded descending bsns_year probe(Implementation Contract rev.1).

    basis 연도(`candidate_basis_instant`의 UTC 연도)부터 내림차순으로 최대 `lookback_years`개,
    provider 하한(2015) 미만은 제외한다. 현재 시각을 읽지 않고 암묵적 "전년도" 기본값이 없다.
    `lookback_years`는 호출자가 정한다 — 기본값이 없고 값은 향후 V0 policy 소유다(OpenDART
    의미 아님, 충분성 / 탐색 완전성 보증 아님).
    """
    if not isinstance(candidate_basis_instant, datetime):
        raise TypeError("candidate_basis_instant must be a datetime")
    if candidate_basis_instant.utcoffset() is None:
        raise ValueError("candidate_basis_instant must be timezone-aware")
    # bool은 int의 subclass이므로 type으로 정확히 거부한다.
    if type(lookback_years) is not int:
        raise TypeError("lookback_years must be an int")
    if lookback_years < 1:
        raise ValueError("lookback_years must be >= 1")

    basis_year = candidate_basis_instant.astimezone(UTC).year
    lowest_year = max(
        basis_year - lookback_years + 1,
        OPENDART_FINANCIAL_DATA_LOWER_BOUND_YEAR,
    )

    return tuple(
        AnnualCandidate(business_year=str(year), report_code=ANNUAL_REPORT_CODE)
        for year in range(basis_year, lowest_year - 1, -1)
    )


class OpenDartTools:
    def __init__(self, service: OpenDartService) -> None:
        self.service = service

    async def find_stock_code_by_name(self, company_name: str) -> str | None:
        # Supervisor가 사용자 발화에 등장한 회사명(예: "삼성전자")을 종목코드로
        # 정확히 일치하는 경우에만 해석하기 위한 조회다. LLM이 종목코드를
        # 스스로 만들어내지 않도록, 코드 매핑은 항상 이 결정론적 조회를
        # 거친다. 정확히 하나로 특정되지 않으면(없거나 모호하면) None을
        # 반환해 호출자가 추측 없이 실패 처리하게 한다.
        corporations = await self.service.get_corporations()

        matches = [
            corporation
            for corporation in corporations
            if corporation.stock_code is not None
            and corporation.corp_name == company_name
        ]

        if len(matches) != 1:
            return None

        return matches[0].stock_code

    async def get_company_financials(
        self,
        stock_code: str,
        business_year: str,
        report_code: str = "11011",
    ) -> CompanyFinancials:
        corp_code = await self.service.resolve_corp_code(stock_code)

        accounts = await self.service.get_financial_accounts(
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
        )

        return CompanyFinancials(
            stock_code=stock_code,
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
            accounts=accounts,
        )

    async def get_key_financials(
        self,
        stock_code: str,
        business_year: str,
        report_code: str = "11011",
    ) -> KeyFinancials:
        financials = await self.get_company_financials(
            stock_code=stock_code,
            business_year=business_year,
            report_code=report_code,
        )

        accounts = financials.accounts
        fs_div = self._select_fs_div(accounts)
        selected_accounts = [
            account for account in accounts if account.fs_div == fs_div
        ]

        return self._extract_key_financials(
            selected_accounts,
            stock_code=financials.stock_code,
            corp_code=financials.corp_code,
            business_year=financials.business_year,
            report_code=financials.report_code,
            fs_div=fs_div,
            term="current",
        )

    async def get_key_financials_history(
        self,
        stock_code: str,
        business_year: str,
        report_code: str = "11011",
    ) -> list[KeyFinancials]:
        # 항상 최소 1건(당기)은 포함한다 — get_key_financials()와 동일한
        # 보장. OpenDART fnlttSinglAcnt.json은 사업보고서(11011)일 때만
        # 전기(frmtrm)/전전기(bfefrmtrm) 컬럼까지 함께 내려주는 것으로 실제
        # API 호출로 확인했다. 분기/반기 보고서와 섞여 잘못된 추세로
        # 해석되지 않도록, 사업보고서가 아니면 당기 1건만 반환한다.
        #
        # 이 메서드는 get_key_financials()를 호출하지 않고 get_company_financials()를
        # 직접 한 번만 호출한다 — 두 메서드를 함께 쓸 때 OpenDART API를 두 번
        # 부르지 않기 위함이다(추가 API 호출 없음).
        financials = await self.get_company_financials(
            stock_code=stock_code,
            business_year=business_year,
            report_code=report_code,
        )

        return [
            key_financials
            for key_financials, _ in self._build_history(
                financials, business_year=business_year, report_code=report_code
            )
        ]

    async def get_key_financials_history_with_evidence(
        self,
        stock_code: str,
        business_year: str,
        report_code: str = "11011",
    ) -> list[KeyFinancialsWithEvidence]:
        """`get_key_financials_history()`와 같은 값/순서에, 각 measure의 evidence
        reference를 함께 반환하는 internal 경로. 공개 tool 출력은 바꾸지 않는다."""
        corp_code = await self.service.resolve_corp_code(stock_code)
        retrieval = await self.service.fetch_financial_accounts(
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
        )
        financials = CompanyFinancials(
            stock_code=stock_code,
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
            accounts=retrieval.accounts,
        )

        return [
            KeyFinancialsWithEvidence(
                key_financials=key_financials,
                evidence=self._extract_measure_evidence(
                    selected_accounts,
                    stock_code=stock_code,
                    period_label=key_financials.business_year,
                    term=term,
                    retrieved_at=retrieval.retrieved_at,
                ),
            )
            for key_financials, (selected_accounts, term) in self._build_history(
                financials, business_year=business_year, report_code=report_code
            )
        ]

    async def select_annual_evidence(
        self,
        corp_code: str,
        *,
        candidate_basis_instant: datetime,
        lookback_years: int,
    ) -> AnnualEvidenceSelection:
        """사업보고서 evidence를 positive-only fallback으로 선택한다(Implementation Contract rev.1).

        후보를 순서대로 조회해 EVIDENCE_RETURNED면 선택하고, FAILURE면 fallback 없이 중단하며,
        REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE일 때만 다음 후보로 간다. 보고서가 반환됐지만
        feature 계정이 없는 것은 EVIDENCE_RETURNED다(feature 단위 문제, fallback 사유 아님).
        `corp_code`는 이미 해석된 값을 받는다(종목 해석은 이 selection 범위 밖).
        """
        candidates = _annual_candidates(candidate_basis_instant, lookback_years=lookback_years)

        def selection(
            trace: list[AnnualSelectionTraceEntry],
            status: AnnualSelectionStatus,
            failure: AnnualSelectionFailure | None = None,
        ) -> AnnualEvidenceSelection:
            return AnnualEvidenceSelection(
                corp_code=corp_code,
                candidate_basis_instant=candidate_basis_instant.astimezone(UTC),
                lookback_years=lookback_years,
                candidates=candidates,
                trace=tuple(trace),
                status=status,
                failure=failure,
            )

        if not candidates:
            return selection([], AnnualSelectionStatus.FAILED, AnnualSelectionFailure.NO_CANDIDATES)

        trace: list[AnnualSelectionTraceEntry] = []

        for candidate in candidates:
            retrieval = await self.service.retrieve_annual_accounts(
                corp_code=corp_code,
                business_year=candidate.business_year,
            )
            trace.append(AnnualSelectionTraceEntry(candidate=candidate, retrieval=retrieval))

            if retrieval.outcome == AnnualEvidenceOutcome.EVIDENCE_RETURNED:
                return selection(trace, AnnualSelectionStatus.SELECTED)

            if retrieval.outcome == AnnualEvidenceOutcome.FAILURE:
                return selection(
                    trace,
                    AnnualSelectionStatus.FAILED,
                    AnnualSelectionFailure.CANDIDATE_FAILURE,
                )

            # REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE만 여기까지 온다 → 다음 후보.

        return selection(
            trace,
            AnnualSelectionStatus.NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES,
        )

    def _build_history(
        self,
        financials: CompanyFinancials,
        *,
        business_year: str,
        report_code: str,
    ) -> list[tuple[KeyFinancials, tuple[list[OpenDartFinancialAccount], str]]]:
        accounts = financials.accounts
        fs_div = self._select_fs_div(accounts)
        selected_accounts = [
            account for account in accounts if account.fs_div == fs_div
        ]

        terms = ["current"]
        if report_code == "11011":
            terms += ["previous", "before_previous"]

        history: list[tuple[KeyFinancials, tuple[list[OpenDartFinancialAccount], str]]] = []
        for term in terms:
            key_financials = self._extract_key_financials(
                selected_accounts,
                stock_code=financials.stock_code,
                corp_code=financials.corp_code,
                business_year=_year_label_for_term(business_year, term),
                report_code=report_code,
                fs_div=fs_div,
                term=term,
            )

            # 당기는 항상 포함한다(값이 전부 비어 있더라도 기존
            # get_key_financials()와 동일한 동작을 보장). 전기/전전기는
            # 값이 전부 None이면(상장 이력이 짧은 회사 등) 의미 있는
            # 데이터가 없다는 뜻이므로 결과에서 생략한다.
            if term == "current" or self._has_any_value(key_financials):
                history.append((key_financials, (selected_accounts, term)))

        return history

    @staticmethod
    def _select_fs_div(accounts: list[OpenDartFinancialAccount]) -> str:
        if any(account.fs_div == "CFS" for account in accounts):
            return "CFS"
        return "OFS"

    @classmethod
    def _extract_key_financials(
        cls,
        accounts: list[OpenDartFinancialAccount],
        *,
        stock_code: str,
        corp_code: str,
        business_year: str,
        report_code: str,
        fs_div: str,
        term: str,
    ) -> KeyFinancials:
        return KeyFinancials(
            stock_code=stock_code,
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
            fs_div=fs_div,
            **{
                field: cls._find_amount(accounts, names, term)
                for field, _, names in _KEY_MEASURES
            },
        )

    @classmethod
    def _extract_measure_evidence(
        cls,
        accounts: list[OpenDartFinancialAccount],
        *,
        stock_code: str,
        period_label: str,
        term: str,
        retrieved_at: datetime,
    ) -> dict[str, EvidenceReference]:
        # _find_amount와 같은 _find_account로 row를 고르므로, evidence는 값이 실제로
        # 선택된 row의 identity다. 값이 None인 measure에는 reference를 만들지 않는다.
        evidence: dict[str, EvidenceReference] = {}
        for _, measure, names in _KEY_MEASURES:
            account = cls._find_account(accounts, names)
            if account is None or getattr(account, _TERM_AMOUNT_ATTR[term]) is None:
                continue

            evidence[measure] = EvidenceReference(
                identity=EvidenceItemIdentity(
                    entity=stock_code,
                    measure=measure,
                    origin=EvidenceOrigin.SOURCE_REPORTED,
                    source=_OPENDART_SOURCE,
                    observation=ObservationIdentity(
                        period_notation=getattr(account, _TERM_DATE_ATTR[term]),
                        period_label=period_label,
                        source_term=term,
                        report_type=account.reprt_code,
                        reporting_basis=account.fs_div,
                        statement=account.statement_div,
                    ),
                    version_anchor=account.rcept_no,
                ),
                retrieved_at=retrieved_at,
            )

        return evidence

    @staticmethod
    def _has_any_value(key_financials: KeyFinancials) -> bool:
        return any(
            value is not None
            for value in (
                key_financials.revenue,
                key_financials.operating_profit,
                key_financials.net_income,
                key_financials.total_assets,
                key_financials.total_liabilities,
                key_financials.total_equity,
            )
        )

    @classmethod
    def _find_amount(
        cls,
        accounts: list[OpenDartFinancialAccount],
        account_names: set[str] | frozenset[str],
        term: str = "current",
    ) -> int | None:
        account = cls._find_account(accounts, account_names)
        if account is None:
            return None
        return getattr(account, _TERM_AMOUNT_ATTR[term])

    @staticmethod
    def _find_account(
        accounts: list[OpenDartFinancialAccount],
        account_names: set[str] | frozenset[str],
    ) -> OpenDartFinancialAccount | None:
        for account in accounts:
            if account.account_name in account_names:
                return account

        return None


def _year_label_for_term(business_year: str, term: str) -> str:
    offset = {"current": 0, "previous": 1, "before_previous": 2}[term]
    return str(int(business_year) - offset)
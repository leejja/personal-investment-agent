import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from zipfile import ZipFile

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.models.annual_evidence import AnnualEvidenceFailureReason, AnnualEvidenceOutcome

ANNUAL_REPORT_CODE = "11011"

# Positive-unavailability admission set(docs/ARCHITECTURE.md §7.3 Implementation Contract rev.1).
# 여기 속한 non-success status만 REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE이 되어 fallback을 허용한다.
# 시작 상태는 비어 있다 — 공식 문서는 013의 메시지("조회된 데이타가 없습니다.")만 정하고 원인을
# 정하지 않으므로 013도 FAILURE(PROVIDER_STATUS)다. 확장은 official evidence + 승인된 live
# contrast + 별도 review가 필요하다(Q2b OPEN).
_POSITIVE_UNAVAILABLE_STATUSES: frozenset[str] = frozenset()


class OpenDartCorporation(BaseModel):
    corp_code: str
    corp_name: str
    corp_eng_name: str | None
    stock_code: str | None
    modify_date: str


class OpenDartFinancialAccount(BaseModel):
    rcept_no: str
    bsns_year: str
    stock_code: str
    reprt_code: str
    account_name: str
    fs_div: str
    fs_name: str
    statement_div: str
    statement_name: str
    current_term_name: str
    current_term_date: str
    current_term_amount: int | None
    previous_term_name: str
    previous_term_date: str
    previous_term_amount: int | None
    # 사업보고서(reprt_code=11011)는 실제로 당기/전기 외에 전전기(2년 전)
    # 컬럼까지 함께 내려준다(bfefrmtrm_*, 실제 API 호출로 확인). 회사에 따라
    # 이 컬럼 자체가 없을 수 있어(예: 상장 이력이 짧은 회사) Optional로 둔다.
    before_previous_term_name: str | None = None
    before_previous_term_date: str | None = None
    before_previous_term_amount: int | None = None
    currency: str


class OpenDartFinancialAccountsRetrieval(BaseModel):
    """internal carrier — 공개 반환 모델(`OpenDartFinancialAccount`)을 바꾸지 않고
    한 번의 provider 응답 수신 시각을 함께 전달한다. `retrieved_at`은 runtime retrieval
    시각이며 published_at / available_at이 아니다. MCP tool이 반환하지 않는다."""

    accounts: list[OpenDartFinancialAccount]
    retrieved_at: datetime


class OpenDartAnnualRetrieval(BaseModel):
    """연간 보고서 후보 하나(`corp_code`, `business_year`, `reprt_code=11011`)의 분류된 조회
    결과(Implementation Contract rev.1). provider 원문 status / message는 있으면 그대로 보존한다.

    `retrieved_at`은 EVIDENCE_RETURNED일 때만 있고, provider 응답을 수신한 runtime 시각이다 —
    published_at / available_at / 접수 시각 / 최신성이 아니다. 복수 `rcept_no`는 row별로 보존하며
    응답을 하나의 filing identity로 요약하지 않는다(filing-anchor 일관성은 S5 소유)."""

    model_config = ConfigDict(frozen=True)

    corp_code: str
    business_year: str
    report_code: str
    outcome: AnnualEvidenceOutcome
    accounts: tuple[OpenDartFinancialAccount, ...] | None = None
    retrieved_at: datetime | None = None
    provider_status: str | None = None
    provider_message: str | None = None
    failure_reason: AnnualEvidenceFailureReason | None = None
    failure_detail: str | None = None

    @model_validator(mode="after")
    def _outcome_invariant(self) -> "OpenDartAnnualRetrieval":
        if self.report_code != ANNUAL_REPORT_CODE:
            raise ValueError(f"annual retrieval requires reprt_code {ANNUAL_REPORT_CODE}")

        if self.outcome == AnnualEvidenceOutcome.EVIDENCE_RETURNED:
            if not self.accounts:
                raise ValueError("EVIDENCE_RETURNED requires at least one account row")
            if self.retrieved_at is None or self.retrieved_at.utcoffset() is None:
                raise ValueError("EVIDENCE_RETURNED requires a timezone-aware retrieved_at")
            if self.provider_status != "000":
                raise ValueError("EVIDENCE_RETURNED requires provider status 000")
            if self.failure_reason is not None or self.failure_detail is not None:
                raise ValueError("EVIDENCE_RETURNED must not carry a failure")
            return self

        if self.accounts is not None or self.retrieved_at is not None:
            raise ValueError(f"{self.outcome.value} must not carry accounts or retrieved_at")

        if self.outcome == AnnualEvidenceOutcome.REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE:
            # admission set 밖에서는 이 분류를 만들 수 없다 — positive unavailability 우회 방지.
            if self.provider_status not in _POSITIVE_UNAVAILABLE_STATUSES:
                raise ValueError("unavailability requires an admitted provider status")
            if self.failure_reason is not None or self.failure_detail is not None:
                raise ValueError("REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE must not carry a failure")
            return self

        if self.failure_reason is None:
            raise ValueError("FAILURE requires a failure reason")
        if self.failure_reason == AnnualEvidenceFailureReason.PROVIDER_STATUS:
            if self.provider_status is None or self.provider_status == "000":
                raise ValueError("PROVIDER_STATUS failure requires a non-success provider status")
            if self.provider_status in _POSITIVE_UNAVAILABLE_STATUSES:
                raise ValueError("an admitted provider status is not a PROVIDER_STATUS failure")
        if (
            self.failure_reason
            in (AnnualEvidenceFailureReason.TRANSPORT, AnnualEvidenceFailureReason.HTTP_STATUS)
            and self.provider_status is not None
        ):
            raise ValueError(f"{self.failure_reason.value} failure has no provider status")
        return self


class OpenDartService:
    BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    async def get_corporations(self) -> list[OpenDartCorporation]:
        url = f"{self.BASE_URL}/corpCode.xml"

        params = {
            "crtfc_key": self.api_key,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

        return self._parse_corporation_zip(response.content)

    async def resolve_corp_code(self, stock_code: str) -> str:
        corporations = await self.get_corporations()

        for corporation in corporations:
            if corporation.stock_code == stock_code:
                return corporation.corp_code

        raise ValueError(f"OpenDART corporation not found: {stock_code}")

    async def get_financial_accounts(
        self,
        corp_code: str,
        business_year: str,
        report_code: str,
    ) -> list[OpenDartFinancialAccount]:
        retrieval = await self.fetch_financial_accounts(
            corp_code=corp_code,
            business_year=business_year,
            report_code=report_code,
        )
        return retrieval.accounts

    async def fetch_financial_accounts(
        self,
        corp_code: str,
        business_year: str,
        report_code: str,
    ) -> OpenDartFinancialAccountsRetrieval:
        url = f"{self.BASE_URL}/fnlttSinglAcnt.json"

        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": business_year,
            "reprt_code": report_code,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

        data = response.json()

        status = data.get("status")

        if status != "000":
            message = data.get("message", "Unknown OpenDART error")
            raise ValueError(
                f"OpenDART API error: status={status}, message={message}"
            )

        rows = data.get("list")

        if not isinstance(rows, list):
            raise TypeError(f"Unexpected OpenDART response: {data}")

        # 성공 응답 수신 직후의 runtime retrieval 시각. 한 응답의 모든 row가 공유한다.
        retrieved_at = datetime.now(UTC)

        return OpenDartFinancialAccountsRetrieval(
            accounts=[self._convert_financial_account(row) for row in rows],
            retrieved_at=retrieved_at,
        )

    async def retrieve_annual_accounts(
        self,
        corp_code: str,
        business_year: str,
    ) -> OpenDartAnnualRetrieval:
        """사업보고서(11011) 후보 하나를 조회해 분류한다(Implementation Contract rev.1).

        legacy `fetch_financial_accounts()`와 달리 provider / transport 결과로 raise하지 않고
        EVIDENCE_RETURNED / REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE / FAILURE 중 하나를 반환한다.
        분류 대상이 아닌 예외(programming error)는 숨기지 않고 그대로 전파한다(fail closed).
        """
        url = f"{self.BASE_URL}/fnlttSinglAcnt.json"

        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": business_year,
            "reprt_code": ANNUAL_REPORT_CODE,
        }

        def classified(
            outcome: AnnualEvidenceOutcome, **fields: Any
        ) -> OpenDartAnnualRetrieval:
            return OpenDartAnnualRetrieval(
                corp_code=corp_code,
                business_year=business_year,
                report_code=ANNUAL_REPORT_CODE,
                outcome=outcome,
                **fields,
            )

        def failure(
            reason: AnnualEvidenceFailureReason, detail: str, **fields: Any
        ) -> OpenDartAnnualRetrieval:
            return classified(
                AnnualEvidenceOutcome.FAILURE,
                failure_reason=reason,
                failure_detail=detail,
                **fields,
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return failure(
                AnnualEvidenceFailureReason.HTTP_STATUS,
                f"HTTP {exc.response.status_code}",
            )
        except httpx.RequestError as exc:
            # 유효한 HTTP / provider 응답이 없다(timeout / connect / protocol 등).
            return failure(AnnualEvidenceFailureReason.TRANSPORT, type(exc).__name__)

        try:
            data = response.json()
        except ValueError:
            return failure(
                AnnualEvidenceFailureReason.MALFORMED_RESPONSE,
                "response body is not valid JSON",
            )

        if not isinstance(data, dict):
            return failure(
                AnnualEvidenceFailureReason.MALFORMED_RESPONSE,
                "top-level JSON value is not an object",
            )

        status = data.get("status")

        if status is None:
            return failure(AnnualEvidenceFailureReason.MALFORMED_RESPONSE, "status missing")

        if not isinstance(status, str):
            return failure(
                AnnualEvidenceFailureReason.MALFORMED_RESPONSE,
                "status is not a string",
            )

        raw_message = data.get("message")
        message = raw_message if isinstance(raw_message, str) else None

        if status != "000":
            if status in _POSITIVE_UNAVAILABLE_STATUSES:
                return classified(
                    AnnualEvidenceOutcome.REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE,
                    provider_status=status,
                    provider_message=message,
                )
            return failure(
                AnnualEvidenceFailureReason.PROVIDER_STATUS,
                f"provider status {status} is not an admitted unavailability status",
                provider_status=status,
                provider_message=message,
            )

        # 아래 실패는 모두 status 000 응답 안의 문제다 — provider status를 그대로 남긴다.
        provider = {"provider_status": status, "provider_message": message}

        if "list" not in data:
            return failure(
                AnnualEvidenceFailureReason.MALFORMED_RESPONSE,
                "status 000 without list",
                **provider,
            )

        rows = data["list"]

        if not isinstance(rows, list):
            return failure(
                AnnualEvidenceFailureReason.MALFORMED_RESPONSE,
                "list is not a JSON array",
                **provider,
            )

        # 공식 문서상 "조회된 데이타가 없습니다."는 013이다. 000 + 빈 list는 문서에 없는 조합이므로
        # positive unavailability로 해석하지 않고 fail closed한다.
        if not rows:
            return failure(
                AnnualEvidenceFailureReason.MALFORMED_RESPONSE,
                "status 000 with empty list",
                **provider,
            )

        accounts: list[OpenDartFinancialAccount] = []

        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                return failure(
                    AnnualEvidenceFailureReason.MALFORMED_RESPONSE,
                    f"list row {index} is not a JSON object",
                    **provider,
                )

            try:
                account = self._convert_financial_account(row)
            except KeyError as exc:
                return failure(
                    AnnualEvidenceFailureReason.INTEGRITY,
                    f"row {index}: required field {exc.args[0]!r} missing",
                    **provider,
                )
            except ValidationError:
                return failure(
                    AnnualEvidenceFailureReason.INTEGRITY,
                    f"row {index}: required field has an invalid value",
                    **provider,
                )
            except (ValueError, TypeError, AttributeError):
                # _parse_amount의 int() / strip() 실패 — 금액 파싱 실패. Q12(금액 의미)는 해소하지 않는다.
                return failure(
                    AnnualEvidenceFailureReason.INTEGRITY,
                    f"row {index}: amount could not be parsed",
                    **provider,
                )

            if account.bsns_year != business_year:
                return failure(
                    AnnualEvidenceFailureReason.INTEGRITY,
                    f"row {index}: bsns_year {account.bsns_year!r} does not match request",
                    **provider,
                )

            if account.reprt_code != ANNUAL_REPORT_CODE:
                return failure(
                    AnnualEvidenceFailureReason.INTEGRITY,
                    f"row {index}: reprt_code {account.reprt_code!r} does not match request",
                    **provider,
                )

            accounts.append(account)

        # EVIDENCE_RETURNED가 확립된 직후의 runtime retrieval 시각(legacy의 "성공 응답 수신 직후"와 같은
        # 의미). published_at / available_at / 접수 시각 / historical availability가 아니다.
        retrieved_at = datetime.now(UTC)

        return classified(
            AnnualEvidenceOutcome.EVIDENCE_RETURNED,
            accounts=tuple(accounts),
            retrieved_at=retrieved_at,
            **provider,
        )

    def _parse_corporation_zip(
        self,
        content: bytes,
    ) -> list[OpenDartCorporation]:
        with ZipFile(BytesIO(content)) as archive:
            filenames = archive.namelist()

            if not filenames:
                raise ValueError("Empty OpenDART corporation archive")

            xml_content = archive.read(filenames[0])

        root = ET.fromstring(xml_content)

        corporations: list[OpenDartCorporation] = []

        for item in root.findall("list"):
            corp_code = item.findtext("corp_code")
            corp_name = item.findtext("corp_name")
            modify_date = item.findtext("modify_date")

            if corp_code is None or corp_name is None or modify_date is None:
                continue

            stock_code = item.findtext("stock_code")
            corp_eng_name = item.findtext("corp_eng_name")

            corporations.append(
                OpenDartCorporation(
                    corp_code=corp_code.strip(),
                    corp_name=corp_name.strip(),
                    corp_eng_name=self._normalize_optional_text(corp_eng_name),
                    stock_code=self._normalize_optional_text(stock_code),
                    modify_date=modify_date.strip(),
                )
            )

        return corporations

    def _convert_financial_account(
        self,
        row: dict[str, Any],
    ) -> OpenDartFinancialAccount:
        return OpenDartFinancialAccount(
            rcept_no=row["rcept_no"],
            bsns_year=row["bsns_year"],
            stock_code=row["stock_code"],
            reprt_code=row["reprt_code"],
            account_name=row["account_nm"],
            fs_div=row["fs_div"],
            fs_name=row["fs_nm"],
            statement_div=row["sj_div"],
            statement_name=row["sj_nm"],
            current_term_name=row["thstrm_nm"],
            current_term_date=row["thstrm_dt"],
            current_term_amount=self._parse_amount(row.get("thstrm_amount")),
            previous_term_name=row["frmtrm_nm"],
            previous_term_date=row["frmtrm_dt"],
            previous_term_amount=self._parse_amount(row.get("frmtrm_amount")),
            before_previous_term_name=row.get("bfefrmtrm_nm"),
            before_previous_term_date=row.get("bfefrmtrm_dt"),
            before_previous_term_amount=self._parse_amount(row.get("bfefrmtrm_amount")),
            currency=row["currency"],
        )

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @staticmethod
    def _parse_amount(value: str | None) -> int | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        normalized = value.replace(",", "")

        # OpenDART는 값이 없는 계정 항목을 빈 문자열이 아니라 "-" 같은
        # placeholder로 내려주기도 한다(실제 API 응답에서 확인). 이는 0이
        # 아니라 "값 없음"을 뜻하므로 None으로 정규화한다. 실제 음수 금액
        # ("-1,234")과 구분하기 위해 부호만 있고 숫자가 없는 경우만
        # placeholder로 취급한다.
        if normalized in {"-", "+"}:
            return None

        return int(normalized)
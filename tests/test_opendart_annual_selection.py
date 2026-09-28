"""OpenDART Annual-Report Evidence Selection (Implementation Contract rev.1) invariants.

No external API calls: HTTP is served by httpx.MockTransport and selection uses an in-process fake
service. Concrete lookback_years values (e.g. 3) are test fixtures, not a production policy.
"""

import inspect
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.mcp import opendart_tools
from app.mcp.opendart_tools import (
    OPENDART_FINANCIAL_DATA_LOWER_BOUND_YEAR,
    AnnualCandidate,
    AnnualEvidenceSelection,
    AnnualSelectionTraceEntry,
    OpenDartTools,
    _annual_candidates,
)
from app.models.annual_evidence import (
    AnnualEvidenceFailureReason,
    AnnualEvidenceOutcome,
    AnnualSelectionFailure,
    AnnualSelectionStatus,
)
from app.services import opendart
from app.services.opendart import OpenDartAnnualRetrieval, OpenDartService

_CORP_CODE = "00126380"
_BASIS = datetime(2026, 3, 1, tzinfo=UTC)


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "rcept_no": "20260310000001",
        "bsns_year": "2025",
        "stock_code": "005930",
        "reprt_code": "11011",
        "account_nm": "매출액",
        "fs_div": "CFS",
        "fs_nm": "연결재무제표",
        "sj_div": "IS",
        "sj_nm": "손익계산서",
        "thstrm_nm": "제 57 기",
        "thstrm_dt": "2025.01.01 ~ 2025.12.31",
        "thstrm_amount": "300,870,903,000,000",
        "frmtrm_nm": "제 56 기",
        "frmtrm_dt": "2024.01.01 ~ 2024.12.31",
        "frmtrm_amount": "258,935,494,000,000",
        "currency": "KRW",
    }
    row.update(overrides)
    return row


def _mock_http(
    monkeypatch: pytest.MonkeyPatch,
    respond: Any,
) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return respond(request)

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def mock_async_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    return requests


def _json_response(payload: Any) -> Any:
    return lambda request: httpx.Response(200, json=payload, request=request)


async def _retrieve(
    monkeypatch: pytest.MonkeyPatch,
    respond: Any,
    business_year: str = "2025",
) -> OpenDartAnnualRetrieval:
    _mock_http(monkeypatch, respond)
    return await OpenDartService(api_key="test-key").retrieve_annual_accounts(
        corp_code=_CORP_CODE,
        business_year=business_year,
    )


def _assert_failure(
    result: OpenDartAnnualRetrieval,
    reason: AnnualEvidenceFailureReason,
) -> None:
    assert result.outcome == AnnualEvidenceOutcome.FAILURE
    assert result.failure_reason == reason
    assert result.failure_detail
    assert result.accounts is None
    assert result.retrieved_at is None


# ================================ classified retrieval ================================


@pytest.mark.anyio
async def test_status_000_with_rows_is_evidence_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = datetime.now(UTC)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"status": "000", "message": "정상", "list": [_row()]},
            request=request,
        )

    result = await _retrieve(monkeypatch, respond)
    after = datetime.now(UTC)

    assert result.outcome == AnnualEvidenceOutcome.EVIDENCE_RETURNED
    assert result.provider_status == "000"
    assert result.provider_message == "정상"
    assert result.failure_reason is None
    assert result.accounts is not None and len(result.accounts) == 1
    assert result.accounts[0].current_term_amount == 300_870_903_000_000
    assert result.retrieved_at is not None
    assert result.retrieved_at.utcoffset() == timedelta(0)
    assert before <= result.retrieved_at <= after
    # 요청 identity: 요청한 연도와 사업보고서 코드만 쓴다.
    assert requests[0].url.params["bsns_year"] == "2025"
    assert requests[0].url.params["reprt_code"] == "11011"
    assert requests[0].url.params["corp_code"] == _CORP_CODE


@pytest.mark.anyio
async def test_013_with_empty_admission_set_is_provider_status_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert opendart._POSITIVE_UNAVAILABLE_STATUSES == frozenset()

    result = await _retrieve(
        monkeypatch,
        _json_response({"status": "013", "message": "조회된 데이타가 없습니다."}),
    )

    _assert_failure(result, AnnualEvidenceFailureReason.PROVIDER_STATUS)
    assert result.provider_status == "013"
    assert result.provider_message == "조회된 데이타가 없습니다."


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status",
    ["010", "011", "012", "014", "020", "021", "100", "101", "800", "900", "901", "999"],
)
async def test_other_non_success_status_is_provider_status_failure(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    result = await _retrieve(monkeypatch, _json_response({"status": status, "message": "m"}))

    _assert_failure(result, AnnualEvidenceFailureReason.PROVIDER_STATUS)
    assert result.provider_status == status
    assert result.provider_message == "m"


@pytest.mark.anyio
async def test_admitted_status_is_unavailable_classification_path_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 분류 경로만 검증한다 — 013의 provider 의미를 확립하지 않는다(admission set은 production에서 비어 있다).
    monkeypatch.setattr(opendart, "_POSITIVE_UNAVAILABLE_STATUSES", frozenset({"013"}))

    result = await _retrieve(
        monkeypatch,
        _json_response({"status": "013", "message": "조회된 데이타가 없습니다."}),
    )

    assert result.outcome == AnnualEvidenceOutcome.REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE
    assert result.provider_status == "013"
    assert result.failure_reason is None
    assert result.accounts is None
    assert result.retrieved_at is None


@pytest.mark.anyio
async def test_transport_error_is_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    result = await _retrieve(monkeypatch, respond)

    _assert_failure(result, AnnualEvidenceFailureReason.TRANSPORT)
    assert result.provider_status is None


@pytest.mark.anyio
@pytest.mark.parametrize("http_status", [404, 500, 503])
async def test_http_error_is_http_status_failure(
    monkeypatch: pytest.MonkeyPatch,
    http_status: int,
) -> None:
    result = await _retrieve(
        monkeypatch,
        lambda request: httpx.Response(http_status, request=request),
    )

    _assert_failure(result, AnnualEvidenceFailureReason.HTTP_STATUS)
    assert result.failure_detail == f"HTTP {http_status}"
    assert result.provider_status is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "respond",
    [
        lambda request: httpx.Response(200, content=b"<html>not json</html>", request=request),
        lambda request: httpx.Response(200, json=[{"status": "000"}], request=request),
        lambda request: httpx.Response(200, json={"message": "no status"}, request=request),
        lambda request: httpx.Response(200, json={"status": 0, "list": []}, request=request),
    ],
    ids=["non-json", "top-level-array", "missing-status", "non-string-status"],
)
async def test_malformed_envelope_is_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
    respond: Any,
) -> None:
    result = await _retrieve(monkeypatch, respond)

    _assert_failure(result, AnnualEvidenceFailureReason.MALFORMED_RESPONSE)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"status": "000", "message": "정상"},
        {"status": "000", "message": "정상", "list": {"rcept_no": "x"}},
        {"status": "000", "message": "정상", "list": []},
        {"status": "000", "message": "정상", "list": ["not-an-object"]},
    ],
    ids=["missing-list", "non-list-list", "empty-list", "non-object-row"],
)
async def test_malformed_000_body_is_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    result = await _retrieve(monkeypatch, _json_response(payload))

    # 000 + 빈 list도 positive unavailability가 아니다(문서상 "데이터 없음"은 013).
    _assert_failure(result, AnnualEvidenceFailureReason.MALFORMED_RESPONSE)
    assert result.provider_status == "000"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "row",
    [
        {k: v for k, v in _row().items() if k != "rcept_no"},
        {k: v for k, v in _row().items() if k != "currency"},
        _row(account_nm=None),
        _row(thstrm_amount="12a"),
        _row(thstrm_amount=12345),
        _row(bsns_year="2024"),
        _row(reprt_code="11014"),
    ],
    ids=[
        "missing-rcept_no",
        "missing-currency",
        "null-account_nm",
        "malformed-amount",
        "non-string-amount",
        "bsns_year-mismatch",
        "reprt_code-mismatch",
    ],
)
async def test_row_integrity_failures(
    monkeypatch: pytest.MonkeyPatch,
    row: dict[str, Any],
) -> None:
    result = await _retrieve(
        monkeypatch,
        _json_response({"status": "000", "message": "정상", "list": [_row(), row]}),
    )

    _assert_failure(result, AnnualEvidenceFailureReason.INTEGRITY)
    assert result.failure_detail is not None and result.failure_detail.startswith("row 1:")
    assert result.provider_status == "000"


@pytest.mark.anyio
async def test_multiple_rcept_no_is_evidence_returned_with_rows_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _retrieve(
        monkeypatch,
        _json_response(
            {
                "status": "000",
                "message": "정상",
                "list": [
                    _row(rcept_no="20260310000001", fs_div="CFS"),
                    _row(rcept_no="20260402000002", fs_div="OFS"),
                ],
            }
        ),
    )

    assert result.outcome == AnnualEvidenceOutcome.EVIDENCE_RETURNED
    assert result.accounts is not None
    assert [account.rcept_no for account in result.accounts] == [
        "20260310000001",
        "20260402000002",
    ]
    # 응답을 하나의 filing identity로 요약하는 필드가 없다.
    assert not any("rcept" in name for name in OpenDartAnnualRetrieval.model_fields)


@pytest.mark.anyio
async def test_report_returned_without_feature_account_is_evidence_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # BS 행만 있고 매출액 계정이 없다 — feature 단위 문제이며 annual-report fallback 사유가 아니다.
    result = await _retrieve(
        monkeypatch,
        _json_response(
            {
                "status": "000",
                "message": "정상",
                "list": [_row(account_nm="자산총계", sj_div="BS", sj_nm="재무상태표")],
            }
        ),
    )

    assert result.outcome == AnnualEvidenceOutcome.EVIDENCE_RETURNED


class _RecordingDatetime(datetime):
    """retrieved_at을 읽는 시점을 기록하는 datetime(실제 시계 대신 고정 instant 반환)."""

    calls = 0
    instant = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        cls.calls += 1
        return cls.instant


@pytest.fixture
def recording_clock(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingDatetime]:
    _RecordingDatetime.calls = 0
    monkeypatch.setattr(opendart, "datetime", _RecordingDatetime)
    return _RecordingDatetime


@pytest.mark.anyio
async def test_retrieved_at_is_captured_once_when_evidence_is_returned(
    monkeypatch: pytest.MonkeyPatch,
    recording_clock: type[_RecordingDatetime],
) -> None:
    result = await _retrieve(
        monkeypatch,
        _json_response({"status": "000", "message": "정상", "list": [_row(), _row()]}),
    )

    assert result.outcome == AnnualEvidenceOutcome.EVIDENCE_RETURNED
    assert recording_clock.calls == 1
    assert result.retrieved_at == recording_clock.instant


@pytest.mark.anyio
@pytest.mark.parametrize(
    "respond",
    [
        lambda request: httpx.Response(200, content=b"not json", request=request),
        lambda request: httpx.Response(200, json={"status": "013"}, request=request),
        lambda request: httpx.Response(200, json={"status": "000", "list": []}, request=request),
        lambda request: httpx.Response(
            200, json={"status": "000", "list": [_row(bsns_year="2024")]}, request=request
        ),
        lambda request: httpx.Response(
            200, json={"status": "000", "list": [_row(thstrm_amount="12a")]}, request=request
        ),
    ],
    ids=["malformed", "provider-status", "empty-list", "integrity-mismatch", "integrity-amount"],
)
async def test_retrieved_at_is_not_captured_for_failures(
    monkeypatch: pytest.MonkeyPatch,
    recording_clock: type[_RecordingDatetime],
    respond: Any,
) -> None:
    # retrieval 시각은 EVIDENCE_RETURNED가 확립된 뒤에만 읽는다 — 실패 응답에는 시각이 없다.
    result = await _retrieve(monkeypatch, respond)

    assert result.outcome == AnnualEvidenceOutcome.FAILURE
    assert result.retrieved_at is None
    assert recording_clock.calls == 0


@pytest.mark.anyio
async def test_legacy_fetch_still_raises_on_013(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_http(monkeypatch, _json_response({"status": "013", "message": "조회된 데이타가 없습니다."}))

    with pytest.raises(ValueError, match="OpenDART API error: status=013"):
        await OpenDartService(api_key="test-key").fetch_financial_accounts(
            corp_code=_CORP_CODE,
            business_year="2025",
            report_code="11011",
        )


def test_retrieval_model_rejects_invalid_states() -> None:
    base = {"corp_code": _CORP_CODE, "business_year": "2025", "report_code": "11011"}

    with pytest.raises(ValidationError):
        OpenDartAnnualRetrieval(**base, outcome=AnnualEvidenceOutcome.EVIDENCE_RETURNED)
    with pytest.raises(ValidationError):
        # admission set 밖에서는 UNAVAILABLE을 만들 수 없다.
        OpenDartAnnualRetrieval(
            **base,
            outcome=AnnualEvidenceOutcome.REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE,
            provider_status="013",
        )
    with pytest.raises(ValidationError):
        OpenDartAnnualRetrieval(**base, outcome=AnnualEvidenceOutcome.FAILURE)
    with pytest.raises(ValidationError):
        OpenDartAnnualRetrieval(
            **{**base, "report_code": "11014"},
            outcome=AnnualEvidenceOutcome.FAILURE,
            failure_reason=AnnualEvidenceFailureReason.TRANSPORT,
        )


# ================================ candidate generation ================================


def _years(candidates: tuple[AnnualCandidate, ...]) -> list[str]:
    return [candidate.business_year for candidate in candidates]


@pytest.mark.parametrize(
    ("basis", "lookback_years", "expected"),
    [
        (_BASIS, 3, ["2026", "2025", "2024"]),
        (_BASIS, 1, ["2026"]),
        (_BASIS, 20, [str(year) for year in range(2026, 2014, -1)]),
        (datetime(2016, 6, 1, tzinfo=UTC), 5, ["2016", "2015"]),
        (datetime(2015, 6, 1, tzinfo=UTC), 1, ["2015"]),
        (datetime(2014, 12, 31, tzinfo=UTC), 3, []),
    ],
    ids=["lookback-3", "lookback-1", "clipped-at-2015", "partially-clipped", "at-bound", "pre-2015"],
)
def test_candidate_generation_is_bounded_descending(
    basis: datetime,
    lookback_years: int,
    expected: list[str],
) -> None:
    candidates = _annual_candidates(basis, lookback_years=lookback_years)

    assert _years(candidates) == expected
    assert all(candidate.report_code == "11011" for candidate in candidates)
    assert _annual_candidates(basis, lookback_years=lookback_years) == candidates


def test_candidate_basis_year_is_the_utc_year_of_the_instant() -> None:
    # 2026-01-01 05:00 KST = 2025-12-31 20:00 UTC → 첫 후보는 basis 자체의 UTC 연도.
    kst = timezone(timedelta(hours=9))
    basis = datetime(2026, 1, 1, 5, 0, tzinfo=kst)

    assert _years(_annual_candidates(basis, lookback_years=2)) == ["2025", "2024"]


def test_lower_bound_is_the_documented_provider_boundary() -> None:
    assert OPENDART_FINANCIAL_DATA_LOWER_BOUND_YEAR == 2015


def test_tz_naive_basis_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _annual_candidates(datetime(2026, 3, 1), lookback_years=3)  # noqa: DTZ001 — intentionally naive


@pytest.mark.parametrize("lookback_years", [0, -1])
def test_non_positive_lookback_is_rejected(lookback_years: int) -> None:
    with pytest.raises(ValueError, match=">= 1"):
        _annual_candidates(_BASIS, lookback_years=lookback_years)


@pytest.mark.parametrize("lookback_years", [True, 3.0, "3", None])
def test_non_int_lookback_is_rejected(lookback_years: Any) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        _annual_candidates(_BASIS, lookback_years=lookback_years)


def test_lookback_years_has_no_default() -> None:
    for function in (_annual_candidates, OpenDartTools.select_annual_evidence):
        parameter = inspect.signature(function).parameters["lookback_years"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty

    with pytest.raises(TypeError):
        _annual_candidates(_BASIS)  # type: ignore[call-arg]


def test_candidate_generation_does_not_read_the_clock() -> None:
    source = inspect.getsource(_annual_candidates)
    assert "now(" not in source
    assert "today(" not in source


def test_candidate_carries_no_ordering_or_latestness_claim() -> None:
    assert set(AnnualCandidate.model_fields) == {"business_year", "report_code"}
    assert not any("latest" in name for name in AnnualEvidenceSelection.model_fields)


# ================================ selection / trace ================================


class _ScriptedOpenDartService:
    """business_year별로 준비한 분류 결과를 반환하는 in-process fake(외부 호출 없음)."""

    def __init__(self, results: dict[str, OpenDartAnnualRetrieval]) -> None:
        self.results = results
        self.calls: list[tuple[str, str]] = []

    async def retrieve_annual_accounts(
        self,
        corp_code: str,
        business_year: str,
    ) -> OpenDartAnnualRetrieval:
        self.calls.append((corp_code, business_year))
        return self.results[business_year]


def _returned(business_year: str) -> OpenDartAnnualRetrieval:
    account = OpenDartService(api_key="unused")._convert_financial_account(
        _row(bsns_year=business_year)
    )
    return OpenDartAnnualRetrieval(
        corp_code=_CORP_CODE,
        business_year=business_year,
        report_code="11011",
        outcome=AnnualEvidenceOutcome.EVIDENCE_RETURNED,
        accounts=(account,),
        retrieved_at=datetime(2026, 3, 1, 0, 0, 1, tzinfo=UTC),
        provider_status="000",
        provider_message="정상",
    )


def _unavailable(business_year: str) -> OpenDartAnnualRetrieval:
    return OpenDartAnnualRetrieval(
        corp_code=_CORP_CODE,
        business_year=business_year,
        report_code="11011",
        outcome=AnnualEvidenceOutcome.REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE,
        provider_status="013",
        provider_message="조회된 데이타가 없습니다.",
    )


def _failed(business_year: str) -> OpenDartAnnualRetrieval:
    return OpenDartAnnualRetrieval(
        corp_code=_CORP_CODE,
        business_year=business_year,
        report_code="11011",
        outcome=AnnualEvidenceOutcome.FAILURE,
        provider_status="020",
        provider_message="요청 제한을 초과하였습니다.",
        failure_reason=AnnualEvidenceFailureReason.PROVIDER_STATUS,
        failure_detail="provider status 020 is not an admitted unavailability status",
    )


@pytest.fixture
def admit_013(monkeypatch: pytest.MonkeyPatch) -> None:
    # fallback 경로를 검증하기 위한 test 전용 주입 — production admission set은 비어 있다.
    monkeypatch.setattr(opendart, "_POSITIVE_UNAVAILABLE_STATUSES", frozenset({"013"}))


async def _select(
    service: _ScriptedOpenDartService,
    *,
    basis: datetime = _BASIS,
    lookback_years: int = 3,
) -> AnnualEvidenceSelection:
    return await OpenDartTools(service).select_annual_evidence(  # type: ignore[arg-type]
        _CORP_CODE,
        candidate_basis_instant=basis,
        lookback_years=lookback_years,
    )


def _trace_years(selection: AnnualEvidenceSelection) -> list[str]:
    return [entry.candidate.business_year for entry in selection.trace]


@pytest.mark.anyio
async def test_first_candidate_returned_is_selected_with_one_attempt() -> None:
    service = _ScriptedOpenDartService({"2026": _returned("2026")})

    selection = await _select(service)

    assert selection.status == AnnualSelectionStatus.SELECTED
    assert selection.failure is None
    assert service.calls == [(_CORP_CODE, "2026")]
    assert _trace_years(selection) == ["2026"]
    assert selection.selected is selection.trace[0].retrieval
    assert _years(selection.candidates) == ["2026", "2025", "2024"]


@pytest.mark.anyio
async def test_first_candidate_failure_stops_without_fallback() -> None:
    service = _ScriptedOpenDartService({"2026": _failed("2026"), "2025": _returned("2025")})

    selection = await _select(service)

    assert selection.status == AnnualSelectionStatus.FAILED
    assert selection.failure == AnnualSelectionFailure.CANDIDATE_FAILURE
    assert service.calls == [(_CORP_CODE, "2026")]
    assert selection.selected is None
    entry = selection.trace[0].retrieval
    assert entry.provider_status == "020"
    assert entry.provider_message == "요청 제한을 초과하였습니다."
    assert entry.failure_reason == AnnualEvidenceFailureReason.PROVIDER_STATUS


@pytest.mark.anyio
async def test_013_without_admission_stops_at_first_candidate() -> None:
    service = _ScriptedOpenDartService(
        {
            "2026": OpenDartAnnualRetrieval(
                corp_code=_CORP_CODE,
                business_year="2026",
                report_code="11011",
                outcome=AnnualEvidenceOutcome.FAILURE,
                provider_status="013",
                provider_message="조회된 데이타가 없습니다.",
                failure_reason=AnnualEvidenceFailureReason.PROVIDER_STATUS,
                failure_detail="provider status 013 is not an admitted unavailability status",
            ),
            "2025": _returned("2025"),
        }
    )

    selection = await _select(service)

    assert selection.status == AnnualSelectionStatus.FAILED
    assert service.calls == [(_CORP_CODE, "2026")]


@pytest.mark.anyio
async def test_unavailable_then_returned_falls_back_once(admit_013: None) -> None:
    service = _ScriptedOpenDartService({"2026": _unavailable("2026"), "2025": _returned("2025")})

    selection = await _select(service)

    assert selection.status == AnnualSelectionStatus.SELECTED
    assert service.calls == [(_CORP_CODE, "2026"), (_CORP_CODE, "2025")]
    assert _trace_years(selection) == ["2026", "2025"]
    assert [entry.retrieval.outcome for entry in selection.trace] == [
        AnnualEvidenceOutcome.REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE,
        AnnualEvidenceOutcome.EVIDENCE_RETURNED,
    ]
    assert selection.selected is not None and selection.selected.business_year == "2025"


@pytest.mark.anyio
async def test_unavailable_then_failure_fails_at_second_candidate(admit_013: None) -> None:
    service = _ScriptedOpenDartService(
        {"2026": _unavailable("2026"), "2025": _failed("2025"), "2024": _returned("2024")}
    )

    selection = await _select(service)

    assert selection.status == AnnualSelectionStatus.FAILED
    assert selection.failure == AnnualSelectionFailure.CANDIDATE_FAILURE
    assert service.calls == [(_CORP_CODE, "2026"), (_CORP_CODE, "2025")]
    assert _trace_years(selection) == ["2026", "2025"]


@pytest.mark.anyio
async def test_all_unavailable_is_bounded_exhaustion(admit_013: None) -> None:
    service = _ScriptedOpenDartService(
        {year: _unavailable(year) for year in ("2026", "2025", "2024")}
    )

    selection = await _select(service)

    assert selection.status == AnnualSelectionStatus.NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES
    assert selection.failure is None
    assert selection.selected is None
    # 탐색 범위가 기록된다 — 결론은 이 후보 집합에 한정된다.
    assert selection.lookback_years == 3
    assert selection.candidate_basis_instant == _BASIS
    assert _years(selection.candidates) == ["2026", "2025", "2024"]
    assert _trace_years(selection) == ["2026", "2025", "2024"]


@pytest.mark.anyio
async def test_no_candidates_fails_without_provider_calls() -> None:
    service = _ScriptedOpenDartService({})

    selection = await _select(service, basis=datetime(2014, 6, 1, tzinfo=UTC))

    assert selection.status == AnnualSelectionStatus.FAILED
    assert selection.failure == AnnualSelectionFailure.NO_CANDIDATES
    assert selection.candidates == ()
    assert selection.trace == ()
    assert service.calls == []


@pytest.mark.anyio
async def test_selection_records_basis_in_utc() -> None:
    kst = timezone(timedelta(hours=9))
    service = _ScriptedOpenDartService({"2026": _returned("2026")})

    selection = await _select(service, basis=datetime(2026, 3, 1, 9, 0, tzinfo=kst))

    assert selection.candidate_basis_instant == datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    assert selection.candidate_basis_instant.utcoffset() == timedelta(0)


def test_status_vocabulary_has_no_global_absence() -> None:
    assert {status.value for status in AnnualSelectionStatus} == {
        "selected",
        "no_annual_report_evidence_among_examined_candidates",
        "failed",
    }


def test_selection_model_rejects_inconsistent_trace(admit_013: None) -> None:
    candidates = _annual_candidates(_BASIS, lookback_years=3)

    def selection(**fields: Any) -> AnnualEvidenceSelection:
        base: dict[str, Any] = {
            "corp_code": _CORP_CODE,
            "candidate_basis_instant": _BASIS,
            "lookback_years": 3,
            "candidates": candidates,
        }
        return AnnualEvidenceSelection(**{**base, **fields})

    def entry(retrieval: OpenDartAnnualRetrieval) -> AnnualSelectionTraceEntry:
        return AnnualSelectionTraceEntry(
            candidate=AnnualCandidate(business_year=retrieval.business_year, report_code="11011"),
            retrieval=retrieval,
        )

    # trace가 후보 순서를 따르지 않는다.
    with pytest.raises(ValidationError):
        selection(trace=(entry(_returned("2025")),), status=AnnualSelectionStatus.SELECTED)
    # FAILURE 다음에 후보가 이어진다(negative fallback).
    with pytest.raises(ValidationError):
        selection(
            trace=(entry(_failed("2026")), entry(_returned("2025"))),
            status=AnnualSelectionStatus.SELECTED,
        )
    # 모든 후보를 시도하지 않았는데 소진이라 주장한다.
    with pytest.raises(ValidationError):
        selection(
            trace=(entry(_unavailable("2026")),),
            status=AnnualSelectionStatus.NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES,
        )
    # 기록된 탐색 범위와 후보가 다르다.
    with pytest.raises(ValidationError):
        selection(
            candidates=candidates[:2],
            trace=(entry(_returned("2026")),),
            status=AnnualSelectionStatus.SELECTED,
        )
    # FAILED인데 원인이 없다.
    with pytest.raises(ValidationError):
        selection(trace=(entry(_failed("2026")),), status=AnnualSelectionStatus.FAILED)
    # lookback_years는 strict int다.
    with pytest.raises(ValidationError):
        selection(
            lookback_years=True,
            trace=(entry(_returned("2026")),),
            status=AnnualSelectionStatus.SELECTED,
        )
    # trace entry의 retrieval과 candidate가 다르다.
    with pytest.raises(ValidationError):
        AnnualSelectionTraceEntry(
            candidate=AnnualCandidate(business_year="2026", report_code="11011"),
            retrieval=_returned("2025"),
        )


def test_no_production_lookback_value_is_defined() -> None:
    # production lookback 값이 모듈에 없다(값은 향후 V0 policy 소유).
    assert not any("LOOKBACK" in name.upper() for name in vars(opendart_tools))

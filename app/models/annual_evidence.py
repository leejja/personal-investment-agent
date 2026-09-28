"""RE-05 OpenDART Annual-Report Evidence Selection — provider-neutral vocabulary.

`docs/ARCHITECTURE.md` §7.3 Implementation Contract(FROZEN, rev.1)의 provider-neutral 어휘다.
결과 분류 이름은 §7.11.4 / §7.11.6 frozen 어휘를 그대로 쓴다. provider-specific 조회 결과
(`OpenDartAnnualRetrieval`)와 OpenDART 후보 / selection / trace 구조는 각각
`app/services/opendart.py`, `app/mcp/opendart_tools.py`에 있다.

이 모듈이 하지 않는 것: 어떤 provider status가 positive unavailability인지 정하기(admission
set은 provider adapter 소유, 시작 상태는 비어 있다), 최신성(latest / corrected / original /
final) 표현, 전역 부재 표현.
"""

from enum import Enum


class AnnualEvidenceOutcome(str, Enum):
    """연간 보고서 후보 하나의 조회 결과. 정확히 하나로 분류된다."""

    EVIDENCE_RETURNED = "evidence_returned"
    # provider status가 positive-unavailability admission set에 속할 때만. 이 분류만 fallback을 허용한다.
    REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE = "requested_annual_evidence_unavailable"
    FAILURE = "failure"


class AnnualEvidenceFailureReason(str, Enum):
    TRANSPORT = "transport"
    HTTP_STATUS = "http_status"
    MALFORMED_RESPONSE = "malformed_response"
    # admission set 밖의 non-success provider status(모르는 코드 포함).
    PROVIDER_STATUS = "provider_status"
    INTEGRITY = "integrity"


class AnnualSelectionStatus(str, Enum):
    SELECTED = "selected"
    # 기록된 후보 집합 안에서 EVIDENCE_RETURNED가 없었다는 것만 뜻한다 — 전역 부재가 아니다.
    NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES = (
        "no_annual_report_evidence_among_examined_candidates"
    )
    FAILED = "failed"


class AnnualSelectionFailure(str, Enum):
    """FAILED selection의 원인. trace만으로도 도출되지만 FAILED 결과를 명시적으로 읽히게 한다
    (validator가 trace와의 일치를 강제한다)."""

    # 후보가 0개(basis 연도가 provider 하한 미만) — provider 조회 0회.
    NO_CANDIDATES = "no_candidates"
    # 마지막으로 시도한 후보의 조회 결과가 FAILURE — fallback 없이 중단.
    CANDIDATE_FAILURE = "candidate_failure"

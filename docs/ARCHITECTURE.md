# Architecture

## 1. Architecture Purpose

이 문서는 **현재 repository에 실제로 존재하는 architecture**만 설명하는
canonical, non-chronological reference다. "왜 이렇게 결정했는가"(historical
rationale), 언제 무엇이 바뀌었는가, provider별 실측 조사 과정은 이 문서의
범위가 아니다 — 그런 내용은 전부 `docs/dev-log/`에 날짜별로 기록돼 있다.

이 문서는 다음을 하지 않는다:

- decision history / FROZEN 과정 서술 (→ `docs/dev-log/`)
- field-by-field model contract 전체 나열 (→ `app/models/*.py` docstring + `tests/`)
- provider별 empirical research 결과 (→ `docs/dev-log/`)
- numeric threshold/weight/calibration (RE-05 기준 전부 OPEN — 이 문서에도 없음)

이 문서가 실제 코드와 어긋나는 것이 발견되면, 코드가 canonical이다 — 이
문서를 갱신해야 한다.

---

## 2. System Context / High-Level Flow

```text
User
  │  UserRequest
  ▼
REST API (FastAPI, app/api/)
  │
  ▼
Supervisor / Router (app/supervisor/)
  │  intent별 고정 dispatch (market_only / stock_research /
  │  candidate_discovery / portfolio_strategy)
  │
  ├──────────────┬────────────────────┬─────────────────────┐
  ▼              ▼                    ▼                     ▼
Market Agent  Stock Research Agent  Candidate Discovery  Portfolio Strategy Agent
(app/agents/  (app/agents/          (app/discovery/)     (app/agents/portfolio/)
 market/)      stock_research/)                           │ MarketAnalysis/
  │              │                    │                    │ StockAnalysis[]/
  │              │                    │                    │ PortfolioContext/
  │              │                    │                    │ InvestorProfile 입력
  │  in-process direct call           │                    │ (Domain Tool 미호출)
  ▼              ▼                    ▼                    ▼
Domain Tools (app/mcp/{ecos,kiwoom,opendart}_tools.py)
  │
  ▼
Services (app/services/{ecos,kiwoom,opendart,llm,portfolio_adapter}.py)
  │
  ▼
External APIs (ECOS, OpenDART, Kiwoom REST)
```

별도 경로(위 흐름과 독립적인 evaluation pipeline, §7 참고):

```text
Stock Research Agent의 deterministic 산출물(DeterministicAnalysisResult)
  ▼
Evaluation Layer (app/evaluation/) — Coverage/Assembly/FeatureEvaluator
  ▼
RecommendationEvaluationState (app/models/research_context.py)
```

이 두 번째 경로는 아직 Agent 흐름에 연결돼 있지 않다 — §7에서 정확한 현재
상태를 구분해서 기술한다.

---

## 3. Layer Responsibilities

| Layer | 책임 | 실제 위치 |
|---|---|---|
| REST API | HTTP boundary, DTO 변환, exception → status mapping | `app/api/` |
| Supervisor / Router | intent 분류, Agent 실행 순서 결정, 부분 실패 정책, 결과 조립 | `app/supervisor/` |
| Agent | 시장·종목·포트폴리오 reasoning, deterministic fact 생성 + LLM grounding | `app/agents/*/` |
| Candidate Discovery | 투자 판단 없는 순수 종목 필터링(Stock Universe → 조건 매칭) | `app/discovery/` |
| Domain Tool | vendor 세부사항을 감춘 의미 기반 연산(`get_base_rate()` 등) | `app/mcp/*_tools.py` |
| MCP Server | Domain Tool을 MCP protocol로 외부에 노출(프로세스 경계) | `app/mcp/server.py` |
| Service | 외부 API 호출, parsing, normalization, 에러 처리 | `app/services/` |
| Model / Contract | 시스템 전체가 공유하는 data contract | `app/models/` |
| Evaluation | Recommendation Evaluation pipeline의 deterministic building block(Coverage/Assembly/FeatureEvaluator) + Recommendation Policy Step 1 Decision Eligibility primitive(§7.4) + Feature Normalization stage(contract FROZEN, 미구현, §7.5) | `app/evaluation/` |

**Agent → Domain Tool 호출은 in-process direct call이며 MCP protocol을
쓰지 않는다.** `Market Agent`/`Stock Research Agent`는 `app/mcp/*_tools.py`의
클래스(`EcosTools`/`KiwoomTools`/`OpenDartTools`)를 같은 Python 프로세스
안에서 직접 인스턴스 호출한다(실제 확인: `app/agents/market/orchestrator.py`,
`app/agents/stock_research/orchestrator.py`가 이 클래스들을 constructor로
받아 직접 메서드를 호출). `Portfolio Strategy Agent`는 Domain Tool을 아예
호출하지 않는다 — 이미 다른 Agent가 만든 `MarketAnalysis`/`StockAnalysis[]`와
`PortfolioContext`/`InvestorProfile`을 입력으로만 받는다.

**MCP Server(`app/mcp/server.py`)는 별도 프로세스/외부 client(다른 Agent
runtime, LLM host 등)를 위한 노출 경계이지, 현재 Agent 실행 경로의 일부가
아니다.** 같은 Domain Tool 클래스를 MCP tool로 wrapping해 재노출할 뿐이며,
9개 tool(`get_base_rate`/`get_exchange_rate`/`get_kospi_index`/
`get_kosdaq_index`/`get_company_financials`/`get_key_financials`/
`get_stock_info`/`get_account_balance`/`get_portfolio_context`)이 등록돼
있다(`app/mcp/server.py`).

**Domain Tool은 물리적으로 `app/mcp/` 패키지 안에 있다** —
`EcosTools`/`KiwoomTools`/`OpenDartTools`가 각각 `app/mcp/ecos_tools.py`/
`kiwoom_tools.py`/`opendart_tools.py`에 정의돼 있고, Agent와 MCP Server
양쪽이 동일한 클래스를 서로 다른 방식(직접 호출 vs MCP tool wrapping)으로
소비한다 — 별도 물리적 "Domain Tool Layer" 디렉터리는 없다.

---

## 4. Agent Layer

| Agent | 역할 | 위치 |
|---|---|---|
| Supervisor / Router | 사용자 요청 해석, 4개 intent 중 하나로 라우팅, Agent 실행/조립 | `app/supervisor/orchestrator.py`, `routing.py` |
| Market Agent | 거시 지표(기준금리/환율/KOSPI/KOSDAQ) 기반 시장 국면 분석 | `app/agents/market/` |
| Stock Research Agent | 개별 종목 재무/가격 deterministic 분석 + LLM reasoning | `app/agents/stock_research/` |
| Portfolio Strategy Agent | 보유 종목 + 시장/종목 분석을 종합한 개인화 전략 | `app/agents/portfolio/` |
| Candidate Discovery | 조건 기반 종목 후보 탐색(투자 판단 없음) | `app/discovery/` |

각 Agent(Supervisor 제외)는 동일한 3-파일 패턴을 따른다: `analysis.py`
(deterministic fact 생성) → `reasoning.py`(LLM 호출, fact-id grounding) →
`orchestrator.py`(둘을 조립, 외부에 노출되는 진입점). Supervisor는
`analysis.py`가 없다 — 입력이 외부 API 수치가 아니라 사용자의 자연어
자체이기 때문이다.

이 5개 컴포넌트 모두 **v1 구현 완료**다. 각 Agent의 내부 판단 로직/필드
세부사항은 이 문서가 아니라 `app/models/{market,stock,portfolio,discovery,
supervisor}.py`와 해당 `tests/`가 canonical이다.

---

## 5. Model / Contract Layer

`app/models/`는 시스템 전체가 공유하는 cross-cutting data contract다 —
호출 흐름상의 한 단계가 아니라 Service/Domain Tool/Agent/Supervisor/
Evaluation이 서로 주고받는 구조의 계약을 정의한다.

| 모듈 | 역할 |
|---|---|
| `common.py` | `RiskLevel`, `AnalysisConfidence`, `Evidence`, `UserRequest` |
| `market.py` | `MarketAnalysis`, `MarketIndicator`, `MarketRegime` |
| `stock.py` | `StockAnalysis`, `StockPriceSnapshot`, `FinancialSnapshot`, `FinancialFeatures` |
| `portfolio.py` | `PortfolioContext`, `PortfolioPosition`, `InvestorProfile` |
| `strategy.py` | `StrategyResult`, `PositionRecommendation` (v1 Portfolio Strategy Agent의 실제 출력) |
| `supervisor.py` | `Intent`, `SupervisorResult` |
| `discovery.py` | `Candidate`, `MarketFilter` |
| `recommendation.py` | RE-04/RE-05 Recommendation Evaluation contract (27개 model/enum) |
| `research_context.py` | RE-05 evaluation 입력 경계(`NormalizedResearchData`, `EvaluationContext`, `RecommendationEvaluationState`, `FeatureEvaluator` Protocol) |

각 model의 field 단위 상세, invariant, validator는 이 문서에서 다시
설명하지 않는다 — **canonical source는 각 모듈의 docstring과
`tests/test_*.py`**다(특히 `recommendation.py`/`research_context.py`는
매우 상세한 근거 docstring을 갖고 있으며, 그 자체가 RE-04/RE-05 FROZEN
contract의 1차 자료다).

중요한 구조적 사실 하나만 강조한다: **`StockOpportunityAssessment`
(`recommendation.py`, 종목 자체의 투자기회 판단)와 `PositionRecommendation`
(`strategy.py`, 현재 v1 Portfolio Strategy Agent의 실제 출력)은 서로 다른
model이며 아직 연결돼 있지 않다.** v1 Portfolio Strategy Agent는
`StockOpportunityAssessment`를 입력으로 받지 않는다 — 이 연결은 Recommendation
Engine이 완성된 이후의 확장 대상이다.

---

## 6. External Data / Service Layer

| Provider | Service | Domain Tool | 역할 | 상태 |
|---|---|---|---|---|
| ECOS(한국은행) | `app/services/ecos.py` | `EcosTools` | 기준금리/환율/KOSPI/KOSDAQ | 통합 완료 |
| OpenDART | `app/services/opendart.py` | `OpenDartTools` | 기업 재무제표/공시 | 통합 완료 |
| Kiwoom REST API | `app/services/kiwoom.py` | `KiwoomTools` | 시세/계좌/수급/종목·테마 카탈로그 | 통합 완료 |
| KIS(한국투자증권) | 없음 | 없음 | Forward 추정실적/투자의견(RE-03 조사 대상) | **미통합** — `app/config.py`에 `kis_app_key`/`kis_secret_key`/`kis_env` 설정 항목만 존재, 실제 `Service`/`Domain Tool` 코드 없음 |

Service Layer 공통 책임: HTTP 호출, 에러 처리, JSON parsing, 응답
정규화(vendor 원시 값 → `app/models`의 구조화된 값). `LLMService`
(`app/services/llm.py`)는 OpenAI Chat Completions 호출을 담당하며 3개
Agent(Market/Stock Research/Portfolio Strategy)가 공유한다.
`PortfolioAdapter`(`app/services/portfolio_adapter.py`)는 Kiwoom 계좌
데이터를 `PortfolioContext`로 변환한다.

Provider별 실측 조사 결과(어떤 필드가 신뢰 가능한지, rate limit이 얼마인지
등)는 이 문서의 범위가 아니다 — `docs/dev-log/`가 canonical이다.

---

## 7. Evaluation / Recommendation Architecture

RE-04(base architecture, Amendment 1 포함)와 RE-05(Recommendation Evaluation
Pipeline)가 FROZEN한 현재 구조다. **이 섹션은 구현 완료 상태와 아직 구현되지
않은 부분을 명확히 구분해서 기술한다.**

### 7.1 Deterministic Pipeline (현재 shape)

```text
DeterministicAnalysisResult          app/agents/stock_research/analysis.py (기존, IMPLEMENTED)
        ↓
NormalizedResearchData                app/evaluation/research_data_builder.py (IMPLEMENTED)
        ↓
FeatureEvaluationResult[]             app/evaluation/fundamental_evaluators.py +
        ↓                             app/evaluation/valuation_evaluators.py (IMPLEMENTED —
        ↓                             14개 registry feature 중 6개 evaluator)
Component Coverage                    app/evaluation/coverage_evaluator.py (IMPLEMENTED)
        ↓
Assembly                              app/evaluation/assembly.py (IMPLEMENTED)
        ↓
State Coverage (top-level)            app/evaluation/coverage_evaluator.py::
        ↓                             evaluate_recommendation_coverage (IMPLEMENTED)
FutureOpportunityEvidence             app/evaluation/coverage_evaluator.py::
        ↓                             evaluate_future_opportunity_evidence (IMPLEMENTED)
RecommendationEvaluationState          app/models/research_context.py (model 존재, IMPLEMENTED)
```

State Coverage와 FutureOpportunityEvidence는 둘 다 Component Coverage에서
파생되는 **서로 독립적인 sibling output**이다 — State Coverage는 FOE를
입력으로 받지 않는다(orchestrator는 State Coverage를 FOE보다 먼저 계산한다).

Evaluator 실행 순서(canonical, `orchestrator.py`):

```text
ROE → Operating Margin → Net Margin → Debt Ratio     (Fundamental)
    → Trailing PER → PBR                             (Valuation)
```

**이 building block들은 `app/evaluation/orchestrator.py`의
`run_first_deterministic_pipeline()`을 통해 First Deterministic Pipeline
Slice로 연결됐다(FROZEN, §7.2 참고)** — repository에 실재 확인함. 위
파이프라인은 이제 "따로따로는 동작이 검증된 부품들의 도면"이 아니라 실제로
실행되는 하나의 흐름이다. 단, `Recommendation Policy`는 여전히 구현되지
않았고(Step 1 Decision Eligibility primitive만 존재하며 orchestrator에 연결되지
않음, §7.4) `StockOpportunityAssessment`는 아직 이 pipeline의 output이 아니다 —
`Core Attractiveness`/`Market Confirmation`/`Risk`/`Confidence` producer도
아직 없다(§7.2/§7.3). top-level `coverage`(State Coverage)만 RE-05 Step J에서
구현됐다(§7.2).

### 7.2 First Deterministic Pipeline Slice — 확정된 architecture 경계

Orchestrator 구현은 First Deterministic Pipeline Slice로 완료/FROZEN됐고,
그 구현이 따르는 architecture 경계는 다음과 같다:

- **`family_assessments`(top-level)**: 각 component assembly가 만든
  `FeatureFamilyAssessment`를 재계산 없이, canonical component/family
  순서(`Component` enum 선언 순서 + `get_component_families()`)에 따라
  reference로 이어붙인 flat list다.
- **`core_attractiveness` = `None`, `market_confirmation` = `None`**: 이번
  slice는 이 두 aggregate/confirmation을 만들지 않는다 — 새로운 집계·판단
  semantics를 발명하지 않는다는 원칙 때문이다. 두 필드가 담을 정보는 이미
  `component_assessments`에 전부 존재하므로 정보 손실은 없다.
- **Orchestration ownership = `app/evaluation/orchestrator.py`**:
  Recommendation Evaluation Layer가 소유하며, Stock Research Agent 내부가
  아니다. vendor/service/MCP/LLM을 새로 import하지 않는다.
- **Executable evaluator = 실제 구현된 것만 실행**: RE-05 Post-Orchestration
  Architecture Review Step A~F(READY Evaluator Expansion) 이후 현재
  `RoeFeatureEvaluator`/`OperatingMarginFeatureEvaluator`/
  `NetMarginFeatureEvaluator`/`DebtRatioFeatureEvaluator`
  (`app/evaluation/fundamental_evaluators.py`) +
  `TrailingPerFeatureEvaluator`/`PbrFeatureEvaluator`
  (`app/evaluation/valuation_evaluators.py`, 신규) 6개다. Feature Registry
  (`app/evaluation/feature_registry.py`)에는 14개 feature identity가
  등록돼 있지만(개수 불변) evaluator가 없는 나머지 8개는 orchestrator가
  fake result를 만들지 않는다 — catalog identity만 있는 채로 남는다.
- **`coverage`(State Coverage) = `evaluate_recommendation_coverage()`**
  (`app/evaluation/coverage_evaluator.py`, RE-05 Step J): 이미 계산된 5개
  component `CoverageAssessment`만 입력으로 받는 top-level
  **evidence-coverage summary**다. Final Decision Eligibility/Recommendation/
  Attractiveness/Confidence/Risk가 아니다. `CoreAttractivenessAssessment
  .coverage`(Core Coverage, 미구현)와도 별개 인스턴스다.
  - `critical_path_satisfied` = Fundamental AND Valuation의
    `critical_path_satisfied`(Fundamental + Valuation critical evidence
    foundation). Forward/Flow/Market Confirmation은 참여하지 않는다 —
    **이 bool 자체는 Final Decision Eligibility가 아니다** — Decision
    Eligibility(§7.4)는 이 bool을 `policy_may_proceed`로 투영하고 FOE
    forward axis를 함께 담는 별도 policy-layer projection이다.
  - `coverage_status` = Fundamental/Valuation/Forward 3개 status만 사용:
    전부 SUFFICIENT → SUFFICIENT, 하나라도 INSUFFICIENT/UNKNOWN →
    INSUFFICIENT, 그 외 → PARTIAL. `coverage_percentage`는 항상 `None`.
  - Forward: critical bool에는 non-gating, `coverage_status`에는 기여한다.
    Forward의 alternative path(Event evidence) 판정은
    `future_opportunity_evidence`(tri-state SATISFIED/NOT_SATISFIED/
    UNKNOWN)에 별도로 보존된다 — Forward component coverage ≠
    FutureOpportunityEvidence ≠ Final Decision Eligibility.
  - Flow/Market Confirmation: 두 top-level axis 모두 non-gating이지만
    transparency bucket에는 포함된다. State Coverage에서 non-gating이라는
    것이 Recommendation Policy에 Market Confirmation producer가 불필요하다는
    뜻은 아니다.
  - bucket(`available_*`/`missing_*`/`optional_*`/`not_applicable`)/
    `source_failures`/`warnings`는 5개 component를 `Component` enum 선언
    순서로 이어붙이기만 한다(sort/dedup/prefix 없음). synthetic
    architecture warning을 추가하지 않는다.

### 7.3 현재 상태 요약

```text
Coverage Layer                = IMPLEMENTATION COMPLETE
Assembly Layer                = IMPLEMENTATION COMPLETE
Future Opportunity Evidence   = IMPLEMENTED
Evaluation Orchestration      = FIRST DETERMINISTIC PIPELINE SLICE COMPLETE / FROZEN
Feature Evaluator             = 6/14 IMPLEMENTED (READY Evaluator Expansion,
                                 RE-05 Post-Orchestration Architecture Review
                                 Step A~F)
Top-level Coverage            = IMPLEMENTED / VERIFIED / FROZEN (Step J)
Decision Eligibility          = Policy Step 1 primitive IMPLEMENTED / VERIFIED / FROZEN
                                 (orchestrator 미연결, 결과 비저장, §7.4)
Core Attractiveness           = NOT IMPLEMENTED (readiness PARTIAL)
Market Confirmation           = NOT IMPLEMENTED (readiness BLOCKED)
Risk                          = NOT IMPLEMENTED (readiness BLOCKED)
Confidence                    = NOT IMPLEMENTED (readiness BLOCKED)
Final AssessmentStatus        = NOT IMPLEMENTED
Recommendation Policy Step 2~8 = NOT IMPLEMENTED (policy consumer 없음; "Step"은 staged policy의
                                 stage 번호 — 아래 numbering 주석 참고)
Feature Normalization         = Ownership & Representation Contract FROZEN (§7.5)
                                 / implementation NOT STARTED (readiness NO, §7.6)
Calibration Readiness Audit   = COMPLETE / INDEPENDENT REVIEW PASS (§7.6)
Calibration Objective & Scope = Contract FROZEN (§7.7)
PIT Financial Evidence        = Contract FROZEN (§7.8) / implementation NOT STARTED (readiness NO)
OpenDART PIT Empirical Verif. = EXECUTION COMPLETE / INDEPENDENT REVIEW PASS / FINDINGS FROZEN (§7.9)
Evidence Identity & Persist.  = Contract DESIGN COMPLETE / REVIEW PASS / FROZEN (§7.10)
                                 / implementation PARTIAL (Evidence Identity Preservation slice만)
Evidence Identity Preservation = IMPLEMENTED / offline verification PASS / live integration
                                 NOT VERIFIED (6-evaluator first slice, 아래 결과 참고)
Numeric Calibration           = OPEN (workflow) / readiness BLOCKED (§7.6)
                                 / calibration NOT STARTED
Trustworthy V0 Contract       = DESIGN COMPLETE / INDEPENDENT REVIEW PASS / FROZEN (§7.11)
                                 / implementation IN PROGRESS (첫 slice source 구현) / §7.11.10 implementation
                                 acceptance NOT YET / Supported Feature Set 0 / USABLE V0 NOT YET
Trustworthy V0 Implementation = IN PROGRESS / NEXT: OpenDART Annual-Report Evidence Selection
                                 (SELECTION FROZEN / IMPLEMENTATION CONTRACT rev.1 FROZEN / SOURCE IMPLEMENTED ·
                                 SOURCE REVIEW PASS · COMMITTED `90d13b7` / live acceptance NOT VERIFIED,
                                 아래 selection / implementation contract / implementation checkpoint 블록)
```

Post-Decision-Eligibility Next Slice Selection(FROZEN):

```text
NEXT    Feature Normalization Ownership & Representation Contract
        — pre-calibration structural prerequisite
          (DESIGN COMPLETE / INDEPENDENT REVIEW PASS / FROZEN, §7.5)
SECOND  Calibration Data & Parameter Provenance Readiness Audit
        — read-only calibration-readiness audit
```

NEXT는 raw feature → normalized feature 경계(`FeatureEvaluationResult
.normalized_value`, 현재 6개 evaluator 전부 `None`)의 ownership/
representation/PolicyConfig boundary를 정하는 structural contract다 —
Numeric Calibration을 시작하지 않으며 numeric parameter/threshold/weight를
정하지 않는다(`Numeric Calibration = OPEN` 유지). contract(rev.1)는 §7.5에
FROZEN됐고 구현은 시작하지 않았다. 이어서 SECOND였던 Calibration Data &
Parameter Provenance Readiness Audit이 COMPLETE됐고(§7.6), post-audit NEXT였던
Calibration Objective & Scope Contract가 FROZEN됐다(§7.7). 이어서 NEXT였던
Point-in-Time Financial Evidence Contract가 FROZEN됐다(§7.8, 구현 NOT STARTED). 이어서
Post-PIT Critical Path Review가 COMPLETE됐고 NEXT가 선택됐다(아래). §7.8 말미의
dependency candidate 목록은 §7.8 freeze 시점 기준이다. 이어서 선택된 NEXT(OpenDART PIT
Empirical Verification)가 실행됐고 findings가 FROZEN됐다(§7.9) — 이 시점에 다음 작업 항목은
NOT SELECTED였다. 아래 selection 블록의 "EXECUTION NOT STARTED"는 선택 시점 기록이다. 이어서
Post-Empirical Critical-Path Review가 NEXT로 Calibration Evidence Identity & Persistence를
선택했고(아래 Post-Empirical selection 블록 — "DESIGN NOT STARTED"는 선택 시점 기록), 그 design
contract가 FROZEN됐다(§7.10, implementation NOT STARTED) — 이 시점에 다음 작업 항목은 NOT
SELECTED였다. 이어서 Post-§7.10 Critical-Path Review가 NEXT로 Evidence Identity Preservation을
선택했고(아래 Post-§7.10 selection 블록 — "IMPLEMENTATION NOT STARTED"는 선택 시점 기록), 그
slice가 구현됐다(아래 구현 결과, offline 검증 PASS / live integration NOT VERIFIED) — 이 시점에
다음 작업 항목은 NOT SELECTED였다. 이어서 read-only Post-EIP Critical-Path Review가 NEXT로 Trustworthy
V0 Product Boundary & Current-Runtime Evidence / Output Contract를 선택했다(아래 Post-EIP selection
블록 — "DESIGN NOT STARTED"는 선택 시점 기록), 그 contract가 rev.0 → rev.1 → rev.1-final을 거쳐
FROZEN됐다(§7.11, implementation NOT STARTED, USABLE V0 NOT YET) — 이 시점에 다음 작업 항목은 NOT
SELECTED였다. 이어서 read-only Trustworthy V0 Implementation NEXT Selection Review가 NEXT로 OpenDART
Annual-Report Evidence Selection을 선택했고(아래 V0 implementation selection 블록 — "IMPLEMENTATION
CONTRACT NOT STARTED"는 선택 시점 기록), 그 implementation contract가 rev.0 → rev.1을 거쳐 FROZEN됐다(아래
implementation contract 블록), 그 contract의 source 구현이 offline 검증 · source review PASS 후 commit됐다(아래
implementation checkpoint). **현재 NEXT는 SELECTION FROZEN / IMPLEMENTATION CONTRACT rev.1 FROZEN / SOURCE
IMPLEMENTED(commit `90d13b7`) / §7.11.10 implementation acceptance NOT YET / live NOT VERIFIED이고,
SECOND/THIRD는 NOT SELECTED다.**

**Post-PIT Critical Path Review → NEXT Selection (FROZEN, 선택 시점 기록 — 실행 결과는 §7.9)**
— work-selection contract이며 새 PIT architecture contract가 아니다(§7.8 semantics 불변):

```text
Post-PIT Critical Path Review   COMPLETE / INDEPENDENT REVIEW PASS
First unresolved blocker        H3 External Source Behavior
NEXT    OpenDART PIT Empirical Verification — SELECTION FROZEN / EXECUTION NOT STARTED
SECOND  NOT SELECTED
THIRD   NOT SELECTED
```

선택 근거: §7.8은 historical PIT evidence가 만족해야 할 조건을 정했지만, 그 contract를
운영하는 데 필요한 source-specific 사실(corrected-filing 동작, historical/original filing
재구성, 권위 있는 publication timestamp 출처, revision identity 동작)은 repository
evidence로 확립돼 있지 않다 — **empirical facts before architecture that depends on those
facts**. dependency analysis(선택 아님): `OpenDART PIT Empirical Verification → (factual
constraints) → Calibration Evidence Identity & Persistence` — 후자는 SECOND가 아니다.

Purpose: 과거 point-in-time 재무 evidence를 revision / reconstruction / publication
semantics 추측 없이 추론하는 데 필요한 OpenDART source-specific 사실을 확립한다. 산출물은
evidence/findings이며 PIT capability가 아니다(`Empirical Verification ≠ PIT Implementation`).

```text
MUST VERIFY
  M1  corrected-filing / revision behavior — fnlttSinglAcnt의 정정공시 전후 동작, 반환
      rcept_no가 식별하는 filing/version, 과거/원본 version 구별·도달 가능성, 정정본과
      이전 version의 개별 관찰 가능성 (consumer revision policy 선택 아님)
  M2  historical/original filing retrieval or reconstruction — 이전 filing/version의 재무
      evidence를 직접 조회 / 다른 OpenDART endpoint로 재구성 / filing metadata로 식별
      가능한지, 또는 조사한 interface로는 재구성 불가한지. 제약 대상: historical
      reconstruction path vs forward accumulation / immutable snapshot path
      (persistence architecture는 이 slice에서 선택하지 않음)
  M3  authoritative publication timestamp — 이를 노출하는 OpenDART source, field/source
      identity, precision, date-only vs time-of-day, timezone(있다면), historical filing에
      대한 가용성. FACT DISCOVERY만 범위이며 available_at POLICY는 범위 밖
SHOULD VERIFY (합리적으로 확립 불가 시 slice 완료를 막지 않음)
  S1  comparative-column equivalence samples — filing Y의 comparative(Y-1) vs filing Y-1
      직접 보고 값. sample equality → universal equivalence 일반화 금지, 차이 미관측 →
      restatement risk 없음 일반화 금지. 차이 검출은 유용한 positive evidence. P3는 결과와
      무관하게 FROZEN 유지
  S2  rcept_no structure / correction relationship — 형식, 날짜 prefix 가능성, 정정공시의
      별도 identifier 여부, identifier 간 관계. 형식만으로 문서화되지 않은 semantics 추론 금지
  S3  post-correction API result mutation — 정정 전 API 응답의 과거 관찰이 없으면 UNKNOWN
      허용, 현재 응답으로 확실성을 만들어내지 않음
  S4  period-field / reprt_code semantics — thstrm_dt / frmtrm_dt / bfefrmtrm_dt /
      reprt_code / fs_div / sj_div를 empirical 또는 권위 있는 source evidence가 뒷받침하는
      범위만. quarterly/half-year/TTM 계산 설계 없음
OUT OF SCOPE
  production source / test changes; PIT implementation / PIT schema implementation;
  Calibration Evidence Identity & Persistence design; persistence / dataset snapshot
  implementation; availability-policy / revision-selection policy; Feature Normalization
  implementation; Numeric Calibration; Recommendation Calibration; historical valuation
  reconstruction; price history integration; corporate-action semantics; Recommendation
  Policy Step 2+; large-scale all-company sweep; providers other than OpenDART
```

Evidence standard(향후 실행 시 finding마다): Question / Method / Source·endpoint / Sample /
Observed result / Evidence reference / Classification(`VERIFIED` / `CONTRADICTED` /
`UNKNOWN`, sample 기반이면 `VERIFIED — sample-bounded`) / Architecture implication /
Remaining uncertainty. 반례 부재를 universal verification으로 바꾸지 않는다.

Expected unlock(보장 아님): Calibration Evidence Identity & Persistence 설계에 필요한 source
사실, available_at policy를 위한 evidence, historical reconstruction 가능성·revision identity
가용성에 대한 evidence, P3 관련 sample evidence. 완료가 PIT implementation / Feature
Normalization implementation / Numeric Calibration / Recommendation Policy Step 2+를
READY로 만들지 않는다.

H1–H7 예상 영향(선택 자체는 아무것도 해소하지 않음 — newly resolved NONE): H2 may narrow ·
H3 direct empirical target, may clarify / narrow · H5 may provide evidence toward
persistence requirements · H6 may clarify available revision identity · H1 / H4 / H7 no
direct effect.

**Post-Empirical Critical-Path Review → NEXT Selection (FROZEN, 선택 시점 기록 — 설계 결과는 §7.10)**
— work-item 선택만 고정한다.
contract 설계·schema·persistence 구현·PIT capability·calibration readiness·numeric parameter
어느 것도 뜻하지 않는다:

```text
Post-Empirical Critical-Path Review   COMPLETE (+ targeted correction)
First route-independent blocker       H5/H6 — evidence / reference-snapshot identity & persistence
NEXT    Calibration Evidence Identity & Persistence
        — SELECTION FROZEN / DESIGN NOT STARTED / IMPLEMENTATION NOT STARTED
SECOND  NOT SELECTED
THIRD   NOT SELECTED
```

선택 근거: 가장 짧은 trustworthy vertical-slice 경로에서 route와 무관한 첫 미해결 blocker는
재현 가능한 evidence / reference-snapshot identity와 persistence semantics(H5/H6)다. current-
runtime 재현성과 향후 historical calibration 양쪽이 이를 요구하므로, 이후 Numeric Policy-Source /
First-Slice Scope 결정과 무관하게 유효하다. §7.9 findings로 source 동작이 확립돼, 다음을 가장하지
않고 설계할 수 있다: latest-only API output == historical evidence / `rcept_dt == available_at` /
reconstruction이 보편적으로 가능 / revision chain이 완전히 알려짐.

Future design scope(경계만 — 이 pass에서 설계하지 않음): per-evidence identity, observation
identity, source / filing / version identity, retrieval identity, availability identity
representation, revision identity representation(UNKNOWN 포함), reference-snapshot identity,
재현성에 필요한 최소 수준의 dataset identity, immutability semantics, lineage preservation,
empirically 확립된 hybrid capability(가능한 곳은 reconstruction + 필요한 곳은 forward
accumulation)의 표현.

```text
OUT OF SCOPE  physical database/storage implementation; database technology selection;
              full historical data warehouse; large-scale historical ingestion; historical
              valuation reconstruction; corporate-action / adjusted-price system; survivorship
              infrastructure; numeric calibration; normalization parameters; thresholds;
              weights; signal boundaries; Feature Normalization / Component Score·Signal /
              Core Attractiveness / Recommendation Policy implementation; Portfolio Strategy
              changes; UI implementation
NOT DECIDED   current cross-sectional reference statistic의 Semantic admissibility(OPEN);
              first trustworthy app version에 historical calibration이 필요한지; exact numeric
              policy source; first-slice terminal output — 모두 이후 Numeric Policy-Source /
              First-Slice Scope Decision의 몫(SECOND 아님)
```

Dependency context(frozen roadmap 아님 — K / B / N / S는 NEXT/SECOND/THIRD가 아니다):

```text
── architecture / identity / provenance readiness ──
A  Calibration Evidence Identity & Persistence        (selected NEXT)
     ↓
K  Numeric Policy-Source / First-Slice Scope Decision  (not selected)
     ↓
B  Parameter Provenance / PolicyConfig                 (not selected)
── actual numeric-policy readiness ──
N  admissible Semantic numeric policy/reference actually established + validated
     ↓
Feature Normalization implementation
     ↓
S  admissible aggregation weights / signal thresholds
     ↓
Component Score / Signal
```

`A + K + B ≠ numeric readiness` — PolicyConfig container/store나 reference-snapshot mechanism은
그 안의 숫자나 특정 reference statistic이 admissible함을 증명하지 않는다(§7.5 N9 / implicit
default 금지, §7.7 C14 / C15).

Product-state 구분(planning 용도):

```text
V0      Evidence → FeatureEvaluationResult — code/test에서 실행 가능(run_first_deterministic_
        pipeline), app/API 미연결, current/latest-known semantics only, evidence lineage 불완전
        (rcept_no / source column 소실). app 기능 완료 아님
V1/V1⁻  normalized decision-support surface — NOT YET FEASIBLE(architecture contract만으로는
        부족, admissible numeric semantics 필요)
V2      Core Attractiveness → staged Recommendation Policy → StockOpportunityAssessment —
        NOT YET FEASIBLE(추가 Recommendation-level evidence와 policy boundary 필요)
```

H1–H7: 선택으로 해소된 blocker 없음(newly resolved NONE). H5/H6은 미해결이며 이 NEXT의 주
대상이다. H2 NARROWED, H3 PARTIALLY EVIDENCED(RESOLVED 아님), H1/H4/H7 미해결.

**Recommendation Policy numbering 주석**: 두 번호 체계가 공존한다. (1) staged Recommendation
Policy candidate(dev-log 2026-08-29 §24.12): 1 Decision Eligibility → 2 Core Economic Assessment
→ 3 Opportunity State → 4 Event / Forward Context → 5 Priced-In → 6 Risk Review → 7 Correlation /
Conflict → 8 Coverage / Confidence Guardrail → 9 StockOpportunityAssessment. Stage 1은
IMPLEMENTED / VERIFIED / FROZEN(§7.4, orchestrator/consumer 미연결), 9-stage 구조는 FROZEN
candidate, stage 2–9는 NOT IMPLEMENTED, stage 2–8의 stage-level contract는 확정되지 않았다.
이 문서와 README의 "Step 2~8 NOT IMPLEMENTED"는 이 stage 번호를 가리킨다. (2) dev-log
2026-08-29 §24.x의 design/calibration "Step 1–12"(예: Step 2 Component Signal Threshold,
Step 3 Core Aggregation, Step 11 = staged policy 자체)는 별도 번호 체계다. 확정된 "8-step
Recommendation Policy"가 존재하는 것은 아니다.

**Post-§7.10 Critical-Path Review → NEXT Selection (FROZEN, 선택 시점 기록 — 구현 결과는 아래)** —
§7.10(parent frozen contract) 아래의 **구현 slice 선택만** 고정한다. 새 architecture contract가 아니며 §7.10을 변경하지 않는다.

```text
NEXT    Evidence Identity Preservation — SELECTION FROZEN / IMPLEMENTATION NOT STARTED
SECOND  NOT SELECTED
THIRD   NOT SELECTED
```

Objective: 기존 deterministic pipeline 전반에 provider-neutral evidence identity와 derivation lineage를
보존해, downstream consumer가 값이 어떤 evidence를 나타내는지, 언제 조회됐는지, source-reported인지
derived인지를 truthful하게 식별할 수 있게 한다. full §7.10 구현보다 좁다.

선택 근거: 현재 코드는 user-visible V0의 Minimum Trustworthy Product gate를 통과하지 못한다 — evidence
identity 소실, `retrieved_at` 부재, OpenDART filing / source-column identity 소실, comparative 값의
relabel, derived 값이 source/raw evidence처럼 보임. 이 slice가 그 trust blocker를 제거한다.

```text
IN SCOPE      provider-neutral Evidence Item Identity; retrieved_at; provider/source identity;
              provider version / filing anchor(실제 제공될 때만); observation identity; report
              identity / reporting basis / source column·term(해당 시); temporal precision 보존;
              source-reported vs derived 구분; derived formula identity/version; derived required-
              input evidence identity; provider/domain boundary → NormalizedResearchData →
              FeatureEvaluationResult provenance까지 identity 보존. exact schema는 고정하지 않음
OpenDART      interface가 실제 제공하는 것만: rcept_no(served filing anchor) / reprt_code / fs_div /
              sj_div / source column·term / observation period / provider·interface / retrieved_at.
              published_at / available_at / revision ordering / revision relationship을 만들지
              않는다. fnlttSinglAcnt는 rcept_dt를 제공하지 않는다 — 이후 interface가 제공하면 source
              precision 유지(date → timestamp 승격 금지)
Kiwoom        provider/interface / security·entity / measure / retrieved_at / current-runtime
              observation identity. version anchor는 실제 있을 때만(만들지 않음). 부재 표현
              (None / ABSENT / enum / optional)은 구현 세부로 고정하지 않음. PER/PBR/ROE는 provider가
              계산한 비율일 수 있으나 이 시스템이 derivation을 모르므로 formula/input lineage를 만들지
              않고 provider-reported 값으로 source identity와 함께 보존
Derived       SOURCE_REPORTED ≠ DERIVED. 현재 pipeline이 derive하는 값은 formula identity/version과
              required input evidence identity 보존(현재 derivation 위치는 사실로 기록 가능).
              lineage preservation ≠ canonical Derived Feature Value Ownership — ownership OPEN
              (analysis.py / evaluator / normalization 등 어느 것도 canonical owner로 선택하지 않음)
Comparative   later filing의 prior-year comparative 값이 해당 연도 original filing 값과 구별 불가능해지지
              않도록 identity 보존(§7.8 P3/P11). historical PIT selection / revision / restatement /
              equivalence policy는 구현하지 않음
OUT OF SCOPE  Evidence Basis Manifest implementation; reproducibility-status representation;
              evidence capture; physical persistence; database/storage selection; retention;
              hashing/content addressing; equivalence-check mechanism; Reference Snapshot
              implementation(universe / statistic / membership / persistence / construction policy
              미선택); availability derivation policy / available_at derivation; revision-selection
              policy; historical PIT implementation; historical calibration infrastructure;
              current-reference Semantic admissibility; numeric policy source; PolicyConfig work;
              calibration parameters; Feature Normalization implementation; component score/signal;
              Core Attractiveness; Recommendation Policy stages 2–9; StockOpportunityAssessment
              changes; V0 app/API wiring; changes to existing v1 LLM outputs; new evaluators
```

- **Reproducibility**: capture도 검증된 recovery/equivalence mechanism도 없으므로 reproducibility를
  **주장하지 않는다**. 그러나 NOT_ESTABLISHED status / enum / flag / CAPTURED / VERSION_ADDRESSABLE을
  구현·고정하지 않는다 — representation은 §7.10 아래 OPEN.
- **Evidence Basis Manifest**: 구현은 OUT OF SCOPE. §7.10 E12 semantic requirement는 그대로 FROZEN이며,
  이 slice는 이후 manifest가 참조할 identity를 만들고 보존할 뿐이다.
- **V0 관계**: `Evidence Identity Preservation → (identity / lineage trust blocker 제거) → trustworthy V0
  App Surface를 별도로 설계·wiring 가능`. 이 NEXT가 V0를 완료하지 않는다 — V0는 이후에도 app/API
  wiring, user-facing output contract, supported-output 검증, 기존 v1 LLM judgment에 대한 product
  decision이 필요하다.
- **기존 v1 LLM 출력(product-boundary finding)**: 현재 app은 RE-05 밖의 LLM investment judgment/action
  (thesis / scenario, BUY / ADD / HOLD / REDUCE / SELL / AVOID)을 이미 노출한다. 이 slice는 이를
  검증·수정·gating하지 않는다. trustworthy V0 출시 전 separation / labeling / gating / coexistence에
  대한 별도 product decision이 필요하다(지금 선택하지 않음).
- **K 관계**: K(Numeric Policy-Source / First-Slice Scope Decision)는 이 slice에 hard implementation
  dependency가 없다. K는 선택되지 않았다.
- **Blocker**: H6은 구현으로 이후 좁혀질 수 있으나 NOT RESOLVED, H5 unchanged / NOT RESOLVED, H1–H4 /
  H7 unchanged. 선택 freeze 자체로 해소된 blocker 없음(newly resolved NONE).

**Evidence Identity Preservation — 구현 결과** (IMPLEMENTED / independent implementation review PASS
WITH NON-BLOCKING NOTE / offline verification PASS / live integration verification not performed):

```text
구현(first slice)  provider-neutral semantic evidence identity(`app/models/evidence.py`)와 retrieval
                   fact 분리(`EvidenceItemIdentity` vs `EvidenceReference`, retrieved_at은 identity
                   equality/hash 밖); provider 응답 수신 직후 retrieved_at 기록(internal fetch 경로);
                   OpenDART: 선택된 row의 rcept_no / reprt_code / fs_div / sj_div / source term /
                   period notation, comparative(previous / before_previous)는 나중 filing의 rcept_no +
                   source term 유지; Kiwoom: ROE / PER / PBR은 SOURCE_REPORTED(Kiwoom / ka10001),
                   version anchor·formula lineage를 만들지 않음; derived: Operating Margin / Net
                   Margin / Debt Ratio는 DERIVED(formula identity/version + semantic input identity +
                   source input reference), FeatureValue.is_derived=True(raw slot 유지);
                   propagation: provider/service → internal evidence-aware tool 경로 → analyze →
                   NormalizedResearchData(FinancialFacts.evidence) → 6개 evaluator →
                   FeatureEvaluationResult.provenance.evidence; fail-fast: evidence 없는 builder 경로,
                   evaluator 소비 값의 evidence 부재, 잘못된 source/derived evidence 구성
Evaluator slice    ROE / Operating Margin / Net Margin / Debt Ratio / Trailing PER / PBR
                   (derived source input: revenue / operating_profit / net_income /
                   total_liabilities / total_equity) — 모든 재무 evidence가 identity를 갖는 것은 아님
미구현 / 유보      NRD history evidence propagation, YoY lineage, trend lineage, Evidence Basis
                   Manifest, capture, persistence/storage, reproducibility-status representation(OPEN),
                   Reference Snapshot, available_at derivation, revision-selection policy(OPEN),
                   historical PIT — §7.10 implementation은 PARTIAL
경계               reproducibility NOT CLAIMED(historical recoverability / snapshot reproducibility /
                   content equivalence / capture completeness / historical PIT eligibility를 확립하지
                   않음); retrieved_at ≠ available_at ≠ published_at — historical PIT NOT READY;
                   Derived Feature Value Ownership OPEN(현재 derivation 위치에 lineage를 기록할 뿐);
                   MCP public contract UNCHANGED; StockAnalysis v1 contract UNCHANGED; 기존 v1 LLM
                   judgment UNCHANGED(이 구현으로 검증·gating되지 않음)
검증               focused invariant tests 15 passed; offline suite 772 passed(live-API test 9개
                   deselect); ruff PASS; live integration NOT VERIFIED
Blocker            H1–H7 newly resolved NONE(H5 / H6 NOT RESOLVED)
```

상세 이력(review 지적 포함)은 `docs/dev-log/2026-09-26.md` §S.

**Post-EIP Critical-Path Review → NEXT Selection (FROZEN, 선택 시점 기록 — 설계 결과는 §7.11)** — work-item 선택만
고정한다. contract 설계·구현·wiring 어느 것도 뜻하지 않으며 새 architecture contract가 아니다
(§7.5 / §7.7 / §7.8 / §7.9 / §7.10 불변):

```text
Post-EIP Critical-Path Review   COMPLETE (read-only, repository unchanged) / independent review PASS
NEXT    Trustworthy V0 Product Boundary & Current-Runtime Evidence / Output Contract
        — SELECTED / SELECTION FROZEN / DESIGN NOT STARTED / IMPLEMENTATION NOT STARTED
SECOND  NOT SELECTED
THIRD   NOT SELECTED
```

선택 근거(baseline `c33f785`, 실제 code inspection): EIP는 선택된 6-evaluator slice에 대해 구현·
offline 검증됐지만 production app 경로에서 도달할 수 없다 — `run_first_deterministic_pipeline` /
`evaluate_decision_eligibility`는 `app/`에 production caller가 없고, evidence-aware retrieval
(`get_stock_info_with_evidence` / `get_key_financials_history_with_evidence`)은 production
orchestrator가 사용하지 않으며, `StockResearchOrchestrator.run()`은 deterministic analysis에 evidence를
전달하지 않는다. user-facing 투자 판단은 여전히 기존 v1 LLM 출력이다. 즉 trustworthy evidence
machinery는 있지만, 그것이 user-visible product가 되는 방식을 정한 frozen product / runtime
contract가 없다 — 이것이 Minimum Trustworthy Product까지의 첫 blocker다.

```text
Evidence Identity Preservation                     DONE for selected first slice
  ↓
Trustworthy V0 Product Boundary
& Current-Runtime Evidence / Output Contract       ← SELECTED NEXT
  ↓
future V0 wiring / integration                     NOT SELECTED
  ↓
Minimum Trustworthy Product
```

numeric-semantic path(K → Parameter Provenance / PolicyConfig → admissible Semantic numeric policy/
reference → Feature Normalization → component aggregation / signal → Core Attractiveness → staged
Recommendation Policy → StockOpportunityAssessment)는 재정의하지 않으며 불필요하다고 판단하지 않는다.
선택 판단은 그 path가 첫 usable Minimum Trustworthy Product까지의 가장 짧은 blocker가 아니라는 것뿐이다.

Objective: production wiring 구현 전에, trustworthy / auditable / 현재 지원되는 RE-05 정보만 사용자에게
노출하는 데 필요한 product 경계와 current-runtime evidence 경계를 정의한다. 이 작업은 UI / output-schema
작업으로 축소되지 않는다 — Product Boundary · Current-Runtime Evidence Selection Boundary · Output
Contract를 포함한다(올바른 output surface라도 runtime이 잘못된 evidence를 고르면 trustworthy하지 않다).

이후 design이 답해야 할 질문(**이 selection에서 답하지 않음**): V0가 노출할 수 있는 것 / 노출하면 안 되는
것 / UNKNOWN·NOT AVAILABLE인 것; 어떤 current-runtime evidence가 eligible한가; V0에서 evaluation_as_of의
의미와 retrieved_at과의 관계; applicable / latest-known report와 current year / reporting period 선택;
source-reported vs derived evidence 표현; output에 동반할 최소 evidence / provenance 정보; 재현성 부재의
정직한 표현; 기존 v1 LLM judgment와 V0의 관계; V0 production wiring 경계; V0 usable 판정에 필요한
acceptance evidence.

```text
CANDIDATE DESIGN TOPICS (결정 아님 — 모두 DESIGN OPEN)
  A  V0 user-visible surface — 후보 입력: 구현된 6개 evaluator 값, source-reported vs derived origin,
     evidence provenance, Coverage, Future Opportunity Evidence, 의미상 적절한 경우 Decision
     Eligibility, UNKNOWN / NOT AVAILABLE. 실제 노출 여부 OPEN
  B  numeric judgment boundary — 후보 원칙: required numeric policy path 이전에 numeric
     interpretation / threshold / score / attractiveness classification / recommendation을 만들지
     않는다(기존 frozen architecture의 제약). exact V0 terminal output OPEN
  C  기존 v1 LLM output(investment_thesis / scenarios / BUY·ADD·HOLD·REDUCE·SELL·AVOID)과 V0의 관계 —
     hidden / retained / legacy·experimental label / separated / gated 중 어느 것도 선택하지 않음.
     public StockAnalysis / presentation contract 영향은 design 중 명시적으로 review
  D  current-runtime evidence semantics — evaluation_as_of, retrieved_at, report / reporting-period
     선택, current-runtime eligibility, history / YoY / trend 제외 또는 표현. historical PIT 구현 아님
  E  evidence / reproducibility representation — §7.10과 양립하는 최소한의 정직한 표현. Evidence Basis
     Manifest / capture / persistence / Reference Snapshot / historical PIT / full reproducibility
     infrastructure 구현을 요구하지 않음(§7.10 전체를 V0로 자동으로 끌어오지 않음)
  F  wiring boundary — 기존 StockResearchOrchestrator 수정 vs 별도 V0 / RE-05 execution path, 선택 없음
  G  acceptance boundary — usable 판정 evidence 정의. live evidence-path verification 고려 예정.
     pytest marker / environment variable / CI job / live-test gating mechanism은 구현 선택이며
     여기서 선택·구현하지 않음. live-test gating은 별도 maintenance candidate, NOT SELECTED
NON-GOALS  V0 implementation / wiring; API·UI implementation; live-test gating implementation; live API
           verification; Evidence Basis Manifest / capture / persistence·storage / Reference Snapshot /
           historical PIT / revision-selection policy implementation; numeric calibration; K
           design·implementation; PolicyConfig; Feature Normalization implementation; component
           score / signal; Core Attractiveness; Recommendation Policy stages 2–9;
           StockOpportunityAssessment implementation; new evaluators
```

- **Frozen architecture 관계**: §7.8 FROZEN(current-runtime boundary 준수) · §7.10 FROZEN(implementation
  PARTIAL) · §7.5 FROZEN(implementation NOT STARTED) · §7.7 FROZEN · RE-04 StockOpportunityAssessment
  contract 불변. selection 시점 architecture-contract 변경 필요: NONE. 이후 design이 기존 frozen
  contract와의 실제 모순을 발견하면 STOP하고 명시적으로 보고한다(frozen contract를 조용히 고쳐 쓰지 않음).
- **불변 상태**: EIP IMPLEMENTED / VERIFIED OFFLINE · §7.10 implementation PARTIAL · reproducibility NOT
  CLAIMED · historical PIT NOT READY / NOT IMPLEMENTED · Derived Feature Value Ownership OPEN · READY
  evaluators 6/14 · live integration NOT VERIFIED. 이 선택으로 해소된 항목은 없다(H1–H7 newly resolved
  NONE).

상세 review 근거는 `docs/dev-log/2026-09-27.md` §J–§K.

**Trustworthy V0 Implementation → NEXT Selection (FROZEN, 선택 시점 기록 — implementation contract는 아래 블록)** — §7.11 FROZEN contract의
구현 순서에서 NEXT 하나만 고정한다. 구현·implementation contract·Q2b / Q3 해소를 뜻하지 않으며 새
architecture contract가 아니고, 이후 전체 구현 순서를 고정하지 않는다(§7.4–§7.11 불변):

```text
Trustworthy V0 Implementation NEXT Selection Review   COMPLETE (read-only, repository unchanged)
                                                       / independent review PASS / freeze readiness YES
NEXT    OpenDART Annual-Report Evidence Selection
        — SELECTED / SELECTION FROZEN / IMPLEMENTATION CONTRACT NOT STARTED / IMPLEMENTATION NOT STARTED
SECOND  NOT SELECTED
THIRD   NOT SELECTED
```

Canonical scope(하나의 coherent implementation slice — Q2b와 Q3를 별도 NEXT로 나누지 않는다):

```text
1  classified annual-evidence retrieval result (Q2b)
2  finite, calendar-assumption-free annual-report candidate generation (Q3)
3  positive-only fallback
4  per-candidate selection trace

candidate retrieval → classified result → positive REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE?
                                            YES → next candidate
                                            NO  → stop / fail
                    → selection trace
```

선택 근거(baseline `78ba30d`, 실제 code inspection): `OpenDartService.fetch_financial_accounts()`
(`fnlttSinglAcnt.json`)는 `status != "000"`을 모두 하나의 `ValueError`로 처리하고, 사업연도 기본값은
`now(UTC).year - 1`(v1 supervisor `_default_business_year`)이며 연간 보고서 후보는 하나, fallback은 없다.
따라서 현재 구현은 §7.11.4의 `EVIDENCE_RETURNED` / `REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE` / `FAILURE`
구분을 만족할 수 없고 positive-only fallback을 안전하게 구현할 수 없다. 또한 production 코드는
`*_with_evidence` / `analyze(..., evidence=...)` / `run_first_deterministic_pipeline`을 호출하지 않는다 —
EIP capability는 존재하고(설계 결함 아님), V0 경로의 production reachability가 없을 뿐이다.

Provider-first over V0-skeleton-first(이 repository 기준): 현재 Supported Feature Set = 0이므로
지금의 V0 skeleton은 OpenDART evidence 경로를 실행하지 않아(§7.11.1: Supported Feature Set과 entity
식별에 필요한 provider만 호출) 가장 이른 trust blocker를 제거하지 못한다. OpenDART annual-evidence
selection은 (a) Supported Feature Set ≥ 1까지의 현재 가장 짧은 경로, (b) OpenDART-derived candidate
feature, (c) V0 report-selection evidence가 공유하는 가장 이른 실제 dependency다.

- **Q12 OPEN — NEXT에 포함하지 않음**: derived-feature support readiness(amount absence semantics ·
  currency / unit 보존 · derived-input coherence · S4 / S5)에 이후 필요하다. NEXT는 currency semantics /
  `"-"` semantics / amount unit semantics / full absence-reason modeling / derived feature support
  determination으로 확장되지 않는다. 예외: Q2b retrieval classification이 malformed / shape / integrity
  failure를 positive unavailability와 구별해야 하는 범위의 failure classification은 NEXT에 속한다 — 이것이
  Q12 전체를 해소하지 않는다.
- **Q1 OPEN — Kiwoom-first 미선택**: 현재 ka10001 기반 ROE / PER / PBR은 S2 / S3 / S4가 미해결이며,
  특히 검사한 응답 경로는 trustworthy V0 supported feature에 필요한 period semantics를 확립하지 않는다.
- **First-supported-feature direction(방향일 뿐 feature 선택 아님)**: 현재 repository evidence상
  Supported Feature Set ≥ 1까지의 가장 짧은 알려진 trustworthy 경로는 OpenDART-derived feature를
  통한다(현재 candidate: Operating Margin / Net Margin / Debt Ratio). 셋 중 무엇이 먼저인지는 선택하지
  않았고 어느 것도 support-ready로 판정하지 않았다. 현재 SUPPORTED feature는 없다(Supported Feature
  Set 0).

Entry conditions: 구현 전에 짧은 implementation contract를 작성하고 independent review를 받는다. 그
contract가 최소한 답할 것(**이 selection에서 답하거나 고정하지 않음**): A. Q3 candidate-generation
approach(검토 예: fiscal / closing-month 기반, filing-list 기반 — 선택 없음) · B. classified retrieval
result type(위치 · naming · failure taxonomy) · C. legacy v1 동작 보존 방식 · D. status semantics에 쓰는
authoritative OpenDART documentation / evidence · E. offline vs live acceptance 경계.

Exit conditions(의도 — 구현되지 않음): offline acceptance는 status / HTTP / parse / shape classified
behavior, positive로 분류된 `REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE` 이후에만 fallback, FAILURE 이후
fallback 없음, finite candidate generation, V0 selection 경로에 암묵적 current-year-minus-one 가정 없음,
완전한 per-candidate selection trace, 근거 없는 latestness 주장 없음, legacy v1 regression 보호, ruff
PASS를 포함한다. Q2b / Q3 해소는 offline code만으로 되지 않는다 — official / documented evidence +
승인된 live verification이 필요하며, 그 전까지 구현은 semantics가 확립되지 않은 곳에서 fail closed한다.

```text
OUT OF SCOPE  Q12 broader value semantics; Q1 Kiwoom semantics; Feature Support Determination; V0
              Evaluation Record implementation; Evidence Basis Manifest projection; dedicated V0 execution
              path; V0 API; Supported feature promotion; Feature Normalization; Numeric Calibration; Core
              Economic Assessment; Decision Eligibility wiring; Recommendation Policy stages; portfolio
              logic; automatic trading; historical PIT reconstruction; persistent evidence storage;
              Reference Snapshot implementation; LLM judgment; legacy v1 redesign; live-test gating
              mechanism
```

Legacy v1은 별도로 review·승인된 변경이 없는 한 이후 NEXT 구현으로 동작이 바뀌지 않는다.

```text
NEXT selection FROZEN ≠ NEXT implementation started ≠ Q2b resolved ≠ Q3 resolved
                      ≠ feature SUPPORTED ≠ usable V0

현재   Trustworthy V0 Contract FROZEN / Trustworthy V0 Implementation NOT STARTED /
       Q2b · Q3 · Q12 · Q1 OPEN / Supported Feature Set 0 / live integration NOT VERIFIED / USABLE V0 NO
```

선택으로 해소된 항목은 없다(H1–H7 newly resolved NONE). 상세 review 근거는 `docs/dev-log/2026-09-27.md` §M.

**OpenDART Annual-Report Evidence Selection — Implementation Contract (FROZEN, rev.1)** — 위 NEXT의 구현
contract다(아래 status의 "Implementation NOT STARTED"와 말미 "freeze 시점" 행은 freeze 시점 기록 — 구현 상태는 아래
implementation checkpoint). 구현을 뜻하지 않으며 새 architecture contract가 아니다 — §7.4–§7.11 위에서 동작하고 그것들을
변경하지 않는다:

```text
Status          DESIGN COMPLETE / INDEPENDENT REVIEW PASS / PRE-FREEZE VERIFICATION PASS / FROZEN (rev.1)
Implementation  NOT STARTED (아래 code surface는 planned — 해당 file / symbol은 아직 존재하지 않는다)
Q2b / Q3        OPEN (contract 구조만 고정 — provider admissibility / label semantics 미해소)
```

*Result taxonomy (Q2b)* — 연간 보고서 후보 하나(`corp_code`, `bsns_year`, `reprt_code=11011`)의 조회 결과는
정확히 하나로 분류된다:

```text
EVIDENCE_RETURNED                       status 000 + integrity 통과 — accounts + tz-aware retrieved_at
REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE   provider status가 positive-unavailability admission set에 속함
FAILURE                                 그 외 전부. failure reason:
  TRANSPORT            transport 오류(timeout / connect)
  HTTP_STATUS          non-2xx
  MALFORMED_RESPONSE   non-JSON · top-level이 object 아님 · status 없음 · 000 + list 없음 / list 아님 ·
                       000 + 빈 list(문서상 "데이터 없음"은 013이므로 문서에 없는 조합 — fail closed)
  PROVIDER_STATUS      admission set 밖의 non-000 status(모르는 코드 포함) — provider status / message 원문 보존
  INTEGRITY            row 필수 필드 누락 · 금액 파싱 실패 · row bsns_year / reprt_code ≠ 요청
```

- 분류되지 않는 예외(programming error)는 FAILURE로 숨기지 않고 그대로 raise한다(fail closed).
- **Positive-unavailability admission set = EMPTY**(시작 상태). 따라서 현재 013 → `FAILURE(PROVIDER_STATUS)` →
  fallback 없음. admission set 확장은 official evidence + 승인된 live contrast + 별도 review가 필요하며, 그
  경우에도 결론은 전제 조건(OpenDART 목록에서 해석된 corp_code · bsns_year ≥ 2015 · reprt_code 11011) 아래의
  좁은 admissibility 결정이지 "013이 보편적으로 연간 evidence 부재를 뜻한다"가 아니다. 표본이 전제로 배제할
  수 없는 overload를 보이면 admission은 비활성으로 유지한다.
- 복수 `rcept_no`는 그 자체로 FAILURE가 아니다. row마다 자기 `rcept_no`를 보존하고, 성공 응답을 하나의 filing
  identity로 요약하지 않는다. 파생 입력의 filing-anchor 일관성은 기존 frozen S5(§7.11.2)가 소유한다(S5 불변).
- Q12(금액 / 통화 / `"-"` / 결측 사유 의미)는 해소하지 않는다 — 금액 파싱 실패를 INTEGRITY로 fail closed할 뿐이다.

*Fallback / selection* — positive UNAVAILABLE 다음에만 다음 후보로 진행한다:

```text
candidates = generate(candidate_basis_instant, lookback_years)
if candidates 비어 있음 → FAILED (조회 0회, trace 비어 있음)
for candidate in candidates (결정론적 순서):
    retrieve → trace에 기록
    EVIDENCE_RETURNED                      → SELECTED, 중단
    FAILURE                                → FAILED, 중단 (fallback 없음)
    REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE  → 다음 후보
소진 → NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES
```

- 보고서가 반환됐지만 feature 계정 / 값이 없거나 일부 statement만 있는 것은 EVIDENCE_RETURNED이며 annual-report
  fallback 사유가 아니다(feature 단위 문제).
- `NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES`(§7.11.4 / §7.11.6 어휘)는 기록된 후보 집합 안에서
  EVIDENCE_RETURNED가 없었다는 것만 뜻한다 — `NO_ANNUAL_REPORT_EVIDENCE_EXISTS` 같은 전역 부재가 아니며, provider
  하한까지 탐색해도 그 범위에 한정된다. admission set이 비어 있는 동안 이 상태는 실제 조회에서 도달하지 않는다.
- 후보 순서는 탐색 순서일 뿐 latest / latest corrected / original / final / best filing을 뜻하지 않는다.

*Candidate generation (Q3 — Bounded Descending bsns_year Probe)*:

```text
inputs      candidate_basis_instant  명시적, tz-aware(아니면 거부) — evaluation_as_of 아님, availability 의미 없음
            lookback_years           필수, 호출자 제공, 기본값 없음, 정수 ≥ 1(아니면 거부)
basis_year  candidate_basis_instant의 UTC 연도
candidates  basis_year부터 내림차순 연속, 최대 lookback_years개, 2015 미만 제외(provider 하한) — 유한 · 결정론적
            basis_year < 2015 → 후보 0개
금지         hidden now() · 암묵적 current-year-minus-one 기본값 · fiscal 달력(12월 결산 등) 가정
```

- **lookback_years 값은 OPEN**이며 향후 V0 실행 경로의 policy가 소유한다 — OpenDART 의미가 아니고, 충분성이나
  탐색 완전성을 보증하지 않는다. offline test의 구체 값(예: 3)은 fixture일 뿐 production 값이 아니다.
- 첫 후보가 basis_year 자체인 이유는 bsns_year 라벨 관례를 가정하지 않기 위해서다. 이 설계는 "bsns_year 라벨은
  basis UTC 연도를 넘지 않는다"는 가정에 기대며 이 가정은 미확립(Q3)이다 — 틀리면 후보를 놓칠 뿐 최신성 주장이
  없으므로 잘못된 주장은 생기지 않는다.
- **§7.11.4 부합 조건**: 후보 생성의 §7.11.4 완전 부합("검증된 provider / report-period semantics")은 위 라벨 상한
  가정을 포함한 Q3 해소에 달려 있다. Q3 해소 전까지 구현은 §7.11.10 implementation acceptance를 주장해서는 안 된다
  (§7.11 불변).

*Selection record / trace* — selection 결과는 탐색 범위와 결과를 식별할 수 있게 `candidate_basis_instant` ·
`lookback_years` · `candidates` · `trace` · 종료 상태(SELECTED / `NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES`
/ FAILED) · 선택된 retrieval을 담는다. trace는 시도한 후보마다 정확히 한 번, 후보 순서대로(후보 목록의 prefix)
candidate · outcome · provider status / message 원문 · failure reason / detail · (EVIDENCE_RETURNED일 때)
`retrieved_at`을 기록하며 결론(최신성, 사유 추정)을 넣지 않는다. 마지막을 제외한 trace entry는 모두 positive
UNAVAILABLE이다. 후보가 lookback_years보다 적으면 provider 하한으로 잘린 것이다. 이 NEXT는 `evaluation_as_of`를
만들거나 정의하지 않는다(§7.11.3 소유) — 이후 record는 `candidate_basis_instant ≤ retrieved_at ≤
evaluation_as_of`를 지킨다. V0 Evaluation Record는 이 NEXT가 만들지 않는다.

*Planned code surface / placement* (구현 전 — 존재하지 않음):

```text
app/models/annual_evidence.py   provider-neutral 어휘: AnnualEvidenceOutcome · AnnualEvidenceFailureReason ·
                                AnnualSelectionStatus · AnnualSelectionFailure
app/services/opendart.py        provider-specific: OpenDartAnnualRetrieval · 빈 positive-unavailability admission
                                set · OpenDartService.retrieve_annual_accounts(corp_code, business_year)
app/mcp/opendart_tools.py       OpenDART candidate / selection / trace: provider 하한 상수(2015) · AnnualCandidate ·
                                AnnualSelectionTraceEntry · AnnualEvidenceSelection · 후보 생성 함수 ·
                                OpenDartTools.select_annual_evidence(corp_code, *, candidate_basis_instant,
                                lookback_years)
tests/test_opendart_annual_selection.py

dependency  app/models ← app/services ← app/mcp (기존 방향, 순환 · service→mcp 의존 없음)
```

`AnnualSelectionFailure`(trace가 비었는지로 도출 가능)와 `AnnualCandidate.ordinal`(tuple 위치로 도출 가능)은
의미상 필수가 아닌 implementation-detail 후보이며, 도출 가능한 정보가 trace / 결과에 남는 한 구현에서 단순화할
수 있다 — contract 의미는 이 둘에 의존하지 않는다.

*Legacy v1 isolation* — `fetch_financial_accounts` / `get_financial_accounts` / `get_company_financials` /
`get_key_financials` / `get_key_financials_history` / `get_key_financials_history_with_evidence` / `_parse_amount` /
`_convert_financial_account`(재사용만) / `_select_fs_div` / `_default_business_year` / `StockResearchOrchestrator`
/ supervisor · MCP server · API · v1 schema는 변경하지 않는다. 새 조회는 legacy 요청 코드를 refactor하지 않고 별도
method로 둔다. 새 symbol의 production caller는 0이다(V0 wiring 범위 밖). LLM routing 변경 없음.

*Official OpenDART evidence (class B — guide 원문 확인, API 호출 없음; §7.9 sample-bounded empirical evidence와
별개)*:

```text
fnlttSinglAcnt   bsns_year "사업연도(4자리) ※ 2015년 이후 부터 정보제공" · 11011 = 사업보고서 · rcept_no =
                 접수번호(14자리) · fs_div OFS 재무제표 / CFS 연결재무제표 · currency "통화 단위"
                 NOT ESTABLISHED: bsns_year ≤ basis 연도 · 응답당 단일 rcept_no · 반환 정정 version ·
                 비12월 결산 라벨 규칙
status 013       원문 메시지 "조회된 데이타가 없습니다." — cause semantics NOT ESTABLISHED(API 공통 메시지 표)
기업개황          acc_mt = "결산월(MM)" — 기준 시점 / 변경 이력 / bsns_year 매핑 NOT ESTABLISHED (Option A 미채택)
공시검색          A001 = 사업보고서 · last_reprt_at(N이면 정정보고서 포함 전체 검색) · sort 기본 접수일자 desc ·
                 report_nm = 공시구분+보고서명+기타정보 · rcept_dt = 공시 접수일자
                 NOT ESTABLISHED: report_nm → bsns_year 파싱 · rcept_no를 fnlttSinglAcnt에 지정하는 요청(요청 인자에
                 없음) · latest / original / final 의미 (Option B 미채택)
```

*Acceptance boundary*:

- offline(구현 시): 13개 status code + 모르는 코드 · transport / HTTP / malformed / integrity 분류, 013 + 빈 admission
  set → FAILURE, 주입된 admission set → UNAVAILABLE(분류 경로만 검증), 후보 생성(명시적 bound · 하한 clip · 내림차순
  · 0개 · tz-naive / 잘못된 lookback_years 거부), UNAVAILABLE → 다음 / FAILURE → 중단 / RETURNED → 중단, 소진 결과와
  기록된 탐색 범위, trace 완전성 · 순서, 복수 rcept_no → EVIDENCE_RETURNED(row별 보존), 보고서 반환 + 계정 부재 →
  fallback 없음, legacy suite 무수정 PASS(013 → ValueError 유지), ruff PASS.
- live(별도 명시 승인 시에만, 전부 sample-bounded): Q2b — 013 원인 대조(진행 중 연도 · 존재하지 않는 corp_code · 형식
  오류 요청 · 2015 미만); Q3 — bsns_year 라벨 동작(비12월 결산 포함); rcept_no — 성공 응답의 receipt identity 집합
  관찰. 표본 관찰은 보편적 provider 사실이 되지 않는다.
- Q2b 해소 = official 인용 + live contrast + 좁은 admissibility 결정 + admission set 변경의 별도 review + offline
  PASS. Q3 해소 = 후보 생성 구조의 offline PASS + 라벨 상한 가정의 문서 또는 sample-bounded live 지지 + review —
  lookback_years 값 선택은 Q3 해소에 필요하지 않으며, Q3 해소는 충분한 lookback · 탐색 완전성 · 보편적 라벨 의미를
  확립하지 않는다.

```text
OPEN        Q2b · Q3 · Q12 · Q1 · lookback_years production 값(향후 V0 policy)
NON-GOALS   Q12 value semantics; Q1 Kiwoom; Feature Support Determination; V0 Evaluation Record; Evidence Basis
            Manifest projection; V0 execution wiring; V0 API; SUPPORTED 승격; Normalization; Calibration; Core
            Assessment; Decision Eligibility wiring; Recommendation Policy; Risk / Confidence; portfolio; historical
            PIT; persistence; Reference Snapshot; LLM routing / judgment; legacy v1 redesign; 자동매매; 범용 live-test
            gating; corp_code 해석 변경; CFS / OFS 선택 변경; 공시검색 · 기업개황 wrapper; S5 일관성 검사 구현
freeze 시점  Implementation Contract rev.1 FROZEN / NEXT implementation NOT STARTED / Supported Feature Set 0 /
            live integration NOT VERIFIED / USABLE V0 NO / SECOND · THIRD NOT SELECTED
```

H1–H7 newly resolved NONE. 설계·검증 이력은 `docs/dev-log/2026-09-27.md` §N.

**OpenDART Annual-Report Evidence Selection — Implementation checkpoint** — 위 frozen contract rev.1의 source
구현 기록이다. contract를 변경하지 않으며 새 architecture decision이 아니다:

```text
Implementation commit   90d13b7d763b40c6bbc452a2b7f3207f0e7276db  feat: implement OpenDART annual evidence selection
State                   SOURCE IMPLEMENTED / OFFLINE VERIFIED / SOURCE REVIEW PASS / COMMITTED / PUSHED
Implemented             1 classified annual-evidence retrieval   OpenDartService.retrieve_annual_accounts
                        2 bounded candidate generation            _annual_candidates
                        3 positive-only fallback selection + trace OpenDartTools.select_annual_evidence /
                                                                  AnnualEvidenceSelection
                        4 offline contract tests                  tests/test_opendart_annual_selection.py
                        provider-neutral 어휘는 app/models/annual_evidence.py
Verification            focused 73 passed · offline suite 845 passed(live 9개 node ID로 deselect) ·
                        full suite NOT RUN · ruff PASS · git diff --check PASS · live API 호출 없음
Production callers      0 (V0 wiring 범위 밖)
```

- 구현된 의미는 contract와 같다: 결과는 EVIDENCE_RETURNED / REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE / FAILURE,
  positive-unavailability admission set은 비어 있어 013 → `FAILURE(PROVIDER_STATUS)`, fallback은 positive
  UNAVAILABLE 다음에만, 후보는 명시적 `candidate_basis_instant` + 호출자 필수 `lookback_years`(기본값 없음, production
  값 없음)로 만든 유한 · 결정론적 내림차순(하한 2015), 소진은 검사한 후보 안에서만, 복수 `rcept_no`는 row별 보존(그
  자체로 실패 아님), `retrieved_at`은 유효한 EVIDENCE_RETURNED가 확립된 뒤에만 tz-aware UTC로 기록, legacy v1 불변.
- contract가 판단을 남긴 경우의 구현 분류(source review에서 accepted): list 안 non-object row · non-string status →
  MALFORMED_RESPONSE, 필수 필드 null / invalid · non-string 금액 → INTEGRITY, `httpx.RequestError` 전체 → TRANSPORT.
  `AnnualCandidate.ordinal`은 두지 않았고(tuple 위치로 표현) `AnnualSelectionFailure`는 두었다(trace와 일치 강제).
- 이 구현은 provider 의미를 확립하지 않는다 — Q2b(어떤 status가 positive unavailability인지) · Q3(provider /
  report-period semantic acceptance, 라벨 상한 가정) · Q12 · Q1은 OPEN이다. 후보 생성 mechanism이 구현됐다고 Q3가
  해소되지 않는다.

```text
source implementation (this NEXT)       IMPLEMENTED / OFFLINE VERIFIED / SOURCE REVIEW PASS
§7.11.10 implementation acceptance      NOT YET (Q2b / Q3 해소 · 승인된 live evidence 등 frozen 요건 미충족)
live acceptance                         NOT VERIFIED
not implemented                         Feature Support Determination · V0 Evaluation Record · Evidence Basis Manifest
                                        projection · V0 execution wiring · V0 API
현재                                    Supported Feature Set 0 / USABLE V0 NO / SECOND · THIRD NOT SELECTED
```

구현 · review 이력은 `docs/dev-log/2026-09-27.md` §O.

RE-04/RE-05의 상세 결정 과정, contract 확정 근거는 `docs/dev-log/
2026-08-29.md` §1~§51(Post-Orchestration Review Step A~J는 `docs/dev-log/
2026-09-07.md`, Final Decision Eligibility는 `docs/dev-log/2026-09-25.md`,
Post-Decision-Eligibility Next Slice Selection / Feature Normalization Contract /
Calibration Readiness Audit / Calibration Objective & Scope Contract /
Point-in-Time Financial Evidence Contract / Post-PIT Critical Path Review /
OpenDART PIT Empirical Verification / Post-Empirical Critical-Path Review /
Calibration Evidence Identity & Persistence Contract / Post-§7.10 Critical-Path Review /
Evidence Identity Preservation 구현은
`docs/dev-log/2026-09-26.md`, Post-EIP Critical-Path Review / NEXT Selection /
Trustworthy V0 Contract 설계·freeze / Trustworthy V0 Implementation NEXT Selection / OpenDART
Annual-Report Evidence Selection Implementation Contract / 구현 checkpoint는 `docs/dev-log/2026-09-27.md`)과
`app/models/recommendation.py`/`research_context.py` docstring이 canonical이다.

### 7.4 Recommendation Policy Step 1 — Decision Eligibility (primitive)

```text
First Deterministic Pipeline (orchestrator.py)
        ↓
RecommendationEvaluationState
  ├─ coverage                     (State Coverage)            ─┐ upstream sibling
  └─ future_opportunity_evidence  (FOE, tri-state)            ─┘ producer outputs

[미래 Recommendation Policy consumer — 아직 없음]
        ↓
evaluate_decision_eligibility(coverage, future_opportunity_evidence)
        ↓
DecisionEligibility(policy_may_proceed, forward_requirement)   transient
```

- **소유**: `app/evaluation/decision_eligibility.py`. orchestrator는 이 함수를
  호출하지 않는다 — 결과를 저장할 곳이 없고 policy consumer가 아직 없으므로
  계산 후 버리는 wiring을 만들지 않는다.
- **입력**: 정확히 `coverage.critical_path_satisfied`와
  `future_opportunity_evidence.requirement_satisfied` 두 개.
- **projection**:
  - `policy_may_proceed = coverage.critical_path_satisfied`
    (Fundamental + Valuation critical evidence foundation만으로 결정)
  - `forward_requirement = future_opportunity_evidence.requirement_satisfied`
    (SATISFIED/NOT_SATISFIED/UNKNOWN을 동일 enum member로 그대로 전달,
    `forward_path_availability`/`event_path_availability`로 재계산하지 않음)
- **`coverage_status`는 입력이 아니다**: State Coverage status에는 Forward가
  포함되므로 이를 gate로 쓰면 Forward가 간접 universal hard gate가 된다.
  현재 대표 runtime(`critical_path_satisfied=True`, `coverage_status=INSUFFICIENT`,
  FOE `UNKNOWN`)의 결과는 `policy_may_proceed=True`, `forward_requirement=UNKNOWN`
  이다 — evidence completeness(`coverage_status`)와 critical foundation은
  별개 semantics다.
- **FOE tri-state 보존**: UNKNOWN은 SATISFIED도 NOT_SATISFIED도 아니다.
  FOE `NOT_SATISFIED`/`UNKNOWN`은 progression을 막지 않는다 — 이후
  forward-dependent policy path가 참조할 독립 axis로 남는다(해당 path 목록은
  미설계).
- **None != UNKNOWN**: `coverage` 또는 `future_opportunity_evidence`가 `None`
  (producer 미실행 = pipeline/programming error)이면 `ValueError`로 fail-fast한다.
  UNKNOWN은 정당한 FOE evidence 상태다.
- **AssessmentStatus와 분리**: 이 함수는 `AssessmentStatus`(ACTIONABLE/
  INSUFFICIENT_EVIDENCE)/`StockOpportunityAssessment`/`OpportunityClassification`
  을 만들지 않는다. `policy_may_proceed=False`가 최종 status에 어떻게 반영되는지는
  아직 정의/구현되지 않은 downstream policy의 몫이다.
- **비영속**: `DecisionEligibility`는 module-local frozen dataclass(Pydantic
  아님)이며 `RecommendationEvaluationState`/`StockOpportunityAssessment`에
  저장되지 않는다 — schema 변경 없음. 두 입력이 이미 state에 있으므로
  `policy_version`이 고정되면 재현 가능하다.
- Recommendation Policy Step 2~8은 설계/구현되지 않았다.

---

### 7.5 Feature Normalization — Ownership & Representation Contract (FROZEN, 미구현)

```text
Status  DESIGN COMPLETE / INDEPENDENT REVIEW PASS / FROZEN (rev.1)
        implementation NOT STARTED — 현재 모든 normalized_value는 None
```

**용어**: 여기서 "normalization"은 **feature normalization**(feature value →
`normalized_value`)만 뜻한다. `NormalizedResearchData`의 source normalization
(vendor → canonical facts), feature derivation, calibration, aggregation,
classification과 구별한다.

```text
FeatureEvaluator
    ↓
Feature Normalization Stage     canonical owner — normalized_value의 유일한 writer
    ↓
Aggregation (family / component, 미구현)
```

- **Owner**: Evaluation layer 안의 전용 Feature Normalization stage.
  module/class 조직은 정하지 않는다. Assembly는 feature를 normalize하지 않고,
  FeatureEvaluator는 normalization을 위해 PolicyConfig를 소비하지 않는다.
- **DOES**: canonical feature input 소비, registry directionality 소비,
  명시적으로 선택된 evaluation basis 소비, versioned normalization policy
  (`EvaluationContext.policy_config_ref`로 식별) 소비, 해당될 때 필요한
  reference data 소비, `normalized_value` 또는 `None` 생산, directionality 1회
  적용, 기존 evidence/status field 보존(입력을 mutate하지 않고 새
  `FeatureEvaluationResult`를 만든다).
- **DOES NOT**: feature value derivation, vendor data fetch, basis silent
  substitution, missing evidence 생성, aggregation, component signal 생산,
  investment opportunity classification, numeric parameter calibration.
- **Derived feature**: `derivation ≠ feature normalization`. stage는 derived
  value를 계산하지 않으며, derived value가 존재하면 input candidate로 소비할 수
  있다. derived value의 canonical producer/공식/ownership architecture는 이
  contract가 정하지 않는다(OPEN).
- **Evaluation basis**: 적용 basis는 명시적이어야 하고, 지원되지 않는 basis는
  적용하지 않으며, reference data 부재 시 다른 basis로 silent fallback하지
  않는다. 적용 basis 선택은 PolicyConfig가 식별하는 normalization policy가
  명시적으로 지원되는 입력 안에서 소유한다. 현재 evaluator의
  `evaluation_basis = [ABSOLUTE]` 출력은 구현 사실일 뿐 architecture
  invariant가 아니다.
- **`normalized_value` 최소 semantics**: canonical raw/derived feature input에
  명시적으로 선택된 evaluation basis + versioned normalization policy + 해당
  reference data를 적용한 **direction-aware evaluative representation**. signal/
  classification/probability/raw 단위 변환이 아니다. 공통 codomain, feature 간
  직접 비교 가능성, aggregation compatibility, boundedness, center, range는
  정하지 않는다(OPEN).
- **Directionality**: 정의는 registry, 적용은 이 stage에서 정확히 1회.
  Aggregation/Signal/Policy는 재해석하지 않는다. `CONTEXT_DEPENDENT` feature에
  default mapping을 만들지 않는다 — 명시적 policy semantics가 없으면
  `normalized_value = None`.
- **Missing / Invalid / N/A**: `UNAVAILABLE → 0`, `INVALID → negative`,
  `NOT_APPLICABLE → missing/zero` 변환 금지. 0은 유효한 입력 후보이고 음수는
  자동으로 INVALID가 아니다. normalization은 availability를 바꾸지 않으므로
  Coverage도 바꾸지 않는다. implicit normalization default 금지 — policy/
  method/basis/reference가 없으면 `None`.
- **Calibration 분리**:

```text
Feature Normalization Contract (FROZEN)
        ↓
Calibration Data & Parameter Provenance Readiness Audit (COMPLETE — readiness BLOCKED, §7.6)
        ↓
Numeric Calibration (OPEN)
        ↓
versioned normalization policy / parameters
        ↓
runtime Feature Normalization Stage (미구현)
```

**Invariants (N1–N11)**:

```text
N1  single owner: feature normalization stage만 normalized_value를 쓴다
N2  raw evidence preservation: raw/derived/availability/provenance 불변, 입력 mutate 금지
N3  no invented evidence: 값이 없거나 INVALID/NOT_APPLICABLE이면 normalized_value=None
N4  UNAVAILABLE → 0 금지, INVALID → negative 금지, NOT_APPLICABLE → missing/zero 금지
N5  normalization은 availability/Coverage를 바꾸지 않는다 (Coverage ≠ Confidence 유지)
N6  directionality는 이 stage에서 한 번만 적용, downstream 재해석 금지
N7  derivation ≠ feature normalization: stage는 derived value를 계산하지 않는다
    (derived value의 canonical producer는 이 contract가 정하지 않는다)
N8  normalization ≠ aggregation ≠ classification: family/component score·signal 생산 금지
N9  calibrated parameter는 versioned PolicyConfig로만 식별, code constant 금지, implicit default 금지
N10 determinism: same FeatureEvaluationResult + same PolicyConfig version
    + same applied basis + same basis reference snapshot → same normalized_value
N11 applied basis는 명시적이어야 하며, 허용되지 않은 basis를 조용히 적용하지 않고,
    relative reference 부재 시 silent fallback하지 않는다
    (허용 basis의 canonical declaration source는 OPEN)
```

**OPEN (이 contract가 해소하지 않음)**:

```text
Derived/input     derived-value canonical ownership/formulas, canonical raw-vs-derived input-slot rule,
                  growth representation
Basis             evaluation_basis final semantics, applicable-basis declaration owner,
                  multi-basis representation
Representation    common normalized codomain, cross-feature direct comparability,
                  aggregation compatibility, scale/range/center
Policy / numeric  feature×basis normalization method, numeric parameters, thresholds, weights,
                  context-dependent mappings, ESTIMATED 허용 policy, peer construction,
                  historical reference, calibration dataset
Traceability      normalization provenance representation, structured None reason
```

설계 대안 비교/review 이력은 `docs/dev-log/2026-09-26.md` §H~§I가 canonical이다.

### 7.6 Calibration Readiness (audit result)

```text
Calibration Data & Parameter Provenance Readiness Audit   COMPLETE / INDEPENDENT REVIEW PASS
Numeric Calibration                 workflow OPEN / readiness BLOCKED
Feature Normalization implementation NOT STARTED / readiness NO
```

`OPEN`은 workflow 상태이고 `BLOCKED`는 readiness 판정이다 — 둘은 다른 축이다.
Feature Normalization 구현 readiness가 NO인 이유: 의미 있는 PolicyConfig/parameter
source가 없고, §7.5가 implicit normalization default를 금지하므로 지금 구현하면
모든 입력에 `None`만 생산한다.

**Readiness findings (stable)**:

```text
runtime data availability      != calibration data readiness
historical value availability  != point-in-time-safe historical evidence
```

- **Point-in-time (OpenDART)**: `rcept_no`는 source account level
  (`OpenDartFinancialAccount`)에 존재하지만 normalized financial evidence
  (`KeyFinancials`/`FinancialSnapshot`) 이전에 버려진다. history helper
  (`get_key_financials_history`)는 전기/전전기 값을 **나중 보고서의 비교 컬럼**에서
  가져온다 → restatement/look-ahead leakage 가능. 정정공시 이후 API 동작과
  `rcept_no` 접수일 prefix 관례는 **UNVERIFIED**다.
- **Valuation**: 현재 PER/PBR snapshot은 available, historical PER/PBR calibration
  evidence는 NOT READY — direct source 부재, 재구성에 필요한 historical shares
  evidence / 검증된 adjusted-price semantics / point-in-time fundamental availability가
  없다. Valuation calibration path = **BLOCKED**(Valuation critical path 병목).
- **Bounded subset**: 14개 feature 전부가 준비돼야 calibration을 시작할 수 있는
  것은 아니다(missing-aware / UNKNOWN 허용 architecture). Operating Margin / Net
  Margin / Debt Ratio는 PIT/provenance prerequisite가 해결되면 bounded candidate
  subset이 될 **가능성**이 있다 — subset NOT SELECTED, calibration NOT STARTED.
  이 subset만으로 Decision/Core path가 열리지 않는다(Valuation 병목).

**Hard blockers**:

```text
H1 OBJECTIVE           calibration objective / label / acceptance criterion undefined
H2 TEMPORAL_SEMANTICS  OpenDART rcept_no / available_at propagation missing;
                       comparative-column historical path has restatement leakage risk
H3 EXTERNAL_SOURCE     corrected-filing behavior UNVERIFIED
H4 DATA                historical valuation reconstruction unavailable
H5 INFRASTRUCTURE      no persistent calibration dataset snapshot
H6 PROVENANCE          dataset / parameter-set / revision identity incomplete;
                       actual PolicyConfig / store absent
H7 SURVIVORSHIP        historical universe / delisted evidence absent —
                       hard only for historical / outcome-based calibration
```

Soft blockers(현재 bounded slice를 논리적으로 막지 않음): peer taxonomy, sector
benchmark, Forward, Flow, macro vintage, quarterly/TTM, financial-sector
applicability, growth representation, derived ownership(feature-specific).

**Post-audit selection (FROZEN)**:

```text
NEXT    Calibration Objective & Scope Contract — design-only, NOT STARTED
SECOND  Point-in-Time Financial Evidence Contract — NOT STARTED
THIRD   not selected
```

(이후 진행: NEXT는 §7.7로 FROZEN됐고, SECOND가 다음 NEXT가 되어 §7.8로 FROZEN됐다 — §7.3 참고.)

- selection 시점에는 selection만 FROZEN이었으며 두 contract의 내용은 설계되지 않았다.
- NEXT는 투자 outcome label(수익률/초과수익/drawdown/Sharpe/ACTIONABLE success
  등)을 고르는 작업이 아니다 — 먼저 Semantic Calibration vs Recommendation
  Calibration의 objective/scope boundary와 "Semantic Calibration이 future outcome
  label을 요구하는가"를 결정한다.
- 선택되지 않은 candidate slice(Calibration Dataset Identity & Persistence,
  Parameter Provenance / PolicyConfig, Historical Valuation Reconstruction,
  Corporate Action / Adjusted Price)는 audit finding으로만 남는다.

evidence 표/14-feature matrix/review 이력은 `docs/dev-log/2026-09-26.md` §J가
canonical이다.

### 7.7 Calibration Objective & Scope Contract (FROZEN)

```text
Status  DESIGN COMPLETE / INDEPENDENT REVIEW PASS / FROZEN (rev.1)
        Numeric Calibration: workflow OPEN / readiness BLOCKED / calibration NOT STARTED
```

이 contract는 calibration의 domain·evidence·validation·versioning 경계만 정한다.
§7.5(N1–N11)와 dev-log 2026-08-29 §24.1 / §24.13의 기존 calibration 요구사항을
개정·약화·재해석하지 않는다. numeric parameter / threshold / weight / formula /
outcome label / horizon / benchmark는 정하지 않는다.

**Domains (Strong Separation)**: calibration은 단일 operation이 아니다. RE-05는
최소 다음 두 domain을 구분한다 — `Semantic Calibration ≠ Recommendation Calibration`.
추가 domain은 두지 않는다.

- **Semantic Calibration**: evidence의 경제적 의미를 보존·표현하는 것이 목적인
  parameter를 정한다. Feature Normalization 같은 feature-level semantic calibration을
  포함하며, canonical architecture가 명시적으로 뒷받침하는 다른 semantic parameter
  class(현재 evidence: §24.13 event-materiality 예시)를 포함할 수 있다.
- **Recommendation Calibration**: 이미 평가된 evidence / decision behavior와 downstream
  investment-decision semantics의 관계를 다룬다. 해당 policy 구조가 허용하는 범위에서
  aggregation / family / component weight, Opportunity State boundary, classification
  boundary를 포함할 수 있다. future investment outcome에 대해 independent /
  out-of-sample semantics로 평가한다. objective / label / horizon / benchmark는 OPEN.
- **Ownership OPEN**(어느 domain에도 배정하지 않음): component signal threshold,
  risk severity, coverage/confidence gate, correlation discount.

**Ownership boundaries**:

- `AssessmentStatus` / `ACTIONABLE` / `INSUFFICIENT_EVIDENCE` 매핑은 policy-contract
  책임이며 Semantic Calibration 책임이 아니다. classification 구조는 Recommendation
  Policy contract 관심사, classification numeric boundary는 잠재적 Recommendation
  Calibration 관심사(값은 OPEN)다.
- `calibration ≠ derivation`: calibration은 ROA / Asset Turnover / Earnings Yield
  formula와 growth representation을 소유하지 않는다(derived ownership OPEN).
- Calibration은 versioned policy parameter를 생산/선택하고, runtime Feature
  Normalization은 이미 선택된 versioned policy를 적용한다. runtime normalization은
  개별 evaluation request로부터 policy parameter를 fit하지 않으며 §7.5 N10의
  결정론을 따른다. reference statistic이 policy parameter인지 runtime/reference
  evidence인지는 OPEN.
- Semantic Feature Normalization calibration은 family / component / aggregation
  weight를 소유하지 않는다. `normalized_value ≠ component score ≠ component signal ≠
  classification`.

**Future outcome boundary (Semantic)**: Semantic Calibration은 future investment
outcome label을 요구하지 않는다. future investment outcome은 Semantic Calibration의
optimization target, fitting target, primary parameter-selection criterion으로 쓰이지
않는다. strictly bounded secondary diagnostic / rejection check로 쓸 수 있는지는
**OPEN**이다 — 나중에 허용된다면 최소한 semantic meaning을 재정의하지 않고, 같은
policy version으로 feedback되지 않으며, selection-leakage risk가 통제돼야 한다.

**Historical evidence boundary**: `Semantic parameter derivation requirement ≠
policy freeze acceptance requirement`. Semantic parameter derivation이 historical
evidence를 요구하는지는 선택된 basis/method에 의존하며 OPEN이다. 이 contract는
numeric Semantic policy를 freeze하기 전에 적용되는 기존 §24.1 / §24.13의
historical/temporal validation 요구를 **면제하지 않는다**. provisional semantic
policy mechanism은 도입하지 않는다(존재 여부 OPEN).

**Calibration vs validation**: calibration은 parameter를 선택/추정하고, validation은
이미 선택된 parameter를 independent evidence로 평가한다. validation evidence는 parameter
fitting/selection에 쓰인 같은 policy version으로 feedback되지 않는다.

**Information boundary**: historical/as-of semantics를 주장하는 evidence는 해당
information boundary 시점에 이용 가능했음을 확립할 temporal identity를 가져야 한다.
개념 identity: observation period / availability(publication) time / evaluation
as_of / reference snapshot as_of / future outcome period. 해당되는 reference snapshot은
`reference snapshot as_of <= evaluation as_of`. future outcome period는
Recommendation/outcome evidence에 속하며 Semantic fitting/primary-selection evidence가
아니다. temporal schema는 정하지 않는다 — 상세는 Point-in-Time Financial Evidence
Contract(§7.8)의 몫이다.

**Semantic evidence classes**:

```text
economic/accounting non-numeric structure            REQUIRED
contemporaneous cross-sectional distribution         CONDITIONAL
historical distribution                              CONDITIONAL
peer-relative distribution                           CONDITIONAL (peer taxonomy 현재 unavailable/deferred)
market-relative distribution                         CONDITIONAL
expert/policy judgment as sole basis for numbers     NOT ALLOWED
future investment outcome                            NOT ALLOWED as optimization/fitting/primary-selection input
outcome label                                        NOT REQUIRED
```

EvaluationBasis mapping(예: cross-sectional method를 어느 basis로 볼지)은 정하지 않는다.

**Semantic acceptance classes (types only)**: REQUIRED — directionality consistency,
semantic monotonicity, missingness behavior, basis consistency, economic
interpretability. 기존 architecture가 요구하는 temporal/stability evidence는 freeze
acceptance 요구로 유지된다. CONDITIONAL — cross-sectional robustness(cross-sectional
basis 사용 시). OUT OF SCOPE as Semantic criterion — predictive power. numeric
threshold 없음.

**Recommendation readiness gates**:

```text
universal    explicit decision objective / outcome semantics
             evidence appropriate to the selected objective
             required information-boundary / PIT semantics
             reproducible dataset identity
             parameter provenance
             independent validation / walk-forward semantics
             explicit versioned Semantic dependency
conditional  historical valuation — selected path/objective가 historical reconstruction이
               필요한 valuation evidence에 의존할 때
             survivorship-safe universe — historical universe/outcome 평가가
               survivorship bias를 유발할 수 있을 때
             adjusted-price evidence — selected outcome semantics가 price-return
               reconstruction에 의존할 때
```

현재 end-to-end Recommendation path는 **BLOCKED**다(§7.6 판정 유지).

**Dataset boundary**: `logical calibration input ≠ physical dataset/storage`. Semantic과
Recommendation calibration evidence는 독립적으로 식별 가능하고 재현 가능해야 한다.
Semantic logical calibration input은 future outcome을 optimization/fitting/
primary-selection input으로 쓰지 않는다. 별도 physical dataset / 공유 dataset /
overlapping snapshot / shared immutable storage 여부는 OPEN.

**Versioning / provenance**: Semantic Calibration policy/provenance와 Recommendation
Calibration policy/provenance는 독립적으로 식별·versioning 가능해야 한다.
Recommendation Calibration은 명시적으로 식별된 Semantic policy version에 의존할 수
있다. Semantic Calibration은 optimization/fitting/primary-selection semantics를 위해
Recommendation Calibration parameter나 future outcome에 의존하지 않는다. 현재 단일
`policy_version` / `PolicyConfigRef.version` 표현은 future implementation/schema
implication일 뿐 이번에 변경하지 않는다.

**PolicyConfig boundary (responsibility only)**: PolicyConfig는 선택된 policy / method /
parameter value / version을 식별한다. Parameter Provenance는 그 policy가 어떻게
생산됐는지를, Calibration Evidence / Dataset Identity는 사용된 evidence를, Reference
Snapshot Identity는 해당 runtime/reference evidence를 식별한다. schema는 정하지 않는다.

**Blocker status**: 이 contract의 freeze로 해소된 H1–H7 blocker는 **없다**.

```text
H1 OBJECTIVE    Semantic: 구조적으로만 명확해짐, operational acceptance 미해결
                Recommendation: objective/outcome semantics OPEN, blocking
H2 TEMPORAL     PIT/as-of evidence가 필요한 곳에서 blocking 유지
H3 EXTERNAL     evidence path에 따라 conditional/blocking 유지
H4 VALUATION    Semantic: 보편적 parameter-derivation 전제는 아님, 해당 basis 또는
                  freeze-validation path에는 relevant/required
                current Recommendation path: blocking 유지
H5 INFRA        blocking 유지
H6 PROVENANCE   blocking 유지
H7 SURVIVORSHIP pure current-date cross-section에는 current-date라는 이유만으로 해당 없음,
                해당 historical universe/outcome path에서는 blocking 유지
```

**Non-goals**: numeric parameter / threshold / weight / normalization formula / score
range, outcome label / horizon / benchmark, dataset / PolicyConfig / provenance /
reference snapshot schema, physical storage 설계, data collection, calibration,
backtest, Feature Normalization 구현, Recommendation Policy Step 2–8 설계/구현,
§24.1 / §24.13 개정.

**Invariants (C1–C15)**:

```text
C1  Calibration은 서로 다른 Semantic / Recommendation domain을 포함한다.
C2  Semantic Calibration은 future investment outcome label을 요구하지 않으며, future
    outcome을 optimization / fitting / primary-selection target으로 쓰지 않는다.
C3  Calibration ≠ Validation. validation evidence는 같은 policy version으로 feedback되지 않는다.
C4  Semantic validation에서 bounded future-outcome diagnostic 사용 여부는 이 contract가
    정하지 않는다(OPEN) — 허용 시 최소 조건: semantic meaning 비재정의, 같은 version
    feedback 금지, selection-leakage 통제.
C5  Calibration ≠ Derivation.
C6  Runtime normalization은 개별 request로부터 policy parameter를 fit하지 않으며
    policy/reference identity 아래 결정론적이다.
C7  Semantic Feature Normalization calibration은 aggregation / family / component weight를
    소유하지 않는다.
C8  AssessmentStatus 매핑은 policy-contract 책임이다. classification numeric boundary는
    Semantic Calibration 책임이 아니다.
C9  Semantic / Recommendation policy·provenance domain은 독립적으로 식별·versioning
    가능하다. Recommendation은 식별된 Semantic version에 의존할 수 있다.
C10 logical calibration evidence identity는 physical dataset organization과 구별된다.
C11 information boundary는 temporal ordering을 보존하며 future evidence가 Semantic
    fitting / primary selection에 들어가지 않게 한다.
C12 as-of evidence는 temporal identity가 필요하다. 해당 cross-sectional evidence는
    reference snapshot identity가 필요하다.
C13 calibration domain을 명확히 하는 것만으로 evidence blocker는 해소되지 않는다.
C14 expert/policy judgment만으로 numeric 값을 만들어내지 않는다.
C15 Semantic parameter derivation 요구는 policy freeze-acceptance 요구와 구별된다.
    이 contract는 기존 freeze 요구를 면제하지 않는다.
```

**OPEN (이 contract가 해소하지 않음)**:

```text
Method / objective   exact Semantic calibration method; exact Recommendation objective,
                     outcome label, horizon, benchmark
Numeric              normalization formula, numeric parameters, thresholds, weights
Semantic boundary    bounded future-outcome diagnostic for Semantic validation;
                     basis/method-specific historical derivation requirement;
                     provisional Semantic policy/version mechanism;
                     operational Semantic acceptance criteria;
                     cross-sectional method → EvaluationBasis mapping
Evidence / storage   physical dataset organization/sharing; dataset schema,
                     PolicyConfig schema, parameter provenance schema,
                     reference snapshot schema
Data                 historical valuation reconstruction; adjusted-price semantics
Feature definition   derived feature ownership; growth representation
Domain ownership     component signal threshold; risk severity;
                     coverage/confidence gates; correlation discount
Runtime              reference statistic: policy parameter vs runtime/reference evidence
Versioning           future representation of independent Semantic / Recommendation
                     policy versions
```

**Dependency ordering (Semantic path, 후보 slice는 선택되지 않음)**:

```text
Calibration Objective & Scope Contract (FROZEN)
        ↓
Point-in-Time Financial Evidence Contract (FROZEN, §7.8 / implementation NOT STARTED)
        ↓
Calibration Evidence Identity & Persistence   (candidate, not selected)
        ↓
Parameter Provenance / PolicyConfig           (candidate, not selected)
        ↓
bounded Semantic Calibration (existing freeze-acceptance requirements apply)
        ↓
Feature Normalization implementation
```

Recommendation path는 별도 branch다 — Recommendation Objective & Outcome Semantics
Contract(candidate)와 선택된 objective에 따른 conditional evidence(historical valuation /
survivorship-safe universe / adjusted-price)가 선행한다.

design rev.0 → rev.1 review 이력은 `docs/dev-log/2026-09-26.md` §K가 canonical이다.

### 7.8 Point-in-Time Financial Evidence Contract (FROZEN)

```text
Status          DESIGN COMPLETE / INDEPENDENT REVIEW PASS / FROZEN (rev.1 + §4.1 wording correction)
Implementation  NOT STARTED (PIT capability 없음)
```

**Purpose**: 재무 evidence가 특정 information boundary에서 정당하게 사용될 수 있는지
판정하는 데 필요한 최소 temporal/evidence semantics를 정한다.

**Scope**: 개별 재무 evidence item(raw / derived), current-runtime usability boundary,
historical PIT eligibility boundary.

**Non-goals**: implementation schema / exact field name, dataset identity, persistence
구현, valuation reconstruction, price / corporate-action semantics, quarterly/TTM 계산,
revision-policy 선택, availability-policy 선택, Numeric Calibration, Feature
Normalization 구현, Recommendation Calibration, numeric parameter / threshold / weight,
normalization formula, outcome label / horizon / benchmark.

**Temporal model**:

```text
economic observation ≠ filing/publication ≠ information availability
                     ≠ evaluation_as_of   ≠ retrieval time
```

architecture가 **표현 가능해야** 하는 evidence 차원: observation identity / filing
identity / availability identity / retrieval identity / revision dimension. 표현 가능성은
모든 evidence item이 다섯 차원 모두의 구체적 값을 안다는 뜻이 아니다 — 어떤 값이
알려져야 하는지는 사용 목적(current-runtime vs historical)과 consumer policy가 정한다.
consumer 측 개념(evidence 속성 아님): `evaluation_as_of`, revision-selection policy.

**Observation identity**: economic/reporting period, report type, reporting basis,
source column / term, (해당 시) raw vs derived origin을 구별할 수 있어야 한다 — FY
연간 / Q4 / 반기 / TTM / 비교 컬럼 값이 조용히 동일시되지 않도록. quarterly/TTM 계산은
설계하지 않는다. Repository finding: OpenDART source parsing(`OpenDartFinancialAccount`:
`bsns_year`/`reprt_code`/`fs_div`/`sj_div`/`thstrm·frmtrm·bfefrmtrm` `_nm`/`_dt`)은
downstream `KeyFinancials`/`FinancialSnapshot`보다 풍부한 기간/source 정보를 갖고,
downstream은 이를 보존하지 않는다(`rcept_no`, 기간 날짜, source column, `sj_div`가
소실되고, `fs_div`는 `FinancialSnapshot`에서 소실).

**Filing identity**: source 문서를 식별한다. 그 자체로 publication timestamp /
availability timestamp / original·corrected status / revision order / replacement
semantics를 증명하지 않는다. OpenDART: `rcept_no` → provider-specific filing identity
후보 → adapter가 generic filing identity로 매핑. generic architecture는 `rcept_no`에
직접 의존하지 않는다. `rcept_no`의 구조/semantics는 empirically UNVERIFIED다(repository에
해석 코드 없음).

**Availability semantics**: `published_at` = source 측 publication/filing event.
`available_at` = 식별 가능한 source-specific availability policy 아래 가장 이른 방어
가능한 information boundary. `published_at == available_at`은 검증된 source-specific
policy가 뒷받침할 때만 허용된다(현재 없음). latency/timezone 가정을 두지 않는다. 정확한
schema 표현은 OPEN.

**Current-runtime usability boundary**: current-runtime latest-known 사용에서, 성공한
source retrieval은 명시적 source/runtime policy 아래 **오직** `available_at <=
retrieved_at`만 확립할 수 있다. 이는 해당 policy 아래 current-runtime usability만
뒷받침한다. exact historical `available_at`을 확립하지 않으며, 임의의 더 이른 `T`에
대해 `available_at <= historical_as_of_T`를 확립해서는 안 된다 — `available_at`은
`retrieved_at`보다 훨씬 이를 수도 있고, historical `T`보다 늦으면서 `retrieved_at`보다는
이를 수도 있으며, upper bound만으로는 두 경우를 구분할 수 없다. 또한 지금 조회된
version이 historical `T`에 존재한 version이라는 것도 증명되지 않는다. 따라서
`Current-runtime usability ≠ Historical PIT eligibility`(P4와 공존: 상한은 현재 사용을
뒷받침하고, P4가 부정하는 것은 historical 가용성이다). upper bound의 field 표현은 OPEN.

**Historical PIT boundary**: 방어 가능한 `available_at <= evaluation_as_of` + consumer의
명시적 revision-selection policy 아래 정당성. `retrieved_at` 단독, `EvaluationContext.as_of`
단독으로는 historical PIT eligibility를 충족하지 않는다.

**Revision dimension**: revision 정보는 반드시 표현 가능해야 한다. source가 확립할 수
없으면 known concrete revision identity는 요구되지 않으며, 이 경우 `revision state =
UNKNOWN`이 명시적으로 유지된다. UNKNOWN은 original / latest-corrected / revision-free를
조용히 뜻하지 않는다. revision identity/state = evidence 속성, revision-selection policy
= consumer/policy 선택. 개념 대안(as-known-at-time / latest-corrected / original-only)
중 어느 것도 선택하지 않는다.

**Comparative-column rule**: filing `Y`의 비교 컬럼 값(economic period `Y-1`)은 filing
`Y`가 available해진 이후 "filing Y가 보고한 비교 값"으로 사용할 수 있다. 그 값을
"`Y-1` historical information boundary에서 알려진 값"으로 자동 표현해서는 안 된다 —
더 이른 boundary에서 실제로 available했던 evidence와의 동등성이 독립적으로 확립된 경우는
예외. source-column / term identity는 downstream 변환에서 보존돼야 한다.
Repository defect/risk: `get_key_financials_history()`(`app/mcp/opendart_tools.py`)는
하나의 나중 filing에서 비교 값을 꺼내 `_year_label_for_term()`으로 더 이른
`business_year`로 relabel한다(`report_code`는 그대로) — downstream 표현은 "나중 filing의
비교 값"과 "더 이른 filing이 직접 보고한 값"의 구분을 잃는다. 실제 restatement 발생이나
production leakage를 주장하지 않는다 — leakage risk가 현재 통제되지 않으며, 이 경로가
historical calibration/backtesting에 재사용되면 탐지 불가능할 수 있다.

**PIT eligibility (conceptual historical predicate, 함수/schema 아님)**: historical
재무 evidence는 다음을 모두 만족할 때만 `evaluation_as_of`에서 사용될 수 있다.

```text
1. observation identity가 존재한다
2. filing identity가 존재한다
3. 식별 가능한 availability policy 아래 방어 가능한 available_at이 존재한다
4. available_at <= evaluation_as_of
5. revision state가 명시적이다(해당 시 UNKNOWN 포함)
6. consumer의 명시적 revision-selection policy 아래 선택 가능하다
7. 비교 컬럼 evidence는 comparative-column rule을 따른다
```

**Missing / UNKNOWN**:

```text
PIT eligibility를 주장하는 내부 object에 필수 identity 부재  → contract violation / fail-fast 후보
source가 historical temporal/revision 사실을 확립 불가        → not PIT-eligible / UNKNOWN
재무 값 자체 부재                                             → 기존 missing-aware semantics
```

latest / current / neutral / zero / SATISFIED로 조용히 fallback하지 않는다. 정확한
status/schema 표현은 OPEN.

**Derived evidence (lower bound only)**: derived evidence item은 그것을 도출하는 데 필요한
어떤 evidence input보다도 이른 availability boundary를 가져서는 안 된다 — 개념적으로
`derived_available_at >= max(required_input_available_at)`. 이는 선택된 구현 공식이 아니며
`= max(...)`를 완전한 semantics로 freeze하지 않는다. derived feature ownership / 완전한
derived-evidence availability semantics / formula identity ownership / policy·config
temporal identity는 OPEN.

**Provenance boundary**:

```text
EvaluationContext.as_of                      consumer information boundary
evidence publication/availability identity   evidence/source temporal identity
retrieved_at                                 retrieval/audit identity
revision-selection policy                    consumer/policy identity
```

`as_of`를 overload하지 않는다. 현재 evaluator `Provenance`는 `source`와
`as_of = context.as_of`만 채우며 `published_at`/`effective_at`/`retrieved_at`은 항상
`None`, `available_at`·revision field는 없다. `Provenance.effective_at` semantics는 OPEN.

**Source-neutral vs OpenDART-specific**: source-neutral — evidence 차원, eligibility
predicate, current-runtime upper-bound 규칙, P1–P12. OpenDART adapter/policy —
`rcept_no` → filing identity, `reprt_code`/`fs_div`/`sj_div` → observation identity,
비교 컬럼 표시, publication timestamp source, availability policy, revision state 판별.

**Leakage classes** (전부 "risk not controlled", "leakage observed" 아님): later-filing
comparative, restatement, corrected-filing, publication-time look-ahead, retrieval-time
confusion, derived-availability advancement.

**Invariants (P1–P12)**:

```text
P1  Economic observation과 information availability는 구별된다.
P2  evaluation_as_of에 쓰이는 historical evidence는 evaluation_as_of 이하의 방어 가능한
    availability boundary를 확립해야 한다.
P3  나중 filing의 비교 값은 독립적 동등성 evidence 없이 더 이른 information boundary로
    back-project되어서는 안 된다.
P4  Retrieval time은 historical availability를 확립하지 않는다.
P5  EvaluationContext.as_of 단독으로는 evidence availability를 확립하지 않는다.
P6  Revision identity/state와 revision-selection policy는 구별된다. 여러 version이 존재할
    수 있으면 consumer policy가 명시적이어야 한다.
P7  UNKNOWN historical availability/revision은 조용히 current/latest evidence가 되어서는
    안 된다.
P8  PIT eligibility는 Numeric Calibration 또는 Feature Normalization readiness를 뜻하지
    않는다.
P9  PIT evidence identity는 calibration dataset identity와 구별된다.
P10 Provider-specific identifier는 generic evidence identity를 구현할 수 있으나, generic
    architecture는 특정 provider에 불필요하게 의존해서는 안 된다.
P11 PIT-relevant identity는 downstream 변환에서 보존돼야 한다. source-column origin을
    지우거나, 나중 filing의 비교 값이 더 이른 filing의 직접 보고 값과 구별 불가능해지도록
    relabel해서는 안 된다.
P12 Derived evidence item은 필요한 어떤 evidence input보다도 이른 availability boundary를
    가져서는 안 된다. 완전한 derived-evidence availability semantics는 OPEN.
```

**OPEN**:

```text
OpenDART corrected-filing retrieval behavior; authoritative publication timestamp source;
defensible available_at source/policy; revision-chain reconstruction; revision-selection policy;
historical filing retrieval capability; comparative-column equivalence verification;
quarterly / half-year / TTM semantics; persistence/schema representation;
calibration dataset identity; historical valuation reconstruction;
corporate-action / adjusted-price semantics; Provenance.effective_at semantics;
PIT-unavailable status representation; _find_amount / sj_div ambiguity;
derived feature ownership; complete derived-evidence availability semantics;
formula/policy/config temporal identity; published_at / available_at field representation;
current-runtime upper-bound field representation
```

**EMPIRICAL VERIFICATION REQUIRED** (이 contract는 아래를 해소하지 않는다):

```text
1. fnlttSinglAcnt original / corrected / latest behavior
2. historical original filing retrieval / reconstruction
3. rcept_no structure and semantics
4. authoritative publication timestamp source
5. API / comparative-column mutation after correction / restatement
6. period-field(thstrm_dt 등) / reprt_code semantics beyond repository-proven facts
```

**Blocker status**: 이 contract의 freeze로 해소된 H1–H7 blocker는 **없다**.

```text
H2 TEMPORAL     CLARIFIED / NARROWED — blocking 유지
H3 EXTERNAL     NARROWED — blocking 유지
H5 INFRA        CLARIFIED — 미해결
H6 PROVENANCE   CLARIFIED — blocking 유지
H1 / H4 / H7    변경 없음
```

**Readiness**: PIT capability implementation NOT STARTED · Feature Normalization
implementation NOT STARTED / readiness NO · Numeric Calibration OPEN / readiness BLOCKED /
NOT STARTED · Recommendation Calibration NOT STARTED / BLOCKED.

**Dependency candidates (선택되지 않음 — NEXT/SECOND/THIRD 아님)**: OpenDART PIT Empirical
Verification(PIT 구현 이전에 필요할 가능성이 높음), Calibration Evidence Identity &
Persistence, Parameter Provenance / PolicyConfig, Historical Valuation Reconstruction,
Corporate Action / Adjusted Price, Recommendation Objective & Outcome Semantics.

design rev.0 → rev.1 → §4.1 wording correction → freeze-readiness review 이력은
`docs/dev-log/2026-09-26.md` §M이 canonical이다.

### 7.9 OpenDART PIT Empirical Verification — Frozen Findings

```text
Status  EXECUTION COMPLETE / INDEPENDENT REVIEW PASS (rev. with R1/R2 + count correction)
        / FINDINGS FROZEN
```

§7.3 selection(M1–M3 MUST, S1–S4 SHOULD)의 실행 결과다. **§7.8은 변경하지 않는다** — 이
findings는 frozen PIT contract를 소급 수정하지 않으며, availability policy / revision-selection
policy / persistence architecture를 선택하지 않는다.

**Scope / method**: official OpenDART 개발가이드(공시검색 `list.json`, 공시서류원본파일
`document.xml`, 단일회사 주요계정 `fnlttSinglAcnt`, 단일회사 전체 재무제표 `fnlttSinglAcntAll`,
재무제표 원본파일 `fnlttXbrl.xml`)와 실제 API 응답. bounded sample(2026-09-26 조회):

```text
A  삼성전자 00126380  FY2023 사업보고서  20240312000736 (조회 범위에서 정정 미관측)
B  셀트리온 00413046  FY2021 사업보고서  original 20220308000956 → [기재정정] 20220317000991
                                          → [기재정정] 20220512000853
C  카카오   00258801  FY2023 사업보고서  original 20240320002039 → [기재정정] 20240321000907
                                          → 20240328001805 → 20240418000375
```

정정 관계는 official metadata(`report_nm`의 `[기재정정]`, `rm`의 "정")로 확인했다 — identifier
형식으로 추론하지 않았다. 분류: `VERIFIED` / `VERIFIED — sample-bounded` / `CONTRADICTED` /
`UNKNOWN`. 근거 유형: OFFICIAL-DOC / EMPIRICAL / REPO. 아래 sample 수치는 **coverage 추정치가
아니다**.

**M1 Corrected-filing / revision behavior — COMPLETE**

```text
fnlttSinglAcnt / fnlttSinglAcntAll            latest correction observed — VERIFIED (sample-bounded)
  (셀트리온 FY2021 → 20220512000853, 카카오 FY2023 → 20240418000375, 단일 version만 노출)
specific historical version request            NOT SUPPORTED — official request 인자는
  (fnlttSinglAcnt)                              corp_code/bsns_year/reprt_code뿐(OFFICIAL-DOC),
                                                추가 rcept_no 인자는 무시됨(EMPIRICAL)
corrected filing의 별도 rcept_no               VERIFIED (sample-bounded)
pre-correction historical endpoint response    UNKNOWN
explicit original↔correction link field       NOT OBSERVED (list.json 필드: corp_cls, corp_code,
                                                corp_name, flr_nm, rcept_dt, rcept_no, report_nm, rm)
official correction signals                    [기재정정] prefix, rm "정", last_reprt_at(OFFICIAL-DOC)
```

**M2 Historical/original reconstruction — COMPLETE**

```text
historical reconstruction                      demonstrated for some filing versions
general structured reconstruction coverage     NOT established
original filing 식별(정정 이후)                  VERIFIED (sample-bounded) — list.json last_reprt_at=N
document.xml (rcept_no-addressed)              version-specific artifact 8 / 8 requested — VERIFIED (sample-bounded)
fnlttXbrl.xml (rcept_no-addressed)             version-specific structured artifact 7 / 8 requested
                                                — VERIFIED (sample-bounded)
observed gap                                   카카오 original 20240320002039 → status 014(파일 없음)
anchor                                         rcept_no — VERIFIED (sample-bounded)
```

셀트리온 FY2021 연결 영업이익: original XBRL `752,485,791,729` vs correction `756,857,107,226`
(당기순이익·자산총계·자본총계도 상이, 오늘의 `fnlttSinglAcnt`는 correction 값). original
`document.xml`에는 original 값이 존재한다 — 이는 official artifact에 값이 **존재함**만 보이며,
production-quality structured extraction method를 확립하지 않는다.

**M3 Publication metadata — COMPLETE**

In the investigated official API/document interfaces, the verified filing-time metadata is
`rcept_dt`, an official receipt date with day-level precision. No time-of-day field was observed
in the investigated interfaces. Whether another authoritative OpenDART surface exposes time-of-day
or stronger public-availability metadata remains UNKNOWN.

```text
rcept_dt                          official "공시 접수일자(YYYYMMDD)" — VERIFIED
precision                         day-level in investigated interfaces — VERIFIED
historical filing metadata        VERIFIED (sample-bounded, 2016 filing 조회 확인)
rcept_no join (list ↔ financial)  VERIFIED (sample-bounded)
time-of-day                       UNKNOWN
timezone                          UNKNOWN
earliest public availability      NOT established
rcept_dt == available_at          NOT established
```

**SHOULD findings**

```text
S1 comparative-column   셀트리온: FY2022 사업보고서의 FY2021 비교값 중 매출액·영업이익이 original과
                        correction 어느 쪽과도 불일치 — VERIFIED (sample-bounded difference).
                        삼성전자/카카오 6개 계정 일치 — sample-bounded equality일 뿐.
                        P3를 뒷받침하는 positive evidence. P3 UNCHANGED
S2 rcept_no             14자리, 관찰 sample 내 unique. prefix == rcept_dt는 126 / 127 일치,
                        반례 1건(20220310001226 vs rcept_dt 20220311) → CONTRADICTED as a general
                        rule. rcept_no 형식에서 receipt/publication 시점을 도출하지 않는다
S3 API mutation         정정 이후 historical API mutation — UNKNOWN
S4 period / codes       reprt_code(11013/11012/11014/11011) / fs_div(OFS/CFS) / sj_div(BS/IS,
                        전체재무제표는 CIS/CF/SCE 추가) — documented semantics VERIFIED.
                        period-field 형식("YYYY.MM.DD 현재" / "YYYY.MM.DD ~ YYYY.MM.DD") —
                        sample-bounded 관찰. documentation 범위를 넘는 quarterly/half-year period
                        semantics — UNKNOWN. TTM/reconstruction design — OUT OF SCOPE
```

**Critical result**:

Evidence supports a hybrid-capability model, with important limits. Historical reconstruction is
empirically demonstrated for some filing versions, but general reconstruction coverage is NOT
established. Forward accumulation remains independently necessary wherever latest-only interfaces
cannot recover prior response states and where version-addressable structured evidence is
unavailable. This is a factual constraint derived from observed source behavior. It is NOT a
selection of persistence architecture.

```text
hybrid-capability evidence  ≠  hybrid persistence architecture selected
```

이 findings는 다음을 주장하지 않는다: 모든 historical filing이 재구성 가능하다 / XBRL이 historical
filing에 일반적으로 존재한다 / document parsing이 검증된 structured reconstruction method다.

**Architecture implications (implications only — 선택 없음)**:

```text
Evidence identity  rcept_no는 per-version filing anchor를 empirically 뒷받침한다.
                   fnlttSinglAcnt 단독으로는 historical version을 표현할 수 없다(latest-only 관찰).
Reconstruction     version-addressed reconstruction은 일부 filing에서 가능, general coverage
                   unestablished, reconstruction-only reproducibility NOT established.
Availability       rcept_dt는 day-level receipt-date fact를 제공한다. earliest public
                   availability와의 관계 UNKNOWN. available_at policy NOT SELECTED.
Revision           per-version rcept_no는 representable version identity를 뒷받침한다.
                   explicit original↔correction chain field NOT OBSERVED. revision-selection
                   policy NOT SELECTED. UNKNOWN revision handling은 여전히 필요하다(§7.8).
PIT implementation 현재 fnlttSinglAcnt integration은 그 자체로 historical PIT에 부적합.
                   PIT implementation NOT STARTED / NOT READY.
```

**Remaining UNKNOWN**: time-of-day / timezone / earliest public availability, pre-correction
endpoint response(S3), original filing에 대한 XBRL coverage, machine-readable original↔correction
link, quarterly/half-year period semantics, 3개 sample 밖으로의 일반화.

**Blocker status** — **H1–H7 newly RESOLVED: NONE**

```text
H1 OBJECTIVE       UNCHANGED
H2 TEMPORAL        NARROWED
H3 EXTERNAL        PARTIALLY EVIDENCED (RESOLVED 아님)
H4 VALUATION       UNCHANGED
H5 INFRA           NARROWED
H6 PROVENANCE      NARROWED
H7 SURVIVORSHIP    UNCHANGED
```

**Work-selection state**:

```text
JUST COMPLETED  OpenDART PIT Empirical Verification
NEXT            NOT SELECTED
SECOND          NOT SELECTED
THIRD           NOT SELECTED
```

Calibration Evidence Identity & Persistence는 post-empirical critical-path review의 **candidate**일
뿐이다. Parameter Provenance / PolicyConfig, PIT implementation, Feature Normalization
implementation, Numeric Calibration도 선택되지 않았다.

실행 / independent review(R1/R2, count correction) 이력은 `docs/dev-log/2026-09-26.md` §O가
canonical이다.

### 7.10 Calibration Evidence Identity & Persistence Contract (FROZEN)

```text
Status          DESIGN COMPLETE / REVIEW PASS / FROZEN (rev.1)
Implementation  NOT STARTED
```

`FROZEN`은 architecture/design contract가 고정됐다는 뜻이다. persistence 구현, evidence capture
구현, reproducibility 달성, PIT 구현, calibration / normalization / numeric policy readiness를
뜻하지 않는다. 이 contract는 §7.5 / §7.7 / §7.8 / §7.9를 **변경하지 않고** 그 위에 선다(§7.8
P1–P12 그대로 적용). 범용 data platform이 아니라 첫 trustworthy vertical slice에 필요한 evidence
측 최소 contract다.

**Problem**: 시스템은 physical persistence 기술이나 numeric / calibration policy를 고르지 않고도
다음을 판정할 수 있어야 한다 — assessment가 정확히 어떤 evidence를 썼는가 / 정확히 어떤
reference snapshot을 썼는가 / 어떤 information·evaluation boundary가 적용됐는가 / 그 evidence
basis가 reproducible한가 / derived evidence가 source evidence와 어떻게 연결되는가. 현재 구현은
adapter boundary에서 filing / version / period / retrieval identity를 잃고(OpenDART:
`KeyFinancials`에서 `rcept_no`·기간 날짜·source column 소실, Kiwoom: `KiwoomStockInfo`에 시간·
version·retrieval identity 없음) 위 질문에 답하지 못한다.

**Conceptual model** (각각 별개):

```text
Evidence Item Identity          하나의 source-backed 관측/값
Temporal / Availability Identity
Revision Identity
Reference Snapshot Identity
Evidence Basis Manifest         assessment/evaluation 단위
Calibration Dataset Identity    별도 — 이후 calibration infrastructure(이 contract 밖)
Policy Identity                 별도 — 이후 PolicyConfig 측(이 contract 밖)

Evidence Item ≠ Reference Snapshot ≠ Calibration Dataset
Evidence Identity ≠ Policy Identity
```

**Evidence Item Identity** (provider-neutral, field 이름 OPEN) — 식별 가능해야 하는 것: entity /
subject, measure(source-reported metric identity), observation period, report type, reporting
basis, source column / source term, provider / source interface 또는 artifact, provider version /
filing anchor(있을 때), source-reported vs derived origin. provider-specific 값(OpenDART
`rcept_no` / `reprt_code` / `fs_div` / `sj_div` 등)은 adapter가 provider-neutral evidence model로
매핑한다. provider model은 downstream canonical type이 아니다. identity는 값(content)을 포함하지
않는다.

**Temporal / Availability Identity** — `published_at` / `available_at` / `retrieved_at` /
`evaluation_as_of`는 별개다.

```text
retrieved_at        runtime-retrieved source evidence에 REQUIRED; historical available_at 아님
evaluation_as_of    consumer boundary; evidence availability 아님
source precision    보존 필수 (예: rcept_dt = day-level 접수일자 — 정밀 timestamp로 만들지 않음)
UNKNOWN timezone / precision   UNKNOWN 유지, upward precision fabrication 금지
available_at        식별된 availability policy의 산출로만 기록, 아니면 UNKNOWN
                    (availability derivation policy NOT SELECTED)
```

**Revision Identity** — 표현 가능해야 하는 것: served version / filing anchor(있을 때), source
serving semantics(예: latest-only at retrieval / version-addressed / UNKNOWN), revision
relationship, source-reported correction/revision signal(그대로 기록). revision relation은
authoritative metadata로 확립되지 않으면 UNKNOWN이며, revision ordering을 identifier 형식에서
추론하지 않는다. revision-selection policy는 선택하지 않는다(as-known-at-time / latest-corrected
/ original-only 중 어느 것도 아님, §7.8 P6).

**Reference Snapshot Identity** — identity 요구만 고정한다: snapshot identity, exact membership,
exact included evidence-item binding, relevant information / as-of boundary. 같은 human label이라도
membership 또는 content가 다르면 다른 snapshot이다. construction-policy identity는 이 contract의
필수 요소가 아니다 — construction-policy metadata 요구 여부, reference universe, reference
statistic, normalization method, current-reference Semantic admissibility는 OPEN(이후 K / B).

**Evidence Basis Manifest** (semantic requirement) — 각 assessment/evaluation은 다음을 식별할 수
있어야 한다: 사용한 evidence item, 사용한 reference snapshot, `evaluation_as_of`, 각 member의
reproducibility 확립 여부, 확립된 경우 그 basis. exact Python type / database representation /
SOA field / evaluation-state field / serialization format은 구현 결정(OPEN). policy identity는
manifest에 포함되지 않는다 — 향후 reproducible decision은 개념적으로 `Evidence Basis + Policy
Identity`를 요구하며, 이 contract는 evidence 측만 소유한다.

**Identity vs Content / Reproducibility** — `Identity ≠ Content`: identifier만으로는
reproducibility가 확립되지 않는다. evidence item은 다음 중 하나가 있을 때만 reproducible하다:

```text
A. immutable captured content
B. per-item verified version-addressable recovery + 실제 사용한 evidence와의 equivalence 확립
otherwise → reproducibility NOT ESTABLISHED
```

provider 수준 또는 sample 수준 evidence만으로 version-addressable recovery를 가정하지 않는다
(§7.9 findings는 sample-bounded).

**Latest-only sources** — latest-only interface는 그 자체로 historical evidence의 recoverability를
확립하지 않는다. 정확한 evidence를 다른 검증된 version-addressable representation에서 독립적으로
복구할 수 있고 equivalence가 확립되면 capture가 반드시 필요한 것은 아니다. 그렇지 않으면
reproducibility를 위해 capture가 필요하다.

**Reproducibility representation** — semantic invariant만 고정한다: 각 evidence item / snapshot에
대해 reproducibility ESTABLISHED / NOT ESTABLISHED를 판정할 수 있어야 하고, established이면 그
basis를 식별할 수 있어야 한다. enum이나 category 이름은 고정하지 않는다(representation OPEN).

**Derived Evidence Lineage** — derived evidence는 source-reported evidence와 구별 가능해야 하고
formula identity / version과 required input evidence identity를 참조해야 한다. input availability가
확립된 곳에서 `derived.available_at ≥ max(required_input.available_at)`(§7.8 P12, lower bound
only). required input의 availability 중 하나라도 UNKNOWN이면 그 input만으로는 historical PIT
eligibility를 확립할 수 없다 — 이는 eligibility 진술이며 `derived.available_at = UNKNOWN`을
universal rule로 고정하지 않는다. derived availability representation OPEN, availability
derivation policy NOT SELECTED, Derived Feature Value Ownership OPEN.

**Current implementation finding (Derived-as-Raw, debt — 이번에 수정하지 않음)**: Operating Margin
/ Net Margin 등 derived 값은 upstream(`app/agents/stock_research/analysis.py`)에서 계산된 뒤
evaluator의 `FeatureValue` `raw` slot에 기록되며, `is_derived` / `Provenance.derived_from` /
`formula_id/version` / input evidence identity가 보존되지 않는다. 이 finding은 contract의 근거일 뿐
새 구현 작업 선택이 아니며, derivation ownership layer는 결정하지 않는다.

**Provider-neutral ownership boundary**:

```text
integration adapter        provider-specific identity 파싱, retrieval fact 기록,
                           provider-neutral evidence representation으로 매핑
provider-neutral identity  downstream으로 생존(adapter boundary 이후 소실 금지)
NormalizedResearchData     fact를 evidence reference와 함께 전달(vendor model import 금지 유지)
Evaluation layer           evidence reference를 소비; 이미 소실된 identity를 재구성하지 않는다
Calibration dataset        이후 calibration infrastructure 관심사
Policy identity            PolicyConfig 측
```

**Requirement / eligibility distinction** — 네 개념은 하나의 status로 합쳐지지 않는다:

```text
Current-runtime usability     identity + retrieved_at + latest-only 명시 — full historical
                              infrastructure를 요구하지 않는다
Reproducibility eligibility   모든 member에 대해 reproducibility ESTABLISHED
Historical PIT eligibility    §7.8 predicate를 계속 따른다
Calibration eligibility       더 넓은 calibration 요구(§7.6 / §7.7)로 여전히 BLOCKED
```

| | Evidence item ID | Availability ID | Revision ID | Ref. snapshot ID | Calib. dataset ID | Immutable / recoverable content | Historical universe ID | Corporate-action policy |
|---|---|---|---|---|---|---|---|---|
| Current-runtime assessment | REQUIRED | CONDITIONAL (`retrieved_at` required, historical `available_at` 불요) | REQUIRED (anchor 또는 ABSENT/UNKNOWN 명시) | CONDITIONAL (relative basis 사용 시) | NOT REQUIRED | CONDITIONAL (reproducibility 주장 시에만) | NOT REQUIRED | NOT REQUIRED |
| Current cross-sectional reference | REQUIRED | CONDITIONAL | REQUIRED | REQUIRED | NOT REQUIRED | REQUIRED | NOT REQUIRED (universe는 K) | OPEN |
| Historical Semantic calibration | REQUIRED | REQUIRED | REQUIRED | CONDITIONAL | REQUIRED | REQUIRED | CONDITIONAL | CONDITIONAL |
| Backtest / walk-forward | REQUIRED | REQUIRED | REQUIRED | CONDITIONAL | REQUIRED | REQUIRED | REQUIRED | OPEN |

**Invariants (E1–E13)**:

```text
E1  Every source-backed evidence item carries a provider-neutral Evidence Item Identity;
    identity must not be dropped or reconstructed downstream (from the adapter boundary).
E2  Evidence items differing in observation identity (period, report type, reporting
    basis, source column) are distinct evidence (§7.8 P3/P11).
E3  Identity ≠ content: identity alone does not establish reproducibility.
E4  An evidence item is reproducible only with (a) immutable captured content, or
    (b) per-item verified version-addressable recovery + established equivalence to the
    evidence actually used; otherwise reproducibility is NOT ESTABLISHED.
E5  A latest-only interface does not by itself establish recoverability of past
    evidence; capture is required only when independently verified recovery +
    equivalence is absent.
E6  retrieved_at is required for runtime-retrieved evidence; it never substitutes for
    historical available_at (§7.8 P4).
E7  Source temporal precision and timezone state are preserved; no upward precision
    fabrication.
E8  available_at is recorded only as the output of an identified availability policy;
    otherwise UNKNOWN.
E9  Revision relation is UNKNOWN unless established by authoritative metadata; revision
    ordering is not inferred from identifier form (§7.8 P6).
E10 Derived evidence is distinguishable from source-reported evidence and references its
    formula identity/version and required input evidence identities; where input
    availability is established, derived.available_at ≥ max(required input
    available_at) (§7.8 P12, lower bound only); UNKNOWN input availability prevents
    historical PIT proof from those inputs alone but does not freeze the derived
    availability representation.
E11 A reference snapshot binds immutable identity to its exact membership, exact
    evidence-item binding and relevant information boundary; construction policy
    remains outside this contract.
E12 An assessment/evaluation references its evidence basis (items + snapshots +
    evaluation_as_of) and, for each member, reproducibility status and (if established)
    its basis; the basis's reproducibility is the conjunction of its members.
E13 Evidence/Snapshot Identity ≠ Policy Identity; this contract does not define or imply
    policy content.
```

**OPEN (이 contract가 해소하지 않음)**:

```text
exact Python schema/types; manifest location/type; physical persistence mechanism;
storage technology; retention; hashing/content addressing; equivalence-check mechanism;
reproducibility-basis representation; recoverability verification procedure;
derived availability representation; availability derivation policy; revision-selection
policy; construction-policy metadata; reference universe; reference statistic;
normalization method; current-reference admissibility; numeric policy source;
calibration dataset metadata; historical universe/survivorship; historical valuation;
Derived Feature Value Ownership; result-level Provenance temporal-field cleanup
(published_at / retrieved_at / effective_at); Kiwoom time/version metadata
```

**Blocker status**: 이 freeze로 해소된 H1–H7 blocker는 **없다**. H5/H6은 해결 경계가 정의·축소됐을
뿐 미해결이다(persistence / reproducibility는 구현되지 않았다).

**Impact**: contract freeze 자체는 실행 가능한 capability를 열지 않는다(contract ≠ implementation ≠
captured evidence ≠ numeric readiness). 구현 이후 V0는 identity를 보존하는 auditable current-runtime
evidence(E4가 확립된 item에 한해 reproducible)에 도달할 수 있다. V1⁻ / V1 / V2는 여전히 NOT YET
FEASIBLE이다(K / B / N / S, V2는 Recommendation-level evidence 추가 필요 — §7.3).

**Work-selection state**: 이 contract freeze 이후 NEXT / SECOND / THIRD는 NOT SELECTED다. 다음
작업(K 또는 구현 포함)은 별도 critical-path review에서 선택한다.

design rev.0 → review(R1–R3) → rev.1 → review PASS → freeze 이력은 `docs/dev-log/2026-09-26.md`
§Q가 canonical이다.

### 7.11 Trustworthy V0 Product Boundary & Current-Runtime Evidence / Output Contract (FROZEN)

```text
Status          DESIGN COMPLETE / INDEPENDENT REVIEW PASS / FROZEN (rev.1-final)
Implementation  NOT STARTED
Live integration NOT VERIFIED
Supported Feature Set  0
USABLE V0       NOT YET
```

`FROZEN`은 product / runtime / output contract가 고정됐다는 뜻이다. V0 구현, live 검증, V0 usable,
SUPPORTED feature 존재, historical PIT 구현, reproducibility 확립, Recommendation Policy 구현을 뜻하지
않는다(`Contract FROZEN ≠ V0 IMPLEMENTED ≠ V0 USABLE`). 이 contract는 RE-04 / §7.4 / §7.5 / §7.7 /
§7.8 / §7.9 / §7.10을 **변경하지 않고** 그 위에 선다. 설계 이력(rev.0 → rev.1 → rev.1-final, review
지적)은 `docs/dev-log/2026-09-27.md` §L이 canonical이다 — 구현은 이 section만으로 contract를 복원할
수 있어야 한다.

**Purpose**: production wiring 구현 전에, trustworthy / auditable / 현재 지원되는 RE-05 정보만 사용자에게
노출하는 데 필요한 Product Boundary · Current-Runtime Evidence Selection Boundary · Output Contract를
정한다.

**Repository basis (baseline `8a9136f`, code inspection)**: EIP evidence 경로 · deterministic pipeline ·
Decision Eligibility는 production app 경로에 연결돼 있지 않다. 기존 사업연도 선택은 `now(UTC).year - 1` /
`reprt_code=11011` 고정이며 OpenDART non-`000` status를 하나의 오류로 처리한다. NRD history / YoY / trends는
evidence가 없고 비교 컬럼을 relabel한다. `FinancialSnapshot.current`는 OpenDART 연도 label 아래 Kiwoom
비율을 섞는다. Kiwoom `ka10001` PER / PBR / ROE의 산출 기준 · 기간 · 결측 인코딩은 확립돼 있지 않다(파서는
`"0"`을 `0.0`으로 읽는다; registry id `trailing_per`의 "trailing"도 근거 없음). 현 구현에서 State Coverage는
구조적으로 항상 `INSUFFICIENT`, FOE는 항상 `UNKNOWN`이다. legacy v1은 LLM thesis / scenarios(목표가 ·
확률) / `InvestmentAction` / `target_weight`를 노출하고 `risk_level`을 `MEDIUM`으로 고정한다.

#### 7.11.1 Product identity

```text
Trustworthy V0  = current-runtime financial evidence surface
                ≠ assessment surface
                ≠ recommendation surface
평가 단위        명시적으로 요청된 한국 상장 종목 1개 / evaluation
종료 출력        V0 Evaluation Record(내부) + 그 사용자 view
```

- V0 경로에 LLM judgment / LLM routing이 없다. legacy v1 출력과 합성하지 않는다.
- V0 capability가 **아닌** 것: recommendation / action / 목표가 / 확률 / scenario / score /
  `normalized_value` / signal / Core / 평가적 해석 · 비교 · 순위 / history · YoY · trend / 가격 /
  Forward · Flow · Market Confirmation · Event / historical as_of 평가 / reproducibility 주장 /
  LLM-generated content.
- 실행 경계: legacy LLM orchestrator를 수정하지 않는 **별도 V0 실행 경로**(명시적 종목 코드; 이름 해석은
  기존 결정론적 exact-match 조회만). 기존 EIP evidence 도구 / `analyze(evidence=…)` / pipeline 재사용은
  허용된다. V0 평가는 Supported Feature Set과 entity 식별에 필요한 provider만 호출한다. 세부 구현은 OPEN.

#### 7.11.2 Candidate vs Supported Feature Set

```text
Candidate Feature Set   V0가 고려할 수 있는 구현된 evaluator feature
                        현재: ROE · Operating Margin · Net Margin · Debt Ratio ·
                              provider-reported PER · PBR
Supported Feature Set   아래 S1–S6이 모두 확립된 candidate
Candidate ≠ Supported   evaluator 구현은 V0 support를 확립하지 않는다
                        (구현 사실 "implemented evaluators 6 / 14"는 support 진술이 아니다)
```

Support eligibility conditions(feature별, 전부 필요):

```text
S1 Evidence identity   EIP evidence reference가 V0 경로에서 산출된다(§7.10 E1).
S2 Measure semantics   source가 보고하는 measure의 정의 / 산출 기준이 문서 또는 empirical evidence로
                       확립돼 있다 — provider 계산값이면 그 계산 기준까지.
S3 Period semantics    값이 가리키는 observation period를 source identity로 알 수 있다.
                       알 수 없으면 S3 불충족(다른 source의 기간을 차용해 충족시킬 수 없다).
S4 Absence encoding    "값 없음"과 실제 값(0 / 음수 포함)을 구별하는 source 인코딩이 확립돼 있다.
                       loss-making 등 경계 사례의 source 동작이 알려져 있다.
S5 Derived coherence   (DERIVED만) 모든 input이 S1–S4를 충족하고, 같은 filing anchor · reporting basis ·
                       source term에서 오며, formula identity / version과 정의역 규칙이 명시돼 있다.
S6 Label honesty       사용자 표시명이 S2–S3로 확립된 것 이상을 주장하지 않는다.
```

Support status:

```text
support_status ∈ { SUPPORTED, NOT_SUPPORTED_IN_V0 }   — 정확히 두 contract state, 세 번째 state 없음
not_supported_reason = SUPPORT_CONDITIONS_NOT_ESTABLISHED + 미확립 S-condition 목록
"support-eligible"   design / readiness prose 전용 — runtime · serialized · 사용자 표시 status나
                     추가 contract state가 아니다(enum 표기 금지)
```

Freeze 시점 Feature Support Determination(evidence 기반 판정 기록이며, 조건 확립 / 반증 시 contract
변경 없이 판정만 바뀐다 — readiness 설명은 판정 기록의 prose이고 출력되지 않는다):

| Candidate | Origin | support_status | 미확립 조건 | readiness 설명(prose) |
|---|---|---|---|---|
| ROE | Kiwoom SOURCE_REPORTED | NOT_SUPPORTED_IN_V0 | S2 · S3 · S4 | — |
| PER (provider-reported) | Kiwoom SOURCE_REPORTED | NOT_SUPPORTED_IN_V0 | S2 · S3 · S4 · S6("trailing" 주장 금지) | — |
| PBR | Kiwoom SOURCE_REPORTED | NOT_SUPPORTED_IN_V0 | S2 · S3 · S4 | — |
| Operating Margin | DERIVED(OpenDART 입력) | NOT_SUPPORTED_IN_V0 | S4 absence encoding(§7.9 수준 evidence) · S5 통화 일관성(Q12) | support-eligible candidate — 남은 조건 확립 대기 |
| Net Margin | DERIVED | NOT_SUPPORTED_IN_V0 | 동일 | 동일 |
| Debt Ratio | DERIVED | NOT_SUPPORTED_IN_V0 | 동일 | 동일 |

```text
SUPPORTED count   0
```

#### 7.11.3 Current-runtime evidence semantics

```text
economic observation ≠ publication ≠ availability ≠ retrieval ≠ evaluation_as_of   (§7.8)
```

- **`evaluation_as_of`** = current-runtime V0 evaluation boundary instant: 평가당 정확히 1회, 그 평가에
  필요한 모든 evidence 조회가 완료된 **후** 기록, tz-aware, canonical UTC. 사용된 모든 source-reported
  item에 대해 `retrieved_at <= evaluation_as_of`. 이 값은 그 current-runtime 순서 관계만 확립한다.
- **`retrieved_at`** = V0 runtime이 해당 provider 응답을 관찰·수신한 tz-aware instant(source-reported
  item마다 REQUIRED, §7.10 E6). V0에서 허용되는 용도는 (1) 조회 시각 보존·표시, (2)
  `retrieved_at <= evaluation_as_of` 순서 확립 **뿐**이다.
- V0는 `retrieved_at` 또는 `evaluation_as_of`로 다음을 확립·산출·표시하지 않는다: `published_at` /
  `available_at` / historical availability / historical PIT eligibility / filing latestness / filing
  originality / correction ordering / reproducibility. identity 구분은 순서가 제약돼도 유지된다:
  `retrieved_at ≠ published_at`, `retrieved_at ≠ available_at`, `retrieved_at ≠ evaluation_as_of`.
- §7.8의 current-runtime relation(retrieval과 availability의 관계)은 frozen architecture reasoning으로
  그대로 유효하다. V0 product contract는 그것을 runtime / product semantic claim으로 사용하지 않는다(V0
  자체 주장 범위의 축소일 뿐 §7.8 변경·재해석 아님). V0는 `available_at`을 산출·확립하지 않는다(E8).
- observation / report type / reporting basis / source term / version anchor는 source 표기 그대로이며,
  source가 제공하지 않으면 "source 미제공"(ABSENT)으로 명시하고 다른 source의 label로 채우지 않는다.
- **Current-runtime eligibility**: (1) SOURCE_REPORTED는 이번 평가 안에서 조회(cache / 이전 요청 /
  snapshot 재사용 금지), `retrieved_at <= evaluation_as_of`, identity 완전. (2) DERIVED는 모든 input이
  (1)을 만족. (3) OpenDART는 선택된 연간 보고서의 당기 컬럼만(비교 컬럼 금지, §7.8 P3). (4) 해당 feature가
  SUPPORTED.
- `Current-runtime usability ≠ Historical PIT eligibility`: historical as_of 요청은 NOT SUPPORTED(거절);
  historical `available_at`을 확립하지 않고, 나중 filing 비교 컬럼을 back-project하지 않으며, history /
  YoY / trend를 노출하지 않는다.

#### 7.11.4 Annual-report selection (provider-neutral semantics only)

- 대상: 이번 평가의 current-runtime 조회 경로에서 실제로 얻을 수 있는 eligible annual-report evidence
  중 검증된 provider / report-period semantics에 따라 가장 최근인 것. eligible annual evidence = adapter가
  검증된 provider 의미로 "연간 보고서"로 분류한 보고서의 당기 evidence(OpenDART `reprt_code=11011` 의미는
  OFFICIAL-DOC VERIFIED, §7.9 S4).
- 후보별 조회 결과 분류: `EVIDENCE_RETURNED` / `REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE`(positive
  classification만) / `FAILURE`.
- 더 최근 후보 → 더 오래된 후보 진행은 더 최근 후보가 `REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE`로 positive
  분류된 경우에**만** 허용된다. network failure / authentication failure / rate-limit · provider
  operational failure / malformed response / unknown status / unclassified provider error / integrity
  failure는 fail closed이며 fallback을 일으키지 않는다.
- 보고서가 반환됐지만 개별 계정 / 값이 없는 것은 report-level fallback 조건이 아니다(해당 feature
  UNAVAILABLE). 모든 후보가 UNAVAILABLE이면 해당 provider 의존 SUPPORTED feature는 UNAVAILABLE
  (`NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES`).
- 조회한 후보와 후보별 분류 결과를 record에 기록한다. 후보 생성은 검증된 provider / report-period
  semantics를 사용하고, 유한하며, 달력 가정(12월 결산 등)을 두지 않는다.
- 후보 완전성이 확립되지 않으면 V0는 latest filing / latest corrected filing / original / final / latest
  financial information을 주장하지 않는다. evidence가 실제로 확립한 identity(`bsns_year` / `reprt_code` /
  제공된 경우 `rcept_no` / `fs_div`·reporting basis / source term / source period 표기)만 노출한다.
- **고정하지 않는 것**: 구체적 OpenDART status-code mapping(Q2b), 특정 후보 알고리즘(Y / Y-1 / Y-2 등),
  12월 결산 가정.

#### 7.11.5 Evidence Basis Manifest / reproducibility

V0 Evaluation Record는 §7.10 **logical Evidence Basis Manifest**를 포함 / 참조한다 — 병렬 대체 개념을
만들지 않는다. §7.10 current-runtime assessment 행(Evidence item ID REQUIRED · Revision ID REQUIRED(anchor
또는 ABSENT/UNKNOWN 명시) · Ref. snapshot ID CONDITIONAL(relative basis 사용 시) · immutable/recoverable
content CONDITIONAL(reproducibility 주장 시에만) · "identity + retrieved_at + latest-only 명시")을 그대로
적용한다.

```text
evidence item members        SUPPORTED output이 사용한 모든 source-reported / derived item과 derived input
reference snapshot members   사용 없음 명시(V0는 relative basis를 사용하지 않는다 — snapshot을 만들지 않음)
evaluation_as_of             §7.11.3
member별 reproducibility      NOT ESTABLISHED(확립된 basis 없음); basis = member의 conjunction → NOT ESTABLISHED
revision / version anchor    item별 anchor 또는 ABSENT; revision relation UNKNOWN(E9)
source serving semantics     OpenDART fnlttSinglAcnt: version을 지정해 요청할 수 없고 provider가 정한 단일
                             version을 제공(latest-only at retrieval, §7.9 M1 OFFICIAL-DOC) — 제공된 version이
                             최신 정정본이라고 주장하지 않는다(그 관찰은 sample-bounded)
policy identity              포함하지 않음(E13)
```

```text
logical Evidence Basis Manifest   REQUIRED
persistent manifest storage       NOT REQUIRED for V0
capture infrastructure            NOT REQUIRED for V0 (reproducibility를 주장하지 않으므로)
Reference Snapshot construction   NOT REQUIRED (relative basis NOT USED)
historical reconstruction / PIT   NOT REQUIRED
reproducibility                   NOT ESTABLISHED
```

manifest의 목적은 evidence-basis identity / binding의 명시이며 replay / reconstruction 증명이 아니다.
identity나 manifest의 존재는 reproducibility를 뜻하지 않는다(E3). `rcept_no`로 복구 가능하다고 주장하지
않고(§7.9 M2), snapshot store 재조회를 재현이라 부르지 않는다. 재현성 enum 이름은 §7.10 아래 OPEN이며
V0에서 허용되는 의미는 NOT ESTABLISHED 하나뿐이다.

#### 7.11.6 Output contract

사용자 view에 노출 가능: entity(symbol, 표시용 name — evidence 아님) · `evaluation_as_of` · scope
declaration(current-runtime only, historical PIT 미지원, unsupported capability와 reason) · report-selection
evidence(조회 후보 · 분류 · 선택 결과) · 모든 candidate의 support status · SUPPORTED feature의 availability /
value / unit · evidence identity / provenance(origin, source provider / interface, report / period / basis /
source term, version anchor 또는 ABSENT, source serving semantics) · `retrieved_at` · derivation lineage
(formula identity / version / 공식 정의 문장 / input evidence) · Evidence Basis Manifest 요약 ·
reproducibility = NOT ESTABLISHED. record에는 `contract_version`과 적용된 Feature Support Determination
식별자가 포함된다.

Feature 항목 규칙:

```text
support_status          SUPPORTED | NOT_SUPPORTED_IN_V0 (필수)
NOT_SUPPORTED_IN_V0     value 없음 · availability 필드 없음 · not_supported_reason 필수
                        (SUPPORT_CONDITIONS_NOT_ESTABLISHED + 미확립 S-condition 목록)
SUPPORTED               availability ∈ {AVAILABLE, UNAVAILABLE}
  AVAILABLE             value + unit(0 / 음수 그대로) + evidence identity / provenance 필수
  UNAVAILABLE           value 없음 · unavailable_reason 필수: NO_MATCHING_SOURCE_ITEM /
                        SOURCE_VALUE_ABSENT / DERIVED_INPUT_UNAVAILABLE / DERIVED_UNDEFINED_FOR_INPUTS /
                        NO_ANNUAL_REPORT_EVIDENCE_AMONG_EXAMINED_CANDIDATES / UNKNOWN_REASON
display label           확립되지 않은 산출 기준 / 기간을 주장하지 않는다(예: "Trailing PER" 금지)
```

pending / support-eligible 같은 runtime state를 만들지 않는다. Coverage / FOE는 테스트 · 감사 · pipeline
검증을 위한 내부 산출물로만 남을 수 있다.

**Prohibited V0 output**: `normalized_value` · `directionality` · `requirement_role` · Decision Eligibility ·
Coverage / FOE architecture enum · score · signal · Core Attractiveness · good / bad · cheap / expensive ·
attractive / unattractive · ranking · threshold interpretation · recommendation · `InvestmentAction` ·
target price · probability · scenario · `target_weight` · legacy v1 thesis · legacy v1 risk / confidence
judgment · LLM-generated summary / judgment · NRD / `RecommendationEvaluationState` 전체 직렬화 · 가격(identity
없음). raw 값은 평가적 판단이 아니다 — 색상 / 아이콘 / 비교로 평가를 암시하지 않는다(§7.5 / §7.7 유지).

#### 7.11.7 Derived evidence

Operating Margin / Net Margin / Debt Ratio는 support 조건이 확립될 때만 SUPPORTED가 될 수 있다. formula
identity · formula version · input evidence identity · origin = DERIVED를 요구한다. V0는 derivation 위치
(module)에 의존하지 않는다 — **Derived Feature Value Ownership은 OPEN이며 고정하지 않는다**. unavailable
reason을 정확히 확립할 수 없으면 `UNKNOWN_REASON`을 쓰고 더 강한 reason을 만들지 않는다. 정의역 규칙(예:
자본 ≤ 0)을 값 부재 사실처럼 표시하지 않는다.

#### 7.11.8 Legacy v1 boundary

V0 trust boundary 필수 조건(이것으로 충분): 별도 trustworthy surface / response boundary; V0 출력에 legacy
judgment 필드(`investment_thesis` / `scenarios` / `risk_level` / `confidence` / `InvestmentAction` /
`target_weight`) 없음; LLM judgment path 없음; LLM routing 없음; v1 결과와 합성 없음; V0 surface는 legacy
thesis / scenarios를 RE-05 validated로 표현하지 않는다.

v1 trust label / gating / hiding / retirement는 별도 OPEN product / maintenance decision이며 V0 contract
freeze나 V0 구현을 막지 않는다. v1의 유지 / 제거는 결정하지 않는다.

Decision Eligibility는 V0 경로에서 호출하지 않으며 사용자에게 보이지 않는다(§7.4 불변). Coverage / FOE
architecture enum은 사용자에게 보이지 않는다(producer 불변).

#### 7.11.9 Failure semantics

```text
semantics not established                     → NOT_SUPPORTED_IN_V0 (UNAVAILABLE로 표시하지 않음)
SUPPORTED, 정당한 source 값 부재              → UNAVAILABLE + reason(불명확하면 UNKNOWN_REASON)
SUPPORTED + AVAILABLE, required identity 없음  → integrity failure → request failure (partial 금지)
required provider operational failure         → fail closed (older-report fallback 금지)
annual candidate positively UNAVAILABLE       → 다음 후보(§7.11.4)
report 반환, 개별 값 부재                     → 해당 feature UNAVAILABLE (fallback 없음)
unsupported capability                        → NOT_SUPPORTED (scope declaration)
version anchor 부재                            → ABSENT 표시 (실패 아님)
reproducibility not established               → NOT ESTABLISHED (실패 아님)
critical path 미충족 / FOE UNKNOWN              → 판정으로 노출하지 않음
Supported Feature Set 비어 있음                 → record 생성 가능, usable 선언 불가
종목 해석 실패 / historical as_of 요청           → request failure / NOT SUPPORTED
```

UNKNOWN / UNAVAILABLE / NOT_SUPPORTED는 0 · neutral · estimated value · evaluative label로 조용히 바뀌지
않는다.

#### 7.11.10 Acceptance / usability boundary

```text
Contract FROZEN ≠ V0 IMPLEMENTED ≠ V0 USABLE
```

- contract acceptance: independent review PASS, frozen contract 충돌 없음, contract-level OPEN 없음 —
  **충족(이 freeze)**.
- implementation acceptance: 각 V0 invariant의 offline test 증명, V0 경로 LLM import 없음, v1 회귀 없음,
  금지 필드 부재 projection test, manifest 구성 §7.11.5 일치, 후보 분류 / fallback §7.11.4 일치, Q2b / Q3
  해소.
- live integration acceptance(메커니즘 — marker / env / CI — 는 지정하지 않음): evidence path end-to-end,
  Q2b / Q3 / Q12 확인, CFS / OFS, 정정 공시 filing, (Kiwoom feature 지원 시) Q1.
- **usable / ready for first real use** = contract acceptance PASS + implementation acceptance PASS + live
  integration acceptance PASS + **Supported Feature Set ≥ 1**. live integration NOT VERIFIED인 동안 usable
  선언 불가.

```text
현재   contract FROZEN / IMPLEMENTATION NOT STARTED / live integration NOT VERIFIED /
       Supported Feature Set = 0 / USABLE V0 = NO
```

#### 7.11.11 Invariants (V0-1 – V0-19, FROZEN)

```text
V0-1  Candidate ≠ Supported: SUPPORTED는 S1–S6이 확립된 feature에만 부여된다. evaluator 존재만으로
      부여되지 않는다.
V0-2  NOT_SUPPORTED_IN_V0 항목에는 value · availability 필드가 없고,
      not_supported_reason(SUPPORT_CONDITIONS_NOT_ESTABLISHED + 미확립 조건 목록)이 있다.
      UNAVAILABLE로 표시되지 않는다.
V0-3  미확립 provider semantics는 AVAILABLE evidence로 표시되지 않는다.
V0-4  display label은 확립되지 않은 산출 기준·기간을 주장하지 않는다.
      다른 source의 기간 label을 차용하지 않는다.
V0-5  AVAILABLE feature마다 evidence identity가 있다. 없으면 요청이 실패한다(partial 금지).
V0-6  V0 Evaluation Record는 §7.10 logical Evidence Basis Manifest를 포함한다(evidence item members ·
      reference snapshot members = 사용 없음 명시 · evaluation_as_of · member별 재현성 판정).
V0-7  모든 member와 basis의 재현성은 NOT ESTABLISHED다. identity나 manifest로부터
      재현성을 주장하지 않는다.
V0-8  evaluation_as_of는 current-runtime V0 evaluation boundary instant다 — 평가당 1회,
      필요한 evidence 조회가 모두 끝난 후 기록되는 tz-aware instant이며 canonical UTC로 저장된다.
      평가에 사용된 모든 source-reported item에 대해 retrieved_at <= evaluation_as_of다.
      retrieved_at과 evaluation_as_of는 별개 identity로 유지된다.
V0-9  V0는 retrieved_at을 (a) 조회 시각 보존·표시, (b) retrieved_at <= evaluation_as_of 순서
      확립에만 사용한다. V0는 retrieved_at이나 evaluation_as_of로부터 published_at · available_at ·
      historical availability · historical PIT eligibility · filing latestness · originality ·
      correction ordering · reproducibility를 확립·산출·표시하지 않으며,
      available_at <= retrieved_at을 V0 runtime / product claim으로 사용하지 않는다.
V0-10 더 최근 연간 보고서 후보에서 더 오래된 후보로의 진행은
      REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE 분류에서만 허용된다. 그 외 결과는 fail closed하며,
      조회한 후보와 결과가 record에 기록된다.
V0-11 후보 완전성이 검증되지 않았으면 "가장 최근" 주장을 하지 않는다.
      latest / corrected / original / final 주장을 하지 않는다.
V0-12 OpenDART evidence는 선택된 연간 보고서의 당기 컬럼만 사용한다.
      history / YoY / trend와 비교 컬럼은 출력에 없다.
V0-13 UNKNOWN / UNAVAILABLE / NOT_SUPPORTED는 0 · neutral · 추정값 · 평가 label로 대체되지 않는다.
V0-14 V0 출력에 recommendation · action · 목표가 · 확률 · score · normalized_value · 평가 label ·
      directionality · Decision Eligibility · Coverage / FOE enum이 없다.
V0-15 V0 실행 경로는 LLM(판단·routing)을 호출하지 않으며, V0 출력에 LLM 생성 텍스트가 없다.
V0-16 V0 출력은 legacy v1 필드를 포함하지 않고 v1 출력과 합성되지 않는다.
V0-17 DERIVED feature는 formula identity/version과 input evidence를 동반한다.
      V0는 derivation 위치(module)에 의존하지 않는다.
V0-18 V0는 historical as_of 요청을 거절한다.
V0-19 V0 support_status는 정확히 두 contract state — SUPPORTED, NOT_SUPPORTED_IN_V0 — 만
      가진다. "support-eligible" 같은 readiness 설명은 runtime · serialized · 사용자 표시 상태를
      추가로 만들지 않는다.
```

#### 7.11.12 OPEN after freeze (frozen contract를 무효화하지 않음)

```text
Q1   Kiwoom ROE / PER / PBR semantics(산출 기준 · 기간 · 결측 인코딩 · 적자 동작)
     — 해당 feature가 SUPPORTED가 되기 전에만 필요
Q2b  concrete OpenDART status → REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE mapping — implementation / live blocker
Q3   annual-report candidate generation / bsns_year semantics(비12월 결산 포함) — implementation / live blocker
Q4   legacy v1 trust label / API field — separate product / maintenance decision
Q5   legacy v1 gating / hiding / retirement — separate product decision
Q8   legacy v1 / V0 사업연도 불일치 — separate product decision
Q9   stronger derived unavailable reasons — non-blocking
Q10  registry trailing_per rename — separate maintenance (사용자 표시 측면은 V0-4로 RESOLVED)
Q12  OpenDART amount currency / absence encoding — 영향받는 derived feature가 SUPPORTED가 되기 전에 필요
RESOLVED  Q2a provider-neutral fallback semantics · Q6 logical Evidence Basis Manifest · Q7 Coverage / FOE
          비노출 · Q11 가격 제외
```

**Non-goals**: V0 implementation / wiring, numeric calibration, K, PolicyConfig, Feature Normalization
implementation, component score / signal / threshold, Core Attractiveness, Recommendation Policy stages 2–9,
StockOpportunityAssessment, historical PIT, persistent manifest / capture / storage / Reference Snapshot
construction, new evaluators, Portfolio Strategy redesign, UI visual design, live-test gating mechanism.

**Frozen-contract compatibility**: RE-04(SOA / action 미생성) · §7.4(불변, V0 미호출) · §7.5(normalized_value
출력 금지, implicit default 없음) · §7.7(calibration 없음) · §7.8(P5: evaluation_as_of ≠ availability; P4 →
V0-9, P3 / P11 → V0-12, P2 / P7 → V0-18; current-runtime relation은 유효하게 남고 V0가 product claim으로 쓰지
않을 뿐) · §7.9(최신 정정본 / 원본 주장 없음, rcept_dt 미사용, general recoverability 미전제) · §7.10(manifest
semantic requirement와 current-runtime 행 그대로 적용, E1–E13 준수, representation OPEN 부분만 V0 범위에서
정함) — **충돌 없음, frozen 문구 변경 없음**.

**Blocker status**: H1–H7 newly resolved NONE. **Work-selection state**: 이 contract freeze 시점에 NEXT /
SECOND / THIRD는 NOT SELECTED다.

## 8. Dependency Boundaries / Invariants

architecture-level invariant만 남긴다(implementation-level assertion 전체는
`tests/`가 canonical):

- **`app/evaluation/*`는 vendor API/Service/MCP/LLM을 직접 import하지
  않는다** — `NormalizedResearchData`/`FeatureEvaluationResult`처럼 이미
  정규화된 값만 소비한다(예외: `research_data_builder.py`가
  `DeterministicAnalysisResult` 타입만 import — 이미 정규화된 산출물의
  **타입**일 뿐, vendor 호출은 하지 않는다).
- **missing evidence ≠ neutral**: 값이 없으면 `score=None`/
  `signal=UNKNOWN`이지 0/NEUTRAL이 아니다.
- **Coverage는 Assembly에서 재계산되지 않는다**: Assembly는 이미 계산된
  `CoverageAssessment`를 파라미터로만 받아 그대로 배치한다.
- **Event evidence는 Forward Coverage를 mutate하지 않는다**: Core
  component는 Event Overlay에 의해 변형되지 않는다.
- **scoring/policy/calibration은 evaluation orchestration과 완전히
  분리돼 있다**: `Numeric Calibration = OPEN`인 동안 orchestrator를 포함한
  어떤 evaluation 코드도 threshold/weight/score를 만들지 않는다.
- **Portfolio Strategy evaluation ≠ Stock Research evaluation**:
  `EvaluationContext`는 `PortfolioContext`/`InvestorProfile`을 포함하지
  않는다 — 서로 다른 입력 경계를 쓴다.

---

## 9. Runtime Interfaces

| Interface | 위치 | 실행 경계 |
|---|---|---|
| REST API (FastAPI) | `app/api/main.py`, `routes.py` | 외부 client ↔ `SupervisorOrchestrator`. `lifespan`에서 의존성 그래프 1회 생성(Kiwoom token 캐싱 유지) |
| MCP Server | `app/mcp/server.py` | 별도 프로세스/외부 MCP client ↔ Domain Tool. 현재 어떤 Agent도 이 경로를 실행에 쓰지 않는다 — 노출 경계로만 존재 |
| In-process Agent execution | `app/agents/*/orchestrator.py` | 같은 Python 프로세스 안에서 Domain Tool을 직접 호출(REST API가 이 경로를 구동) |

REST API와 MCP Server는 서로 독립된 두 개의 외부 노출 경계다 — REST API가
MCP Server를 거쳐 Domain Tool을 호출하지 않는다(둘 다 같은 Domain Tool
클래스를 각자 직접 참조할 뿐).

---

## 10. Canonical Sources

```text
Current Architecture
→ docs/ARCHITECTURE.md (이 문서)

Current Executable Contracts / Invariants
→ app/models/*.py (docstring) + tests/test_*.py

Decision Rationale / FROZEN History / Empirical Research
→ docs/dev-log/

Project Map / Current Position / NEXT
→ README.md

Claude Code Session / Repository Operating Rules
→ CLAUDE.md
```

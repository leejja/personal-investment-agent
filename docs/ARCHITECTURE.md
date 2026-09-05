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
| Evaluation | Recommendation Evaluation pipeline의 deterministic building block(Coverage/Assembly/FeatureEvaluator) | `app/evaluation/` |

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
FeatureEvaluationResult[]             app/evaluation/fundamental_evaluators.py (IMPLEMENTED —
        ↓                             단 ROE/Operating Margin 2개 evaluator뿐)
Coverage                              app/evaluation/coverage_evaluator.py (IMPLEMENTED)
        ↓
Assembly                              app/evaluation/assembly.py (IMPLEMENTED)
        ↓
FutureOpportunityEvidence             app/evaluation/coverage_evaluator.py::
        ↓                             evaluate_future_opportunity_evidence (IMPLEMENTED)
RecommendationEvaluationState          app/models/research_context.py (model 존재, IMPLEMENTED)
```

**이 5개 building block은 각각 개별적으로 구현·테스트 완료 상태이지만,
이들을 하나의 실행 경로로 연결하는 orchestrator는 아직 존재하지 않는다**
(`app/evaluation/orchestrator.py`는 아직 생성되지 않았다 — repository에
실재 확인함). 즉 위 파이프라인은 "따로따로는 동작이 검증된 부품들의 도면"
이지 "실제로 실행되는 하나의 흐름"이 아직 아니다.

### 7.2 First Deterministic Pipeline Slice — 확정된 architecture 경계

Orchestrator 구현(NEXT, 아직 미착수)이 따라야 할 architecture 경계는
확정됐다:

- **`family_assessments`(top-level)**: 각 component assembly가 만든
  `FeatureFamilyAssessment`를 재계산 없이, canonical component/family
  순서(`Component` enum 선언 순서 + `get_component_families()`)에 따라
  reference로 이어붙인 flat list다.
- **`core_attractiveness` = `None`, `market_confirmation` = `None`**: 이번
  slice는 이 두 aggregate/confirmation을 만들지 않는다 — 새로운 집계·판단
  semantics를 발명하지 않는다는 원칙 때문이다. 두 필드가 담을 정보는 이미
  `component_assessments`에 전부 존재하므로 정보 손실은 없다.
- **Orchestration ownership = `app/evaluation/orchestrator.py`(예정)**:
  Recommendation Evaluation Layer가 소유하며, Stock Research Agent 내부가
  아니다. vendor/service/MCP/LLM을 새로 import하지 않는다.
- **Executable evaluator = 실제 구현된 것만 실행**: 현재 `RoeFeatureEvaluator`/
  `OperatingMarginFeatureEvaluator`(`app/evaluation/fundamental_evaluators.py`)
  2개뿐이다. Feature Registry(`app/evaluation/feature_registry.py`)에는 14개
  feature identity가 등록돼 있지만 evaluator가 없는 12개는 orchestrator가
  fake result를 만들지 않는다 — catalog identity만 있는 채로 남는다.

### 7.3 현재 상태 요약

```text
Coverage Layer                = IMPLEMENTATION COMPLETE
Assembly Layer                = IMPLEMENTATION COMPLETE
Future Opportunity Evidence   = IMPLEMENTED
Evaluation Orchestration      = ARCHITECTURE READY, NOT IMPLEMENTED (NEXT)
Recommendation Policy         = NOT IMPLEMENTED
Numeric Calibration           = OPEN
```

RE-04/RE-05의 상세 결정 과정, contract 확정 근거는 `docs/dev-log/
2026-08-29.md` §1~§51과 `app/models/recommendation.py`/`research_context.py`
docstring이 canonical이다.

---

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

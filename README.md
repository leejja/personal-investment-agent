# Personal Investment Multi-Agent System

개인의 실제 투자 의사결정을 지원하기 위한 **Multi-Agent 기반 개인화 투자 분석 시스템**.

단순한 종목 추천이나 자동매매 시스템이 아니라, 여러 독립적인 데이터 소스를 수집·분석하고 사용자의 실제 포트폴리오와 기존 투자 전략을 함께 고려하여 **일관되고 근거를 추적할 수 있는 투자 전략과 신규 투자 후보를 생성하는 것**을 목표로 한다.

이 README는 **Project Map / Navigation Entry**다 — 상세 architecture spec, decision history, executable contract는 아래 [Documentation Map](#documentation-map)이 가리키는 문서/코드가 canonical source다.

---

## Overview

- **무엇을 만드는가**: 시장 환경 → 개별 종목 분석 → 신규 투자 후보 탐색 → 실제 포트폴리오 영향 분석 → 개인화 투자 전략으로 이어지는 investment decision-support 파이프라인.
- **무엇이 아닌가**: 자동매매 시스템, 단순 종목 스크리너. 최종 결과에는 데이터 출처·분석 근거·Confidence·Risk·Bull/Base/Bear 시나리오·추천/제외 근거가 함께 포함되도록 설계한다.
- **자동매매**는 이 프로젝트의 최종 확장 단계로만 고려한다 — 상세 로드맵은 `docs/AUTOMATED_TRADING_ROADMAP.md` 참고.

## Final Goal

최종 목표는 **종목 자체의 투자기회 판단**과 **실제 포트폴리오를 반영한 행동 판단**을 분리된 2단 decision으로 만드는 것이다(RE-04 FROZEN contract):

```text
Stock Research Agent
  │
  ▼
StockOpportunityAssessment
  종목 자체의 투자기회 판단 (ATTRACTIVE / NEUTRAL / UNATTRACTIVE)

PortfolioContext ─────────────┐
StockOpportunityAssessment ───┼──▶ Portfolio Strategy
InvestorProfile ──────────────┘
  │
  ▼
PortfolioActionRecommendation
  실제 보유/exposure를 반영한 행동 판단
  │
  ▼
BUY / ADD / HOLD / REDUCE / EXIT
```

> `StockOpportunityAssessment`(종목 자체 판단)와 `PortfolioActionRecommendation`(exposure를 반영한 행동 판단)은 RE-04에서 FROZEN된 2단 contract다. Final input은 정확히 `StockOpportunityAssessment` + `PortfolioContext` + `InvestorProfile` 3개이며 `MarketAnalysis`는 포함되지 않는다 — `MarketAnalysis`는 독립 market capability로 남고 이 경로에 직접 연결되지 않는다(아래 [Architecture](#architecture) 참고). **현재 v1 Portfolio Strategy Agent는 아직 `StockOpportunityAssessment`를 입력으로 받지 않는다** — `MarketAnalysis`/`StockAnalysis[]`(LLM narrative 포함)와 보유 종목만으로 `StrategyResult`를 만든다(current v1 한정 특징, final target 아님). `PortfolioContext`/`InvestorProfile`은 어느 경우든 다른 값에서 파생되지 않는 독립 입력이다 — 현재 실제 구현 topology는 아래 [Architecture](#architecture) 참고.

---

## Architecture

README Architecture는 **전체 시스템 topology를 한눈에 이해하기 위한 것**이다. 상세 spec/dependency boundary/runtime interface/RE-04·RE-05 세부 architecture는 → **`docs/ARCHITECTURE.md`**.

```text
전체 구조를 한눈에 본다 (System Architecture Overview)
        ↓
영역별 diagram으로 세부 관계를 확인한다 (아래 각 section)
        ↓
상세 specification은 docs/ARCHITECTURE.md에서 확인한다
```

### System Architecture Overview

```text
                                                      ┌──────┐
                                                      │ User │
                                                      └──────┘
                                                         │
                                             ┌─────────────────────────┐
                                             │ API / Runtime Interface │
                                             └─────────────────────────┘
                                                         │
                                               ┌─────────────────────┐
                                               │ Supervisor / Router │
                                               └─────────────────────┘
                                                         │
          ┌────────────────────┬─────────────────────────┤
          ▼                    ▼                         ▼
   ┌──────────────┐  ┌─────────────────────┐  ┌──────────────────────┐
   │ Market Agent │  │ Candidate Discovery │  │ Stock Research Agent │
   └──────────────┘  └─────────────────────┘  └──────────────────────┘
          │                                              │
   MarketAnalysis      candidate symbols ────────────────┤
   (independent market                                   │
    capability)                                          ▼
                                                   DeterministicAnalysisResult
                                                         │
                                            Recommendation Evaluation
                           (Normalization → Feature Evaluation → Coverage → Assembly)
                                                         │
                                   ┌─────────────────────┼─────────────────────────┐
                                   ▼                     ▼                         ▼
                          Core Attractiveness   Market Confirmation    FutureOpportunityEvidence
                 (Fundamental/Valuation/Forward/Flow)    │                         │
                                   │           (Momentum/Technical)                │
                                   │                     │                         │
                                   └─────────────────────┴─────────────────────────┘
                                                         │
                             Event Overlay (parallel) ───┼─── Risk / Coverage / Confidence
                                                         │
                                           RecommendationEvaluationState
                                        (progressively populated container)
                                                         │
                                               Recommendation Policy
                                             (9-stage staged decision)
                                                         │
                                            StockOpportunityAssessment
                                                         │
                                         ┌───────────────┼───────────────┐
                                         │               │               │
                                 PortfolioContext        │        InvestorProfile
                                (account/provider)       │        (user/request)
                                         │               │               │
                                         └───────────────┼───────────────┘
                                                         ▼
                                                Portfolio Strategy
                                                         │
                                           PortfolioActionRecommendation
                                                         │
                                         BUY / ADD / HOLD / REDUCE / EXIT

  Evidence / Source Traceability: StockOpportunityAssessment → Decision Reason
  → Metric/Interpretation → Fact/Claim → Evidence → Original Source (all stages)


── Shared Data Access ──

Market Agent · Candidate Discovery · Stock Research Agent
                    │
              Domain Tools
                    │
                Services
                    │
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
    ECOS        OpenDART       Kiwoom

KIS — research / empirical verification only, not integrated


── External / Process Boundary ──

External MCP Client
  │
    MCP protocol
  ▼
MCP Server
  │
Domain Tools (same classes)

Normal Agent execution does NOT use MCP.
```

위 diagram은 **final target architecture**(RE-04 FROZEN 기준)다 — 구현 진행 상태(DONE/NEXT/v1 등)는 담지 않는다. 현재 어디까지 구현됐는지는 [Current Development Position](#current-development-position)과 아래 각 상세 section에서 설명한다.

아래 각 section은 위 overview의 각 영역을 상세화한 것이다 — `Application / Decision Flow`는 현재 runtime, `Recommendation Evaluation`/`Portfolio Strategy`는 final contract와 현재 구현 상태를 함께 대조한다.

### Application / Decision Flow

```text
User
  │
  ▼
FastAPI REST API (app/api/)
  │
  ▼
Supervisor / Router (app/supervisor/)
intent 분류(LLM은 enum만 제안) → Python 고정 dispatch
  │
  ├── Market Agent (app/agents/market/)
  ├── Stock Research Agent (app/agents/stock_research/)
  ├── Portfolio Strategy Agent (app/agents/portfolio/)
  └── Candidate Discovery (app/discovery/)
         │  Agent가 아니다 — 투자 판단 없는 순수 종목 필터링
         ▼
    candidate symbols
         │
         ▼
    Stock Research Agent 실행
```

### Recommendation Evaluation (RE-05)

```text
DeterministicAnalysisResult    Stock Research Agent 산출(기존 구현)
        ↓
NormalizedResearchData
        ↓
Feature Evaluation              14개 registered feature 중 6개 실제 구현
                                 (ROE/Operating Margin/Net Margin/Debt
                                 Ratio/Trailing PER/PBR)
        ↓
Component Coverage
        ↓
Assembly
        ↓
RecommendationEvaluationState
  ├─ State Coverage (top-level)     ─┐ 서로 독립적인 sibling producer output
  └─ FutureOpportunityEvidence      ─┘ (현재 orchestrator가 채우는 범위는 여기까지)
        ↓
[미래 Recommendation Policy consumer — 아직 없음]
  Step 1 Decision Eligibility projection   (primitive만 구현, orchestrator 미연결)
  Step 2~8                                 NOT IMPLEMENTED
```

```text
Coverage                DONE
Assembly                DONE
Full Orchestration      FIRST DETERMINISTIC PIPELINE SLICE COMPLETE / FROZEN
READY Evaluator Expansion   IMPLEMENTED (Net Margin/Debt Ratio/Trailing PER/PBR)
Top-level Coverage      IMPLEMENTED / VERIFIED / FROZEN (Step J)
Decision Eligibility    Policy Step 1 primitive IMPLEMENTED / VERIFIED / FROZEN
                        (orchestrator 미연결, 결과 비저장)
Recommendation Policy   NOT IMPLEMENTED (Step 2~8 + 실제 policy consumer 없음)
PIT Financial Evidence  Contract FROZEN (§7.8) — implementation NOT STARTED
OpenDART PIT Verif.     EXECUTION COMPLETE / FINDINGS FROZEN (§7.9)
Evidence Identity       Contract FROZEN (§7.10) — implementation PARTIAL
                        (Evidence Identity Preservation slice IMPLEMENTED / offline 검증 PASS)
Trustworthy V0 Contract Contract FROZEN (§7.11) — implementation NOT STARTED / USABLE V0 NOT YET
Trustworthy V0 Impl.    NOT STARTED — NEXT: OpenDART Annual-Report Evidence Selection (SELECTION FROZEN)
Numeric Calibration     OPEN (readiness BLOCKED — Calibration Readiness Audit)
```

**연결 완료된 canonical path**(`app/evaluation/orchestrator.py::run_first_deterministic_pipeline`)가 위 building block을 순서대로 호출해 `RecommendationEvaluationState`를 만든다 — "연결될 설계"가 아니라 실제로 실행되는 하나의 흐름이다. Net Margin/Debt Ratio evaluator가 추가되면서 Fundamental component의 `critical_path_satisfied`가, Trailing PER evaluator가 추가되면서 Valuation component의 `critical_path_satisfied`가 각각 evidence가 있을 때 `True`로 계산된다(coverage_evaluator.py는 이번 확장에서 수정하지 않았다 — 기존 FROZEN Tier 판정 로직이 evaluator 확장에 자연스럽게 반응한 것이다). Step J 이후 `RecommendationEvaluationState.coverage`(top-level evidence-coverage summary)도 `evaluate_recommendation_coverage()`가 채운다 — `critical_path_satisfied`는 Fundamental + Valuation critical evidence foundation일 뿐 **그 자체가 Final Decision Eligibility는 아니다**(세부 semantics는 `docs/ARCHITECTURE.md` §7.2). Recommendation Policy Step 1의 deterministic primitive `evaluate_decision_eligibility()`(`app/evaluation/decision_eligibility.py`)는 이 두 sibling output을 **나중에** 소비하는 projection이다 — `policy_may_proceed = coverage.critical_path_satisfied`, `forward_requirement = FOE tri-state 그대로`이며 `coverage_status`는 입력이 아니다(세부 경계는 `docs/ARCHITECTURE.md` §7.4). **이것이 Numeric Calibration/Producer(Core Attractiveness/Market Confirmation/Risk/Confidence)/Recommendation Policy 완료를 의미하지 않는다** — 전부 여전히 OPEN/NOT IMPLEMENTED다.

### Domain / Data Access

```text
Domain Tools
    ↓
Services
    ↓
ECOS / OpenDART / Kiwoom
```

- Market/Stock Research Agent가 Domain Tool을 **in-process로 직접 호출**한다(별도 프로토콜 아님).
- Domain Tool은 개념적 layer이며, 현재 실제 구현(`EcosTools`/`KiwoomTools`/`OpenDartTools`)은 물리적으로 `app/mcp/*_tools.py`에 있다 — 별도 디렉터리로 분리돼 있지 않다.
- **KIS(한국투자증권)**: research / empirical verification only — production 코드에 통합되지 않음(`app/config.py`에 설정 항목만 존재, `Service`/`Domain Tool` 없음).

### External MCP Boundary

```text
External MCP Client
        │  MCP protocol
        ▼
MCP Server (app/mcp/server.py)
        │
        ▼
Domain Tools   (위와 동일한 클래스)
```

**Normal Agent execution은 MCP를 쓰지 않는다** — Agent는 Domain Tool을 in-process로 직접 호출한다. MCP Server는 별도 프로세스/외부 client(다른 Agent runtime 등)를 위한 노출 경계일 뿐, 현재 어떤 Agent 실행 경로에도 포함되지 않는다.

### Portfolio Strategy

**Final target(RE-04 FROZEN)** — 입력은 정확히 3개다:

```text
StockOpportunityAssessment  ← Recommendation Evaluation + Recommendation Policy
PortfolioContext            ← 계좌/provider 데이터, 독립 입력
InvestorProfile             ← 사용자 요청, 독립 입력
        │
        ▼
Portfolio Strategy
        │
        ▼
PortfolioActionRecommendation
        │
        ▼
BUY / ADD / HOLD / REDUCE / EXIT
```

**현재 v1** — `StockOpportunityAssessment`가 아직 존재하지 않으므로(Recommendation Policy `NOT IMPLEMENTED`) 다른 4개 입력으로 독립 동작한다:

```text
MarketAnalysis      ← Market Agent
StockAnalysis[]     ← Stock Research Agent
PortfolioContext    ← Kiwoom 계좌 (독립 fetch)
InvestorProfile     ← 사용자 요청 (독립 입력)
        │   4개 모두 독립 입력 — 서로 파생 관계 아님
        ▼
Portfolio Strategy Agent
        │
        ▼
StrategyResult   (v1 실제 출력)
```

`MarketAnalysis`는 final target에서 독립 market capability로 유지되며(위 [System Architecture Overview](#system-architecture-overview) 참고) `StockOpportunityAssessment`/`PortfolioActionRecommendation` 경로에 직접 연결되지 않는다 — v1이 `MarketAnalysis`를 쓰는 것은 현재 구조의 특징일 뿐 final contract는 아니다. `StockAnalysis[]`(LLM narrative) 역시 final input이 아니다 — final path의 canonical source는 `DeterministicAnalysisResult`를 거친 `StockOpportunityAssessment`다.

---

## Current Development Position

| | |
|---|---|
| **Phase** | RE-05 — Recommendation Evaluation Pipeline |
| **Current Task** | **NEXT: OpenDART Annual-Report Evidence Selection**(Trustworthy V0 첫 implementation slice — Q2b classified annual-evidence retrieval result + Q3 finite, calendar-assumption-free candidate generation + positive-only fallback + per-candidate selection trace) — SELECTION FROZEN / IMPLEMENTATION CONTRACT NOT STARTED / IMPLEMENTATION NOT STARTED(근거 `docs/dev-log/2026-09-27.md` §M, `docs/ARCHITECTURE.md` §7.3 V0 implementation selection 블록) · Q2b / Q3 / Q12 / Q1 OPEN · 직전: **Trustworthy V0 Product Boundary & Current-Runtime Evidence / Output Contract** — DESIGN COMPLETE / INDEPENDENT REVIEW PASS / **FROZEN**(`docs/ARCHITECTURE.md` §7.11, 근거 `docs/dev-log/2026-09-27.md` §L) · implementation NOT STARTED · Supported Feature Set 0 · **USABLE V0 NOT YET** · 그 이전: Post-EIP Critical-Path Review — COMPLETE(read-only, repository 변경 없음) · 그 이전: Evidence Identity Preservation — **IMPLEMENTED**(offline 검증 PASS, live integration NOT VERIFIED) · 그 이전: Calibration Evidence Identity & Persistence Contract — DESIGN COMPLETE / REVIEW PASS / FROZEN(§7.10, implementation **PARTIAL** — 위 identity slice만) · 그 이전: OpenDART PIT Empirical Verification — EXECUTION COMPLETE / INDEPENDENT REVIEW PASS / FINDINGS FROZEN(PIT 구현 NOT STARTED, Numeric Calibration은 여전히 OPEN / readiness BLOCKED) |

### RE-05 Critical Path — Current Position

현재 active workstream(RE-05)의 **critical path 위치**만 보여준다 — 전체 완료 상태 matrix는 아래 [Project Completion Overview](#project-completion-overview), 세부 semantics는 `docs/ARCHITECTURE.md` §7이 canonical이다. `FROZEN`은 design/contract 확정이지 구현 완료가 아니다.

```text
JUST COMPLETED   Trustworthy V0 Product Boundary & Current-Runtime Evidence / Output Contract
                 — DESIGN COMPLETE / INDEPENDENT REVIEW PASS / FROZEN (docs/ARCHITECTURE.md §7.11)
                 · V0 = current-runtime financial evidence surface (assessment / recommendation 아님)
                 · Candidate Feature Set(구현 evaluator 6) ≠ Supported Feature Set(S1–S6) — 현재 SUPPORTED 0
                 · implementation NOT STARTED / live integration NOT VERIFIED / USABLE V0 NOT YET
NEXT WORK ITEM   OpenDART Annual-Report Evidence Selection  (Trustworthy V0 첫 implementation slice)
                 — SELECTED / SELECTION FROZEN / IMPLEMENTATION CONTRACT NOT STARTED / IMPLEMENTATION NOT STARTED
                 · Q2b classified retrieval result + Q3 finite, calendar-assumption-free candidate generation
                   + positive-only fallback + per-candidate selection trace (하나의 slice)
                 · Q2b / Q3 / Q12 / Q1 OPEN · Supported Feature Set 0 (docs/ARCHITECTURE.md §7.3)
SECOND / THIRD   NOT SELECTED
(이전 완료: Post-EIP Critical-Path Review — read-only, docs/dev-log/2026-09-27.md §J — EIP evidence 경로 ·
 deterministic pipeline · Decision Eligibility가 production app 경로에 미연결, user-facing 판단은 기존 v1 LLM 출력)
(이전 완료: Evidence Identity Preservation — IMPLEMENTED(§7.10의 identity-only 구현 slice, 6개 evaluator
 경로) — offline 검증 PASS / live integration NOT VERIFIED · 미포함: history / YoY / trends identity ·
 capture · persistence · manifest · reproducibility(NOT CLAIMED) · historical PIT(NOT READY))
(이전 완료: Calibration Evidence Identity & Persistence Contract — FROZEN §7.10, implementation
 PARTIAL · OpenDART PIT Empirical Verification — findings FROZEN §7.9)
(이전 완료: OpenDART PIT Empirical Verification — findings FROZEN §7.9 · Point-in-Time Financial
 Evidence Contract — contract FROZEN §7.8, 구현 NOT STARTED)

RE-05 Evaluation / Recommendation
│
├─ Feature Evaluators                          6 / 14 IMPLEMENTED
│
├─ Evidence / Calibration Foundation           (design contracts — 구현 아님)
│    ├─ Feature Normalization Contract         contract FROZEN / implementation NOT STARTED
│    ├─ Calibration Objective & Scope Contract contract FROZEN
│    ├─ PIT Financial Evidence Contract        contract FROZEN / implementation NOT STARTED
│    └─ Evidence Identity & Persistence        contract FROZEN / implementation PARTIAL
│         └─ Evidence Identity Preservation    IMPLEMENTED (offline 검증)
│
├─ Trustworthy V0 Product Boundary &
│  Current-Runtime Evidence / Output Contract  contract FROZEN (§7.11) ← JUST COMPLETED
│                                               / implementation NOT STARTED / SUPPORTED 0 / USABLE NOT YET
│    └─ V0 implementation NEXT                 OpenDART Annual-Report Evidence Selection
│                                               SELECTION FROZEN / IMPLEMENTATION NOT STARTED ← NEXT
│
├─ Calibration Readiness
│    └─ Numeric Calibration                    OPEN / readiness BLOCKED / NOT STARTED
│
├─ Feature Normalization implementation        NOT STARTED / readiness NO
│
├─ Component Score / Signal                    NOT READY (normalized_value 항상 None)
│
├─ Core Attractiveness                         NOT IMPLEMENTED
│   (Market Confirmation / Risk / Confidence   NOT IMPLEMENTED / BLOCKED)
│
└─ Recommendation Policy
     ├─ Step 1 Decision Eligibility            IMPLEMENTED / VERIFIED / FROZEN
     │                                          (primitive, orchestrator 미연결)
     └─ Step 2–8                               NOT IMPLEMENTED
```

**왜 Numeric Calibration이 자동으로 다음 작업이 아닌가**: PIT contract freeze, empirical verification, Evidence Identity & Persistence contract freeze로 해소된 H1–H7 blocker는 **없다**(H2/H5/H6 NARROWED, H3 PARTIALLY EVIDENCED — `docs/ARCHITECTURE.md` §7.9; §7.10은 H5/H6의 해결 경계를 정의했을 뿐 persistence / reproducibility를 구현하지 않았다). 남은 readiness debt에는 H2 Temporal Semantics · H3 External Source Behavior · H5 Infrastructure · H6 Provenance와 남은 empirical UNKNOWN(time-of-day / earliest public availability, 원본 filing의 XBRL coverage, 정정 전 API 응답 등)이 포함된다 — 이 목록은 readiness 판정 근거이지 향후 구현 계획 전체가 아니다.

**알려진 dependency 방향** — *현재 NEXT는 Trustworthy V0 첫 implementation slice인 OpenDART Annual-Report Evidence Selection(SELECTION FROZEN / IMPLEMENTATION NOT STARTED)이고 SECOND/THIRD는 NOT SELECTED다. Trustworthy V0 Contract는 FROZEN(§7.11)이며 구현되지 않았다. `not selected` 항목은 dependency context일 뿐, 선택된 roadmap이 아니다(SECOND/THIRD 아님). 아래 numeric path는 재정의되지 않았으며 불필요하다고 판단된 것도 아니다 — 첫 Minimum Trustworthy Product까지의 가장 짧은 blocker가 아닐 뿐이다*:

```text
PIT Financial Evidence Contract (FROZEN)
        ↓
OpenDART PIT Empirical Verification             COMPLETE / FINDINGS FROZEN
        ↓ (factual constraints)
── architecture / identity / provenance readiness ──
Calibration Evidence Identity & Persistence     contract FROZEN (§7.10) / implementation PARTIAL
  └─ Evidence Identity Preservation             IMPLEMENTED (identity-only slice, offline 검증)
       → trustworthy V0 App Surface를 별도로 설계·wiring 가능 (V0 완료 아님)
             └─ Trustworthy V0 Product Boundary &
                Current-Runtime Evidence / Output Contract   contract FROZEN (§7.11) / implementation NOT STARTED
                  → V0 implementation NEXT: OpenDART Annual-Report Evidence Selection (SELECTION FROZEN)
                  → 이후 V0 implementation / wiring (not selected) → Minimum Trustworthy Product
        ↓
Numeric Policy-Source / First-Slice Scope       not selected
        ↓
Parameter Provenance / PolicyConfig             not selected
── actual numeric-policy readiness (위 3개만으로는 생기지 않는다) ──
admissible Semantic numeric policy/reference 확립 + 검증
        ↓
Feature Normalization implementation → admissible weights / signal thresholds
        → Component Score / Signal → Core / staged Recommendation Policy stage 2–9
```

**Product surface 상태**: V0(Evidence → FeatureEvaluationResult)는 code/test에서 실행 가능하지만 app/API에 연결되지 않았고 current/latest-known semantics이며 lineage가 불완전하다(app 기능 완료 아님). V1/V1⁻(normalized decision-support)와 V2(Core → staged policy → StockOpportunityAssessment)는 NOT YET FEASIBLE — architecture contract만으로는 부족하고 admissible numeric semantics(V2는 추가로 Recommendation-level evidence/boundary)가 필요하다. staged policy의 "Step 2~8"은 9-stage candidate 구조의 stage 번호이며 확정된 "8-step policy"가 아니다(`docs/ARCHITECTURE.md` §7.3 numbering 주석).

### Project Completion Overview

**프로젝트 전체**의 구현 완료 상태를 한눈에 보여준다 — RE-05는 이 중 현재 active workstream 하나다. 이 표는 기존 status를 모아 보여주는 요약일 뿐이며, 각 영역의 세부 semantics는 위 [Architecture](#architecture) 각 section과 `docs/ARCHITECTURE.md`가 canonical이다.

> **Status:** ✅ `DONE` · 🟡 `PARTIAL` · 🔵 `OPEN` · ⛔ `BLOCKED` · ⬜ `NOT IMPLEMENTED` · ⚪ `LATER / RESEARCH ONLY`
>
> `FROZEN`(architecture/contract 안정성)과 `VERIFIED`(검증 상태)는 implementation completion과 별개인 보조 qualifier다 — `FROZEN`만으로 완료를 뜻하지 않는다.

| Area | Status | Remaining / Notes |
|---|---|---|
| **Foundation / Infrastructure** | | |
| Foundation / Model Layer | ✅ `DONE` | Model Layer v1 |
| ECOS Integration | ✅ `DONE` | |
| OpenDART Integration | ✅ `DONE` | |
| Kiwoom Integration | ✅ `DONE` | |
| MCP Boundary | ✅ `DONE` | 외부 노출 경계 — Agent 실행 경로에는 사용되지 않음 |
| KIS(한국투자증권) | ⚪ `RESEARCH ONLY` | production 미통합 — config 항목만 존재 |
| **Application / Agent Layer** | | |
| Supervisor / Router | ✅ `v1 DONE` | |
| Market Agent | ✅ `v1 DONE` | |
| Stock Research Agent | ✅ `v1 DONE` | |
| Candidate Discovery | ✅ `v1 DONE` | Industry + Theme axis |
| REST API (FastAPI) | ✅ `v1 DONE` | Analysis Snapshot Lifecycle 포함 |
| Portfolio Strategy Agent | 🟡 `v1 DONE / FINAL PENDING` | v1은 `StrategyResult` 출력 — final `StockOpportunityAssessment` 입력 경로 미연결 |
| **Recommendation Evaluation (RE-05)** | 🟡 `PARTIAL` | **현재 active workstream** (RE-01~RE-04 architecture/contracts는 `DONE / FROZEN`) |
| ↳ Coverage Layer | ✅ `DONE` | |
| ↳ Assembly Layer | ✅ `DONE` | |
| ↳ Evaluation Orchestration | ✅ `FIRST SLICE DONE / FROZEN` | First Deterministic Pipeline Slice |
| ↳ Feature Evaluators | 🟡 `6 / 14` | ROE/Operating Margin/Net Margin/Debt Ratio/Trailing PER/PBR |
| ↳ Top-level State Coverage | ✅ `DONE / VERIFIED / FROZEN` | Step J |
| ↳ Future Opportunity Evidence | ✅ `DONE` | State Coverage와 sibling output |
| ↳ Decision Eligibility | ✅ `STEP 1 PRIMITIVE / VERIFIED / FROZEN` | Policy Step 1 primitive만 — orchestrator 미연결, 결과 비저장, policy consumer 없음 |
| ↳ Core Attractiveness | ⬜ `NOT IMPLEMENTED` | readiness `PARTIAL` — Numeric Calibration 선행 필요 |
| ↳ Market Confirmation | ⛔ `BLOCKED` | NOT IMPLEMENTED — 입력 evidence/data integration 부재 |
| ↳ Risk | ⛔ `BLOCKED` | NOT IMPLEMENTED |
| ↳ Confidence | ⛔ `BLOCKED` | NOT IMPLEMENTED |
| ↳ Recommendation Policy | ⬜ `NOT IMPLEMENTED` | Step 2~8 + 실제 policy consumer 없음 (Step 1 primitive만 존재) |
| ↳ Final AssessmentStatus production | ⬜ `NOT IMPLEMENTED` | |
| ↳ Numeric Calibration | 🔵 `OPEN` | readiness `BLOCKED`(Calibration Readiness Audit, `docs/ARCHITECTURE.md` §7.6) · Calibration Objective & Scope Contract `FROZEN`(§7.7) — calibration NOT STARTED |
| ↳ Point-in-Time Financial Evidence | ⬜ `NOT IMPLEMENTED` | Contract `FROZEN`(§7.8) — PIT capability 구현 NOT STARTED(readiness NO), 현재 historical 경로는 PIT-safe 아님 · OpenDART empirical findings `FROZEN`(§7.9): `fnlttSinglAcnt` latest correction만 관찰, version-specific 재구성은 일부 filing에서만 입증(general coverage 미확립), time-of-day / public availability UNKNOWN |
| ↳ Trustworthy V0 Product Boundary / Output Contract | ⬜ `NOT IMPLEMENTED` | Contract `FROZEN`(§7.11) — implementation NOT STARTED, live integration NOT VERIFIED, Supported Feature Set 0, USABLE V0 NOT YET · implementation NEXT: OpenDART Annual-Report Evidence Selection(SELECTION FROZEN) |
| ↳ Evidence Identity & Persistence | 🟡 `PARTIAL` | Contract `FROZEN`(§7.10) — Evidence Identity Preservation(6-evaluator identity slice)만 구현(offline 검증 PASS, live integration NOT VERIFIED). persistence / evidence capture / manifest / reproducibility / reference snapshot / history·YoY·trends identity NOT IMPLEMENTED, 저장 기술 미선택 |
| **Final Decision Path** | | |
| `StockOpportunityAssessment` production | ⬜ `NOT IMPLEMENTED` | contract(RE-04 FROZEN)만 존재 — Recommendation Policy 선행 필요 |
| Final Portfolio Decision Flow (`PortfolioActionRecommendation`) | ⬜ `NOT IMPLEMENTED` | SOA + PortfolioContext + InvestorProfile → BUY/ADD/HOLD/REDUCE/EXIT |
| **Long-term Scope** | | |
| Event & Disclosure Intelligence Overlay | ⚪ `LATER` | Amendment 1 |
| Automated Trading | ⚪ `LATER` | `docs/AUTOMATED_TRADING_ROADMAP.md` |

### Detailed Development Position

현재 위치까지 **어떻게 진행돼 왔는가**(RE-01~RE-05 development progression)를 보여준다.

```text
RE-01 ~ RE-04
Architecture / Research / Contracts
DONE / FROZEN
        │
        ▼
RE-05 Recommendation Evaluation Pipeline
        │
        ▼
Coverage Layer                                IMPLEMENTATION COMPLETE
        │
        ▼
Assembly Layer                                IMPLEMENTATION COMPLETE
        │
        ▼
Evaluation Orchestration
    ├─ Final Contract Review                  DONE
    ├─ Architecture Boundary Resolution       DONE (ARCHITECTURE READY)
    ├─ First Deterministic Pipeline Slice     COMPLETE / FROZEN
    └─ Freeze                                 DONE
        │
        ▼
READY Evaluator Expansion(Post-Orchestration Review Step A~F)
    ├─ Net Margin / Debt Ratio                IMPLEMENTED (Fundamental)
    ├─ Trailing PER / PBR                     IMPLEMENTED (Valuation, 신규
    │                                          app/evaluation/valuation_evaluators.py)
    ├─ Registry metadata synchronization      DONE (evaluator_id/version만, 14개
    │                                          registry 전체 개수/필드는 불변)
    └─ Tests                                  712 PASSED
        │
        ▼
Producer Readiness Re-evaluation(Step G)      FROZEN (아래는 Step G 당시 평가)
    ├─ Core Attractiveness / Risk / Confidence /
    │  Market Confirmation                    PARTIAL 또는 BLOCKED(Numeric
    │                                          Calibration/입력 evidence 부재)
    └─ Top-level Coverage                     PARTIAL — Numeric Calibration
                                               없이 가장 먼저 닫을 수 있는
                                               producer로 식별
        │
        ▼
Top-level Coverage Aggregation Contract(Step H)   FROZEN
    (`RecommendationEvaluationState.coverage`의 정확한 semantics — 최초
    설계안의 UNKNOWN→True 오류를 독립 검토로 발견/수정한 이력 포함)
        │
        ▼
Top-level Coverage Implementation Contract(Step I)   FROZEN
    (`evaluate_recommendation_coverage()` 함수 시그니처/merge 규칙/
    orchestrator 통합 지점까지 구현 직전 수준으로 확정)
        │
        ▼
Top-level Coverage Implementation(Step J)     IMPLEMENTED / VERIFIED / FROZEN
    └─ Tests                                  738 PASSED
        │
        ▼
Post-Step-J Next Slice Selection              FROZEN (→ Final Decision Eligibility)
        │
        ▼
Final Decision Eligibility(Policy Step 1)
    ├─ Design Contract                        FROZEN
    ├─ Implementation Contract                FROZEN
    ├─ Implementation + Tests                 IMPLEMENTED / VERIFIED / FROZEN
    │                                          (orchestrator 미연결, 결과 비저장)
    └─ Tests                                  766 PASSED
        │
        ▼
Post-Decision-Eligibility Next Slice Selection   FROZEN
    ├─ NEXT    Feature Normalization Ownership & Representation Contract
    │          (pre-calibration structural prerequisite — DESIGN COMPLETE /
    │           INDEPENDENT REVIEW PASS / FROZEN, implementation NOT STARTED)
    └─ SECOND  Calibration Data & Parameter Provenance Readiness Audit
               (read-only calibration-readiness audit)
        │
        ▼
Feature Normalization Ownership & Representation Contract
                                              FROZEN (implementation NOT STARTED)
        │
        ▼
Calibration Data & Parameter Provenance Readiness Audit
                                              COMPLETE / REVIEW PASS
    ├─ Numeric Calibration readiness          BLOCKED (H1~H7)
    ├─ NEXT    Calibration Objective & Scope Contract
    │          (design-only)
    └─ SECOND  Point-in-Time Financial Evidence Contract
        │
        ▼
Calibration Objective & Scope Contract        FROZEN (rev.1)
    ├─ Semantic Calibration ≠ Recommendation Calibration (Strong Separation)
    ├─ Numeric Calibration                    OPEN / readiness BLOCKED / NOT STARTED
    ├─ NEXT    Point-in-Time Financial Evidence Contract
    │          (selected)
    └─ SECOND  NOT SELECTED
        │
        ▼
Point-in-Time Financial Evidence Contract     FROZEN (rev.1 + §4.1 wording correction)
    ├─ Current-runtime usability ≠ Historical PIT eligibility
    ├─ Comparative-column / derived lower-bound invariant (P1–P12)
    ├─ PIT capability implementation          NOT STARTED
    ├─ Corrected-filing semantics             UNKNOWN (empirical verification 필요)
    ├─ NEXT    NOT SELECTED (freeze 시점)
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
Post-PIT Critical Path Review                 COMPLETE / INDEPENDENT REVIEW PASS
    ├─ First unresolved blocker               H3 External Source Behavior
    ├─ NEXT    OpenDART PIT Empirical Verification
    │          (SELECTION FROZEN / EXECUTION NOT STARTED — 선택 시점)
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
OpenDART PIT Empirical Verification           EXECUTION COMPLETE / INDEPENDENT REVIEW PASS /
                                              FINDINGS FROZEN (§7.9)
    ├─ M1 fnlttSinglAcnt                      latest correction만 관찰 (sample-bounded)
    ├─ M2 version-specific reconstruction     일부 filing에서 입증 / general coverage NOT established
    ├─ M3 rcept_dt                            day-level 접수일자 / time-of-day·public availability UNKNOWN
    ├─ H1–H7 newly resolved                   NONE
    ├─ NEXT    NOT SELECTED (findings freeze 시점)
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
Post-Empirical Critical-Path Review           COMPLETE (+ targeted correction: A+K+B ≠ numeric readiness)
    ├─ First route-independent blocker        H5/H6 evidence / reference-snapshot identity & persistence
    ├─ NEXT    Calibration Evidence Identity & Persistence
    │          (SELECTION FROZEN / DESIGN NOT STARTED / IMPLEMENTATION NOT STARTED — 선택 시점)
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
Calibration Evidence Identity & Persistence Contract
                                              DESIGN COMPLETE / REVIEW PASS / FROZEN (§7.10)
    ├─ Evidence Item / Temporal / Revision / Reference Snapshot identity + Evidence Basis Manifest
    ├─ Identity ≠ Content · Evidence Identity ≠ Policy Identity (E1–E13)
    ├─ Implementation                         NOT STARTED
    ├─ H1–H7 newly resolved                   NONE (H5/H6 해결 경계만 정의)
    ├─ NEXT    NOT SELECTED (contract freeze 시점)
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
Post-§7.10 Critical-Path Review               COMPLETE (+ targeted scope revision rev.1)
    ├─ V0 trust blocker                       identity 소실 / retrieved_at 부재 / source column relabel /
    │                                          derived-as-raw
    ├─ NEXT    Evidence Identity Preservation
    │          (SELECTION FROZEN / IMPLEMENTATION NOT STARTED — 선택 시점)
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
Evidence Identity Preservation                IMPLEMENTED (review PASS WITH NON-BLOCKING NOTE)
    ├─ 6-evaluator evidence identity / retrieved_at / derived lineage
    ├─ 검증                                   offline 772 passed · focused 15 passed · ruff PASS
    │                                          · live integration NOT VERIFIED
    ├─ 미포함                                 history / YoY / trends · capture · persistence ·
    │                                          manifest · reproducibility · historical PIT
    ├─ H1–H7 newly resolved                   NONE
    ├─ NEXT    NOT SELECTED (구현 시점)
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
Post-EIP Critical-Path Review                 COMPLETE (read-only, repository unchanged)
    ├─ First MTP blocker                      EIP / pipeline / Decision Eligibility가 production app 경로에
    │                                          미연결 · product / current-runtime evidence / output contract 부재
    ├─ NEXT    Trustworthy V0 Product Boundary & Current-Runtime Evidence / Output Contract
    │          (SELECTION FROZEN / DESIGN NOT STARTED — 선택 시점)
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
Trustworthy V0 Product Boundary & Current-Runtime Evidence / Output Contract
                                              DESIGN COMPLETE / INDEPENDENT REVIEW PASS / FROZEN (§7.11)
    ├─ V0 = current-runtime financial evidence surface (assessment / recommendation 아님, LLM 없음)
    ├─ Candidate ≠ Supported (S1–S6)          SUPPORTED 0 (Kiwoom 3 + derived 3 NOT_SUPPORTED_IN_V0)
    ├─ logical Evidence Basis Manifest        REQUIRED / persistence · capture NOT REQUIRED /
    │                                          reproducibility NOT ESTABLISHED
    ├─ Implementation                         NOT STARTED / USABLE V0 NOT YET
    ├─ NEXT    NOT SELECTED (contract freeze 시점)
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
Trustworthy V0 Implementation NEXT Selection Review
                                              COMPLETE (read-only) / INDEPENDENT REVIEW PASS
    ├─ provider-first over V0-skeleton-first  (Supported 0 → skeleton은 OpenDART evidence 경로 미실행)
    ├─ NEXT    OpenDART Annual-Report Evidence Selection
    │          (Q2b + Q3 + positive-only fallback + selection trace — SELECTION FROZEN /
    │           IMPLEMENTATION CONTRACT NOT STARTED / IMPLEMENTATION NOT STARTED)
    ├─ Q2b / Q3 / Q12 / Q1                    OPEN
    └─ SECOND / THIRD  NOT SELECTED
        │
        ▼
Current producer / policy status
    ├─ Top-level Coverage                     IMPLEMENTED
    ├─ Future Opportunity Evidence            IMPLEMENTED
    ├─ Decision Eligibility primitive         IMPLEMENTED
    ├─ Core Attractiveness                    NOT IMPLEMENTED (PARTIAL)
    ├─ Market Confirmation / Risk /
    │  Confidence                             NOT IMPLEMENTED (BLOCKED)
    └─ Final AssessmentStatus production      NOT IMPLEMENTED
        │
        ▼
Recommendation Policy Step 2~8                NOT IMPLEMENTED
        │
        ▼
Numeric Calibration                           OPEN (readiness BLOCKED)
```

**연결 완료된 canonical path**(`app/evaluation/orchestrator.py::run_first_deterministic_pipeline`): `DeterministicAnalysisResult → NormalizedResearchData → FeatureEvaluationResult[](ROE/Operating Margin/Net Margin/Debt Ratio/Trailing PER/PBR, 6개) → Component Coverage → Assembly → {State Coverage, FutureOpportunityEvidence} → RecommendationEvaluationState` (State Coverage와 FOE는 서로 독립적인 sibling output이며, orchestrator 호출 순서만 State Coverage → FOE다). Scoring/Recommendation Policy는 이번 slice 범위 밖(`Numeric Calibration = OPEN` 유지) — evaluator가 6개로 늘어난 것은 raw evidence 확보 범위의 확장이지, "저평가/고평가 판단"이나 "상승 가능성 예측"이 아니다(`normalized_value`는 6개 evaluator 전부 항상 `None`).

**Feature Normalization Ownership & Representation Contract**(Post-Decision-Eligibility NEXT) — **FROZEN**(rev.1, canonical contract는 `docs/ARCHITECTURE.md` §7.5, 구현 미착수). raw feature → normalized feature 경계(`normalized_value` 생산 ownership / input·output representation semantics / PolicyConfig boundary)를 정하는 **pre-calibration structural prerequisite**다 — Numeric Calibration의 시작이 아니며 numeric parameter/threshold/weight를 정하지 않는다(`Numeric Calibration = OPEN` 유지). 이어서 **Calibration Data & Parameter Provenance Readiness Audit** — COMPLETE / REVIEW PASS(read-only): Numeric Calibration은 workflow `OPEN`이지만 readiness `BLOCKED`다(objective 미정의, OpenDART point-in-time/restatement leakage, historical valuation 부재, dataset/parameter provenance·persistence 부재 등 H1~H7, `docs/ARCHITECTURE.md` §7.6). Feature Normalization 구현 readiness도 NO다. 이어서 **Calibration Objective & Scope Contract** — **FROZEN**(rev.1, `docs/ARCHITECTURE.md` §7.7): Semantic Calibration ≠ Recommendation Calibration(Strong Separation). Semantic Calibration은 future outcome label을 요구하지 않고 future outcome을 optimization/fitting/primary selection에 쓰지 않으며, 기존 freeze-acceptance 요구(historical/temporal validation)를 면제하지 않는다. Recommendation Calibration은 별도 objective/outcome semantics가 필요하다(objective/label/horizon/benchmark OPEN). 이 freeze로 해소된 blocker(H1~H7)는 없고 calibration은 시작되지 않았다. 이어서 **Point-in-Time Financial Evidence Contract** — **FROZEN**(rev.1 + §4.1 wording correction, `docs/ARCHITECTURE.md` §7.8): economic observation ≠ filing/publication ≠ information availability ≠ evaluation_as_of ≠ retrieval time. current-runtime 조회는 명시적 policy 아래 `available_at <= retrieved_at`만 확립하며 historical PIT eligibility가 아니다. 나중 filing의 비교 컬럼 값은 동등성 evidence 없이 더 이른 boundary로 back-project할 수 없다 — 현재 `get_key_financials_history()`는 비교 값을 더 이른 `business_year`로 relabel해 이 구분을 잃는다(leakage risk 미통제, leakage 관측 아님). **PIT capability 구현은 NOT STARTED**이고, corrected-filing semantics 등은 empirical verification이 필요하며, 해소된 H1~H7 blocker는 없다. 이어서 **Post-PIT Critical Path Review** — COMPLETE: 첫 미해결 blocker는 H3 External Source Behavior였고(empirical facts before architecture that depends on those facts), NEXT로 `OpenDART PIT Empirical Verification`이 선택됐다(범위는 `docs/ARCHITECTURE.md` §7.3). 이어서 **OpenDART PIT Empirical Verification** — **EXECUTION COMPLETE / INDEPENDENT REVIEW PASS / FINDINGS FROZEN**(`docs/ARCHITECTURE.md` §7.9, fact discovery only): `fnlttSinglAcnt`는 latest correction만 노출하는 것으로 관찰됐고(sample-bounded), `rcept_no`로 version-specific artifact를 조회해 과거 version 재구성이 일부 filing에서 입증됐지만 general coverage는 확립되지 않았다(hybrid-capability evidence ≠ persistence architecture 선택). `rcept_dt`는 day-level 접수일자이며 time-of-day / earliest public availability는 UNKNOWN이다. 해소된 H1–H7 blocker는 없다. PIT 구현·availability/revision policy·calibration은 시작/선택되지 않았다. findings freeze 시점에 다음 작업 항목은 NOT SELECTED였다. 이어서 **Post-Empirical Critical-Path Review**(targeted correction 포함: architecture / identity / provenance 준비 ≠ admissible numeric semantics) — route와 무관한 첫 미해결 blocker는 H5/H6(재현 가능한 evidence / reference-snapshot identity와 persistence semantics)이다. **NEXT**: `Calibration Evidence Identity & Persistence` — **selection FROZEN / design NOT STARTED / implementation NOT STARTED**(범위·OUT OF SCOPE는 `docs/ARCHITECTURE.md` §7.3). 물리 저장 기술·numeric policy source·calibration parameter는 선택하지 않았고, Numeric Policy-Source / First-Slice Scope Decision과 Parameter Provenance / PolicyConfig는 dependency context일 뿐 선택되지 않았다. 해소된 H1–H7 blocker는 없다. 이어서 **Calibration Evidence Identity & Persistence Contract** — **DESIGN COMPLETE / REVIEW PASS / FROZEN**(`docs/ARCHITECTURE.md` §7.10, **implementation NOT STARTED**): Evidence Item / Temporal·Availability / Revision / Reference Snapshot identity와 Evidence Basis Manifest를 정의하고 `Identity ≠ Content`(reproducible = immutable capture 또는 per-item 검증된 version-addressable recovery + equivalence), `Evidence Identity ≠ Policy Identity`를 고정했다(E1–E13). latest-only가 곧 capture-only는 아니며, derived availability representation은 OPEN(P12 lower bound만), snapshot identity와 construction-policy admissibility는 분리된다. 현재 derived 값(Operating/Net Margin)이 lineage 없이 raw slot에 기록되는 문제는 debt로 기록만 했다(ownership OPEN). storage 기술·revision/availability policy·numeric policy는 선택하지 않았고 해소된 H1–H7 blocker는 없다. contract freeze 시점에 다음 작업 항목은 NOT SELECTED였다. 이어서 **Post-§7.10 Critical-Path Review**(targeted scope revision 포함) — 현재 user-visible V0는 identity 소실 / `retrieved_at` 부재 / source column relabel / derived-as-raw 때문에 Minimum Trustworthy Product gate를 통과하지 못한다. **NEXT**: `Evidence Identity Preservation` — **selection FROZEN / implementation NOT STARTED**(§7.10 아래 identity-only 구현 slice, 범위는 `docs/ARCHITECTURE.md` §7.3). Evidence Basis Manifest · reproducibility-status representation · capture · persistence · Reference Snapshot · V0 wiring은 범위 밖이고, reproducibility는 주장하지 않으며, Derived Feature Value Ownership은 OPEN이다. 이 slice가 V0를 완료하지 않는다. 현재 app이 노출하는 기존 v1 LLM judgment(BUY/SELL 등)는 변경하지 않으며, trustworthy V0 출시 전 별도 product decision이 필요하다. 이어서 **Evidence Identity Preservation** — **IMPLEMENTED**(independent review PASS WITH NON-BLOCKING NOTE): 6개 evaluator 경로의 provider-neutral evidence identity(`retrieved_at`은 semantic identity 밖), OpenDART filing/source column identity, Kiwoom ROE/PER/PBR의 SOURCE_REPORTED 표시, Operating/Net Margin·Debt Ratio의 derived lineage가 `FeatureEvaluationResult.provenance`까지 보존된다. 검증은 offline(focused 15 passed, offline suite 772 passed, live-API test 9개 제외, ruff PASS)이며 live integration은 NOT VERIFIED다. history / YoY / trends identity, capture, persistence, manifest는 구현되지 않았고 reproducibility는 주장하지 않으며, historical PIT는 여전히 NOT READY다(§7.10 implementation PARTIAL). Derived Feature Value Ownership은 OPEN이고 MCP public contract와 StockAnalysis v1 contract는 변경되지 않았다. 해소된 H1–H7 blocker는 없다. 근거는 `docs/dev-log/2026-09-26.md`. 이어서 **Post-EIP Critical-Path Review**(read-only, repository 변경 없음) — 실제 code inspection 결과 `run_first_deterministic_pipeline` / `evaluate_decision_eligibility`는 production caller가 없고, evidence-aware retrieval은 production orchestrator가 사용하지 않으며, `StockResearchOrchestrator.run()`은 deterministic analysis에 evidence를 전달하지 않는다 — EIP slice는 user-facing 경로에서 도달 불가하고 user-facing 판단은 여전히 기존 v1 LLM 출력이다. **NEXT**: `Trustworthy V0 Product Boundary & Current-Runtime Evidence / Output Contract` — **SELECTION FROZEN / DESIGN NOT STARTED / IMPLEMENTATION NOT STARTED**(Product Boundary + Current-Runtime Evidence Selection Boundary + Output Contract, 범위·candidate topic·non-goal은 `docs/ARCHITECTURE.md` §7.3). design 질문(노출 범위, evaluation_as_of / report 선택, 재현성 부재 표현, 기존 v1 LLM judgment와의 관계, wiring 경계, acceptance)은 아직 답하지 않았다. V0 wiring은 선택되지 않았고 frozen contract 변경은 없으며 해소된 H1–H7 blocker는 없다. **SECOND / THIRD**: NOT SELECTED. 근거는 `docs/dev-log/2026-09-27.md` §J–§K. 이어서 **Trustworthy V0 Product Boundary & Current-Runtime Evidence / Output Contract** — **DESIGN COMPLETE / INDEPENDENT REVIEW PASS / FROZEN**(rev.1-final, canonical contract는 `docs/ARCHITECTURE.md` §7.11): V0는 한 종목의 current-runtime financial evidence surface이며 assessment / recommendation surface가 아니다(LLM judgment / routing 없음, legacy v1과 합성 없음). Candidate Feature Set(구현 evaluator 6개) ≠ Supported Feature Set(S1–S6 확립) — Kiwoom ROE / PER / PBR은 provider semantics 미확립, derived Operating / Net Margin · Debt Ratio는 남은 조건 미확립으로 모두 `NOT_SUPPORTED_IN_V0`이고 SUPPORTED는 0개다(support_status는 SUPPORTED / NOT_SUPPORTED_IN_V0 두 state뿐). `evaluation_as_of`는 조회 완료 후 1회 기록되는 current-runtime evaluation boundary이며 V0는 `retrieved_at` / `evaluation_as_of`로 availability / historical PIT / 최신성 / 재현성을 확립하지 않는다. 연간 보고서 fallback은 provider-neutral positive classification에서만 허용되고(OpenDART status mapping은 OPEN), §7.10 logical Evidence Basis Manifest는 필수이지만 persistence / capture는 요구하지 않으며 reproducibility는 NOT ESTABLISHED다. legacy v1 label / gating은 별도 product decision이다. **implementation NOT STARTED, live integration NOT VERIFIED, USABLE V0 NOT YET**(usable = contract / implementation / live acceptance PASS + Supported Feature Set ≥ 1). frozen contract(§7.4–§7.10) 변경 없음, 해소된 H1–H7 blocker 없음. **다음 작업 항목**: NOT SELECTED. **SECOND / THIRD**: NOT SELECTED. 근거는 `docs/dev-log/2026-09-27.md` §L. 이어서 **Trustworthy V0 Implementation NEXT Selection Review**(read-only, independent review PASS) — 이 repository에서는 provider-first가 V0-skeleton-first보다 앞선다: Supported Feature Set이 0이라 지금의 V0 skeleton은 OpenDART evidence 경로를 실행하지 않는다. 현재 `fetch_financial_accounts()`는 `status != "000"`을 모두 하나의 `ValueError`로 처리하고, 사업연도 기본값은 `now(UTC).year - 1`, 연간 보고서 후보는 하나, fallback은 없어 §7.11.4의 `EVIDENCE_RETURNED` / `REQUESTED_ANNUAL_EVIDENCE_UNAVAILABLE` / `FAILURE` 구분과 positive-only fallback을 만족할 수 없다(EIP capability는 존재하고 V0 경로의 production reachability가 없을 뿐이다). **NEXT**: `OpenDART Annual-Report Evidence Selection` — **SELECTION FROZEN / IMPLEMENTATION CONTRACT NOT STARTED / IMPLEMENTATION NOT STARTED**(하나의 slice: Q2b classified annual-evidence retrieval result + Q3 finite, calendar-assumption-free candidate generation + positive-only fallback + per-candidate selection trace, 범위·entry / exit·OUT OF SCOPE는 `docs/ARCHITECTURE.md` §7.3). 구현 전에 implementation contract와 independent review가 필요하며, Q2b / Q3 해소에는 official / documented evidence와 승인된 live verification이 필요하다. Q12(더 넓은 value semantics)와 Q1(Kiwoom)은 OPEN이며 NEXT에 포함되지 않는다. 첫 supported feature는 OpenDART-derived feature(Operating Margin / Net Margin / Debt Ratio) 방향이지만 선택되지 않았고 Supported Feature Set은 0이다. **SECOND / THIRD**: NOT SELECTED. 근거는 `docs/dev-log/2026-09-27.md` §M. 이전 선택들의 SECOND 후보(Step C: Market Confirmation Feature Identity Design, Post-Step-J: Derived Feature Value Ownership Contract)는 이력으로만 남는다.

상세 architecture 경계(확정된 First Deterministic Pipeline Slice decision)는 `docs/ARCHITECTURE.md` §7 참고. 이 자리에서 다시 설명하지 않는다.

---

## Current Capabilities

| 영역 | 상태 |
|---|---|
| Supervisor / Router | `v1 완료` — LLM closed-enum intent 분류 + Python 고정 dispatch |
| Market Agent | `v1 완료` |
| Stock Research Agent | `v1 완료` (다년 재무 추세 + RE-01 구조화 `financial_features` 포함) |
| Portfolio Strategy Agent | `v1 완료` — 단, `StockOpportunityAssessment`는 아직 소비하지 않음(위 Final Goal 참고) |
| Candidate Discovery | `v1 완료` — Industry + Theme axis(UX-01) |
| REST API (FastAPI) | `v1 완료` — `POST /analysis`, `GET /analysis/{analysis_id}`(`view=detail\|summary`) |
| ECOS 통합 | 완료 |
| OpenDART 통합 | 완료 |
| Kiwoom 통합 | 완료 |
| KIS(한국투자증권) | **research / empirical verification only — production 코드에 통합되지 않음**(`app/config.py`에 설정 항목만 존재) |
| MCP boundary | 노출 경계로 구현 완료 — 현재 어떤 Agent도 이 경로를 실행에 사용하지 않음(in-process 직접 호출) |
| **Recommendation Evaluation** | Coverage Layer `DONE` · Assembly Layer `DONE` · `RecommendationEvaluationState` First Deterministic Pipeline Slice `COMPLETE / FROZEN` · Feature Evaluator `6/14`(ROE/Operating Margin/Net Margin/Debt Ratio/Trailing PER/PBR) · Top-level Coverage(Step H/I contract + Step J 구현) `IMPLEMENTED / FROZEN` · Decision Eligibility(Policy Step 1 primitive) `IMPLEMENTED / FROZEN`(orchestrator 미연결) · Core Attractiveness/Market Confirmation/Risk/Confidence producer `NOT IMPLEMENTED` · Recommendation Policy Step 2~8 `NOT IMPLEMENTED` · Numeric Calibration `OPEN` · Point-in-Time Financial Evidence Contract `FROZEN`(PIT capability 구현 NOT STARTED) |

---

## Roadmap

| | |
|---|---|
| **DONE** | Foundation · Model Layer v1 · ECOS/OpenDART/Kiwoom Integration · Market/Stock Research/Portfolio Strategy Agent v1 · Supervisor/Router v1 · Candidate Discovery v1(Theme Axis 포함) · REST API v1 · Analysis Snapshot Lifecycle · RE-01~RE-04 Architecture/Research/Contracts(FROZEN) · RE-05 Coverage Layer · RE-05 Assembly Layer · RE-05 `RecommendationEvaluationState` First Deterministic Pipeline Slice(Evaluation Orchestration) · RE-05 Post-Orchestration Architecture Review Step A~F(READY Evaluator Expansion: Net Margin/Debt Ratio/Trailing PER/PBR evaluator + registry metadata sync) · Step G(Producer Readiness Re-evaluation) · Step H(Top-level Coverage Aggregation Contract) · Step I(Top-level Coverage Implementation Contract)(G~I는 architecture/design review, 구현 아님) · Step J(Top-level Coverage Implementation + Tests) · Post-Step-J Next Slice Selection · Final Decision Eligibility(Policy Step 1 primitive: Design/Implementation Contract + Implementation + Tests) · Post-Decision-Eligibility Readiness Review / Next Slice Selection · Feature Normalization Ownership & Representation Contract(FROZEN, design only — 구현 아님) · Calibration Data & Parameter Provenance Readiness Audit(read-only, readiness BLOCKED 판정) · Calibration Objective & Scope Contract(FROZEN, design only — calibration 아님) · Point-in-Time Financial Evidence Contract(FROZEN, design only — PIT capability 구현 아님) · Post-PIT Critical Path Review · OpenDART PIT Empirical Verification(findings FROZEN, fact discovery only — PIT 구현 아님) · Post-Empirical Critical-Path Review · Calibration Evidence Identity & Persistence Contract(FROZEN, design only — persistence 구현 아님) · Post-§7.10 Critical-Path Review · Evidence Identity Preservation(6-evaluator identity slice 구현, offline 검증 — §7.10 전체 구현 아님) · Post-EIP Critical-Path Review(read-only) · Trustworthy V0 Product Boundary & Current-Runtime Evidence / Output Contract(FROZEN, design only — V0 구현 / usable 아님) · Trustworthy V0 Implementation NEXT Selection Review(read-only) |
| **NEXT** | OpenDART Annual-Report Evidence Selection(Trustworthy V0 첫 implementation slice — SELECTION FROZEN / IMPLEMENTATION NOT STARTED) |
| **SECOND** | NOT SELECTED |
| **그 외 후보** *(선택되지 않음, 확정된 순서 아님)* | Numeric Policy-Source / First-Slice Scope Decision · Parameter Provenance / PolicyConfig · Historical Valuation Reconstruction · Corporate Action / Adjusted Price · Recommendation Objective & Outcome Semantics · Derived Feature Value Ownership Contract(ROA/Asset Turnover/Earnings Yield 공통) · Growth representation contract(Revenue/Operating Profit/Net Income Growth) · Market Confirmation Feature Identity Design · Forward/Flow upstream workstream · Core Attractiveness/Market Confirmation/Risk/Confidence producer · Recommendation Policy Step 2~8 · 이후 V0 implementation / wiring(Q12 value semantics · Feature Support Determination · V0 Evaluation Record · manifest projection · V0 path / API) · live-test gating(maintenance) — 현재 readiness snapshot은 `docs/dev-log/2026-09-26.md`, Post-EIP review는 `docs/dev-log/2026-09-27.md` §J |
| **LATER** | Numeric Calibration(`OPEN`) · Portfolio Strategy Agent가 `StockOpportunityAssessment`를 입력으로 받도록 확장 · Event & Disclosure Intelligence Overlay(Amendment 1) · 자연어 조건 기반 후보 필터링 확장(시가총액/거래대금 상위, 관심종목 등) · Classification Coverage Gap(UX-05) 보완 · 자동매매 확장(`docs/AUTOMATED_TRADING_ROADMAP.md`) |

각 항목의 세부 구현 단계(session별 변경 이력, test 개수, 버그 수정 서사)는 README에 담지 않는다 — `docs/dev-log/`가 canonical이다.

> **Legacy note**: 이전 README는 `RecommendedStock`/`RecommendationResult`라는 이름의 pre-RE-04 weighted-sum recommendation 설계를 초기 로드맵으로 담고 있었다. 이 설계는 RE-04에서 FROZEN된 staged-decision architecture(Eligibility → Core → Event Context → ... → Recommendation Policy, weighted sum 아님)로 대체됐다 — 현재 실행 가능한 contract는 `app/models/recommendation.py`다. 원문은 Git history로 보존된다.

---

## Documentation Map

| 문서 | 역할 |
|---|---|
| `docs/ARCHITECTURE.md` | **Current system architecture** — layer 구조, dependency boundary, runtime interface, RE-04/RE-05 evaluation architecture |
| `docs/dev-log/` | **Decision rationale / FROZEN history / empirical research / session handoff** — 날짜별 작업 이력 |
| `docs/AUTOMATED_TRADING_ROADMAP.md` | 장기 자동매매 확장 로드맵 |
| `app/models/*.py` + `tests/` | **Current executable contracts / invariants** — field 단위 상세는 여기가 canonical |
| `CLAUDE.md` | Claude Code session / repository operating rules |

**code/docstring은 executable contract의 canonical source이고, architecture decision의 rationale/history의 canonical source는 아니다** — "왜 이렇게 결정했는가"는 항상 `docs/dev-log/`를 확인한다.

---

## Development

### Setup

```bash
git clone https://github.com/leejja/personal-investment-agent.git
cd personal-investment-agent

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # OPENAI_API_KEY / KIWOOM_APP_KEY / KIWOOM_SECRET_KEY / ECOS_API_KEY / OPENDART_API_KEY 채우기
```

### Run

```bash
uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

- 브라우저에서 `http://127.0.0.1:8000/docs`(FastAPI 자동 문서)로 `POST /analysis`를 바로 실행해볼 수 있다.
- `question`은 자연어 그대로 넣으면 Supervisor가 내부에서 intent(market_only/stock_research/candidate_discovery/portfolio_strategy)를 분류한다.
- `?view=summary`로 요약 응답, 응답 header의 `X-Analysis-ID`로 `GET /analysis/{analysis_id}` 재조회(재실행 없음) 가능.

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/analysis \
  -H "Content-Type: application/json" \
  -d '{"question": "삼성전자 어때?"}'
```

### Test

```bash
pytest
ruff check .
```

`tests/`는 `app/`과 동일한 구조(Agent/Service/Domain Tool/Model/API 단위)로 구성돼 있다 — 개별 테스트 파일 목록/세부 케이스는 README에 나열하지 않는다. **실행 가능한 contract와 invariant는 코드/테스트 자체가 canonical source다.**

---

## Disclaimer

이 프로젝트는 개인적인 학습 및 투자 의사결정 지원을 목적으로 개발한다. 이 시스템이 생성하는 어떤 분석·추천·전략도 투자 권유가 아니며, 실제 투자 결정과 그 결과에 대한 책임은 전적으로 사용자 본인에게 있다.

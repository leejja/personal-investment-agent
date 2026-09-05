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
Feature Evaluation              현재 ROE / Operating Margin만 실제 구현
        ↓
Coverage
        ↓
Assembly
        ↓
FutureOpportunityEvidence
        ↓
RecommendationEvaluationState
        ↓
Recommendation Policy
```

```text
Coverage                DONE
Assembly                DONE
Full Orchestration      ARCHITECTURE READY / IMPLEMENTATION NEXT
Recommendation Policy   NOT IMPLEMENTED
Numeric Calibration     OPEN
```

**이 pipeline은 현재 하나의 실행 경로로 연결돼 있지 않다.** 5개 building block은 각각 구현·테스트 완료 상태이지만, 이를 순서대로 호출해 `RecommendationEvaluationState`를 만드는 `app/evaluation/orchestrator.py`는 아직 존재하지 않는다(NEXT) — 위 흐름은 "이미 동작 중인 실행 경로"가 아니라 "연결될 설계"로 읽는다.

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
| **Current Task** | RE-05 Post-Orchestration Architecture Review — 다음 deterministic implementation slice 결정 |
| **Status** | Coverage Layer `IMPLEMENTATION COMPLETE` · Assembly Layer `IMPLEMENTATION COMPLETE` · Evaluation Orchestration `FIRST DETERMINISTIC PIPELINE SLICE COMPLETE / FROZEN` |
| **Recommendation Policy** | `NOT IMPLEMENTED` |
| **Numeric Calibration** | `OPEN` |

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
    ├─ Tests                                  677 PASSED
    └─ Freeze                                 DONE
        │
        ▼
Recommendation Policy                         NOT IMPLEMENTED
        │
        ▼
Numeric Calibration                           OPEN
```

**연결 완료된 canonical path**(`app/evaluation/orchestrator.py::run_first_deterministic_pipeline`): `DeterministicAnalysisResult → NormalizedResearchData → FeatureEvaluationResult[] → Coverage → Assembly → FutureOpportunityEvidence → RecommendationEvaluationState`. Scoring/Recommendation Policy는 이번 slice 범위 밖(`Numeric Calibration = OPEN` 유지).

**NEXT**: RE-05 Post-Orchestration Architecture Review — 다음 deterministic implementation slice를 이 review에서 결정한다(candidate: Valuation/Forward/Flow/Market raw feature evaluator 확장, Core Attractiveness producer, Market Confirmation producer, Risk/Coverage/Confidence producer, Recommendation Policy — 순서는 아직 FROZEN되지 않음, 이 목록이 곧 확정된 순서를 의미하지 않는다).

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
| **Recommendation Evaluation** | Coverage Layer `DONE` · Assembly Layer `DONE` · `RecommendationEvaluationState` First Deterministic Pipeline Slice `COMPLETE / FROZEN` · Recommendation Policy `NOT IMPLEMENTED` · Numeric Calibration `OPEN` |

---

## Roadmap

| | |
|---|---|
| **DONE** | Foundation · Model Layer v1 · ECOS/OpenDART/Kiwoom Integration · Market/Stock Research/Portfolio Strategy Agent v1 · Supervisor/Router v1 · Candidate Discovery v1(Theme Axis 포함) · REST API v1 · Analysis Snapshot Lifecycle · RE-01~RE-04 Architecture/Research/Contracts(FROZEN) · RE-05 Coverage Layer · RE-05 Assembly Layer · RE-05 `RecommendationEvaluationState` First Deterministic Pipeline Slice(Evaluation Orchestration) |
| **CURRENT** | RE-05 Post-Orchestration Architecture Review — 다음 deterministic implementation slice 결정 |
| **NEXT** *(review 결과로 확정 예정 — 아래는 candidate이지 확정된 순서 아님)* | Valuation/Forward/Flow/Market raw feature evaluator 확장 · Core Attractiveness producer · Market Confirmation producer · Risk/Coverage/Confidence producer · Recommendation Policy |
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

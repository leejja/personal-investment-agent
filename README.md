# Personal Investment Multi-Agent System

개인의 실제 투자 의사결정을 지원하기 위한 **Multi-Agent 기반 개인화 투자 분석 시스템**.

단순한 종목 추천이나 자동매매 시스템이 아니라, 여러 독립적인 데이터 소스를 수집·분석하고 사용자의 실제 포트폴리오와 기존 투자 전략을 함께 고려하여 **일관되고 근거를 추적할 수 있는 투자 전략과 신규 투자 후보를 생성하는 것**을 목표로 한다.

> **Current Status:** ECOS / OpenDART / Kiwoom integration + Stock Research Agent v1(다년 재무 추세 + RE-01 구조화 financial_features 포함) + Market Agent v1 + Portfolio Strategy Agent v1 + Supervisor / Router v1 + Candidate Discovery v1(Industry + Theme axis) + REST API v1 (FastAPI, `POST /analysis?view=detail|summary` + `GET /analysis/{analysis_id}?view=detail|summary` analysis snapshot lifecycle) completed  
> **Next:** 두 번째 Fundamental `FeatureEvaluator` 구현(예: Operating Margin/Net Margin) → 두 evaluator가 등장하는 시점에 최소 Feature Registry 도입 여부 재확인(§33.4 trigger) → UX-02(InvestorProfile persistence) — RE-01~RE-03.4 데이터 조사 전부 완료 + **RE-04 Final Recommendation Architecture(base) FROZEN**, **Amendment 1 Step 1~14 전체 FROZEN** + **RE-05 Step 1~12 Policy/Contract 문서화 완료(FROZEN candidate)** + **RE-05 Data Availability Audit 완료** + **RE-05 Data Verification PARTIAL(유지)** + **RE-05 V1 Feature Set FROZEN** + **RE-05 Recommendation/Scoring Data Model DESIGN COMPLETE + Contract Audit PASSED** + **RE-05 Evaluation Boundary/Input Contract FROZEN**(`app/models/research_context.py`) + **RE-05 First Deterministic Feature Evaluation Vertical Slice 완료**(`app/evaluation/` 신규 — `NormalizedResearchData` builder + 첫 ROE `FeatureEvaluator`, 실제 실행 경로로 검증, numeric parameter 없음, 상세는 `docs/dev-log/2026-08-29.md` §25~§34)

---

# 🎯 Project Goal

최종적으로 다음과 같은 개인 투자 의사결정 지원 시스템을 구축한다.

```text
                         User
                          │
                          ▼
                 Supervisor / Router
                          │
                ┌─────────┴─────────┐
                ▼                   ▼
          Market Agent       Stock Research Agent
                │                   │
                ▼                   ▼
         MarketAnalysis       StockAnalysis[]
                │                   │
                └─────────┬─────────┘
                          │
                 PortfolioContext
                 InvestorProfile
                          │
              ┌───────────┴────────────┐
              │                        │
              ▼                        ▼
 Recommendation Engine       Portfolio Strategy Agent
              │                        │
              │ RecommendationResult   │
              └────────────┬───────────┘
                           │
                           ▼
                    StrategyResult
```

시스템은 단순히 현재 시장 상황이나 특정 종목을 분석하는 데 그치지 않고,

```text
시장 환경 분석
      ↓
개별 종목 분석
      ↓
신규 투자 후보 탐색
      ↓
실제 포트폴리오 영향 분석
      ↓
개인화 투자 전략
```

까지 연결하여 분석한다.

최종 결과에는 가능한 한 다음 정보가 포함되도록 설계한다.

- 데이터 출처
- 분석 근거
- Agent별 분석 결과
- 판단 과정
- Confidence
- Risk
- Bull / Base / Bear Scenario
- 신규 종목 추천 후보
- 추천 종목별 Score
- 추천 / 제외 근거
- Portfolio Fit
- 최종 Portfolio Strategy

---

# 🏗 Architecture

전체 시스템은 다음 영역으로 구성한다.

```text
Agent Layer
MCP Layer
Domain Tool Layer
Service Layer
External Data Sources

          +

Model Layer
Recommendation Engine
```

핵심 외부 데이터 호출 흐름은 다음과 같다.

```text
Agent
  │
  │ MCP Client
  ▼
MCP Server
  │
  │ MCP Tool
  ▼
Domain Tool
  │
  ▼
Service
  │
  ▼
External API
```

여기서 **Model Layer는 위에서 아래로 호출되는 하나의 실행 단계가 아니다.**

Model Layer는 Service, Tool, Agent, Supervisor 등이 서로 주고받는 구조화된 데이터의 계약을 정의하는 **cross-cutting Data Contract Layer**다.

Recommendation Engine 역시 외부 API를 직접 호출하기보다 Agent 및 Model Layer를 통해 만들어진 구조화된 분석 결과를 입력으로 사용한다.

---

# 🏛 Overall Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                            User                              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               │ UserRequest
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                Supervisor / Router — v1 ✓                    │
│                                                              │
│  • LLM 기반 intent 분류 (closed enum, Python이 강제)          │
│    market_only / stock_research / candidate_discovery /      │
│    portfolio_strategy                                        │
│  • 종목명/코드 해석 (OpenDART 정확 일치, 추측 없음)            │
│  • intent별 고정 실행 단계 (범용 DAG 엔진 없음)                │
│  • 부분 실패 정책 (root 실패=전체 실패 /                       │
│    fan-out 개별 실패=skip / sink 실패=부분 결과)               │
│  • SupervisorResult 결정론적 조립 (LLM synthesis 없음)         │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼


=========================== AGENT LAYER =========================


          ┌──────────────────────┐
          │ Stock Research Agent │
          │       (v1 ✓)         │
          │                      │
          │ • Deterministic      │
          │   analysis           │
          │ • LLM reasoning      │
          │ • Domain Tool 직접   │
          │   호출 (in-process)  │
          └──────────┬───────────┘
                     │
          ┌──────────────────────┐
          │     Market Agent     │
          │       (v1 ✓)         │
          │                      │
          │ • Deterministic      │
          │   analysis           │
          │ • LLM reasoning      │
          │   (fact-grounded)    │
          │ • Domain Tool 직접   │
          │   호출 (in-process)  │
          └──────────┬───────────┘
                     │
          ┌──────────────────────┐
          │ Portfolio Strategy   │
          │   Agent (v1 ✓)       │
          │                      │
          │ • Deterministic      │
          │   analysis           │
          │ • LLM reasoning      │
          │   (fact-grounded)    │
          │ • MarketAnalysis /   │
          │   StockAnalysis[] /  │
          │   PortfolioContext / │
          │   InvestorProfile을  │
          │   입력으로 받음      │
          │   (Domain Tool 미호출)│
          └──────────┬───────────┘
                     │
                     │ Domain Tool 직접 호출
                     │ (MCP Protocol 아님)
                     ▼


============================ MCP LAYER ==========================


          ┌──────────────────────────────────┐
          │            MCP Server            │
          │                                  │
          │ app/mcp/server.py                │
          │                                  │
          │ Exposed MCP Tools                │
          │                                  │
          │ • get_base_rate                  │
          │ • get_exchange_rate              │
          │ • get_kospi_index                │
          │ • get_kosdaq_index               │
          │ • get_company_financials         │
          │ • get_key_financials             │
          │ • get_stock_info                 │
          │ • get_account_balance            │
          │ • get_portfolio_context          │
          └────────────────┬─────────────────┘
                           │
                           │ Python calls
                           ▼


======================== DOMAIN TOOL LAYER ======================


        ┌──────────────────┐
        │    EcosTools     │
        │                  │
        │ get_base_rate()  │
        │ get_exchange_    │
        │  rate()          │
        │ get_kospi_       │
        │  index()         │
        │ get_kosdaq_      │
        │  index()         │
        └────────┬─────────┘
                 │
                 │
        ┌────────┴─────────┐
        │  OpenDartTools   │
        │                  │
        │ get_company_     │
        │  financials()    │
        │ get_key_         │
        │  financials()    │
        └────────┬─────────┘
                 │
                 │
        ┌────────┴─────────┐
        │   KiwoomTools    │
        │                  │
        │ get_stock_info() │
        │ get_account_     │
        │  balance()       │
        └────────┬─────────┘
                 │
                 ▼


========================== SERVICE LAYER ========================


        ┌────────────────────────┐
        │      EcosService       │
        │                        │
        │ ✓ implemented          │
        │                        │
        │ • HTTP request         │
        │ • Error handling       │
        │ • JSON parsing         │
        │ • Validation           │
        │ • Normalization        │
        └────────────┬───────────┘
                     │

        ┌────────────────────────┐
        │    OpenDartService     │
        │                        │
        │ ✓ implemented          │
        └────────────┬───────────┘
                     │

        ┌────────────────────────┐
        │     KiwoomService      │
        │                        │
        │ ✓ implemented          │
        └────────────┬───────────┘
                     │

        ┌────────────────────────┐
        │       LLMService       │
        │                        │
        │ ✓ implemented          │
        │                        │
        │ • OpenAI Chat          │
        │   Completions 호출     │
        │ • Stock Research       │
        │   Agent 전용           │
        └────────────┬───────────┘
                     │
                     ▼


====================== EXTERNAL DATA SOURCES ====================


          ┌─────────────────┐
          │    ECOS API     │
          │                 │
          │ 금리 / 환율 /   │
          │ 거시경제 지표   │
          └─────────────────┘

          ┌─────────────────┐
          │  OpenDART API   │
          │                 │
          │ 공시 / 재무     │
          │ 기업 데이터     │
          └─────────────────┘

          ┌─────────────────┐
          │ Kiwoom REST API │
          │                 │
          │ 가격 / 수급 /   │
          │ 계좌 / 거래     │
          └─────────────────┘


=========================== MODEL LAYER =========================


          시스템 전체에서 사용하는 Data Contract

          ┌─────────────────────────────┐
          │       Common Models         │
          │                             │
          │ • UserRequest               │
          │ • Evidence                  │
          │ • RiskLevel                 │
          │ • AnalysisConfidence        │
          └─────────────────────────────┘

          ┌─────────────────────────────┐
          │      Analysis Models        │
          │                             │
          │ • MarketAnalysis            │
          │ • StockAnalysis             │
          │   (StockPriceSnapshot /     │
          │    FinancialSnapshot에      │
          │    250거래일 고저,          │
          │    자산/부채/자본 포함)     │
          │ • PortfolioContext          │
          │ • InvestorProfile           │
          │ • StrategyResult            │
          └─────────────────────────────┘

          ┌─────────────────────────────┐
          │     Integration Models      │
          │                             │
          │ • EcosStatisticPoint        │
          │ • OpenDartCorporation       │
          │ • OpenDartFinancialAccount  │
          │ • KiwoomStockInfo           │
          │ • KiwoomAccountBalance      │
          │ • ...                       │
          └─────────────────────────────┘

          ┌─────────────────────────────┐
          │   Recommendation Models     │
          │          (future)           │
          │                             │
          │ • RecommendedStock          │
          │ • RecommendationResult      │
          └─────────────────────────────┘
```

---

# 🔄 MCP Client / Server Relationship

MCP에서 Client와 Server의 역할을 명확하게 구분한다.

```text
MCP Client
= Tool을 발견하고 호출하는 쪽

MCP Server
= Tool을 등록하고 노출하는 쪽
```

현재 프로젝트에 적용하면 다음과 같다.

## Current

```text
tests/test_mcp_server.py
        │
        │ MCP Client
        │
        │ list_tools()
        │ call_tool()
        ▼
app/mcp/server.py
        │
        │ MCP Server
        │
        │ exposes 9 tools:
        │ get_base_rate
        │ get_exchange_rate
        │ get_kospi_index
        │ get_kosdaq_index
        │ get_company_financials
        │ get_key_financials
        │ get_stock_info
        │ get_account_balance
        │ get_portfolio_context
        ▼
Domain Tool Layer
        │
        ▼
Service Layer
        │
        ▼
External API
```

`tests/test_mcp_server.py`의 MCP Client가 이 경로를 실제 외부 API까지 end-to-end로 검증한다.

**Stock Research Agent v1과 Market Agent v1 모두 이 MCP Client 경로를 사용하지 않는다.** 같은 Python 프로세스 안에서 Domain Tool(`KiwoomTools`, `OpenDartTools`, `EcosTools`)을 직접 호출한다. MCP Server는 별도 프로세스나 외부 클라이언트(예: 다른 Agent Runtime, LLM host)를 위한 노출 경계로 유지된다.

**Portfolio Strategy Agent v1은 Domain Tool을 아예 호출하지 않는다.** 이미 다른 Agent가 만든 `MarketAnalysis`/`list[StockAnalysis]`와 `PortfolioContext`/`InvestorProfile`을 입력으로 받아 판단만 한다(호출자가 Market Agent·Stock Research Agent·`PortfolioAdapter`를 먼저 실행해 이 입력을 준비한다). `LLMService`만 다른 두 Agent와 동일하게 직접 호출한다.

## Future

향후 Agent들의 기본 패턴은 다음과 같다.

```text
Agent (in-process, 예: Stock Research Agent, Market Agent)
        │
        │ 직접 호출 (MCP Protocol 아님)
        ▼
Domain Tool
        │
        ▼
Service
        │
        ▼
External API


External MCP Client (별도 프로세스, 다른 Agent Runtime 등)
        │
        │ MCP Protocol
        ▼
MCP Server
        │
        ▼
Domain Tool
```

즉, MCP Client/Server 경로는 프로세스 경계를 넘는 외부 연동이 필요할 때 사용하고, 같은 프로세스 안의 Agent → Domain Tool 호출에는 사용하지 않는다. Portfolio Strategy Agent v1도 이 원칙을 그대로 따르되, Domain Tool을 직접 호출할 필요 자체가 없다(위 참고).

---

# 🧱 Layer Responsibilities

| Layer | Responsibility |
| --- | --- |
| **Supervisor / Router** | User Request 분석, Agent routing, orchestration, 결과 종합 |
| **Agent Layer** | 시장·종목·포트폴리오 reasoning 및 투자 판단 |
| **MCP Client** | MCP Server의 Tool discovery 및 Tool invocation |
| **MCP Server** | Domain 기능을 MCP Tool로 노출 |
| **Domain Tool Layer** | Agent가 이해하기 쉬운 의미 기반 기능 제공 |
| **Service Layer** | 외부 API 호출, 오류 처리, parsing, normalization |
| **External Data Sources** | 실제 시장·기업·계좌 데이터 제공 |
| **Model Layer** | 시스템 전체의 명시적인 Data Contract |
| **Recommendation Engine** | 신규 투자 후보 평가·랭킹 및 Portfolio Fit 분석 |

핵심 책임 분리는 다음과 같다.

```text
Agent
→ reasoning / investment decision

MCP Client
→ MCP Tool discovery / invocation

MCP Server
→ Tool exposure / protocol boundary

Domain Tool
→ semantic domain operation

Service
→ external API access / parsing / normalization

External API
→ raw data provider

Model
→ data contract

Recommendation Engine
→ explainable stock ranking / filtering / portfolio fit
```

---

# 📡 Data Access Flow

Agent가 외부 API의 내부 구현 세부사항을 직접 알지 않도록 한다.

```text
Agent
  │
  │ "기준금리를 조회하고 싶다"
  ▼
MCP Client
  │
  │ call_tool("get_base_rate")
  ▼
MCP Server
  │
  │ get_base_rate
  ▼
Domain Tool
  │
  │ EcosTools.get_base_rate()
  ▼
Service
  │
  │ EcosService.get_statistic()
  ▼
External API
```

Agent는 ECOS API의 다음 내부 코드를 알 필요가 없다.

```text
STAT_CODE  = 722Y001
ITEM_CODE1 = 0101000
```

대신 Agent는 의미 기반 Tool만 사용한다.

```text
get_base_rate(
    start_date,
    end_date
)
```

내부에서는 다음과 같이 변환된다.

```text
Agent / MCP Client
        │
        ▼
get_base_rate
        │
        ▼
MCP Server
        │
        ▼
EcosTools.get_base_rate()
        │
        ▼
EcosService.get_statistic(
    statistic_code="722Y001",
    cycle="D",
    item_code1="0101000",
    ...
)
        │
        ▼
ECOS API
```

이를 통해 Agent reasoning을 특정 외부 API 구현으로부터 분리한다.

---

# 📊 ECOS End-to-End Flow

현재 ECOS 연동은 MCP Client부터 실제 한국은행 ECOS API까지 end-to-end로 연결되어 있다.

```text
MCP Client
    │
    │ list_tools()
    ▼
MCP Server
    │
    │ discovers:
    │ get_base_rate
    │
    │ call_tool()
    ▼
get_base_rate MCP Tool
    │
    ▼
EcosTools.get_base_rate()
    │
    ▼
EcosService.get_statistic()
    │
    ├── URL construction
    ├── async HTTP request
    ├── HTTP error handling
    ├── JSON parsing
    ├── response validation
    └── data normalization
    │
    ▼
ECOS API
    │
    │ raw JSON
    ▼
EcosStatisticPoint[]
    │
    ▼
MCP structured_content
```

실제 ECOS API 응답의 문자열 기반 값:

```text
DATA_VALUE = "2.75"
```

은 Service Layer에서 다음과 같이 정규화된다.

```text
EcosStatisticPoint.value = 2.75
                           └── float
```

MCP Tool 호출 결과에서는 structured content로 전달된다.

```text
structured_content
└── result[]
    ├── statistic_code
    ├── statistic_name
    ├── item_code1
    ├── item_name1
    ├── unit
    ├── time
    └── value
```

현재 실제 MCP end-to-end 테스트를 통해 다음 경로를 검증했다.

```text
MCP Client
    ↓
MCP Server
    ↓
get_base_rate
    ↓
EcosTools
    ↓
EcosService
    ↓
Real ECOS API
    ↓
value = 2.75
```

---

# 🧩 Model Layer

Model Layer는 호출 흐름상의 단일 단계가 아니라 **시스템 전체에서 사용하는 Data Contract Layer**다.

```text
Service ────────────┐
                    │
Domain Tool ────────┤
                    │
MCP Server ─────────┼────► Model Layer
                    │
Agent ──────────────┤
                    │
Recommendation ─────┤
                    │
Supervisor ─────────┘
```

Agent 사이의 데이터 계약은 Pydantic 모델로 명시적으로 정의한다.

현재 Model Layer v1:

```text
common.py
├── RiskLevel
├── AnalysisConfidence
├── Evidence
└── UserRequest

market.py
├── MarketRegime
├── MarketIndicator
└── MarketAnalysis

stock.py
├── ScenarioType
├── StockPriceSnapshot
├── FinancialSnapshot
├── StockScenario
└── StockAnalysis

portfolio.py
├── PortfolioPosition
├── PortfolioContext
└── InvestorProfile

strategy.py
├── InvestmentAction
├── PositionRecommendation
└── StrategyResult

supervisor.py
├── Intent
└── SupervisorResult
```

`stock.py`의 `StockPriceSnapshot`/`FinancialSnapshot`은 Kiwoom·OpenDART에서 이미 확보된 데이터를 손실 없이 담기 위해 다음 필드를 포함한다.

```text
StockPriceSnapshot
├── symbol, name, price, change_pct, volume
├── high_250d   # 250거래일 최고가
└── low_250d    # 250거래일 최저가

FinancialSnapshot
├── revenue, operating_profit, net_income
├── total_assets
├── total_liabilities
├── total_equity
└── per, pbr, roe
```

외부 API integration에서도 구조화된 데이터 모델을 사용한다.

현재:

```text
EcosStatisticPoint
├── statistic_code
├── statistic_name
├── item_code1
├── item_name1
├── unit
├── time
└── value: float

OpenDartCorporation / OpenDartFinancialAccount
KiwoomStockInfo / KiwoomAccountBalance / KiwoomAccountPosition
```

향후 Recommendation Engine 구현 시 다음 모델을 추가한다.

```text
RecommendedStock
RecommendationResult
```

---

# 🤖 Agents

## 1. Supervisor / Router — ✅ v1 구현 완료

사용자의 질문(`UserRequest`)을 해석해 필요한 Agent를 선택하고, Agent 간 의존성을 올바른 순서로 실행한 뒤 결과를 조립한다. Router(의도 분류)와 Supervisor(실행·조립)를 별도 컴포넌트로 분리하지 않고 하나의 `SupervisorOrchestrator`로 시작했다 — intent가 3종류뿐인 지금 분리는 간접 계층만 늘릴 뿐이라고 판단했다(원칙: 불필요한 abstraction을 미리 만들지 않는다).

v1 구현 구조:

```text
app/supervisor/
├── routing.py       # LLM 기반 intent 분류 (closed enum 검증 + 재시도)
└── orchestrator.py  # intent별 고정 실행 단계, 부분 실패 처리, SupervisorResult 조립
```

다른 세 Agent와 달리 `analysis.py`가 없다 — routing의 입력은 외부 API 수치가 아니라 사용자의 자연어 자체라, "LLM에게 넘기기 전에 Python이 먼저 정리할 deterministic fact"가 없기 때문이다.

v1이 지원하는 intent 4종(closed enum, LLM이 이 중 하나만 고를 수 있고 Python이 강제):

```text
market_only          → Market Agent만 실행
stock_research        → 언급된 종목의 Stock Research Agent만 실행
candidate_discovery    → Candidate Discovery → 후보 종목들의 Stock Research 실행
                          (개인화 BUY/AVOID 판단 없음)
portfolio_strategy     → Market + (명시 종목 | discovery 후보 | 보유종목 전체) Stock Research
                          + PortfolioContext + InvestorProfile → Portfolio Strategy Agent
```

v1의 핵심 정책:

- **LLM은 tool-calling 권한이 없다**: LLM은 `intent` enum과 `mentioned_stock_terms`(원문에 언급된 종목명/코드 텍스트)만 구조화 출력하고, 어떤 Agent를 어떤 순서로 실행할지는 Python의 고정 dispatch가 100% 결정한다. 존재하지 않는 Agent/tool을 LLM이 호출하는 경로 자체가 없다.
- **종목명 해석도 Python이 결정론적으로 검증한다**: `UserRequest.symbols`가 있으면 그대로 신뢰하고, 없으면 LLM이 추출한 텍스트를 `OpenDartTools.find_stock_code_by_name()`(OpenDART 회사 목록과 정확히 일치할 때만)으로 해석한다. 모호하거나 못 찾으면 추측하지 않고 실패시킨다 — LLM이 종목코드를 자기 지식으로 만들어내는 경로를 원천 차단한다.
- **PORTFOLIO_STRATEGY 내부에서 우선순위 3단 분기를 쓴다**(discovery 자체는 새 intent를 추가했지만, portfolio_strategy에 discovery를 엮는 것은 새 intent 없이 기존 실행 로직을 재사용): 특정 종목을 명시한 질문(예: "삼성전자 더 사도 될까?")은 그 종목만 Stock Research를 실행하고, discovery 조건이 있는 질문(예: "내 포트폴리오에 없는 반도체 후보 찾아줘")은 Candidate Discovery로 찾은 후보를, 둘 다 없으면(예: "내 포트폴리오 분석해줘") 보유종목 전체를 실행한다. 매번 보유종목 전체를 재분석하는 비용을 피하기 위한 정책이다.
- **부분 실패 정책은 위치에 따라 다르다**: 다른 단계가 의존하는 root(Market Agent, 명시적으로 물어본 종목의 Stock Research)가 실패하면 전체 요청을 실패시킨다(근거 없는 fallback을 만들지 않음). 전체 포트폴리오 fan-out의 개별 종목 실패(예: OpenDART에 재무 데이터가 없는 ETF)는 그 종목만 skip하고 나머지로 계속 진행한다. 아무도 의존하지 않는 sink인 Portfolio Strategy Agent의 reasoning 실패(`ReasoningError`)는 이미 확보한 `MarketAnalysis`/`StockAnalysis[]`/`PortfolioContext`를 그대로 반환하는 부분 결과를 허용한다.
- **보유종목 fan-out은 동시성을 제한한다**: 종목 수만큼 무제한 병렬 실행하면 Kiwoom OAuth 토큰 발급이 몰려 429가 발생함을 실제 E2E에서 확인해, `Semaphore`로 동시 실행 개수를 제한했다(자세한 내용은 dev-log 참고).
- **최종 조립은 결정론적이며, 별도 LLM synthesis가 없다**: `SupervisorResult`는 각 Agent가 이미 만든 evidence-grounded 결과 객체를 그대로 담을 뿐, 이를 재해석해 새 문장을 생성하는 추가 LLM 호출을 두지 않는다 — 그 자체가 새로운 fabrication 위험을 재도입하기 때문이다.
- `InvestorProfile`은 아직 저장소가 없어 `SupervisorOrchestrator.run()`의 별도 파라미터로 호출자가 공급한다(Portfolio Strategy Agent 데모와 동일한 한계).

주요 출력(`app/models/supervisor.py`, 신규):

```text
SupervisorResult
├── intent
├── resolved_symbols[]
├── candidates[]       # Candidate Discovery를 거친 경우에만 채워짐
├── market_analysis
├── stock_analyses[]
├── portfolio_context
├── strategy_result
└── skipped[]
```

---

## 2. Market Agent — ✅ v1 구현 완료

전체 시장 환경을 분석한다.

v1 구현 구조는 Stock Research Agent와 동일한 패턴을 따른다:

```text
app/agents/market/
├── analysis.py       # deterministic 분석 (raw facts, 20/60일 변화율, confidence 상한)
├── reasoning.py       # LLM reasoning (summary / suggested_regime / suggested_risk_level)
└── orchestrator.py    # 위 둘을 조합해 최종 MarketAnalysis 생성
```

v1이 실제로 사용하는 데이터 (모두 ECOS, `as_of_date` 기준 lookback 조회):

- `get_base_rate` — 한국 기준금리
- `get_exchange_rate` — USD/KRW 환율
- `get_kospi_index` — KOSPI지수
- `get_kosdaq_index` — KOSDAQ지수

해외 지수(S&P500/NASDAQ), 외국인/기관 수급, 시장 뉴스는 v1 범위에서 제외했다(추가 외부 데이터 소스 또는 신규 Kiwoom 엔드포인트가 필요해 v2 이후로 미룸). 다만 ECOS `802Y001` 테이블에 외국인 순매수 데이터도 이미 존재함을 확인했고, 이는 향후 별도 외부 연동 없이 확장 가능한 후보로 남겨둔다.

v1의 핵심 정책:

- **Evidence-grounded**: LLM은 `analysis.py`가 만든 deterministic facts만 근거로 사용하고, 뉴스·수급·해외 지수 등 제공되지 않은 정보를 추측하지 않는다.
- **평가 없는 raw fact**: 기준금리 변경폭(bp), 환율/지수 20·60거래일 변화율은 수치 사실만 제공하고 "긴축적/완화적" 같은 판단을 하지 않는다. 해석은 reasoning 단계(LLM)의 몫이다.
- **날짜 계산의 두 가지 방식**: 기준금리는 주말 포함 매일 값이 채워지므로 "60일 전"을 달력일 기준으로 찾고, 환율/지수는 영업일에만 값이 존재하므로 리스트 위치("20/60거래일 전") 기준으로 찾는다 — 실제 ECOS 데이터로 두 지표의 밀도 차이를 확인하고 반영했다.
- **regime / risk_level은 Python 상수로 고정하지 않는다**: Stock Research Agent의 `risk_level`과 달리 Market Agent의 존재 이유 자체이므로 LLM의 `suggested_regime`/`suggested_risk_level`을 사용한다. 대신 **fact-id grounding**으로 구조적으로 통제한다 — `regime_fact_ids`/`risk_fact_ids`가 각각 비어 있거나, 존재하지 않는 fact id를 하나라도 포함하면 검증 실패로 처리한다(일부만 유효해도 조용히 걸러내고 통과시키지 않음).
- **grounding 실패 시 1회 재시도 후 예외 전파**: JSON 파싱 실패와 동일하게, grounding 검증 실패도 최대 2회 시도 후에도 실패하면 `ReasoningError`를 raise한다 — 근거 없는 regime/risk_level을 confidence만 낮춰 반환하지 않고, "근거 없는 결과는 반환하지 않는다"는 원칙을 그대로 유지한다.
- **confidence 상한**: 기준금리·USD/KRW 20일 변화율·KOSPI 20일 변화율이 모두 계산 가능하면 MEDIUM, 하나라도 없으면 LOW(v1은 HIGH를 반환하지 않는다).

주요 출력:

```text
MarketAnalysis
├── regime
├── risk_level
├── summary
├── indicators[]
├── confidence
└── evidence[]
```

`MarketAnalysis`/`MarketIndicator` 모델은 변경 없이 그대로 사용한다 — v1 지표(기준금리/환율/KOSPI/KOSDAQ)를 표현하기에 이미 충분히 범용적이었다.

---

## 3. Stock Research Agent — ✅ v1 구현 완료

개별 종목을 심층 분석한다.

v1 구현 구조:

```text
app/agents/stock_research/
├── analysis.py       # deterministic 분석 (facts, confidence 상한, risk_level)
├── reasoning.py       # LLM reasoning (thesis / catalysts / risks / scenarios)
└── orchestrator.py    # 위 둘을 조합해 최종 StockAnalysis 생성
```

v1이 실제로 사용하는 데이터:

- Kiwoom `get_stock_info` — 현재가, 등락률, 거래량, PER/PBR/ROE, 250거래일 고/저
- OpenDART `get_key_financials_history` — 매출/영업이익/순이익, 자산/부채/자본총계를 **최근 3개 사업연도**(당기·전기·전전기) 분량으로 조회

`PortfolioContext`는 의도적으로 사용하지 않는다. 종목 자체의 분석(재사용 가능)과 사용자별 투자 판단(Portfolio Strategy Agent의 역할)을 분리하기 위함이다.

v1의 핵심 정책:

- **Evidence-grounded**: LLM은 `analysis.py`가 만든 deterministic facts만 근거로 사용하고, 뉴스·공시·산업 동향 등 제공되지 않은 정보를 추측하지 않는다.
- **평가 없는 raw fact**: PER/PBR/ROE 등 비교 기준이 없는 지표는 수치 사실만 제공하고 "고평가/저평가/양호" 같은 판단을 하지 않는다.
- **target_price / probability 미생성**: v1에는 목표주가 산정 근거가 없으므로 항상 `null`이며, Python이 파싱 후 구조적으로 강제한다.
- **catalyst 엄격 정의**: 향후 주가·실적·기업가치에 영향을 줄 구체적 이벤트만 catalyst로 인정하고, 단순 재무 규모 재진술이나 과거 재무 추세 개선 자체도 catalyst로 취급하지 않는다.
- **risk_level 고정(MEDIUM)**: 단일연도 재무 데이터만으로는 LOW/HIGH를 판단할 근거가 부족해 v1은 중립값을 사용하며, LLM은 이 값을 변경할 수 없다.
- **confidence 상한**: `analysis.py`가 데이터 완전성에 따라 계산한 상한과 LLM이 제안한 값 중 더 낮은 쪽을 최종 `confidence`로 사용한다(v1은 다년 추세 데이터가 있어도 HIGH를 반환하지 않는다).
- `catalysts` / `risks` / `scenarios`는 근거가 없으면 빈 리스트를 정상 출력으로 허용한다.

**다년 재무 추세(financial_history)**:

- OpenDART `fnlttSinglAcnt.json`은 사업보고서(`report_code="11011"`)일 때 하나의 호출로 당기/전기/전전기(`thstrm`/`frmtrm`/`bfefrmtrm`) 3개 연도를 함께 내려준다는 점을 실제 API 호출로 확인했고, 이를 그대로 재사용한다 — **추가 API 호출 없이** 3개년 추세를 얻는다.
- 분기/반기 보고서(`report_code != "11011"`)에서는 전기/전전기를 추세로 섞지 않고 당기 1건만 사용한다.
- `analysis.py`는 매출/영업이익/순이익의 전년 대비 변동을 계산하되, 손익 부호가 바뀌는 경우(흑자→적자, 적자→흑자)나 둘 다 적자인 경우 백분율이 아니라 "흑자전환/적자전환/적자 규모 확대·축소"로 표현해 왜곡을 피한다. 전년 값이 0이면 변동률 자체를 생략한다.
- 연도별 영업이익률·순이익률·부채비율과, 3개 연도 데이터가 모두 있고 방향이 단조로울 때만 "최근 3개 연도 연속 상승/하락" fact를 만든다 — 이 모든 값은 결정론적으로 계산되며 "좋다/나쁘다" 같은 평가는 포함하지 않는다.
- `financial_history`의 각 연도 스냅샷은 PER/PBR/ROE를 절대 채우지 않는다 — Kiwoom은 현재 시점 valuation만 제공하고 OpenDART는 과거 시가총액/주가를 주지 않으므로 과거 밸류에이션 지표는 계산 근거가 없다. (`financials`, 즉 최신 연도 스냅샷의 PER/PBR/ROE는 기존과 동일하게 Kiwoom 현재가 기준으로 채워진다.)
- reasoning 프롬프트는 다년 추세가 있으면 `investment_thesis`가 이를 적극 활용하도록 지시하되, 과거 추세만으로 미래 실적·주가를 단정하지 않도록 명시한다.
- `risks` 정책은 절대적 금지가 아니라 완화된 형태로 규정한다: 비교 기준(업종 평균 등) 없는 단일 시점 수치(PER/PBR/ROE/거래량/부채비율 등)만으로 고평가/저평가·위험/안전을 단정하지 않되, 다년 추세나 흑자/적자 전환 같은 fact는 더 강한 risk 근거로 사용할 수 있다. 핵심은 deterministic fact와 risk 판단을 혼동하지 않는 것이다.

**구조화된 재무 feature(`financial_features`, RE-01)** — Recommendation Engine을 위한 기반:

- 위 다년 추세 계산(영업이익률/순이익률/부채비율, YoY 변동/흑자·적자 전환, 3개년 연속 상승·하락)은 이전까지 `Evidence.description` **텍스트로만** 존재해, 향후 Recommendation Engine이 숫자를 쓰려면 텍스트를 파싱하거나 같은 계산을 다시 구현해야 하는 문제가 있었다. `StockAnalysis.financial_features`는 **같은 계산 결과**를 machine-readable 구조(`AnnualFinancialFeatures`/`FinancialYoYChange`/`FinancialTrendEntry`)로 추가 노출한다 — 새로운 계산식이나 새로운 투자 판단이 아니라 기존 deterministic 계산의 구조화일 뿐이다.
- **Single source of truth**: `_operating_margin`/`_net_margin`/`_debt_ratio`/YoY 분류/3개년 방향 판단은 한 곳에서만 계산되고, 그 결과가 (a) 기존과 byte-identical한 `Evidence` 텍스트와 (b) `financial_features` 구조값 양쪽에 그대로 쓰인다 — 같은 값을 두 번 계산하지 않는다. 실제 E2E(005930/373220/080220)로 `financial_features.annual[]`의 모든 margin/debt_ratio 수치가 대응하는 `Evidence.description` 문자열과 정확히 일치함을 확인했다.
- **`annual`은 `financial_history`와 독립적인 gate를 쓴다**: `financial_history`(공개 필드)는 여전히 2개 연도 이상일 때만 채워지는 기존 semantics를 그대로 유지하지만, `financial_features.annual`은 **최소 1개 연도(당기)만 있어도** 채워진다 — margin/debt_ratio는 원래 단일 연도로 계산 가능한 기존 공식이라 2개년 추세 요건과 묶일 이유가 없었다. `yoy`/`trends`는 기존과 동일하게 각각 2개년/3개년 이상을 요구한다.
- `FinancialTransition`(LOSS_TO_PROFIT/PROFIT_TO_LOSS/LOSS_WIDENING/LOSS_NARROWING/LOSS_UNCHANGED)과 `FinancialTrendDirection`(INCREASING/DECREASING)은 기존 코드가 실제로 구분하던 케이스만 담는다 — "MIXED"/"FLAT" 같은 새 판단은 추가하지 않았다. `LOSS_UNCHANGED`는 기존 코드에 있었지만 지금까지 테스트되지 않았던 분기라 이번에 단위 테스트를 추가했다.
- **PER/PBR/ROE와 EPS/BPS는 RE-01 범위 밖**이다 — PER/PBR/ROE는 기존 `financials`(Kiwoom 현재 시점 스냅샷)에 그대로 두고 옮기거나 복제하지 않았고, EPS/BPS는 Kiwoom에 존재하지만 이번에도 추가하지 않았다.
- **API/UX 호환성**: `POST /analysis`(view=detail)의 `stock_analyses[].financial_features`에 additive로 노출되고, 기존 필드는 전혀 바뀌지 않는다. `view=summary`(UX-03)에는 기존 화이트리스트 구조가 자동으로 이 필드를 제외해 별도 코드 변경이 필요 없었다(실제 E2E로 확인). LLM reasoning 프롬프트에는 `financial_features`를 추가하지 않았다 — 이번 변경은 Recommendation Engine을 위한 기반일 뿐, Recommendation Engine 자체는 아직 구현하지 않았다.

주요 출력:

```text
StockAnalysis
├── symbol
├── name
├── price
├── financials              # 최신 연도 스냅샷(PER/PBR/ROE 포함)
├── financial_history[]     # 오래된 연도 → 최신 연도, 사업보고서 기준 최대 3개년(PER/PBR/ROE는 항상 null)
├── financial_features       # RE-01: annual[]/yoy[]/trends[] — Evidence와 동일 계산의 구조화 버전
├── investment_thesis
├── catalysts[]
├── risks[]
├── scenarios[]
├── risk_level
├── confidence
└── evidence[]
```

---

## 4. Portfolio Strategy Agent — ✅ v1 구현 완료

Market Agent와 Stock Research Agent의 결과를 사용자의 실제 포트폴리오·투자 성향과 결합해 종목별 action을 판단한다. 이 Agent의 존재 이유는 "종목 자체가 좋은가"(Stock Research Agent)나 "시장이 어떤가"(Market Agent)가 아니라 **"이 사용자는 지금 이 종목에 대해 무엇을 해야 하는가"**를 판단하는 것이다.

v1 구현 구조는 Market Agent·Stock Research Agent와 동일한 패턴을 따른다:

```text
app/agents/portfolio/
├── analysis.py       # deterministic 분석 (portfolio/market/종목 fact, 종목별 allowed_actions)
├── reasoning.py       # LLM reasoning (action/portfolio_risk, symbol·fact-id·action 3중 grounding)
└── orchestrator.py    # 위 둘을 조합해 최종 StrategyResult 생성
```

v1 최소 input contract:

```text
MarketAnalysis
list[StockAnalysis]
PortfolioContext
InvestorProfile
```

`RecommendationResult`는 아직 구현되지 않아(Recommendation Engine 미착수) v1 입력에서 제외했다. 따라서 v1의 "미보유 종목 추천"은 전체 시장을 스캔한 신규 발굴이 아니라, **호출자가 `stock_analyses`에 명시적으로 포함한 종목**(보유 종목 + 사용자가 물어본/워치리스트 종목)에 한정된다 — Recommendation Engine이 구현되면 v2에서 정식 입력으로 추가할 예정이다.

v1의 핵심 정책:

- **Evidence-grounded**: LLM은 `analysis.py`가 만든 deterministic fact와 "판단 대상 종목" 목록만 근거로 사용하고, 뉴스·공시·목록에 없는 종목 등 제공되지 않은 정보를 추측하거나 지어내지 않는다.
- **평가 없는 raw fact**: 현금 비중, 종목별 비중, 집중도(top1/top3), 평가손익률, 시장 regime/risk_level, 사용자 risk_tolerance 등은 수치·라벨 사실만 제공하고 "과도하다/적절하다" 같은 판단을 하지 않는다. 판단은 reasoning 단계(LLM)의 몫이다. 섹터 집중도는 Kiwoom/OpenDART 어디에도 업종 데이터가 없어 v1 범위에서 제외했다.
- **action은 3중으로 grounding한다**: ① `recommendations[].symbol`은 반드시 입력으로 주어진 `stock_analyses`의 symbol 집합에 있어야 하고(새 종목을 지어내는 것을 원천 차단), ② `suggested_action`은 보유 여부에 따라 Python이 계산한 허용 action 집합(미보유: BUY/AVOID, 보유: ADD/HOLD/REDUCE/SELL) 안에 있어야 하며, ③ `fact_ids`/`portfolio_risk_fact_ids`는 비어 있으면 안 되고 존재하지 않는 fact id를 포함해도 안 된다(Market Agent의 fact-id grounding과 동일 원칙, 일부만 유효해도 통과시키지 않음). 세 검증 모두 `reasoning.py`의 동일한 재시도 루프 안에서 처리되고, 최종 실패 시 `ReasoningError`를 raise한다 — `orchestrator.py`는 이 검증을 중복하지 않고 target_weight 강제/confidence cap/evidence 조립/최종 조립만 담당한다.
- **target_weight는 v1에서 항상 null이다**: 포지션 사이징 근거(리스크 버짓, 밸류에이션 모델 등)가 없기 때문이다 — Stock Research Agent가 근거 없는 `target_price`를 항상 null로 강제한 것과 동일한 문제·동일한 해법이다. `reasoning.py`의 응답 스키마 자체에 숫자 필드가 없어 LLM이 애초에 값을 만들 통로가 없고, `orchestrator.py`가 최종 조립 시점에도 명시적으로 `None`을 강제한다.
- **핵심 분석 근거가 없는 종목은 recommendation을 만들지 않는다**: `stock_analyses`에 없는 보유 종목(예: OpenDART에 재무 데이터가 없는 ETF)은 recommendation 대상에서 제외된다. 다만 portfolio-level fact(비중, 집중도 등)에는 계속 반영된다.
- **confidence 상한**: `stock_analyses`가 하나라도 있으면 MEDIUM, 없으면 LOW — v1은 HIGH를 절대 반환하지 않는다(Market Agent·Stock Research Agent와 동일 원칙). 최종 confidence는 `min(LLM 제안값, analysis 상한)`이다.
- `recommendations`는 판단 근거가 부족한 종목을 억지로 채우지 않고 빈 리스트/부분 리스트를 정상 출력으로 허용한다.

이를 기반으로 v1은 다음 action을 판단한다(기존 `InvestmentAction` enum 그대로 사용, 신규 enum 값 추가 없음).

- BUY (신규 매수) — 미보유 종목에만 허용
- ADD (비중 확대) — 보유 종목에만 허용
- HOLD (유지) — 보유 종목에만 허용
- REDUCE (비중 축소) — 보유 종목에만 허용
- SELL (매도) — 보유 종목에만 허용
- AVOID (신규 진입 회피) — 미보유 종목에만 허용

단계적 매수/매도, 리밸런싱, 목표가격 기반 대응 등은 별도 enum이 아니라 `rationale`/`conditions` 텍스트로 표현하며, 정확한 수량·금액 산정과 함께 v2 이후 범위다.

주요 출력(모델 변경 없이 기존 `StrategyResult`/`PositionRecommendation`을 그대로 사용):

```text
StrategyResult
├── summary
├── recommendations[]
│   ├── symbol / name
│   ├── action
│   ├── current_weight   # 보유 종목만, 미보유는 null
│   ├── target_weight     # v1은 항상 null
│   ├── rationale
│   └── conditions[]
├── portfolio_risk
├── confidence
└── evidence[]
```

---

## 5. Candidate Discovery — ✅ v1 구현 완료 (Industry + Theme axis, UX-01)

"어떤 종목을 Stock Research Agent의 분석 대상으로 올릴 것인가"만 담당한다. 종목 자체의 매력도(Stock Research Agent)나 사용자별 BUY/AVOID 판단(Portfolio Strategy Agent)에는 관여하지 않는다 — 아래 전체 범위의 Recommendation Engine(scoring/ranking)과는 다른, 더 좁은 v1 기능이다.

Agent가 아니라 Supervisor와 동일한 얇은 2단 구조로 구현했다 — "투자 판단을 내리는 reasoning" 단계가 없기 때문이다(LLM은 자유 텍스트를 구조화하는 역할만 한다).

```text
app/discovery/
├── filter_intent.py   # LLM이 질문 → DiscoveryFilter로 구조화 (closed set 검증 + 재시도)
└── orchestrator.py     # universe/theme catalog 조회, 필터 적용, 후보 과다 시 정책, Candidate[] 조립
```

v1이 실제로 사용하는 데이터:

- Kiwoom `ka10099`(종목정보 리스트) — KOSPI/KOSDAQ 각각 단일 호출로 전체 종목(2026-08 기준 KOSPI 2,481종목)과 함께 종목코드/종목명/시장구분/업종명(`upName`)/규모구분(`upSizeName`)/상장주식수/최근가/감리구분/투자유의여부를 확보한다. ETF/ETN(`mrkt_tp` 8/60 등)은 애초에 조회 대상에 넣지 않아 구조적으로 제외된다.
- Kiwoom `ka90001`(테마그룹별요청)/`ka90002`(테마구성종목요청) — 아래 "Industry vs Theme" 참고.

### Industry vs Theme — 두 개의 서로 다른 classification axis (UX-01)

원래 가설은 "`ka10101`(업종코드 리스트)이 `upName`보다 세분화돼 있을 것"이었으나, **실제 API 호출로 확인한 결과 `ka10101`은 `upName`과 사실상 동일한 굵직한 KRX 대분류(~27~34개)였다** — 삼성전자·SK하이닉스·LG에너지솔루션이 전부 "전기/전자" 하나에 뭉뚱그려진다(2026-08-28 UX-01 조사). 그래서 **Industry axis는 별도 API 연동 없이 기존 `ka10099.upName`을 그대로 재사용**하고, 대신 실제로 세분화된 정보를 제공하는 **Theme axis(`ka90001`/`ka90002`)를 완전히 별도의 새 axis로 추가**했다. 두 axis를 같은 필드에 섞지 않는다 — "전기/전자"(Industry, 84종목)와 "반도체_생산"(Theme, 3종목: 삼성전자/SK하이닉스/DB하이텍)은 granularity가 전혀 다르다.

```text
User
 │
 ▼
LLM Intent Parsing (concept → 실제 카탈로그 값 선택, closed-set)
 │
 ▼
DiscoveryFilter
 ├─ market / size            (기존과 동일)
 ├─ sector_terms             Industry axis — ka10099.upName 재사용
 └─ theme_requests[]         Theme axis — ka90001/ka90002 grounding
      └─ {concept, matched_themes[]}
 │
 ▼
Market ∩ Size ∩ Industry ∩ (Theme A ∪ Theme B ∪ ...) ∩ Ownership
 │
 ▼
Candidates
```

- **`theme_requests`는 "사용자 concept"과 "실제 grounding된 테마명"을 분리해서 담는다**: `ThemeRequest.concept`은 사용자가 언급한 원래 표현("반도체", "원전")을, `matched_themes`는 `ka90001` 실제 카탈로그에 존재하는 값만 담는다(존재하지 않는 이름을 LLM이 지어내면 재시도 → 최종 실패 시 `FilterIntentError`, `sector_terms`/`size_terms`와 동일한 grounding 원칙). LLM이 "원전 → 원자력_기자재/원자력_설계시공"처럼 사용자 표현과 카탈로그 공식 명칭 사이의 동의어 수준 normalization을 제안할 수 있지만, 최종적으로 Python이 실제 카탈로그에 다시 검증한다 — **LLM이 taxonomy의 최종 권한이 아니다.**
- **같은 concept의 여러 테마는 UNION, 서로 다른 axis(market/size/industry/theme/ownership)는 INTERSECTION**이다. 예: "코스피 대형주 중 반도체 관련 종목"은 `KOSPI ∩ 대형주 ∩ (반도체_생산 ∪ 반도체_설계 ∪ ... 8개 세부 테마)` — 실제 E2E로 SK하이닉스/삼성전자/한미반도체 3종목이 정확히 이 교집합으로 나옴을 확인했다.
- **지원하지 않는 concept은 조용히 무시하지 않고 명시적으로 실패시킨다**: "AI"처럼 카탈로그에 대응하는 테마가 전혀 없으면(`matched_themes=[]`) `DiscoveryError`로 실패한다. "AI 반도체 관련주"처럼 concept이 여러 개고 그중 하나만 지원되지 않아도, 지원되는 concept("반도체")만으로 조용히 좁혀서 반환하지 않는다 — 사용자가 요청한 것과 다른 답을 몰래 주지 않기 위함이다.
- **LLM의 "의미상 유사" 판단이 실제로는 과도하게 관대할 수 있음을 실측으로 발견했다**: 초기 프롬프트로는 "AI" concept이 "클라우드 컴퓨팅"/"보안_인터넷"/"SI(시스템통합)" 등 AI가 응용될 뿐인 산업 테마에 잘못 매칭되는 것을 실제 LLM 응답으로 확인했다(테마명 자체는 실제 카탈로그 값이라 구조적 grounding은 통과하지만, 의미상 "AI 자체를 가리키는 테마"가 아니다). 이를 "확신이 서지 않으면 포함하지 말라"는 명시적 지침과 부정 예시로 프롬프트를 강화해 해결했다 — Python 쪽에 하드코딩된 alias table을 추가하는 방식은 쓰지 않았다("근거 없는 semantic synonym expansion을 Python에 hard-code하지 않는다"는 원칙 유지).
- **Theme membership은 사전 구축하지 않고 lazy lookup한다**: 142개 테마 전체의 멤버십을 미리 `ka90002`로 조회하지 않고, 이번 요청에서 실제로 grounding된(=사용자가 요청하고 카탈로그에 실재하는) 테마에 대해서만 조회한다.
- **Theme catalog(`ka90001`)는 `KiwoomService` instance에 24시간 TTL로 캐시한다**(`THEME_CATALOG_CACHE_TTL`). Access token 캐시와 다른 캐시이며, **"테마 분류가 며칠간 금융적으로 유효하다"는 뜻이 아니라 "Kiwoom 외부 메타데이터를 얼마나 자주 다시 조회할 것인가"라는 순수 API refresh 정책일 뿐이다.** UX-04의 Analysis Snapshot Store(API/UI request lifecycle 캐시)와도 목적이 다르다. **24시간이라는 값은 Kiwoom이 실제로 테마 카탈로그를 얼마나 자주 개편하는지 관측한 근거가 아니다** — "종목 편입/편출이 하루 안에 여러 번 바뀌지는 않을 것"이라는 보수적 추정으로 정한 현재의 operational 값이며, 실제 개편 주기가 이후 관측되면(더 자주 바뀌거나 훨씬 드물게 바뀌거나) 그에 맞춰 조정할 수 있는 잠정치다.
- **`Candidate.sector`/`matched_filters: dict[str, str]`는 그대로 유지**했다(backward compatibility). Theme 매칭 evidence는 `matched_filters["theme"]`(실제 매칭된 테마명, 여러 개면 쉼표 구분)과 `matched_filters["theme_concept"]`(그 테마를 요청하게 만든 사용자 concept)로 추가했다 — 새 필드를 만들거나 타입을 느슨하게 넓히지 않았다.
- **sector_terms(Industry) 정책은 UX-01 이전과 완전히 동일하다**: `ka10099`/`ka10101` 모두 세분화되지 않은 대분류이므로, "반도체" 같은 세부 개념은 여전히 sector_terms에서 매칭되지 않는다(대신 theme_requests가 처리한다). "대형 통신 종목 후보 찾아줘"(Industry axis) 결과는 UX-01 전후로 완전히 동일함을 실제 E2E로 재확인했다.
- **후보 과다 시 subset을 고르지 않는 기존 정책은 그대로 유지**한다: `MAX_STOCK_RESEARCH_FANOUT`을 초과하면(Theme union이 넓은 경우도 포함, 예: "반도체"만 단독 요청하면 8개 세부 테마 union이 44종목이 되어 초과) 일부를 임의로 골라내지 않고 Stock Research를 0건 실행한다. Theme 도입을 이유로 momentum/거래량 기반 ranking을 추가하지 않았다.
- **관리종목/투자유의/거래정지는 여전히 filter 조건으로 쓰지 않는다**: `auditInfo`/`orderWarning` 필드는 실제 flagged 값을 관측하지 못해 raw fact로만 전달한다.

**알려진 taxonomy 한계(dev-log UX-05로 별도 기록)**: 실제 API로 확인한 결과 Kiwoom 테마 카탈로그(142개)에는 "AI"/"인공지능"/"데이터센터"/"HBM"/"자율주행" 같은 최근 핵심 투자 테마가 전혀 없고, "2차전지_완제품" 테마에는 LG에너지솔루션이 빠져 있다(SK이노베이션/LG화학/삼성SDI만 존재 — 스핀오프 이전 구조를 반영하는 것으로 보인다). 이런 taxonomy coverage gap은 UX-01에서 보정하지 않는다 — 근거 없이 Python이나 LLM이 빈 자리를 채우면 이 프로젝트가 지켜온 "grounding 없이 생성하지 않는다" 원칙이 깨진다.

Supervisor 연결: 새 intent `candidate_discovery`(후보만 반환) 추가. `portfolio_strategy`는 기존 "특정 종목 우선 → 보유종목 전체" 2단 분기에 "discovery 조건 있으면 그 후보로" 분기를 하나 추가해 확장했다(새 intent 아님, 기존 실행 로직 재사용). 이 연결은 UX-01에서 변경하지 않았다.

주요 출력:

```text
Candidate
├── symbol / name
├── market
├── sector              # Industry axis(ka10099.upName) — 변경 없음
└── matched_filters      # {"sector": "통신", "size": "대형주",
                          #  "theme": "반도체_생산", "theme_concept": "반도체"} — 점수/매력도 없음
```

---

# ⭐ Recommendation Engine

Recommendation Engine은 **신규 투자 후보를 탐색하고 우선순위를 결정하는 역할**을 담당한다.

단순히 상승 가능성이 높은 종목을 나열하는 것이 아니라 다음 정보를 함께 고려한다.

```text
MarketAnalysis
StockAnalysis[]
PortfolioContext
InvestorProfile
        │
        ▼
Recommendation Engine
        │
        ▼
RecommendationResult
```

## Recommendation Principles

추천 결과는 가능한 한 다음 요소를 기반으로 생성한다.

- Fundamental
- Earnings Momentum
- Valuation
- Price Momentum
- 외국인 / 기관 수급
- Catalyst
- Risk
- Portfolio Fit
- Market Regime
- 투자 기간
- 사용자 Risk Tolerance

초기 구현은 설명 가능한 **Rule-based / Quantitative Scoring** 방식으로 시작한다.

```text
Phase 1
Rule-based / Quantitative Scoring

        ↓

Phase 2
Agent-based Qualitative Evaluation

        ↓

Phase 3
Hybrid Recommendation

Quantitative Score
        +
Agent Reasoning
        +
Portfolio Constraints
```

---

## Stock Universe

모든 상장 종목을 무조건 심층 분석하지 않고 먼저 추천 대상 Universe를 정의한다.

예:

```text
KOSPI 200
KOSDAQ 150
시가총액 상위 종목
거래대금 상위 종목
특정 Sector
사용자 Watchlist
```

사용자 요청에 따라 Universe를 동적으로 제한할 수도 있다.

```text
"반도체를 제외하고 추천해줘"

"2차전지 종목 중에서 추천해줘"

"KOSPI 200에서만 찾아줘"

"내 관심종목 중에서 골라줘"
```

---

## Recommendation Scoring

초기 Recommendation Score는 다음 요소를 조합하는 방향으로 설계한다.

```text
Recommendation Score
        │
        ├── Fundamental Score
        ├── Earnings Momentum Score
        ├── Valuation Score
        ├── Price Momentum Score
        ├── Flow Score
        ├── Catalyst Score
        ├── Portfolio Fit Score
        │
        └── Risk Penalty
```

초기 가중치 예시:

```text
Fundamental         25%
Earnings Momentum   20%
Valuation           15%
Flow                15%
Price Momentum      10%
Catalyst            10%
Portfolio Fit        5%

        -

Risk Penalty
```

위 비율은 초기 설계 예시이며 고정된 투자 판단 기준은 아니다.

향후 실제 데이터 및 Backtest 결과를 기반으로 조정할 수 있도록 설계한다.

---

## Portfolio Fit

Recommendation Engine의 중요한 특징은 **개별 종목의 매력도만 평가하지 않는 것**이다.

예를 들어 어떤 반도체 종목의 자체 Score가 높더라도 기존 포트폴리오가 이미 반도체에 과도하게 집중되어 있다면 Portfolio Fit을 낮출 수 있다.

```text
Stock Quality
      +
Market Environment
      +
Current Portfolio
      +
Investor Profile
      │
      ▼
Personalized Recommendation
```

따라서 같은 시장 상황에서도 사용자마다 다른 추천 결과가 나올 수 있다.

---

## Recommendation Models

향후 다음 모델을 추가한다.

```text
RecommendedStock
├── symbol
├── name
├── score
├── recommendation_reason
├── fundamental_score
├── earnings_score
├── valuation_score
├── momentum_score
├── flow_score
├── catalyst_score
├── risk_score
└── portfolio_fit_score
```

최종 Recommendation 결과:

```text
RecommendationResult
├── market_context
├── recommended_stocks[]
├── excluded_stocks[]
├── confidence
└── evidence[]
```

`excluded_stocks[]`에는 점수가 높더라도 Risk, Portfolio Concentration, 사용자 Constraint 등의 이유로 추천 대상에서 제외된 종목을 기록할 수 있다.

즉,

```text
왜 추천했는가?
        +
왜 추천하지 않았는가?
```

모두 추적 가능하도록 설계한다.

---

## Example Recommendation Queries

최종적으로 다음과 같은 요청을 처리하는 것을 목표로 한다.

```text
"지금 신규매수할 종목 5개 추천해줘"

"반도체는 제외하고 추천해줘"

"현재 내 포트폴리오를 고려해서 추천해줘"

"향후 6개월 기준으로 추천해줘"

"중위험 이하 종목만 추천해줘"

"내가 보유하지 않은 종목 중에서 추천해줘"

"현재 시장에서 가장 유리한 섹터와 종목을 추천해줘"
```

---

# 🔄 Agent Data Flow

전체 분석 흐름:

```text
UserRequest
     │
     ▼
Supervisor / Router
     │
     ├──────────────► Market Agent
     │                    │
     │                    ▼
     │              MarketAnalysis
     │
     ├──────────────► Stock Research Agent
     │                    │
     │                    ▼
     │              StockAnalysis[]
     │
     │
     │       PortfolioContext
     │       InvestorProfile
     │              │
     │              ├───────────────────┐
     │              │                   │
     │              ▼                   ▼
     │     Recommendation         Portfolio Strategy
     │         Engine                  Agent
     │              │                   │
     │              ▼                   │
     │     RecommendationResult         │
     │              │                   │
     │              └────────┬──────────┘
     │                       │
     └───────────────────────▼
                       StrategyResult
```

예를 들어:

```text
"지금 내 포트폴리오에서 신규매수할 종목 3개 추천해줘"
```

라는 요청은 향후 다음 경로로 처리한다.

```text
UserRequest
     │
     ▼
Supervisor
     │
     ├── Market Agent
     │      │
     │      ├── MCP Tool Calls
     │      └── MarketAnalysis
     │
     ├── Stock Research Agent
     │      │
     │      ├── OpenDART / Kiwoom Tool Calls
     │      └── StockAnalysis[]
     │
     ├── PortfolioContext
     │
     └── InvestorProfile
                    │
                    ▼
           Recommendation Engine
                    │
                    ▼
          RecommendationResult
                    │
                    ▼
           Portfolio Strategy Agent
                    │
                    ▼
               StrategyResult
```

---

# 🌐 REST API — ✅ v1 구현 완료

기존 `SupervisorOrchestrator`를 외부 client(향후 Web/Flutter 등)에서 호출할 수 있게 하는 **얇은 FastAPI boundary**다. 새로운 투자 판단 로직은 이 레이어에 넣지 않는다 — routing/reasoning/필터링은 전부 이미 존재하는 Core(`SupervisorOrchestrator`)의 책임으로 남긴다.

```text
app/api/
├── main.py           # FastAPI 앱, lifespan(의존성 그래프 1회 생성), 예외 핸들러
├── routes.py         # AnalysisRequest DTO, GET /health, POST /analysis(?view=), GET /analysis/{analysis_id}(?view=)
├── presentation.py   # SupervisorResult → PresentationResult 순수 조립 함수
└── snapshot_store.py # analysis_id → SupervisorResult in-memory TTL store (UX-04)
```

## Endpoint

v1은 분석 생성과 조회를 분리한 **두 endpoint**로 Supervisor의 모든 intent(`market_only`/`stock_research`/`candidate_discovery`/`portfolio_strategy`)를 처리한다. Market/Stock/Portfolio/Discovery별로 endpoint를 나누지 않는다 — Supervisor 자체가 이미 "어떤 종류의 요청인가"를 안전하게 판단하는 역할을 하므로, endpoint를 나누면 client와 Supervisor가 이 판단을 각자 따로 내리게 되어 서로 어긋날 위험이 생긴다.

```text
POST /analysis                          = 새로운 분석 생성 (Supervisor/Agent/LLM/외부 API 실행)
GET  /analysis/{analysis_id}            = 이미 생성된 분석 snapshot 조회 (재실행 없음)
```

```text
HTTP Request
    ↓
AnalysisRequest (API 전용 DTO)
    ↓
UserRequest + investor_profile (분리 유지)
    ↓
SupervisorOrchestrator.run()
    ↓
SupervisorResult
    ↓
JSON Response (별도 response model 없이 그대로 반환)
```

`AnalysisRequest`는 `app/api/routes.py`에만 존재하는 API 전용 DTO다. **Core의 domain model인 `UserRequest`에는 `investor_profile`을 추가하지 않는다** — `SupervisorOrchestrator.run(request, investor_profile=...)`이 이미 이 둘을 의도적으로 분리하고 있으므로, HTTP transport 편의를 위해 그 경계를 허물지 않고 endpoint에서 다시 나눠 넘긴다.

`GET /health`는 외부 API(Kiwoom/OpenAI/ECOS/OpenDART)를 호출하지 않고 프로세스 생존 여부만 확인한다.

## Dependency lifecycle

`lifespan`에서 `KiwoomService`/`EcosService`/`OpenDartService`/`LLMService`와 그 위의 Orchestrator 전체를 **프로세스 생애주기 동안 1회만** 생성해 `app.state.supervisor`에 저장한다(`scripts/supervisor_demo.py`와 동일한 구성). 요청마다 새로 만들지 않아야 `KiwoomService`의 access token instance-level 캐싱이 의미가 있다. `routes.py`의 `get_supervisor(request: Request)`가 이 인스턴스를 꺼내 `Depends()`로 주입한다 — 테스트에서는 `app.dependency_overrides[get_supervisor]`로 fake Supervisor를 주입해 실제 외부 API 없이 검증한다. 별도 dependency injection framework나 `dependencies.py`는 만들지 않았다.

v1은 `--workers 1`(uvicorn 기본값) 전제다 — 멀티 워커는 워커마다 별도 프로세스라 token 캐시가 워커별로 분리되고, 이를 공유하려면 Redis 등이 필요한데 원칙상 미리 넣지 않는다(v2+).

## Error mapping

`RoutingError`/`SupervisorError`/`DiscoveryError`/`FilterIntentError`/`ReasoningError`(Market/Stock Research/Portfolio Strategy — 이름은 같지만 각기 다른 클래스 3개) 전부를 확인해 다음과 같이 매핑했다.

```text
400  SupervisorError, DiscoveryError
     → 클라이언트가 요청을 고치면 해결 가능한 실패
       (investor_profile 누락, 후보 과다, 종목 특정 불가 등)

502  RoutingError, FilterIntentError, ReasoningError(3종)
     → 이 프로젝트에서 502는 단순 "네트워크 게이트웨이 오류"가 아니라
       routing/filter-intent/reasoning 같은 이 프로젝트의 LLM 기반
       dependency를 통해 요청을 정상 완료하지 못한 경우(재시도까지
       실패)를 가리키는 API 정책이다.

500  그 외 모든 미분류 예외
     → 원문(str(exc))을 절대 client에 노출하지 않는다.
```

**미분류 예외를 원문 그대로 노출하지 않는 것이 특히 중요하다.** 실제 코드로 확인한 결과 **ECOS는 API key가 URL 경로 세그먼트에**(`app/services/ecos.py`), **OpenDART는 쿼리 파라미터에**(`app/services/opendart.py`) 그대로 포함된다. `httpx.HTTPStatusError` 등 예외의 기본 `str()`에는 request URL이 포함되므로, 이런 예외를 그대로 client에 전달하면 API key가 유출된다. 서버 로그에는 전체 스택트레이스를 남기고, client에는 고정된 일반 메시지만 반환한다 — 실패를 숨기는 게 아니라(500은 정직하게 알림), 실패의 원문 내용만 감춘다. 실제 `httpx.HTTPStatusError`(URL에 가짜 API key 포함)를 이용한 회귀 테스트로 이 정책을 검증했다.

## Response contract

`SupervisorResult`를 별도 FastAPI response model 없이 그대로 반환한다. 모든 Enum이 `str, Enum`이라 JSON에서 평문 문자열로, `Evidence.timestamp`는 ISO 8601 문자열/`null`로, Optional 필드는 `null`로 직렬화되어 Flutter/Web client가 별도 변환 없이 소비할 수 있다.

## Presentation view — `?view=detail|summary`

`portfolio_strategy` 응답은 보유 종목 수만큼의 `StockAnalysis`(각각 investment_thesis/risks/catalysts/financial_history/evidence를 포함)가 전부 들어가 Swagger에서 사람이 읽기엔 지나치게 길다. 반면 이 상세 데이터는 향후 Web/Flutter의 상세 조회나 machine-readable contract로서 가치가 있어 없애고 싶지는 않았다. 그래서 **기존 `SupervisorResult`는 전혀 바꾸지 않고**, 그 위에 사람이 읽기 쉬운 **읽기 전용 파생 뷰**를 얹었다.

```text
POST /analysis                  (view 생략, 기본값 detail)
POST /analysis?view=detail      → 기존과 완전히 동일한 SupervisorResult 그대로
POST /analysis?view=summary     → PresentationResult(요약)
POST /analysis?view=아무값       → 422 (Literal["detail", "summary"] 자동 검증)
```

`view=both`는 v1에 넣지 않았다 — 원래 문제 자체가 "응답이 너무 길다"인데 summary+detail을 함께 반환하면 그 문제가 그대로 남기 때문이다. 향후 실제 Flutter 사용에서 summary→detail 재요청 latency가 문제가 되면 그때 caching/storage와 함께 both를 재검토한다.

**핵심 설계 원칙**: `PresentationResult`는 `SupervisorResult`의 순수 파생이다.

- `app/api/presentation.py`의 `build_presentation(result: SupervisorResult) -> PresentationResult`는 **LLM이나 어떤 외부 API/Service도 인자로 받지 않는 순수 함수**다 — 함수 시그니처 자체가 새 판단을 만들 수단을 없앤다.
- `MarketAnalysis.summary` / `StrategyResult.summary` / `StockAnalysis.investment_thesis` / `PositionRecommendation.rationale` 등 기존에 이미 grounded된 문자열/구조화 필드를 그대로 옮기거나(pass-through) 개수를 세는 것만 한다. 새 자유생성 LLM synthesis는 v1에서 쓰지 않는다 — 기존 5개 Agent가 지켜온 "grounding 없이 생성하지 않는다" 원칙을 우회하는 새 hallucination 표면을 만들지 않기 위함이다.
- `RecommendationSummary`에는 `target_weight`/`target_price` 같은 "만들면 안 되는" 필드를 아예 선언하지 않는다 — null로 강제하는 기존 패턴보다 한 단계 더 강한 안전장치(실수로도 채울 수 없음)다.

```text
PresentationResult
├── intent
├── headline              # 해당 intent의 기존 summary/thesis pass-through (여러 종목이면 None)
├── market: MarketSummary | None            # regime/risk_level/summary/confidence
├── stocks: list[StockSummary]              # STOCK_RESEARCH/CANDIDATE_DISCOVERY에서만 채움
│   └── symbol/name/price/change_pct/investment_thesis/risks/catalysts/risk_level/confidence
├── discovery: DiscoverySummary | None       # candidate_count + Candidate 그대로(matched_filters 포함)
├── portfolio: PortfolioSummary | None       # portfolio_risk/confidence/summary/recommendation_count
│   └── recommendations: list[RecommendationSummary]
│       └── symbol/name/action/current_weight/rationale/conditions
└── skipped                                  # SupervisorResult.skipped 그대로
```

`portfolio_strategy`의 `PresentationResult.stocks`는 의도적으로 항상 빈 리스트다 — 종목별 상세는 `portfolio.recommendations`(간결한 `RecommendationSummary`)로만 노출하고, raw `StockAnalysis`/`Evidence`/`financial_history`는 `view=detail`에서만 확인하도록 경계를 나눴다. 이렇게 하지 않으면 원래 문제(응답 과다)가 요약 응답에서도 재현된다.

## Analysis Snapshot Lifecycle — `analysis_id` / `X-Analysis-ID` (UX-04)

`view=summary`/`view=detail`을 각각 별도 `POST /analysis`로 요청하면 Supervisor/Agent/LLM pipeline이 매번 독립적으로 재실행된다. LLM reasoning은 비결정적이므로, 같은 질문인데도 두 호출 사이에 market regime이나 portfolio recommendation 개수·action이 달라지는 현상이 실제 E2E에서 관측됐다(상세 관측치는 dev-log `2026-08-28.md` §13.5 참고). UX-04는 **한 번 실행된 `SupervisorResult`에 하나의 `analysis_id`를 부여하고, 이후 summary/detail 조회가 항상 동일 snapshot을 공유하게** 해 이 문제를 해결한다.

```text
POST /analysis
    │
    ▼
Supervisor.run()  →  SupervisorResult
    │                      │
    │                      ├──► AnalysisSnapshotStore.put()  →  analysis_id
    │                      └──► (view에 따라) body 그대로 / build_presentation()
    ▼
Response: body(기존과 동일한 shape) + header X-Analysis-ID: <analysis_id>


GET /analysis/{analysis_id}?view=detail|summary
    │
    ▼
AnalysisSnapshotStore.get(analysis_id)  →  같은 SupervisorResult (Supervisor.run() 재호출 없음)
    │
    ▼
(view에 따라) body 그대로 / build_presentation()
```

핵심 invariant는 `one analysis_id = one SupervisorResult`다. 이를 구조적으로 지키기 위한 설계 결정:

- **`analysis_id`는 Core model에 들어가지 않는다** — `UserRequest`/`SupervisorResult`/`PresentationResult` 어디에도 필드로 추가하지 않았다. `analysis_id`는 투자 분석 domain data가 아니라 API/snapshot lifecycle metadata이고, Supervisor는 snapshot 개념 자체를 모른다. 대신 `POST /analysis` 응답의 `X-Analysis-ID` HTTP header로만 전달한다 — body wrapper를 새로 만들면 기존 client의 backward compatibility가 깨지므로 header를 택했다. `view` 생략(기본값 `detail`) 시 body는 여전히 기존 `SupervisorResult`와 100% 동일하다.
- **`GET /analysis/{analysis_id}`는 조회 전용이다 — refresh/재분석이 아니다.** `Supervisor.run()`/LLM 호출/Kiwoom·OpenDART·ECOS 호출을 절대 하지 않는다. `view=summary`도 저장된 동일 `SupervisorResult`에 이미 순수 함수인 `build_presentation()`(위 Presentation view 참고)을 적용할 뿐이라, summary/detail 사이의 일관성이 구조적으로 보장된다.
- **`AnalysisSnapshotStore`(`app/api/snapshot_store.py`)는 in-memory TTL store다.** DB/Redis/background job은 추가하지 않았다 — 지금 실제로 관측된 문제는 "동일 snapshot을 summary/detail이 공유하지 못한다" 하나뿐이므로, 이를 푸는 최소 구조만 만들었다. `put()`이 `uuid4()` 기반 `analysis_id`를 발급하고, `get()`은 만료 여부를 함께 판정한다. 별도 background cleanup task 없이 `put()`/`get()` 호출 과정에서 만료 항목을 함께 제거하는 lazy cleanup만 둔다.
- **TTL 기본값은 30분이며, 투자 판단의 금융적 유효기간이 아니다.** "30분 후 분석이 틀렸다"는 뜻이 아니라 "30분 이후에는 동일 `analysis_id` 재조회가 보장되지 않는다"는 API navigation/session lifecycle 상의 의미일 뿐이다. `MAX_STOCK_RESEARCH_FANOUT`(discovery)과 동일한 관례로 모듈 상수(`DEFAULT_ANALYSIS_SNAPSHOT_TTL`)로 두었고, config.py나 환경변수로 노출하지 않았다(아직 관측되지 않은 확장 가능성만으로 미리 설정 가능하게 만들지 않는다는 원칙).
- **없거나 만료된 `analysis_id`는 404를 반환한다**(`{"detail": "Analysis snapshot not found or expired."}`). Store가 "과거에 존재했던 id"와 "애초에 존재하지 않았던 id"를 구분해 보관하지 않으므로 410 Gone은 쓰지 않는다 — 이를 정확히 지원하려면 tombstone/history가 필요한데 v1 범위 밖이다.
- **Lock을 예방적으로 추가하지 않았다.** `put()`/`get()`은 `await` 지점이 없는 순수 동기 dict 연산이라 이벤트 루프 안에서 원자적으로 실행된다 — race가 발생할 지점 자체가 없어 `asyncio.Lock`을 넣지 않았다. 이 판단은 현재 `--workers 1` 단일 프로세스 전제에서만 유효하다.
- **Process restart/`--reload`/multi-worker에서는 snapshot이 소멸하거나 조회되지 않는다.** in-memory이므로 프로세스가 재시작되면 모든 snapshot이 사라진다(bug가 아니라 v1의 명시적 제약이며, 분석 history/persistence 기능이 아니다). `--workers 1` 전제도 그대로 유지한다 — 멀티 워커는 워커마다 별도 프로세스라 worker A가 만든 snapshot을 worker B가 조회할 수 없다(Kiwoom access token 캐시와 동일한 성격의 제약). 향후 실제 multi-worker 배포가 필요해지면 `AnalysisSnapshotStore`를 공유 store로 교체할 수 있도록 책임 경계(`get_snapshot_store()` dependency)만 유지했고, 이를 이유로 지금 Redis 등 interface hierarchy를 미리 만들지 않았다.

실제 E2E로 확인한 결과는 dev-log `2026-08-28.md` §16 참고 — POST(수 분 소요, 실제 Supervisor 실행)와 동일 `analysis_id`로의 GET(수 ms, 재실행 없음)의 latency 차이, 그리고 detail/summary 사이의 recommendation 개수·필드 완전 일치를 실측했다.

## 처리 시간 / 아직 넣지 않은 것

전체 포트폴리오 분석처럼 실제로 수 분이 걸릴 수 있는 요청도 v1은 **동기 HTTP request-response**로 그대로 처리한다(client가 넉넉한 timeout을 두는 것을 전제). 아래는 의도적으로 v1에 넣지 않았다(v2+ 후보):

```text
DB, login/auth, history, Redis/Celery, background job, WebSocket,
Service 레이어 httpx client lifecycle 리팩터링, multi-worker 지원
```

---

# 🔌 Service Layer

Service Layer는 외부 API 접근과 응답 정규화를 담당한다.

Service Layer는 투자 판단을 수행하지 않는다.

```text
External API request
        +
HTTP error handling
        +
Response parsing
        +
Validation
        +
Normalization
```

## EcosService

현재 첫 번째 Service인 `EcosService` v1이 구현되어 있다.

```text
ECOS API
   │
   │ raw JSON
   ▼
EcosService
   │
   ├── URL construction
   ├── async HTTP request
   ├── HTTP error handling
   ├── JSON parsing
   ├── response validation
   └── data normalization
   │
   ▼
EcosStatisticPoint[]
```

ECOS의 문자열 기반 수치 데이터는 애플리케이션에서 사용하기 적합한 타입으로 변환한다.

## OpenDartService / KiwoomService

`EcosService`와 동일한 원칙(URL/parameter 구성, HTTP 오류 처리, JSON/XML 파싱, 정규화)으로 구현되어 있다.

```text
OpenDartService
├── corp_code resolution (stock_code → corp_code)
├── 재무제표 조회 (CFS 우선, 없으면 OFS fallback)
└── ZIP/XML corpCode 파싱

KiwoomService
├── OAuth Access Token 발급 + instance-level 캐싱
│   (expires_dt 기반 만료 판정, KST로 명시적 해석, asyncio.Lock으로
│    동시 요청 시 중복 발급 방지)
├── 공통 request() (cont-yn / next-key 연속조회 포함)
├── 주식 기본정보 조회
└── 계좌평가잔고 조회
```

Access Token 캐싱은 `get_access_token(force_refresh=False)`를 통해 제공된다. `KiwoomTools`의 모든 호출부는 매번 새 토큰을 발급받던 기존 `issue_access_token()` 대신 이 메서드를 사용한다 — Supervisor가 보유종목 다수를 동시에 분석할 때 Kiwoom OAuth 서버에서 실제로 `429 Too Many Requests`가 발생한 것을 계기로 추가했다(자세한 내용은 dev-log 16절 참고). `expires_dt`에는 timezone 정보가 없어 KST로 명시적으로 해석하는 정책을 코드 주석에 남겼고, 공식 Kiwoom 명세로 확정되면 재검토가 필요한 가정임을 함께 기록했다.

## LLMService

Stock Research Agent의 LLM 호출만을 담당하는 얇은 Service wrapper다.

```text
LLMService
├── OpenAI Chat Completions API 직접 호출 (httpx, 벤더 SDK 미사용)
├── HTTP error handling
└── 응답 파싱 (content, model, finish_reason)
```

prompt 구성, 재시도 정책, 구조화 검증은 `LLMService`가 아니라 Agent Layer(`reasoning.py`)의 책임이다. `LLMService`는 raw 요청/응답 처리 이상의 판단을 하지 않는다.

---

# 🛠 Domain Tool Layer

Domain Tool은 Service의 저수준 인터페이스를 Agent가 이해하기 쉬운 **의미 기반 기능**으로 변환한다.

현재 구현된 ECOS Domain Tool:

```text
EcosTools
└── get_base_rate(
        start_date,
        end_date
    )
```

내부적으로는:

```text
get_base_rate()
      ↓
EcosService.get_statistic()
```

을 호출한다.

Agent는 다음 ECOS-specific code를 알 필요가 없다.

```text
722Y001
0101000
```

이러한 API-specific detail은 Domain Tool / Service 계층에서 관리한다.

같은 원칙으로 `OpenDartTools`(`get_company_financials`, `get_key_financials`)와 `KiwoomTools`(`get_stock_info`, `get_account_balance`)도 구현되어 있다.

---

# 🔗 MCP Layer

MCP Layer는 Domain 기능을 표준 MCP Tool로 노출한다.

현재 MCP Server:

```text
app/mcp/server.py
```

현재 노출된 MCP Tool:

```text
personal-investment-agent
├── get_base_rate
├── get_exchange_rate
├── get_kospi_index
├── get_kosdaq_index
├── get_company_financials
├── get_key_financials
├── get_stock_info
├── get_account_balance
└── get_portfolio_context
```

MCP Client에서는 다음 작업을 수행할 수 있다.

```text
Tool Discovery
      │
      │ list_tools()
      ▼
9개 Tool 발견

      ↓

Tool Invocation
      │
      │ call_tool()
      ▼
Tool 실행
```

현재 `tests/test_mcp_server.py`에서 실제 MCP Client를 사용하여 9개 Tool 모두 실제 외부 API까지 end-to-end로 검증한다.

Stock Research Agent v1과 Market Agent v1 모두 이 MCP Client 경로를 사용하지 않고 Domain Tool을 직접 호출한다(자세한 내용은 위 "MCP Client / Server Relationship" 참고). 향후 프로세스 경계를 넘는 외부 Agent Runtime이나 다른 클라이언트가 이 MCP Client 역할을 담당할 수 있다.

---

# 📊 Data Sources

초기 단계에서는 다음 API를 사용한다.

| Data Source | Purpose | Status |
| --- | --- | --- |
| 한국은행 ECOS API | 기준금리 / USD-KRW 환율 / KOSPI·KOSDAQ 지수 | **Service + Tool + MCP Integrated** |
| OpenDART API | 기업 공시 / 재무 데이터 | **Service + Tool + MCP Integrated** |
| Kiwoom REST API | 계좌 / 주가 / 거래 / 수급 데이터 | **Service + Tool + MCP Integrated** |
| OpenAI API | Stock Research Agent / Market Agent LLM reasoning | **Service Integrated (LLMService, Agent 전용, MCP 미노출)** |
| KIS Developers API (한국투자증권) | Broker Investment Opinion / Target Price(`invest-opinion`/`invest-opbysec`) — v1 후보로 실측 검증 완료. `estimate-perform`(Forward Revenue/OpProfit/NetIncome/EPS/PER/PBR/ROE 추정치)은 실제 호출·값 확인은 했으나 row semantics 미문서화 + 종목별 reliability 불일치로 v1 제외 | **라이브 검증 완료, production 미통합** — OAuth 인증 성공, 3개 TR 전부 실측(RE-03.2/RE-03.3), Forward Feature Verification Matrix 확정 |

향후 필요에 따라 추가할 수 있다.

- 시장 뉴스
- 증권사 리포트
- 산업 자료
- 해외 시장 데이터
- 추가 경제 지표
- 기업 IR 자료

**RE-03(Forward-Looking Data Source Investigation)에서 조사했으나 채택하지 않은 소스** (근거는 dev-log §20 참고, 코드 미반영):

- KRX MDC(`data.krx.co.kr`) 비공식 내부 엔드포인트 — historical PER/PBR/EPS/BPS 시계열이 실제로 존재함을 확인했으나(pykrx 오픈소스로 구조 확인), 세션 쿠키/Referer 스푸핑이 필요한 비공식 채널이라 "기술적으로 가능하나 프로덕션 권장 = NO"로 분류(Tier C). 정식 등록형 `openapi.krx.co.kr`이 동일 데이터셋을 제공하는지는 미확인(open question).
- NAVER Finance 직접 접근 — 비공식 접근 + FnGuide 2차 데이터 재배포 리스크로 Reject.
- FnGuide DataGuide — 데이터 자체는 유효하나 유료 B2B 연간 계약(개인/무료 tier 없음)이라 Tier B(비용상 부적합).

---

# 🧠 Design Principles

## Evidence Based

가능한 모든 투자 판단에 데이터와 분석 근거를 제공한다.

## Traceable

최종 전략 및 종목 추천이 **어떤 데이터와 어떤 분석 결과에서 만들어졌는지 추적 가능**하도록 설계한다.

```text
Evidence
├── source
├── description
├── reference
└── timestamp
```

## Personalized

일반적인 투자 의견이 아니라 사용자의 실제 포트폴리오, 투자 목표 및 기존 전략을 반영한다.

## Explainable Recommendation

단순 추천 Score만 제공하지 않는다.

```text
추천 종목
    +
추천 이유
    +
주요 Risk
    +
Portfolio Fit
    +
제외 종목 및 제외 이유
```

를 가능한 한 함께 제공한다.

## Consistent

동일한 상황에서 판단 기준이 임의로 변경되지 않도록 명시적인 데이터 모델과 판단 기준을 사용한다.

## Risk Aware

상승 가능성뿐만 아니라 하락 위험과 포트폴리오 전체 Risk를 함께 고려한다.

## Layered

```text
Agent
  ↓
MCP
  ↓
Domain Tool
  ↓
Service
  ↓
External API
```

외부 데이터 접근과 투자 reasoning의 책임을 분리한다.

## API Abstraction

Agent가 특정 외부 API의 구현 세부사항에 의존하지 않도록 한다.

```text
Bad

Agent
 ↓
ECOS statistic_code 직접 사용
 ↓
ECOS API


Preferred

Agent
 ↓
get_base_rate
 ↓
EcosTools
 ↓
EcosService
 ↓
ECOS API
```

## Human-in-the-Loop

시스템의 목적은 완전 자동매매가 아니다.

최종 투자 판단과 주문 실행은 사용자가 결정하며 시스템은 **투자 의사결정을 지원하는 역할**을 한다.

---

# 🗂 Project Structure

현재 구현된 파일과 향후 계획된 구조를 구분한다.

```text
personal-investment-agent/
│
├── app/
│   ├── api/                         # REST API v1 — 구현 완료
│   │   ├── main.py                 # FastAPI 앱, lifespan, 예외 핸들러
│   │   ├── routes.py                # AnalysisRequest DTO, GET /health, POST /analysis, GET /analysis/{analysis_id}
│   │   ├── presentation.py          # SupervisorResult → PresentationResult 순수 조립 함수
│   │   └── snapshot_store.py        # analysis_id → SupervisorResult in-memory TTL store (UX-04)
│   │
│   ├── agents/                     # AI Agent Layer
│   │   ├── market/                 # Market Agent — v1 구현 완료
│   │   │   ├── analysis.py         # Deterministic 분석 (raw facts, 20/60일 변화율, confidence 상한)
│   │   │   ├── reasoning.py        # LLM reasoning (fact-id grounding 검증 포함)
│   │   │   └── orchestrator.py     # MarketAnalysis 조립
│   │   ├── stock_research/         # Stock Research Agent — v1 구현 완료
│   │   │   ├── analysis.py         # Deterministic 분석 (facts, confidence 상한, risk_level)
│   │   │   ├── reasoning.py        # LLM reasoning
│   │   │   └── orchestrator.py     # StockAnalysis 조립
│   │   └── portfolio/              # Portfolio Strategy Agent — v1 구현 완료
│   │       ├── analysis.py         # Deterministic 분석 (portfolio/market/종목 fact, allowed_actions)
│   │       ├── reasoning.py        # LLM reasoning (symbol/fact-id/action 3중 grounding)
│   │       └── orchestrator.py     # StrategyResult 조립 (target_weight=None 강제)
│   │
│   ├── supervisor/                 # Supervisor / Router — v1 구현 완료
│   │   ├── routing.py              # LLM intent 분류 (closed enum 검증 + 재시도)
│   │   └── orchestrator.py         # intent별 실행, 부분 실패 처리, SupervisorResult 조립
│   │
│   ├── discovery/                  # Candidate Discovery — v1 구현 완료 (Industry + Theme axis, UX-01)
│   │   ├── filter_intent.py        # LLM → DiscoveryFilter (sector/size/theme_requests closed set 검증 + 재시도)
│   │   └── orchestrator.py         # universe/theme catalog 조회, union/intersection 적용, 후보 과다 정책
│   │
│   ├── recommendation/             # Recommendation Engine (planned)
│   │   └── engine.py               # Recommendation logic (planned)
│   │
│   ├── mcp/
│   │   ├── ecos_tools.py           # ECOS Domain Tools (기준금리/환율/KOSPI/KOSDAQ)
│   │   ├── opendart_tools.py       # OpenDART Domain Tools (find_stock_code_by_name 포함)
│   │   ├── kiwoom_tools.py         # Kiwoom Domain Tools (get_kospi/kosdaq_stock_list, get_theme_groups/get_theme_stocks 포함)
│   │   └── server.py               # MCP Server / Tool exposure
│   │
│   ├── services/
│   │   ├── ecos.py                 # ECOS Service
│   │   ├── opendart.py             # OpenDART Service
│   │   ├── kiwoom.py               # Kiwoom Service (get_stock_list/ka10099, get_theme_groups/get_theme_stocks(ka90001/ka90002, 24h TTL 캐시) 포함)
│   │   ├── portfolio_adapter.py    # Kiwoom → PortfolioContext 변환
│   │   └── llm.py                  # LLM Service (Stock Research / Market / Portfolio Strategy Agent 전용)
│   │
│   ├── models/
│   │   ├── common.py
│   │   ├── market.py
│   │   ├── stock.py
│   │   ├── portfolio.py
│   │   ├── strategy.py
│   │   ├── supervisor.py           # Intent, SupervisorResult
│   │   └── discovery.py            # MarketFilter, Candidate
│   │
│   ├── config.py
│   ├── main.py
│   └── __init__.py
│
├── tests/
│   ├── test_models.py
│   ├── test_ecos_service.py / test_ecos_tools.py
│   ├── test_opendart_service.py / test_opendart_tools.py
│   ├── test_kiwoom_service.py / test_kiwoom_tools.py
│   ├── test_portfolio_adapter.py
│   ├── test_llm_service.py
│   ├── test_market_analysis.py
│   ├── test_market_reasoning.py
│   ├── test_market_orchestrator.py
│   ├── test_stock_research_analysis.py
│   ├── test_stock_research_reasoning.py
│   ├── test_stock_research_orchestrator.py
│   ├── test_portfolio_analysis.py
│   ├── test_portfolio_reasoning.py
│   ├── test_portfolio_orchestrator.py
│   ├── test_supervisor_routing.py
│   ├── test_supervisor_orchestrator.py
│   ├── test_discovery_filter_intent.py
│   ├── test_discovery_orchestrator.py
│   ├── test_api.py
│   ├── test_snapshot_store.py
│   └── test_mcp_server.py
│
├── scripts/
│   ├── demo.py
│   ├── kiwoom_stock_info_demo.py
│   ├── stock_research_demo.py      # Stock Research Agent v1 실제 E2E 데모
│   ├── market_agent_demo.py        # Market Agent v1 실제 E2E 데모
│   ├── portfolio_strategy_demo.py  # Portfolio Strategy Agent v1 실제 E2E 데모
│   └── supervisor_demo.py          # Supervisor v1 실제 E2E 데모 (6개 시나리오, discovery 포함)
├── docs/
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

> `app/recommendation/`과 관련 모델은 프로젝트의 공식 설계에 포함되었지만 아직 구현되지 않았다.

---

# ⚙️ Development Environment

현재 개발 환경:

```text
OS       : Windows 10 + WSL2 Ubuntu
Editor   : VS Code + WSL
Python   : >= 3.12
Package  : pip / pyproject.toml
HTTP     : httpx
MCP      : MCP Python SDK
Model    : Pydantic
Test     : pytest
Lint     : Ruff
```

프로젝트는 WSL2 Ubuntu filesystem에서 관리한다.

```text
~/project/personal-investment-agent
```

VS Code에서:

```bash
cd ~/project/personal-investment-agent
code .
```

가상환경:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Dependency 설치:

```bash
pip install -e ".[dev]"
```

---

# 📦 Dependencies

현재 주요 Python dependency:

```text
httpx
mcp
pydantic
pydantic-settings
fastapi
uvicorn

Development:
pytest
ruff
```

- `httpx`: 외부 REST API async HTTP client
- `mcp`: Model Context Protocol Server / Client
- `pydantic`: 구조화된 Data Model 및 validation
- `pydantic-settings`: 환경변수 및 API Key 관리
- `fastapi`: REST API v1 (`app/api/`)
- `uvicorn`: FastAPI용 ASGI 서버(`mcp[cli]`의 transitive dependency로 이미 설치되어 있었으나 REST API v1부터 직접 의존성으로 명시)
- `pytest`: automated testing
- `ruff`: lint 및 code quality 검사

---

# 🔐 Environment Configuration

실제 API Key와 계좌 관련 민감정보는 Git Repository에 저장하지 않는다.

`.env.example`:

```text
OPENAI_API_KEY=
KIWOOM_APP_KEY=
KIWOOM_SECRET_KEY=
ECOS_API_KEY=
OPENDART_API_KEY=
```

각 사용자는 프로젝트 root에 `.env` 파일을 생성하고 자신의 API Key를 설정한다.

```text
.env             # 실제 API Key / Git 제외
.env.example     # 환경변수 Template / Git 포함
```

설정 구조:

```text
.env
 │
 ▼
app/config.py
 │
 ▼
Settings
 │
 ├── openai_api_key
 ├── kiwoom_app_key
 ├── kiwoom_secret_key
 ├── ecos_api_key
 └── opendart_api_key
```

---

# 🚀 Setup

Repository clone:

```bash
git clone https://github.com/leejja/personal-investment-agent.git
cd personal-investment-agent
```

가상환경 생성:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Dependency 설치:

```bash
pip install -e ".[dev]"
```

환경변수 설정:

```bash
cp .env.example .env
```

설정 로딩 확인:

```bash
python - <<'PY'
from app.config import settings

print("OPENAI:", bool(settings.openai_api_key))
print("KIWOOM APP:", bool(settings.kiwoom_app_key))
print("KIWOOM SECRET:", bool(settings.kiwoom_secret_key))
print("ECOS:", bool(settings.ecos_api_key))
print("OPENDART:", bool(settings.opendart_api_key))
PY
```

테스트:

```bash
pytest
```

Lint:

```bash
ruff check .
```

REST API v1 로컬 실행(WSL):

```bash
uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

`--reload`는 개발 중 코드 수정 시 자동 재시작(운영 시에는 뺀다). `--host 127.0.0.1`(기본값)로 로컬 머신 밖에서 접근할 수 없게 하는 것이 v1의 실질적인 보안 경계다 — 아직 인증 시스템은 없다.

브라우저에서 바로 써보기 — FastAPI가 자동으로 만들어주는 API 문서 UI로 요청을 직접 날려볼 수 있다:

```text
http://127.0.0.1:8000/docs
```

`POST /analysis`를 펼쳐 "Try it out" → question 입력 → "Execute"만 누르면 된다(WSL이면 Windows 브라우저에서 `localhost:8000/docs`로 접속).

curl로 각 intent 확인:

```bash
# health check (외부 API 미호출)
curl http://127.0.0.1:8000/health

# 시장 상황 (market_only)
curl -X POST http://127.0.0.1:8000/analysis \
  -H "Content-Type: application/json" \
  -d '{"question": "요즘 시장 상황 어때?"}'

# 특정 종목 (stock_research)
curl -X POST http://127.0.0.1:8000/analysis \
  -H "Content-Type: application/json" \
  -d '{"question": "삼성전자 어때?"}'

# 조건 기반 후보 탐색 (candidate_discovery)
curl -X POST http://127.0.0.1:8000/analysis \
  -H "Content-Type: application/json" \
  -d '{"question": "대형 통신 종목 후보 찾아줘"}'

# 개인화 판단 (portfolio_strategy) — investor_profile 필요
curl -X POST http://127.0.0.1:8000/analysis \
  -H "Content-Type: application/json" \
  -d '{
    "question": "내 포트폴리오 분석해줘",
    "investor_profile": {"risk_tolerance": "medium"}
  }'

# 사람이 읽기 쉬운 요약(portfolio_strategy처럼 응답이 긴 경우 특히 유용)
curl -X POST "http://127.0.0.1:8000/analysis?view=summary" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "내 포트폴리오 분석해줘",
    "investor_profile": {"risk_tolerance": "medium"}
  }'

# analysis_id로 동일 snapshot 재조회 (Supervisor 재실행 없음, 응답 header의
# X-Analysis-ID 값을 사용 — 아래는 예시 id)
curl -i http://127.0.0.1:8000/analysis/3f5d41c6-40c7-4b7d-8c36-716aa25d8703?view=detail
curl -i http://127.0.0.1:8000/analysis/3f5d41c6-40c7-4b7d-8c36-716aa25d8703?view=summary
```

`question`은 자연어 그대로 넣으면 되고, 어떤 intent로 처리할지는 Supervisor가 내부에서 알아서 분류한다(endpoint를 따로 고를 필요 없음). `portfolio_strategy`처럼 보유종목 전체를 분석하는 요청은 실제로 몇 분 걸릴 수 있다 — v1은 synchronous라 client가 넉넉한 timeout을 두는 것을 전제로 한다(자세한 내용은 위 REST API 섹션의 "처리 시간" 참고).

`?view=summary`를 붙이면 같은 요청을 동일하게 한 번만 처리하되, 응답을 사람이 읽기 쉬운 `PresentationResult`(위 REST API 섹션의 "Presentation view" 참고)로 받는다. `view`를 생략하면(또는 `view=detail`) 기존과 완전히 동일한 상세 응답을 받는다.

모든 `POST /analysis` 응답은 `X-Analysis-ID` header를 포함한다. 이 id로 `GET /analysis/{analysis_id}`를 호출하면 Supervisor를 다시 실행하지 않고 같은 `SupervisorResult` snapshot을 detail/summary 어느 쪽으로도 재조회할 수 있다(기본 TTL 30분, 자세한 내용은 위 REST API 섹션의 "Analysis Snapshot Lifecycle" 참고). `GET`은 조회 전용이며 새로운 분석이 필요하면 다시 `POST`해야 한다.

---

# 🧪 Testing

현재 Model Layer, ECOS / OpenDART / Kiwoom integration, LLMService, Stock Research Agent v1, Market Agent v1, Portfolio Strategy Agent v1, Supervisor / Router v1, Candidate Discovery v1, REST API v1 전체 경로에 대한 테스트를 구현했다.

```text
tests/
├── test_models.py
├── test_ecos_service.py / test_ecos_tools.py
├── test_opendart_service.py / test_opendart_tools.py
├── test_kiwoom_service.py / test_kiwoom_tools.py
├── test_portfolio_adapter.py
├── test_llm_service.py
├── test_market_analysis.py
├── test_market_reasoning.py
├── test_market_orchestrator.py
├── test_stock_research_analysis.py
├── test_stock_research_reasoning.py
├── test_stock_research_orchestrator.py
├── test_portfolio_analysis.py
├── test_portfolio_reasoning.py
├── test_portfolio_orchestrator.py
├── test_supervisor_routing.py
├── test_supervisor_orchestrator.py
├── test_discovery_filter_intent.py
├── test_discovery_orchestrator.py
├── test_api.py
├── test_snapshot_store.py
└── test_mcp_server.py
```

## Model Tests

```text
Valid Input
├── UserRequest
├── MarketAnalysis
├── StockScenario
├── StockPriceSnapshot / FinancialSnapshot
├── PortfolioPosition
├── InvestorProfile
└── StrategyResult

Invalid Input
├── empty question
├── probability > 1
├── portfolio weight > 1
└── negative quantity
```

## Service / Domain Tool Tests

ECOS, OpenDART, Kiwoom 각 Service/Domain Tool을 `httpx.MockTransport` 또는 `AsyncMock` 기반으로 검증한다(URL/parameter 구성, HTTP 오류 처리, 응답 정규화, Kiwoom continuation 처리 등). 일부는 실제 외부 API를 호출하는 real-path 테스트(`test_real_*`)도 함께 포함한다. `test_kiwoom_service.py`는 [UX-01]에서 `ka90001`/`ka90002`(테마 카탈로그/멤버십) 파싱·continuation과, `KiwoomService` instance-level 테마 카탈로그 캐시(hit/TTL 만료/force_refresh/인스턴스 독립성)도 access token 캐시와 동일한 "이미 만료된 값을 미리 채워 검증" 관례로 검증한다(clock monkeypatch 없이).

## LLMService Tests

OpenAI Chat Completions 호출을 `httpx.MockTransport`로 mock하여 검증한다. 실제 OpenAI API는 호출하지 않는다.

## Market Agent Tests

```text
test_market_analysis.py
├── 기준금리 변경 방향/변경폭(bp) — 달력일 기준 lookback
├── USD/KRW·KOSPI·KOSDAQ 20/60거래일 변화율 — 리스트 위치 기준 lookback
├── lookback 데이터 부족 시 change fact 조용히 생략
├── confidence 상한 (핵심 지표 3종 20일 변화율 완전 → MEDIUM, 불완전 → LOW)
├── raw fact에 평가어("높다/낮다/양호/부진/고평가/저평가/긴축적/완화적") 없음
└── fact id 중복 없음

test_market_reasoning.py
├── LLM 응답 구조화 검증 + 최소 재시도 (mock, 실제 OpenAI 미호출)
├── regime_fact_ids / risk_fact_ids가 비어 있으면 검증 실패 → 재시도 → 최종 실패 시 ReasoningError
├── 존재하지 않는 fact id가 하나라도 섞이면 검증 실패(일부 valid만 남겨 통과시키지 않음)
└── 재시도에서 grounding을 충족하면 정상 복구

test_market_orchestrator.py
├── EcosTools / LLMService 전부 mock 주입
├── as_of_date → start_date(LOOKBACK_DAYS=100) 계산 및 4개 tool 호출 검증
├── confidence = min(LLM 제안값, analysis 상한)
├── evidence는 deterministic facts + 실제 tool 호출 출처로만 구성
└── ReasoningError(구조화 실패 및 grounding 실패 포함) 발생 시 fallback 없이 예외 전파
```

## Stock Research Agent Tests

```text
test_stock_research_analysis.py
├── StockPriceSnapshot / FinancialSnapshot 매핑 손실 없음
├── deterministic facts (250거래일 가격 위치, 부채비율, raw 수치 10종)
├── confidence 상한 (핵심 재무 완전 → MEDIUM, 불완전 → LOW, HIGH 없음)
├── risk_level 고정 (v1은 항상 MEDIUM)
├── financial_history: 2개 연도 미만이면 빈 리스트, 3개 연도면 오래된 순으로 정렬
├── financial_history 스냅샷은 PER/PBR/ROE를 절대 생성하지 않음
├── YoY: 정상 흑자 구간 백분율, 전년 0이면 생략, 흑자↔적자 전환은 "전환" 문구, 둘 다 적자면 "규모 확대/축소" 문구(백분율 왜곡 없음)
├── 연도별 영업이익률/순이익률/부채비율 fact
├── "최근 3개 연도 연속 상승/하락"은 3개년이 모두 있고 단조로울 때만 생성
├── [RE-01] financial_features.annual: financial_history 없이 당기 1건만으로도 생성됨(독립 gate)
├── [RE-01] annual 항목은 값이 전부 None이어도 business_year와 함께 생성됨(missing != 항목 생략)
├── [RE-01] annual이 financial_history와 동일한 오래된→최신 순서/길이
├── [RE-01] yoy: 정상 growth_pct, loss_to_profit/profit_to_loss/loss_widening/loss_narrowing/loss_unchanged 5종 transition
├── [RE-01] yoy: previous==0 또는 값 결측이면 entry 자체가 생성되지 않음, growth_pct/transition 상호배타
└── [RE-01] trends: 단조 상승/하락만 entry 생성, 비단조·3개년 미만·결측 포함 시 entry 없음

test_stock_research_reasoning.py
├── LLM 응답 구조화 검증 + 최소 재시도 (mock, 실제 OpenAI 미호출)
├── target_price / probability는 항상 null로 강제
├── scenarios=[] 정상 허용
├── catalyst 엄격 정의(정적 규모 재진술·과거 추세 개선 자체는 catalyst 아님) 프롬프트 반영
├── catalysts / risks 빈 리스트 허용
├── 다년 재무 추세가 있으면 프롬프트 user message에 오래된 연도 → 최신 연도 순으로 포함, 없으면 섹션 자체 생략
├── risks 정책이 절대 금지가 아니라 완화된 형태(단일 시점 수치 단정 금지 + 다년 추세는 더 강한 근거)로 반영됨
└── "과거 추세로 미래 실적/주가 단정 금지" 프롬프트 반영

test_stock_research_orchestrator.py
├── KiwoomTools / OpenDartTools / LLMService 전부 mock/fake 주입
├── confidence = min(LLM 제안값, analysis 상한)
├── risk_level은 analysis 결과만 사용 (LLM이 변경 불가)
├── evidence는 deterministic facts + 실제 tool 호출 출처로만 구성(get_key_financials_history)
├── financial_history가 StockAnalysis에 오래된 순으로 그대로 반영됨
├── history가 1건(당기만)이면 StockAnalysis.financial_history는 빈 리스트
├── ReasoningError 발생 시 fallback 없이 예외 전파
├── [RE-01] financial_features가 StockAnalysis에 재계산 없이 그대로 연결됨(annual/yoy/trends)
└── [RE-01] financial_history가 비어도(history 1건) financial_features.annual은 1건 채워짐

test_opendart_service.py (추가분)
├── bfefrmtrm_* 필드가 있으면 before_previous_term_* 로 정상 파싱
└── bfefrmtrm_* 필드가 응답에 없으면(분기/반기 보고서 등) None으로 안전 처리

test_opendart_tools.py (추가분)
├── _year_label_for_term: business_year 기준 -1/-2년 계산
├── get_key_financials_history: 사업보고서(11011)는 3개 연도, 그 외 보고서는 당기 1건만
├── OpenDART API는 회사당 1회만 호출됨(추가 API 호출 없음)
├── 전전기 데이터가 전혀 없으면 해당 연도는 결과에서 생략
└── 당기는 값이 전부 비어 있어도 항상 포함(get_key_financials()와 동일 보장)
```

## Portfolio Strategy Agent Tests

```text
test_portfolio_analysis.py
├── 보유 종목 → current_weight + held actions(ADD/HOLD/REDUCE/SELL)
├── 미보유 종목 → current_weight=None + unheld actions(BUY/AVOID)
├── portfolio-level fact (현금 비중, 주식 노출 비중, top1/top3 집중도)
├── total_value=0일 때 현금/노출 비중 fact 생략
├── InvestorProfile 선택 필드(horizon/objectives/constraints) 존재할 때만 fact 포함
├── 종목별 fact(risk_level/confidence/현재 비중/평가손익률, 미보유는 not_held)
├── raw fact에 평가어 없음
├── max_confidence: stock_analyses 있으면 MEDIUM, 없으면 LOW, 개별 StockAnalysis가 HIGH여도 상한 불변
└── fact id 중복 없음

test_portfolio_reasoning.py
├── LLM 응답 구조화 검증 + 최소 재시도 (mock, 실제 OpenAI 미호출)
├── recommendations 빈 배열 정상 허용
├── portfolio_risk_fact_ids 비어 있거나 존재하지 않는 id 포함 시 검증 실패 → 재시도 → 최종 실패 시 ReasoningError
├── recommendation의 symbol이 판단 대상 종목 목록에 없으면 검증 실패(새 종목 지어내기 차단)
├── recommendation의 fact_ids가 비어 있거나 존재하지 않는 id를 포함하면 검증 실패(일부 valid만 남겨 통과시키지 않음)
├── 보유 종목에 BUY/AVOID, 미보유 종목에 SELL/REDUCE/ADD/HOLD를 제안하면 검증 실패(action-보유여부 구조적 검증)
├── 미보유 종목에 BUY는 정상 허용
└── 재시도에서 세 검증(symbol/fact-id/action)을 모두 충족하면 정상 복구

test_portfolio_orchestrator.py
├── LLMService만 mock 주입 (Domain Tool 호출 없음)
├── recommendation 조립 (symbol/name/action/current_weight)
├── target_weight는 LLM이 값을 끼워 넣어도 항상 None으로 강제
├── confidence = min(LLM 제안값, analysis 상한), v1은 HIGH를 절대 반환하지 않음
├── evidence는 deterministic facts(PortfolioContext/MarketAnalysis/StockAnalysis/InvestorProfile 출처)로만 구성
├── ReasoningError(구조화 실패 및 3중 grounding 실패 포함) 발생 시 fallback 없이 예외 전파
└── 보유 종목에 BUY 같은 허용되지 않은 action은 재시도 루프 안에서 걸러지고 최종 ReasoningError로 전파
```

## Supervisor / Router Tests

```text
test_supervisor_routing.py
├── LLM intent 분류(market_only/stock_research/portfolio_strategy) + mentioned_stock_terms 전달 (mock, 실제 OpenAI 미호출)
├── 구조화 실패 시 재시도
├── closed enum에 없는 intent 값도 ValidationError로 걸려 재시도됨
└── 최종 실패 시 RoutingError

test_supervisor_orchestrator.py
├── 네 Agent/Discovery orchestrator + KiwoomTools/OpenDartTools 전부 fake 주입
├── market_only: Market Agent 실행, 실패 시 그대로 전파
├── stock_research: UserRequest.symbols 우선 신뢰, 없으면 회사명 조회로 해석, 실패 시 SupervisorError/전파
├── candidate_discovery: 찾은 후보로 Stock Research 실행, 조건 없으면 SupervisorError, DiscoveryError 시 Stock Research 0건
├── portfolio_strategy(explicit symbol 없음, discovery 조건도 없음): 보유종목 전체만 Stock Research 실행
├── portfolio_strategy(explicit symbol 있음): 그 종목만 실행(보유종목 20개가 있어도 재실행 안 함) — PortfolioContext는 전체 유지
├── portfolio_strategy(discovery 조건 있음): discovery 후보로 fan-out(개별 실패 skip 허용), DiscoveryError는 held-symbols로 폴백하지 않고 전체 요청 실패
├── explicit symbol의 Stock Research 실패 → 전체 요청 실패(필수 dependency)
├── 보유종목 fan-out 개별 실패 → skip하고 나머지로 계속 진행
├── Market Agent 실패(root) → 전체 요청 실패
├── Portfolio Strategy reasoning 실패(sink, ReasoningError) → market_analysis/stock_analyses/portfolio_context는 그대로 반환하는 부분 결과
└── investor_profile 없이 portfolio_strategy 요청 시 SupervisorError
```

## Candidate Discovery Tests

```text
test_discovery_filter_intent.py
├── LLM 응답 구조화 검증 + 최소 재시도 (mock, 실제 OpenAI 미호출)
├── 빈 필터(모든 필드 기본값) 정상 허용 — fact-id grounding과 달리 "언급 없음"은 유효한 응답
├── market은 closed enum이라 알 수 없는 값이면 ValidationError로 재시도
├── sector_terms/size_terms가 실제 관측된 집합(known_sectors/known_sizes) 밖이면 검증 실패 → 재시도 → 최종 실패 시 FilterIntentError
│  (일부만 유효해도 전체 실패 처리, 부분 valid만 남기지 않음)
├── exclude_owned은 LLM이 문장에서 판단한 값을 그대로 신뢰(구조 검증 대상 아님, 의미 판단은 프롬프트 책임)
├── [UX-01] theme_requests: "반도체" 같은 concept이 실제 카탈로그의 여러 세부 테마로 grounding됨
├── [UX-01] "원전" → "원자력_*" 같은 colloquial 표현의 정상화(normalization) 후 실제 카탈로그 값으로 grounding됨
├── [UX-01] concept은 있으나 matched_themes가 빈 배열인 것은 정상(grounding 성공) — 실패로 취급하지 않음
├── [UX-01] 카탈로그에 없는 테마명(hallucination)은 검증 실패 → 재시도 → 최종 실패 시 FilterIntentError
├── [UX-01] "AI 반도체"처럼 concept 2개가 동시에 오면 독립적으로 각각 유지(하나를 조용히 누락시키지 않음)
└── [UX-01] known_themes 인자를 생략해도(기존 호출부) 기존과 동일하게 동작

test_discovery_orchestrator.py
├── KiwoomTools fake로 KOSPI/KOSDAQ universe 주입
├── 조건 없음(모든 필드 기본값) → None 반환
├── market/sector/size 필터 적용, matched_filters에 매칭 근거 기록
├── exclude_owned=True/False에 따라 보유종목 제외 여부가 실제로 달라짐
├── 후보가 MAX_STOCK_RESEARCH_FANOUT 초과 시 DiscoveryError, 이하면 일부를 고르지 않고 전체 통과
├── symbol/name이 비어있는 항목은 제외
├── [UX-01] theme catalog가 존재해도 sector-only 요청은 기존과 동일하게 동작(회귀 없음), ka90002 미호출
├── [UX-01] 같은 concept의 서로 다른 테마 멤버십은 UNION됨
├── [UX-01] Market ∩ Size ∩ Theme 교집합이 실제로 적용됨
├── [UX-01] 지원하지 않는 theme concept(matched_themes=[])은 DiscoveryError로 명시적 실패, ka90002 미호출
├── [UX-01] concept 여러 개 중 하나만 unsupported여도 전체 실패(나머지 concept만으로 조용히 좁히지 않음)
├── [UX-01] 실제로 grounding된 테마 코드에 대해서만 ka90002 호출(lazy lookup, 사전 전체 구축 없음)
├── [UX-01] Candidate.matched_filters에 매칭된 실제 테마명/요청 concept이 evidence로 기록됨
└── [UX-01] theme 제약이 활성이어도 universe에 매칭 종목이 없으면 빈 리스트(None과 구분)
```

## REST API Tests

`tests/test_api.py` — 전부 `app.dependency_overrides`로 fake Supervisor를 주입해 실제 외부 API 없이 검증한다(FastAPI `TestClient`).

```text
├── GET /health는 200 반환, Supervisor 호출 없음
├── POST /analysis (market_only)가 SupervisorResult를 그대로 JSON으로 반환
├── investor_profile이 UserRequest가 아니라 별도 인자로 전달됨 (UserRequest.model_fields에 investor_profile 없음 확인)
├── 빈 question → 422 (Pydantic 자동 검증, Supervisor 호출 없음)
├── RoutingError/FilterIntentError/ReasoningError → 502, SupervisorError/DiscoveryError → 400 (parametrize)
├── 미분류 예외(RuntimeError) → 500 + 원문(exception 메시지, 타입명) 응답 바디에 없음
├── 실제 httpx.HTTPStatusError(URL에 가짜 ECOS API key 포함) → 500 + key가 응답 바디에 없음
├── view 생략 시 응답이 view=detail과 완전히 동일(headline 등 summary 전용 필드 없음) — 기존 client 호환성 확인
├── view=summary: MARKET_ONLY/STOCK_RESEARCH/CANDIDATE_DISCOVERY/PORTFOLIO_STRATEGY 4종 모두 정상 응답
├── view=summary 응답에 financial_history/evidence/target_weight/target_price 없음
├── PORTFOLIO_STRATEGY view=summary에서 stocks=[](종목별 raw StockAnalysis 미노출, recommendations로만 표현)
├── view=both(v1 미지원) 등 잘못된 값 → 422, Supervisor 호출 없음
├── POST /analysis 응답에 X-Analysis-ID header 존재, body shape은 header 추가와 무관하게 기존과 동일
├── 서로 다른 POST는 서로 다른 analysis_id 발급
├── POST에서 받은 analysis_id로 GET /analysis/{id}?view=detail → 저장된 SupervisorResult와 완전히 동일
├── 동일 analysis_id로 GET ?view=summary → 같은 snapshot에 build_presentation()을 적용한 결과와 동일
├── 존재하지 않는 analysis_id → 404(고정 메시지), GET에 잘못된 view=both → 422
├── **핵심 invariant**: POST 이후 동일 analysis_id로 GET detail/summary를 몇 번 조회해도 fake Supervisor의 호출 횟수가 POST 시점 1회에서 늘어나지 않음(GET이 Supervisor.run()을 재호출하지 않음을 call count로 직접 검증)
├── [RE-01] view=detail의 stock_analyses[].financial_features가 additive로 노출됨, 기존 필드 불변
├── [RE-01] financial_features 없이 만든 StockAnalysis는 필드가 null로 직렬화됨(구버전 호출부 호환)
├── [RE-01] view=summary에는 financial_features가 노출되지 않음(기존 화이트리스트 구조가 자동으로 제외)
└── [RE-01] UX-04 snapshot(GET)에서도 financial_features가 재계산 없이 POST 시점과 동일하게 유지됨
```

`tests/test_presentation.py` — `build_presentation()` 자체를 실제 외부 API/LLM 없이 순수 unit test로 검증한다(HTTP 레이어 없이 함수 직접 호출).

```text
├── build_presentation 시그니처가 SupervisorResult 하나만 받음(외부 dependency 없음, 동기 함수) — 순수 함수 구조 자체를 확인
├── MARKET_ONLY: MarketSummary + headline=market_analysis.summary
├── STOCK_RESEARCH: 단일 종목이면 headline=investment_thesis, 복수 종목이면 headline=None(합성 문장 생성 안 함)
├── StockSummary 모델에 financial_history/evidence/financials/scenarios 필드 자체가 없음
├── CANDIDATE_DISCOVERY: candidate_count + Candidate 그대로 pass-through, 후보 stock_analyses도 stocks에 반영
├── PORTFOLIO_STRATEGY: market summary 포함, stocks=[](의도적으로 비움), portfolio.recommendations 구성
├── recommendation의 action/rationale/conditions/current_weight가 원본 PositionRecommendation과 정확히 동일(회귀)
├── strategy_result가 None(부분 실패)이면 portfolio 섹션 자체를 만들지 않음
├── RecommendationSummary/PortfolioSummary/PresentationResult에 target_weight/target_price/evidence/stock_analyses/portfolio_context 필드 없음
└── skipped가 모든 intent에서 그대로 pass-through
```

`tests/test_snapshot_store.py` — `AnalysisSnapshotStore`를 HTTP 레이어 없이 직접 검증한다. TTL 경과는 `sleep()` 대신 clock을 생성자에 주입해(`clock: Callable[[], datetime]`) 결정론적으로 시뮬레이션한다.

```text
├── put() → analysis_id(uuid) 발급
├── put() 직후 get(id) → 동일 SupervisorResult 인스턴스
├── 서로 다른 put() → 서로 다른 id, 각각 올바른 결과로 조회됨
├── 존재하지 않는 id → None
├── TTL 이전(만료 1초 전) → 정상 조회
├── TTL 경과 후(만료 1초 후, 정확히 경계값 포함) → None
├── 만료된 snapshot은 get() 호출 시 내부 dict에서 lazy eviction됨
└── 만료된 snapshot은 다음 put() 호출 시에도 lazy eviction됨(무한 누적 방지)
```

## MCP End-to-End Test

`tests/test_mcp_server.py`에서 실제 MCP Client로 9개 Tool 전체를 실제 외부 API까지 end-to-end로 검증한다.

현재 전체 테스트 결과:

```text
361 passed
```

전체 lint 결과:

```text
All checks passed!
```

---

# 🚧 Current Status

현재 프로젝트는 **Foundation, Model Layer v1, ECOS / OpenDART / Kiwoom 외부 데이터 Integration을 완료하고, Stock Research Agent v1·Market Agent v1·Portfolio Strategy Agent v1·Supervisor / Router v1·Candidate Discovery v1까지 구현하고 그 위에 REST API v1(FastAPI)까지 얹어 실제 E2E 검증을 마친 단계**다.

Market Agent보다 Stock Research Agent를 먼저 구현했다. Kiwoom/OpenDART로 이미 종목 단위 데이터(가격, 재무)가 충분히 확보된 반면, 시장 전체 데이터는 기준금리뿐이었기 때문이다. Market Agent v1을 구현하며 ECOS를 환율/KOSPI/KOSDAQ까지 확장했고, regime/risk_level 판단은 Stock Research Agent의 `risk_level`처럼 Python 상수로 고정할 수 없어 대신 fact-id grounding(존재하지 않거나 비어 있는 참조는 검증 실패 → 재시도 → `ReasoningError`)으로 구조적으로 통제했다.

당초 로드맵은 Recommendation Engine을 다음 단계로 잡았지만, Portfolio Strategy Agent v1은 `RecommendationResult` 없이도(v1은 이 입력을 아예 받지 않음, 보유 종목 + 호출자가 명시적으로 분석 요청한 종목만 다룸) 독립적으로 구현 가능하다고 판단해 순서를 바꿔 먼저 구현했다. Portfolio Strategy Agent v1은 Market Agent의 fact-id grounding 패턴을 확장해 **symbol/fact-id/action 3중 grounding**을 적용했고(새 종목 지어내기·보유여부에 안 맞는 action을 구조적으로 차단), `target_weight`는 Stock Research Agent의 `target_price`와 동일한 이유(포지션 사이징 근거 없음)로 v1에서 항상 `null`로 강제한다. 실제 계좌(보유 종목 다수 + ETF 포함) E2E 검증 과정에서 Kiwoom 계좌 종목코드 시장 접두문자(`"A005930"`) 미정규화, OpenDART `"-"` placeholder 금액 파싱 오류라는 두 개의 기존 Service 버그를 추가로 발견해 수정했다(자세한 내용은 dev-log 참고).

세 Agent가 모두 갖춰진 뒤 이를 실제 사용자 요청 하나로 연결하는 Supervisor / Router v1을 구현했다. Router(intent 분류)와 Supervisor(실행·조립)를 분리하지 않고 하나의 `SupervisorOrchestrator`로 시작했고, LLM은 closed enum만 제안하며 어떤 Agent를 호출할지는 Python의 고정 dispatch가 전담해 LLM이 존재하지 않는 Agent/tool을 호출하는 경로 자체를 없앴다. 종목명(예: "삼성전자")은 OpenDART 회사 목록과 정확히 일치할 때만 종목코드로 해석하고, 특정 종목을 명시한 질문은 보유종목 전체가 아니라 그 종목만 재분석해 비용을 아낀다. 부분 실패는 위치별로 다르게 처리한다 — root(Market Agent, 명시적 종목의 Stock Research) 실패는 요청 전체 실패, 보유종목 fan-out의 개별 실패는 skip, sink(Portfolio Strategy reasoning) 실패는 부분 결과 반환. 실제 계좌(보유 28종목) E2E 검증 중 보유종목 전체를 무제한 병렬 실행하면 Kiwoom OAuth 토큰 발급이 몰려 429가 발생하는 문제와, Portfolio Agent의 프롬프트에서 "이름(코드)" 표기가 LLM의 `symbol` 필드 혼동을 유발하는 문제를 발견해 각각 동시성 제한(Semaphore)과 프롬프트 포맷 분리로 수정했다. 이후 Kiwoom access token을 매 호출마다 재발급하던 근본 원인을 확인해 `KiwoomService`에 instance-level 캐싱(`asyncio.Lock` 기반 double-checked locking)을 추가했다(자세한 내용은 dev-log 참고).

"지금 살 만한 종목 찾아줘" 같은 요청을 처리하려면 Stock Research Agent의 분석 대상을 스스로 찾는 Candidate Discovery가 필요했다. 처음에는 현재 데이터로 안전한 Stock Universe를 구성할 수 없다고 판단해 보류했으나, Kiwoom 공식 REST API를 실측 조사한 결과 `ka10099`(종목정보 리스트)로 KOSPI/KOSDAQ 전체 종목과 종목코드/종목명/시장구분/업종명/규모구분/상장주식수를 단일 호출로 확보할 수 있음을 확인해 v1을 구현했다. Candidate Discovery는 Agent가 아니라 Supervisor와 같은 얇은 구조(LLM 조건 구조화 + deterministic 필터 실행)로 만들었다 — 투자 판단(reasoning) 단계가 전혀 없기 때문이다. 실제 업종명(`upName`)이 "반도체" 같은 세분화된 업종이 아니라 27개의 굵직한 KRX 대분류라는 것도 실측으로 확인했고, 매칭되는 업종이 없으면 근거 없이 대체하지 않고 실패시킨다. 후보가 `MAX_STOCK_RESEARCH_FANOUT`(투자 threshold가 아닌 fan-out 실행/비용 안전 한도)을 초과하면 momentum 등 암묵적 기준으로 일부를 골라내지 않고 Stock Research를 0건 실행한 뒤 조건을 더 좁혀달라고 요청한다. `exclude_owned`(보유종목 제외 여부)는 Portfolio Strategy 경로를 탄다는 사실과 무관하게 사용자 문장 자체("내 포트폴리오에 없는" 등)에서만 grounding하도록 설계해, 실제 E2E로 같은 종목 집합에 대해 표현에 따라 이 값이 정확히 갈리는 것을 확인했다.

다섯 Agent/컴포넌트가 전부 갖춰진 뒤, 이를 실제 client에서 호출할 수 있는 REST API v1(FastAPI)을 얇게 얹었다. 새 투자 로직은 넣지 않고 `SupervisorOrchestrator`를 그대로 core로 재사용하며, `POST /analysis` 단일 endpoint로 Supervisor의 모든 intent를 처리한다(Market/Stock/Portfolio/Discovery별 endpoint를 나누지 않음 — Supervisor가 이미 라우팅을 담당하므로 나누면 판단 주체가 이중화됨). `UserRequest`/`investor_profile` 분리 계약을 지키기 위해 API 전용 `AnalysisRequest` DTO에서만 investor_profile을 받고, Core의 domain model 자체는 바꾸지 않았다. `lifespan`에서 의존성 그래프를 프로세스 생애주기 동안 1회만 생성해 Kiwoom access token 캐싱이 그대로 유효하게 했다. 미분류 예외를 client에 그대로 노출하면 안 되는 이유를 실제 코드로 확인했다 — **ECOS는 API key가 URL 경로에, OpenDART는 쿼리 파라미터에 그대로 포함**되어 있어(`app/services/ecos.py`, `app/services/opendart.py`), 이런 예외의 원문이 그대로 client에 전달되면 credential이 유출된다. 실제 `httpx.HTTPStatusError`(URL에 가짜 key 포함)로 이 정책을 회귀 테스트했다. 502는 이 프로젝트에서 단순 네트워크 게이트웨이 오류가 아니라 routing/filter-intent/reasoning 같은 LLM 기반 dependency 실패를 가리키는 API 정책으로 정의했다.

REST API v1까지 갖춘 뒤, Stock Research Agent의 `investment_thesis`가 최근 한 해 수치만 재진술하고 `risks`에 비교 기준 없는 단일 PER/PBR/거래량 재진술이 섞이는 문제를 개선하기 위해 OpenDART 다년(3개년) 재무 추세를 추가했다. 실제 API 호출로 OpenDART `fnlttSinglAcnt.json`이 사업보고서(`reprt_code=11011`)일 때 하나의 호출로 당기/전기/전전기(`thstrm`/`frmtrm`/`bfefrmtrm`) 3개 연도를 이미 함께 내려준다는 사실을 확인해, **추가 API 호출이나 새 인프라(캐시/DB) 없이** 기존 단일 호출을 재사용하는 방식으로 설계했다. `analysis.py`는 손익 항목의 흑자↔적자 전환이나 두 해 모두 적자인 경우 백분율 대신 "전환/규모 확대·축소"로 표현해 왜곡을 피하고, 3개년 데이터가 모두 있고 방향이 단조로울 때만 "연속 상승/하락" fact를 만든다. 과거 연도 스냅샷(`financial_history`)에는 PER/PBR/ROE를 절대 채우지 않는다 — OpenDART가 과거 시가총액/주가를 제공하지 않아 계산 근거가 없기 때문이다. `risks` 프롬프트 정책은 애초 설계했던 "단일 수치는 risk가 될 수 없다"는 절대 금지 대신, 사용자 검토를 거쳐 "비교 기준 없는 단일 시점 수치만으로 단정하지 않되 다년 추세/전환 fact는 더 강한 근거로 쓸 수 있다"는 완화된 형태로 반영했다 — deterministic fact와 risk 판단을 혼동하지 않는 것이 핵심이다. 실제 삼성전자(005930) E2E로 확인한 결과 `investment_thesis`가 2023→2024→2025 매출/영업이익/순이익 연속 상승과 마진 추이를 실제로 서술했고, `risks` 3건 중 2건이 다년 추세(수익성 변동, 부채비율 상승 추세)를 근거로 했으며(나머지 1건은 PER 단일 수치를 여전히 근거로 삼되 "고평가"가 아니라 "실적 민감도"로 완화된 표현을 사용), catalysts는 여전히 근거 없이 생성되지 않았고 confidence는 MEDIUM 상한을 유지했다(자세한 내용은 dev-log 참고).

OpenDART 다년 재무 추세를 추가한 뒤, 실제 Swagger 사용에서 `portfolio_strategy` 응답이 보유 종목 수만큼의 `StockAnalysis`를 모두 포함해 사람이 읽기 어려울 정도로 길다는 문제가 확인됐다. `SupervisorResult`는 향후 Web/Flutter의 상세 조회와 machine-readable contract로 계속 가치가 있어 바꾸고 싶지 않았기 때문에, 이를 전혀 건드리지 않고 그 위에 읽기 전용 파생 뷰 `PresentationResult`를 얹었다. `app/api/presentation.py`의 `build_presentation()`은 LLM이나 외부 API를 인자로 받지 않는 순수 함수이며, `MarketAnalysis.summary`/`StockAnalysis.investment_thesis`/`StrategyResult.summary`/`PositionRecommendation.rationale` 같은 기존 grounded 필드를 그대로 옮기거나 개수만 세는 것으로 제한했다 — 새 자유생성 LLM synthesis는 이 프로젝트가 지켜온 "grounding 없이 생성하지 않는다" 원칙을 우회하는 새 hallucination 표면이 되므로 v1에서 명시적으로 배제했다. `RecommendationSummary`에는 `target_weight`/`target_price` 같은 필드를 아예 선언하지 않아 null 강제보다 한 단계 더 강한 안전장치로 새 투자 판단 생성을 구조적으로 차단했다. API는 `POST /analysis?view=detail|summary`로 노출했고, `view` 생략 시 기존 `SupervisorResult` 응답과 완전히 동일해 기존 client 호환성을 100% 유지했다(both는 v1에서 의도적으로 제외 — payload를 줄이는 게 목적인데 요약+상세를 함께 반환하면 문제가 그대로 남기 때문). 실제 E2E로 확인한 결과 `stock_research`(삼성전자)는 9,208바이트(detail) → 3,094바이트(summary), `portfolio_strategy`(보유 20여종목)는 211,862바이트(detail) → 5,123바이트(summary)로 줄었다 — 특히 portfolio는 약 97.6% 감소해 원래 문제를 직접 해결했음을 확인했다(자세한 내용은 dev-log 참고).

Presentation view를 실사용(Swagger)한 결과 `view=summary`/`view=detail`을 각각 별도 요청하면 Supervisor pipeline이 매번 독립적으로 재실행되어, 동일 질문인데도 LLM reasoning의 비결정성 때문에 market regime이나 portfolio recommendation 개수·action이 두 응답 사이에 달라지는 현상이 실제로 관측됐다(UX-04). 이를 해결하기 위해 **한 번 실행된 `SupervisorResult`에 `analysis_id`를 부여하고 이후 조회가 동일 snapshot을 공유하게** 하는 analysis snapshot lifecycle을 추가했다. `POST /analysis`가 실행 직후 결과를 `app/api/snapshot_store.py`의 `AnalysisSnapshotStore`(in-memory TTL store, 기본 30분)에 저장하고 `X-Analysis-ID` 응답 header로 id를 돌려주며, 신규 `GET /analysis/{analysis_id}?view=detail|summary`는 그 id로 저장된 동일 snapshot을 조회만 할 뿐 `Supervisor.run()`/LLM/Kiwoom/OpenDART/ECOS 어느 것도 다시 호출하지 않는다. `analysis_id`는 API/snapshot lifecycle metadata일 뿐 투자 분석 domain data가 아니라는 경계를 지키기 위해 `UserRequest`/`SupervisorResult`/`PresentationResult` 어디에도 필드로 추가하지 않았고, body는 header 추가와 무관하게 기존과 완전히 동일하게 유지해 backward compatibility를 지켰다. DB/Redis/background job은 이번에도 추가하지 않았다 — 관측된 문제가 "동일 snapshot을 summary/detail이 공유하지 못한다" 하나뿐이라 이를 푸는 최소 구조(in-memory dict + lazy TTL eviction)로 충분하다고 판단했고, `put()`/`get()`에 `await` 지점이 없어 `asyncio.Lock`도 예방적으로 추가하지 않았다. 실제 E2E로 동일 `analysis_id`에 대해 POST(수 분, 실제 실행)와 GET(수 ms, 재실행 없음)의 latency 차이, 그리고 detail/summary 간 recommendation 개수·필드가 완전히 일치함을 확인해 §13.5에서 관측됐던 불일치(6건 vs 10건)가 재현되지 않음을 검증했다(자세한 내용은 dev-log 참고).

UX-04까지 마친 뒤 Candidate Discovery v1의 "반도체"/"2차전지" 같은 세부 업종 질문이 실패하는 UX-01(세부 업종 taxonomy)을 다뤘다. 애초 가설은 "Kiwoom `ka10101`(업종코드 리스트)이 `ka10099.upName`보다 세분화돼 있을 것"이었으나, 실제 API 호출로 확인한 결과 **`ka10101`은 `upName`과 사실상 동일한 굵직한 KRX 대분류(~27~34개)였다** — 삼성전자·SK하이닉스·LG에너지솔루션이 전부 "전기/전자" 하나에 뭉뚱그려짐을 실측으로 확인했다. 대신 Kiwoom의 테마 API(`ka90001` 테마그룹별요청/`ka90002` 테마구성종목요청)에 실제로 세분화된 정보(반도체 8개 세부 테마, 2차전지 2개, 로봇 1개, 원자력 2개 등 총 142개 테마)가 존재함을 확인해, **Industry axis는 기존 `upName`을 그대로 재사용하고 Theme axis(`ka90001`/`ka90002`)를 완전히 별도로 추가하는 "Semantic Industry + Grounded Theme"(C안) 구조**를 채택했다. `DiscoveryFilter`에 `theme_requests: list[ThemeRequest]`(concept + 실제 grounding된 테마명)를 신설해 Industry(`sector_terms`)와 절대 섞지 않았고, 같은 concept의 여러 테마는 UNION, 서로 다른 axis(market/size/industry/theme/ownership)는 INTERSECTION으로 결합했다. LLM은 "원전 → 원자력_기자재/원자력_설계시공"처럼 사용자 표현과 카탈로그 공식 명칭 사이의 동의어 수준 normalization을 제안할 수 있지만 Python이 실제 카탈로그로 다시 검증하며, 지원되지 않는 concept(예: "AI" — 카탈로그에 전혀 없음을 실측 확인)은 조용히 무시하지 않고 `DiscoveryError`로 명시적으로 실패시킨다. 실제 LLM 응답을 검증하는 과정에서 초기 프롬프트가 "AI"를 "클라우드 컴퓨팅"/"보안_인터넷" 같은 응용 산업 테마에 과도하게 매칭시키는 것을 발견해, 하드코딩된 alias table 대신 프롬프트 지침을 "확신이 서지 않으면 포함하지 말라"는 방향으로 강화해 해결했다. Theme catalog(`ka90001`)는 `KiwoomService` instance에 24시간 TTL로 캐시하고(access token 캐시와 별개, UX-04 Analysis Snapshot Store와도 목적이 다른 순수 외부 metadata refresh 정책), 실제 멤버십(`ka90002`)은 요청된 테마만 lazy 조회한다(142개 전체 사전 구축 없음). 기존 `Candidate.sector`/`matched_filters: dict[str, str]`는 변경하지 않고 그대로 유지해 backward compatibility를 지켰다. 실제 E2E로 "대형 통신 종목"(Industry axis) 결과가 UX-01 전후로 완전히 동일함을 재확인했고, "반도체"(Theme, 8개 세부 테마 union), "코스피 대형주 중 반도체"(Market ∩ Size ∩ Theme 교집합, SK하이닉스/삼성전자/한미반도체 3종목), "원전"(정상화 후 9종목), "AI"(unsupported, `DiscoveryError`)를 확인했다. "2차전지"는 실제로 17종목(완제품 3 + 소재 14)이 나와 fan-out 한도를 넘었는데, 이는 LG에너지솔루션이 Kiwoom 테마 카탈로그에 아예 존재하지 않는(스핀오프 이전 구조를 반영하는 것으로 보이는) coverage gap 때문임을 실측으로 확인했다 — 이런 gap은 코드로 보정하지 않고 UX-05(Classification Coverage Gap)로 별도 기록했다. 이번 조사 중 `ka90002`에서 실제 HTTP 429(rate limit)를 처음으로 관측했는데(짧은 시간에 여러 테마를 연속 조회할 때), 응답 헤더에는 여전히 rate-limit 정보가 노출되지 않아 정확한 한도는 확인하지 못했다(자세한 내용은 dev-log 참고).

RE-01(구조화된 재무 feature) commit·push 이후 Recommendation Engine v1의 scoring 설계를 위해 네 차례의 순수 조사(RE-02/RE-03/RE-03.1/RE-03.2, 전부 production code 미변경, `git status` clean으로 종료)를 거쳤다. RE-02는 `financial_features` + `financials.per/pbr/roe` + price/confidence 필드만으로 Financial Quality/Growth-Trend/Valuation/Price Position/Risk 5개 scoring 컴포넌트의 실현 가능성을 검토했다 — Kiwoom ROE와 OpenDART 파생 net_income의 부호가 실제로 불일치하는 사례(RE-01 조사 중 LG에너지솔루션에서 발견)가 있어 ROE를 기본적으로 신뢰 가능하다고 가정하지 않았고, absolute/relative/hybrid 채택 여부 등 6개 최종 결정 질문은 아직 사용자 확정 전이다. RE-03은 이 Fundamental/Historical layer 옆에 둘 "Forward Opportunity Layer"(Forward EPS/Revenue/OpProfit/NetIncome, Earnings Revision, Consensus Target Price, Historical Valuation, Grounded Catalyst)의 실제 데이터 소스를 조사했다. Kiwoom/OpenDART 모두 forward-looking 데이터가 없음을 재확인했고(OpenDART는 다만 `report_nm` 필드가 실제로는 매우 구체적인 기업행위성 공시명임을 라이브 API 호출로 확인해 — "세분화가 부족하다"던 최초 간접 조사 결과를 실측으로 정정했다 — Grounded Catalyst는 제한적으로 YES), KIS Developers(한국투자증권)의 공식 GitHub/Postman 컬렉션에서 forward 추정실적/투자의견 관련 TR 3개(`estimate-perform`/`invest-opinion`/`invest-opbysec`)가 실존함을 확인했다. 다만 request 파라미터만 확정됐을 뿐 response schema는 공식 문서(포털은 JS SPA라 접근 불가)로도 확인할 수 없었다(RE-03.1). 이후 KIS App Key/Secret이 `.env`에 설정된 뒤 실제 인증을 시도했으나(RE-03.2) `POST /oauth2/tokenP`가 `403 EGW00103(유효하지 않은 AppKey입니다)`로 일관되게 실패해 — 재현성 확인 2회, 모의투자 도메인 진단 1회 모두 동일 — 3개 TR 중 어느 것도 아직 실제로 호출하지 못했다. **Forward Opportunity Layer의 데이터 계약은 여전히 전부 미확정이며, 유효한 KIS credential 확보가 다음 단계(RE-04)의 유일한 blocker다.** Recommendation Engine(scoring/ranking 기반 신규 투자 후보 평가)은 프로젝트 공식 범위에 포함되어 있으며, UX-02(InvestorProfile persistence)와 함께 다음 구현 대상이다.

다음 세션에서 이 blocker가 풀렸다(RE-03.2 재개) — 원인은 KIS App Key 자체가 무효했던 게 아니라 `.env`의 `KIS_APP_KEY`에 **Kiwoom App Key가 잘못 들어가 있었던 것**으로 확인됐다. 사용자가 실제 KIS Developers 계좌·앱 키/시크릿을 새로 발급받아 `.env`를 교체한 뒤 동일한 인증 흐름을 재실행한 결과 `POST /oauth2/tokenP`가 정상적으로 access token을 발급했고, `estimate-perform`/`invest-opinion`/`invest-opbysec` 3개 TR 모두 실제 호출·response schema·값 검증까지 완료했다. 이 과정에서 KIS token 발급이 분당 1회로 제한되고(`EGW00133`) TR 호출 자체에도 초당 제한(`EGW00201`)이 있음을 실측으로 확인했다 — 향후 실제 통합 시 Kiwoom과 마찬가지로 caching/pacing이 필요하다.

이어진 RE-03.3(Forward Data Semantics & Reliability Verification)에서는 공식 GitHub/Postman 자료에 `estimate-perform`의 response 필드(`output1~4`, `data1~data5`) 설명이 전혀 없음을 재확인한 뒤, 업종을 분산한 10개 종목(005930/000660/005380 필수 포함 + 금융/인터넷/바이오/화학/통신/산업재/유틸리티)으로 직접 cross-validation을 수행했다. `output2` row1은 OpenDART 실측 대조(005930)로 매출액임을 확인했지만, 2026E/2027E 추정치가 **삼성전자·SK하이닉스 2개 종목에서만 비현실적으로(전년 대비 최대 +112%~+258%) 재현**되고 나머지 8개 종목(현대차/KB금융/NAVER/셀트리온/LG화학/SK텔레콤/HD한국조선해양/한국전력)은 과거 추세와 자연스럽게 이어지는 값을 보이는 불일치가 관찰됐다 — **원인은 확인하지 못했고 추측하지 않았다.** `output2`/`output3`의 나머지 row(영업이익/순이익/EPS/PER/PBR/ROE로 추정되는 후보들)는 공식 문서가 전혀 없어 매핑을 확정하지 않고 UNKNOWN으로 남겼다. 반면 `invest-opinion`/`invest-opbysec`의 브로커별 투자의견·목표주가는 10종목 전부에서 안정적으로 검증됐다 — 다만 응답이 최대 100건으로 상한되며(6년 넘게 조회 기간을 넓혀도 동일), `tr_cont` 헤더가 `M`으로 오는 경우가 한 번도 없어 100건 초과 시 실제 연속조회가 작동하는지는 확인하지 못했다(UNKNOWN). `estimate-perform.output1.rcmd_name`(투자의견 후보 필드)도 10종목 중 9종목은 최근 20건 브로커 의견의 다수와 일치했지만 1종목(한국전력)은 명백히 불일치해 semantics를 확정하지 못했다.

**결론: Forward Opportunity Layer v1 후보는 Broker Investment Opinion/Target Price 계열(및 그 파생 — Consensus Target Price, Implied Upside, Broker Opinion Revision)로 좁혀졌다.** `estimate-perform` 기반 Forward Revenue/Operating Profit/Net Income/EPS/PER/PBR/ROE와 `rcmd_name` 기반 Consensus Investment Opinion은 row semantics 미확정 및 reliability 불일치로 v1에서 제외한다. "Estimate Revision"이라는 모호한 이름 대신, 실제로 검증된 범위가 개별 브로커 리포트의 의견 변경(`invt_opnn` vs `rgbf_invt_opnn`) 추적임을 분명히 하기 위해 **Broker Opinion Revision**으로 명명한다 — EPS/영업이익 consensus estimate의 revision이 검증됐다는 뜻이 아니다. 상세는 dev-log §20.3/§21 참고.

이어서 RE-03.4로 Kiwoom의 Valuation/Investor Flow/Historical/Technical 데이터를 실측 검증했고(Kiwoom 공식 머신리더블 스펙 `kiwoom_api_spec.json`을 1차 자료로 활용), 이 모든 데이터 조사 결과를 종합해 **RE-04 Final Recommendation Architecture**를 설계했다 — Recommendation Engine 구현 직전의 pipeline/component/contract 설계 단계다. base architecture(pipeline, Core Attractiveness/Market Confirmation/Opportunity State, Risk/Coverage/Confidence 분리, Stock Research/Portfolio Strategy 경계, `as_of` 원칙)는 **FROZEN**으로 확정했고, 설계 도중 필요성이 드러난 **Amendment 1(Event & Disclosure Intelligence Overlay — 최신 공시/뉴스 기반 catalyst·risk를 Core 위에 얹는 별도 layer)**의 Step 1~5(Source/Lifecycle/Normalization/Contract/Taxonomy 방향)까지 확정했다.

같은 날짜에 이어진 세션에서 Amendment Step 6(Materiality & Impact Model)부터 Step 14(Amendment v1 Scope Freeze)까지 마저 확정해 **RE-04 Final Recommendation Architecture + Amendment 1을 전체 FROZEN**으로 마무리했다. Materiality는 `HIGH`/`MEDIUM`/`LOW`/`UNKNOWN` 4-level semantic으로만 정의하고 계산(Evaluator)과 threshold(PolicyConfig)의 책임을 분리했으며, Verification(사실 확인)과 Confidence(해석 신뢰도)를 Claim 단위로 분리했다. Investment Interpretation(Catalyst/Headwind/Risk/Context)은 Event 자체의 속성이 아니라 Event가 가질 수 있는 여러 `ImpactPath`별 속성으로 설계해 하나의 Event가 서로 다른 방향의 여러 interpretation을 동시에 가질 수 있게 했다. Stock Research와 Portfolio Strategy의 책임 경계를 `StockOpportunityAssessment`(status: ACTIONABLE/INSUFFICIENT_EVIDENCE, classification: ATTRACTIVE/NEUTRAL/UNATTRACTIVE) → `PortfolioActionRecommendation`(BUY/ADD/HOLD/REDUCE/EXIT 등) 2단 contract로 명시해 "Research는 Portfolio Decision이 아니다" 원칙을 구조화했고, Recommendation Policy는 weighted sum이 아니라 Eligibility → Core → Event Context → Priced-In → Risk → Market Confirmation → Correlation/Conflict → Coverage/Confidence 순서의 staged decision으로 정의했다. Priced-In LOW는 그 자체로 매수 신호가 아니며(방향은 Catalyst/Headwind가 별도로 결정), Market Confirmation은 mandatory veto가 아니고, missing/failure는 어디서도 neutral로 치환하지 않는다는 기존 원칙을 Event Intelligence 전 영역에 일관되게 적용했다. **RE-04/Amendment 1 전 과정에서 실제 numeric threshold·weight·score·calibration 값은 의도적으로 하나도 정하지 않았다** — 이 전부는 다음 단계인 **RE-05(Scoring & Weight Policy)**로 넘긴다. 상세는 아래 Phase 7과 `docs/dev-log/2026-08-29.md` §23 참고.

```text
Foundation                         completed
    │
    ▼
Model Layer v1                     completed
    │
    ▼
ECOS Integration                   completed
    │
    ▼
OpenDART Integration                completed
    │
    ▼
Kiwoom Integration                  completed
    │
    ▼
Stock Research Agent v1             completed
    ├── LLMService              ✓
    ├── Deterministic Analysis  ✓
    ├── LLM Reasoning           ✓
    ├── Orchestrator            ✓
    └── 실제 E2E Demo           ✓
    │
    ▼
Market Agent v1                     completed
    ├── ECOS 확장 (환율/KOSPI/KOSDAQ)  ✓
    ├── Deterministic Analysis        ✓
    ├── LLM Reasoning + fact grounding ✓
    ├── Orchestrator                  ✓
    └── 실제 E2E Demo                 ✓
    │
    ▼
Portfolio Strategy Agent v1         completed
    ├── Deterministic Analysis (portfolio/market/종목 fact) ✓
    ├── LLM Reasoning + symbol/fact-id/action 3중 grounding ✓
    ├── target_weight 항상 null 강제                        ✓
    ├── Orchestrator                                        ✓
    └── 실제 E2E Demo (실제 계좌 전체)                       ✓
    │
    ▼
Supervisor / Router v1               completed
    ├── LLM intent 분류 (closed enum, LLM tool-calling 권한 없음) ✓
    ├── 종목명 해석 (OpenDART 정확 일치, 추측 없음)               ✓
    ├── PORTFOLIO_STRATEGY explicit symbol 분기 (비용 절감)      ✓
    ├── 위치별 부분 실패 정책 (root/fan-out/sink)                 ✓
    ├── 보유종목 fan-out 동시성 제한 (Kiwoom 429 대응)            ✓
    ├── Kiwoom access token instance-level 캐싱                  ✓
    └── 실제 E2E Demo                                             ✓
    │
    ▼
Candidate Discovery v1               completed
    ├── Kiwoom ka10099 실측 조사 + 연동 (Stock Universe 확보)     ✓
    ├── LLM 조건 구조화 + closed set(실측 업종/규모) grounding    ✓
    ├── 후보 과다 시 임의 narrowing 없이 0건 실행 정책             ✓
    ├── exclude_owned 사용자 문장 기반 grounding                  ✓
    ├── Supervisor candidate_discovery intent 연결                ✓
    └── 실제 E2E Demo (성공/과다/personalized 케이스 전부)        ✓
    │
    ▼
REST API v1                          completed
    ├── POST /analysis 단일 endpoint (Supervisor가 라우팅 전담)    ✓
    ├── AnalysisRequest DTO (Core domain model 변경 없음)          ✓
    ├── lifespan 의존성 그래프 1회 생성 (token 캐싱 유지)          ✓
    ├── Core exception → HTTP status 매핑 + 원문 비노출            ✓
    ├── GET /health (외부 API 미호출)                              ✓
    ├── POST /analysis?view=detail|summary (Presentation view)     ✓
    └── 실제 E2E (health/MARKET_ONLY/STOCK_RESEARCH)               ✓
    │
    ▼
Analysis Snapshot Lifecycle (UX-04)  completed
    ├── AnalysisSnapshotStore — in-memory TTL store (lock 없음)    ✓
    ├── POST /analysis → X-Analysis-ID header 발급, body 불변      ✓
    ├── GET /analysis/{analysis_id}?view=detail|summary 신규       ✓
    ├── GET은 Supervisor.run()/LLM/외부 API 재호출 없음(call count로 검증) ✓
    ├── 없거나 만료된 id → 404(고정 메시지, 410 미사용)            ✓
    ├── analysis_id는 Core model(UserRequest/SupervisorResult/PresentationResult)에 미포함 ✓
    └── 실제 E2E (stock_research/portfolio_strategy, POST~분 vs GET~ms, snapshot 일치 확인) ✓
    │
    ▼
Candidate Discovery Theme Axis (UX-01) completed
    ├── ka10101 실측 결과 upName보다 세분화되지 않음 확인 → Industry는 upName 재사용 ✓
    ├── ka90001/ka90002 실제 연동 — 142개 테마 카탈로그 + lazy membership   ✓
    ├── DiscoveryFilter.theme_requests(concept + 실제 grounding된 테마명) 신설 ✓
    ├── 같은 concept 내 UNION, 서로 다른 axis 간 INTERSECTION              ✓
    ├── Theme catalog KiwoomService instance 캐시(24h TTL, lock 없음)      ✓
    ├── 지원하지 않는 concept → DiscoveryError(조용한 축소 없음)            ✓
    ├── Candidate.sector/matched_filters 구조 불변(backward compatibility) ✓
    ├── 신규 테스트 29건 + 기존 301건 회귀 없음(330 passed)                ✓
    └── 실제 E2E(통신/반도체/코스피대형+반도체/원전/AI unsupported/2차전지) ✓
    │
    ▼
Recommendation Engine Investigation  completed (조사만, 구현 아님)
    ├── RE-01 구조화된 재무 feature(financial_features)                 ✓ (Phase 6에 이미 반영)
    ├── RE-02 Scoring Architecture 조사                                  ✓ (조사)
    ├── RE-03 Forward-Looking Data Source 조사                          ✓ (조사)
    ├── RE-03.1 KIS 공식 스키마 조사(response schema 미문서화 확인)      ✓ (조사)
    ├── RE-03.2 KIS 라이브 인증 + 3개 TR 실측(재시도 후 성공)            ✓ (조사)
    ├── RE-03.3 KIS Forward Feature Verification Matrix 확정             ✓ (조사)
    └── RE-03.4 Valuation/Investor Flow/Historical/Technical 데이터 검증  ✓ (조사, Kiwoom)
    │
    ▼
RE-04 Final Recommendation Architecture   FROZEN (base + Amendment 1 전체)
    ├── Pipeline + 10개 architecture principle 확정                      ✓
    ├── Core Attractiveness / Market Confirmation / Opportunity State    ✓
    ├── ComponentResult / RiskResult contract 확정                       ✓
    ├── Coverage(evidence 존재) vs Confidence(evidence 신뢰도) 분리       ✓
    ├── Stock Research vs Portfolio Strategy 책임 경계 재확인             ✓
    ├── AS_OF 원칙(look-ahead bias 방지) 신규 확정                       ✓
    ├── Amendment 1 Step 1~5 — Event Source/Lifecycle/Normalization/Contract/Taxonomy 방향 ✓
    ├── Amendment 1 Step 6 — Materiality & Impact Model (Evaluator/Policy/PolicyConfig 분리) ✓
    ├── Amendment 1 Step 7 — Verification(Claim 단위) / Confidence(Interpretation 단위) 분리 ✓
    ├── Amendment 1 Step 8 — Investment Interpretation(Catalyst/Headwind/Risk/Context는 ImpactPath 속성) ✓
    ├── Amendment 1 Step 9 — 기존 Component 관계 audit(Priced-In/Correlation/Conflict 포함)     ✓
    ├── Amendment 1 Step 10 — Recommendation Policy Integration(StockOpportunityAssessment → PortfolioActionRecommendation 2단 contract, staged decision) ✓
    ├── Amendment 1 Step 11 — LLM vs Deterministic Logic 최종 경계                              ✓
    ├── Amendment 1 Step 12 — Failure / Missing News / Missing Disclosure semantics             ✓
    ├── Amendment 1 Step 13 — Evidence Lineage 최종 audit                                        ✓
    └── Amendment 1 Step 14 — Amendment v1 Scope Freeze(numeric 항목 전부 RE-05로 DEFERRED 목록화) ✓
    │
    ▼
RE-05 Recommendation Scoring / Policy Calibration   IN PROGRESS
    ├── Step 1~12 Policy/Contract 문서화(FROZEN candidate, numeric parameter는 OPEN) ✓ (dev-log §24)
    ├── Calibration Protocol(AS_OF/walk-forward/bias guardrail/archetype stress test) 문서화 ✓
    └── Data Availability Audit — Feature별 AVAILABLE_NOW/DERIVABLE_NOW/SOURCE_AVAILABLE_
        BUT_NOT_IMPLEMENTED/NEW_SOURCE_REQUIRED/UNAVAILABLE/DEFERRED/UNKNOWN 분류 완료 ✓ (dev-log §25)
    │
    ▼
RE-05 Data Verification & V1 Scope Resolution   PARTIAL
    ├── OpenDART Fundamental 5종목 업종분산 실측(현금흐름표 부재 확정,
    │   금융업/비금융 applicability 예외 확인) ✓
    ├── Kiwoom Market Cap/Free Float 실제 응답 산술 교차검증 ✓
    ├── Kiwoom OHLCV(ka10081) 메커니즘 확인(최대 depth·수정주가 diff는 미완료) ✓
    ├── Investor Flow(ka10061) 기간합산 확인(일별 series 여부는 미확정) ✓
    └── V1 Feature Set = NOT READY — dev-log §26
    │
    ▼
RE-05 Design Resolution — Fundamental scope 정정 + Forward Coverage/Core 구조 확정
    ├── OpenDART fnlttSinglAcnt는 "주요계정"뿐 — OCF/FCF/CAPEX/ROIC는 이 endpoint
    │   기준 UNAVAILABLE, OpenDART 전체 기준은 VERIFICATION_REQUIRED로 정정 ✓
    ├── Core Attractiveness는 v1도 Fundamental/Valuation/Forward/Flow 4-component 유지 ✓
    ├── Forward unavailable → score=unavailable/signal=UNKNOWN/coverage=insufficient ✓
    ├── Decision Eligibility에 Future-Opportunity Evidence Requirement(Forward evidence
    │   OR qualifying future-facing Event) 신설(numeric은 OPEN) ✓
    ├── Open Design Question #1/#2 RESOLVED, #3/#4는 여전히 OPEN
    └── Broker Opinion/Target Price = Supplemental Research Context로 최종 확정 ✓ (dev-log §27)
    │
    ▼
RE-05 Targeted Data Verification   PARTIAL → 거의 COMPLETE
    ├── fnlttSinglAcntAll.json 실측 — CF(현금흐름표) 33~69행/사 확인,
    │   fnlttSinglAcnt(주요계정)는 여전히 UNAVAILABLE이지만 OpenDART 전체는
    │   AVAILABLE_RAW로 정정 ✓
    ├── Kiwoom 일별 investor flow 시계열 확보 확인(Open Design Question #3 RESOLVED) ✓
    └── ka10081 수정주가(upd_stkpc_tp) 효과 — 3종목 600거래일 diff했으나 여전히
        UNKNOWN(known corporate action 종목 미확보, Open Design Question #4 유지)
    │
    ▼
RE-05 V1 Feature Set   FROZEN
    ├── scope contract 확정 — V1_REQUIRED/V1_OPTIONAL/V1_DEFERRED/V1_BLOCKED/
    │   VERIFICATION_REQUIRED 경계가 Component별로 명확해짐 ✓ (dev-log §29)
    ├── FROZEN != 모든 데이터 완비 — Data Verification은 여전히 PARTIAL ✓
    ├── Forward 4-component 구조·UNKNOWN coverage 처리는 변경 없이 유지 ✓
    └── 남은 Data Verification/Feature Semantic/Calibration Question은 그대로 보존 ✓
    │
    ▼
RE-05 Recommendation / Scoring Data Model Design   완료
    ├── app/models/recommendation.py 신규(27개 model/enum) — 기존 model
    │   무수정, 완전히 additive ✓
    ├── Feature→FeatureFamily→Component→Core/MarketConfirmation→
    │   StockOpportunityAssessment 전 layer 구현 ✓
    ├── Forward unavailable(score=None/signal=UNKNOWN/coverage=insufficient),
    │   INSUFFICIENT_EVIDENCE→classification=null을 model_validator로 강제 ✓
    ├── evaluator/aggregator/scorer/policy logic/numeric parameter 없음 ✓
    └── 신규 테스트 15건(스키마/invariant만, threshold 테스트 없음), 전체
        376 passed, ruff clean ✓ (dev-log §30)
    │
    ▼
RE-05 Data Model Contract Audit(§31)   PASSED
    ├── Risk severity 미분류 상태(risk_level=None) 표현 가능하도록 수정 ✓
    ├── FutureOpportunityEvidence를 bool→tri-state(AVAILABLE/UNAVAILABLE/
    │   UNKNOWN)로 격상해 source failure를 False로 collapse하지 않게 함 ✓
    ├── StockOpportunityAssessment 양방향 invariant(ACTIONABLE→classification
    │   non-null도 강제) ✓
    └── Event enum(EventRole/PricedInLevel) canonical ownership TODO 문서화 ✓
    │
    ▼
RE-05 Evaluation Boundary & Input Contract(§32~§33)   FROZEN
    ├── app/models/research_context.py 신규 — NormalizedResearchData/
    │   EvaluationContext/RecommendationEvaluationState/FeatureEvaluator
    │   (Protocol, 구현 없음) ✓
    ├── canonical source는 vendor→deterministic normalization(analysis.py의
    │   기존 출력) — StockAnalysis는 sibling 산출물이지 부모가 아님(§33.1,
    │   LLM narrative 역유입 구조적으로 차단) ✓
    ├── RecommendationEvaluationInput → RecommendationEvaluationState로
    │   개명, context/normalized_research_data만 필수(§33.2) ✓
    ├── vendor model이 evaluator contract에 노출 안 됨(테스트로 구조적 보장),
    │   EvaluationContext에 Portfolio 없음, Event path 분리 유지 ✓
    ├── Feature Registry = USEFUL LATER(트리거: 2번째 evaluator 또는 첫
    │   Coverage evaluator 등장 시, §33.4) ✓
    └── 신규 테스트 17건, 전체 403 passed, ruff clean ✓ (dev-log §32~§33)
    │
    ▼
RE-05 First Deterministic Feature Evaluation Vertical Slice(§34)   완료
    ├── app/evaluation/research_data_builder.py 신규 — DeterministicAnalysisResult
    │   (analysis.py, LLM 이전 단계)에서 NormalizedResearchData 조립, 재계산
    │   없이 financial_facts만 그대로 참조 ✓
    ├── app/evaluation/fundamental_evaluators.py 신규 — 첫 FeatureEvaluator
    │   실제 구현(RoeFeatureEvaluator: Fundamental/profitability/ROE) ✓
    ├── normalized_value는 실제 실행 결과로도 항상 None(Numeric Calibration
    │   OPEN), availability=AVAILABLE과는 독립적으로 확인 ✓
    ├── vendor model 비노출·StockAnalysis 비의존·recommendation/portfolio
    │   필드 없음을 실제 실행 경로에서 재검증 ✓
    └── 신규 테스트 17건, 전체 420 passed, ruff clean ✓ (dev-log §34)
    │
    ▼
두 번째 Fundamental FeatureEvaluator 구현 → Feature Registry 도입 여부
재확인(트리거 도달 시)   ← NEXT (dev-log 2026-08-29 §34.9 참고)
```

---

# 🗺 Roadmap

## Phase 1 — Foundation

- [x] Development environment
- [x] Project structure
- [x] Environment configuration
- [x] Pydantic configuration
- [x] Agent data models
- [x] Portfolio data models
- [x] Strategy data models
- [x] Validation test framework
- [x] Service interface pattern

## Phase 2 — ECOS Integration

- [x] ECOS API integration
- [x] ECOS Service
- [x] ECOS response normalization
- [x] ECOS Service tests
- [x] ECOS Domain Tool
- [x] `get_base_rate`
- [x] MCP Server integration
- [x] MCP Tool discovery
- [x] MCP Tool invocation
- [x] ECOS MCP end-to-end test
- [ ] Additional ECOS market indicators

## Phase 3 — OpenDART Integration

- [x] OpenDART Service
- [x] OpenDART response normalization
- [x] OpenDART Service tests
- [x] OpenDART Domain Tools
- [x] OpenDART MCP Tools
- [x] OpenDART MCP end-to-end tests

## Phase 4 — Kiwoom Integration

- [x] Kiwoom market data integration
- [x] Kiwoom account integration
- [x] Position / P&L data
- [ ] Trade history
- [x] Kiwoom Domain Tools
- [x] Kiwoom MCP Tools
- [x] Kiwoom MCP end-to-end tests

## Phase 5 — Market Agent ✅ v1 완료

> Stock Research Agent(Phase 6)와 동일하게 MCP Client 대신 in-process Domain Tool 직접 호출 방식으로 구현했다.

- [x] Direct Domain Tool invocation (MCP Client 대신 in-process 직접 호출)
- [x] ECOS 지표 확장 (`get_exchange_rate`, `get_kospi_index`, `get_kosdaq_index`)
- [x] Market data collection (`as_of_date` 기준 lookback 조회)
- [x] Market indicator normalization (deterministic fact: 기준금리 변경폭, 환율/지수 20·60거래일 변화율)
- [x] Market regime / risk_level 분석 (LLM suggested + fact-id grounding, Python 상수 고정 없음)
- [x] Market Agent implementation (`analysis.py`/`reasoning.py`/`orchestrator.py`)
- [x] MarketAnalysis generation
- [x] 실제 E2E demo (`scripts/market_agent_demo.py`)

## Phase 6 — Stock Research Agent ✅ v1 완료

> Market Agent(Phase 5)보다 먼저 구현했다. 이유는 위 "Current Status" 참고.

- [x] Direct Domain Tool invocation (MCP Client 대신 in-process 직접 호출)
- [x] OpenDART Tool invocation
- [x] Kiwoom Tool invocation
- [x] LLMService (OpenAI Chat Completions wrapper)
- [x] Deterministic fundamental analysis (`analysis.py`)
- [x] LLM reasoning (`reasoning.py`) — evidence-grounded catalysts/risks/scenarios
- [x] Stock Research Agent implementation (`orchestrator.py`)
- [x] Bull / Base / Bear scenarios (근거 없으면 빈 배열 허용)
- [x] StockAnalysis generation
- [x] 실제 E2E demo (`scripts/stock_research_demo.py`)
- [x] OpenDART 다년(최근 3개 사업연도) 재무 추세 (`financial_history`) — 기존 단일 API 호출 재사용, 추가 호출 없음
- [x] **RE-01: 구조화된 재무 feature(`financial_features`)** — 기존 다년 추세 계산(margin/debt_ratio/YoY/3개년 방향)을 Evidence 텍스트와 동일한 계산에서 machine-readable 구조로 추가 노출. Recommendation Engine의 기반이며, Recommendation Engine 자체는 아직 미구현.

## Phase 7 — Recommendation Engine (scoring/ranking)

> Stock Universe 확보와 조건 기반 후보 탐색은 Phase 7a(Candidate Discovery)로 먼저 구현했고, 종목별 구조화된 재무 feature는 Phase 6의 RE-01로 먼저 마련했다. 구현 착수 전 순수 데이터 조사(RE-02/RE-03~RE-03.4)와 architecture 설계(RE-04, Amendment 1 포함 전체 FROZEN)를 완료했다 — **아직 구현 미착수**. RE-05(Scoring & Weight Policy)의 Step 1~12 Policy/Contract와 Calibration Protocol도 문서화했다(FROZEN candidate — numeric threshold/weight/calibration parameter는 전부 OPEN, RE-05 Overall = IN PROGRESS, 상세는 `docs/dev-log/2026-08-29.md` §24). 이어서 Data Availability Audit으로 현재 repository/verified API가 RE-05 Feature Contract를 실제로 충족하는지 Feature 단위로 분류했다 — Fundamental Quality 다수는 이미 구현·검증됐지만(AVAILABLE_NOW), Forward Opportunity(consensus 수치 기반)는 여전히 제외 상태이고 Market Cap/Investor Flow/OHLCV historical/Broker Opinion 등은 API는 검증됐으나 서비스 코드가 없는 상태(SOURCE_AVAILABLE_BUT_NOT_IMPLEMENTED)다(상세는 `docs/dev-log/2026-08-29.md` §25). 이어서 핵심 항목을 실제 API 호출로 검증했다(`app/services/opendart.py`/`kiwoom.py`를 읽기 전용으로 import한 `/tmp` scratch 스크립트, production 코드 미변경) — OpenDART 5개 업종 분산 종목 실측으로 **`fnlttSinglAcnt.json`(주요계정) 하나에는 현금흐름표 계정이 구조적으로 전혀 없음을 확인**했고(OCF/FCF/CFO÷NI는 **이 endpoint 기준**으로만 UNAVAILABLE — OpenDART에는 별도의 전체 재무제표 endpoint `fnlttSinglAcntAll.json`이 존재해 아직 미검증인 채로 남아 있어, source 전체 기준 판정은 `VERIFICATION_REQUIRED`로 되돌렸다, 상세는 `docs/dev-log/2026-08-29.md` §27.0) 금융업/비금융 업종별로 확보 가능한 계정이 다름을 실측했다. Kiwoom `ka10001`의 `mac`(시가총액)은 `flo_stk × 현재가`와 산술적으로 일치함을 교차검증했고, `ka10081`(일봉차트)이 실제로 작동하며 거래대금까지 매일 제공함을 확인했다(최대 depth·수정주가 효과는 미확인). Investor Flow(`ka10061`)는 기간 합산 값만 확인했고 일별 시계열 확보 가능 여부는 미확정이다. 이 검증 결과 Broker Opinion/Target Price를 Forward Component input이 아니라 Supplemental Research Context로 재분류하며 v1 Forward Opportunity Component가 사용 가능한 input을 하나도 갖지 못한다는 사실이 드러났는데, 이에 대해 **Core Attractiveness는 v1에서도 Fundamental/Valuation/Forward/Flow 4-component 구조를 그대로 유지하고(3-component로 축소하지 않음), Forward가 unavailable이면 score=unavailable/signal=UNKNOWN/coverage=insufficient로만 표현하며(missing을 neutral/0으로 바꾸지 않음), Decision Eligibility에 "reliable Forward evidence 또는 검증된 future-facing Event 근거" 중 하나로 충족 가능한 Future-Opportunity Evidence Requirement를 신설**하기로 확정했다(numeric boundary는 여전히 OPEN, 상세는 `docs/dev-log/2026-08-29.md` §27.1~§27.3). **V1 Feature Set은 아직 FROZEN하지 않았다(NOT READY)** — `fnlttSinglAcntAll.json` 실측과 Investor Flow 일별 시계열 확인이 남아 있다. 상세는 `docs/dev-log/2026-08-29.md` §26~§27.
>
> **데이터 조사** (production code 미변경):
>
> - **RE-02**: Financial Quality/Growth-Trend/Valuation/Price Position/Risk 5개 컴포넌트의 데이터 실현 가능성 검토.
> - **RE-03~RE-03.3**: KIS Developers 라이브 검증 완료. **v1 채택**: Broker Investment Opinion/Target Price(+ 파생 Consensus Target Price/Implied Upside/Broker Opinion Revision). **v1 제외**: `estimate-perform` 기반 Forward Revenue/OpProfit/NetIncome/EPS/PER/PBR/ROE(row semantics 미문서화 + 종목별 reliability 불일치), `rcmd_name` 기반 Consensus Investment Opinion.
> - **RE-03.4**: Kiwoom Valuation/Investor Flow/Historical/Technical 데이터 실측 검증(공식 spec `kiwoom_api_spec.json` 기반). **v1 채택**: Current PER/PBR/시가총액(`ka10001.mac`, 기존 통합 API에 이미 존재), Investor Flow(5D/20D/60D 순매수 `ka10061`, 추정평균매수가 `ka10045`, flow intensity), OHLCV historical(수정주가 `upd_stkpc_tp` 포함, 삼성전자 기준 최대 40년 depth 확인), Momentum/MA/52W/Volatility/Drawdown 전부. **v1 제외**: Peer-relative Valuation(기존 Industry axis `upName`가 우선주·이업종 지주사를 같은 그룹으로 묶어 UNRELIABLE로 확인됨), Historical PER/PBR percentile(전용 API 없음 + 표본 부족), Dividend Yield(필드 자체 없음).
>
> **Architecture 설계 — RE-04 Final Recommendation Architecture(base) FROZEN + Amendment 1 Step 1~5 확정**:
>
> ```text
> Data Acquisition → Deterministic Feature Layer → Independent Component Evaluators
>   → Core Attractiveness(Fundamental/Valuation/Forward/Investor Flow) × Market Confirmation(Momentum/Technical)
>   → Opportunity State → Risk + Coverage + Confidence(완전 분리) → Recommendation Policy
>   → Structured StockRecommendation → Grounded LLM Explanation
> ```
>
> LLM은 numeric scoring engine으로 쓰지 않고 evidence 기반 explanation에만 쓴다. `NO DATA != NEUTRAL`, component 실패가 전체 Stock Research 실패를 의미하지 않는다, 모든 evidence는 분석 기준시점 `as_of` 이후 발행된 것을 쓰지 않는다(look-ahead bias 방지) 등 10개 architecture principle을 확정했다. Amendment 1로 **Event & Disclosure Intelligence Overlay**(공시·뉴스 기반 catalyst/risk를 반영하는 별도 overlay — Core의 새 weighted component가 아님)를 추가했고, Event source(OpenDART 우선 + News provider abstraction, provider 미확정)/lifecycle/normalization/taxonomy 방향(Step 1~5)에 이어 Materiality & Impact Model(Step 6)/Verification·Confidence(Step 7)/Investment Interpretation(Step 8)/기존 Component 관계 audit(Step 9, Priced-In·Correlation·Conflict 포함)/Recommendation Policy Integration(Step 10, Stock Research → `StockOpportunityAssessment` → Portfolio Strategy → `PortfolioActionRecommendation` 책임 분리)/LLM-Deterministic 경계(Step 11)/Failure semantics(Step 12)/Evidence Lineage(Step 13)/Scope Freeze(Step 14)까지 **Step 1~14 전체를 FROZEN**으로 확정했다. **RE-04/Amendment 1 전 과정에서 numeric materiality threshold/component weight/aggregation formula/calibration 값은 의도적으로 하나도 정하지 않았다** — 전부 다음 단계인 **RE-05(Scoring & Weight Policy)**로 DEFERRED했다.
>
> 상세는 `docs/dev-log/2026-08-28.md` §19~§21(RE-02~RE-03.3 — RE-03.4는 이 파일에 없음, 위 RE-03.4 요약이 현재 유일한 기록), `docs/dev-log/2026-08-29.md`(RE-04 base + Amendment 1 Step 1~5는 §1~§21, Amendment 1 Step 6~14 Final Freeze + RE-05 Handoff는 §23) 참고.

- [x] Recommendation data models(`app/models/recommendation.py` — `FeatureEvaluationResult`/`ComponentAssessment`/`RiskAssessment`/`CoreAttractivenessAssessment`/`StockOpportunityAssessment` 등 27개 model/enum, evaluator/aggregator/scorer 없음, 상세는 dev-log §30)
- [ ] Data Acquisition / Deterministic Feature Layer(evaluator — `app/evaluation/`에서 첫 vertical slice 시작, ROE 1개 feature만 구현, 나머지 Fundamental feature와 Valuation/Forward/Flow/Market Confirmation은 미착수)
- [ ] Core Attractiveness — Fundamental Quality(ROE `FeatureEvaluator` 1개 완료, ComponentAssessment 조립은 미착수)
- [ ] Core Attractiveness — Valuation Attractiveness
- [ ] Core Attractiveness — Forward Opportunity
- [ ] Core Attractiveness — Investor Flow
- [ ] Market Confirmation — Momentum
- [ ] Market Confirmation — Technical Confirmation
- [ ] Opportunity State 산출 (Core × Market)
- [ ] Risk (Base + Cross-Component)
- [ ] Coverage / Confidence 분리 평가
- [ ] Event & Disclosure Intelligence Overlay (Amendment 1)
- [ ] Recommendation Policy / Guardrail (double-counting 등, RE-05)
- [ ] Portfolio Fit (Portfolio Strategy Agent 연계 — Stock Research에서는 생성하지 않음)
- [ ] Grounded LLM Explanation / Presentation
- [ ] Backtesting / calibration (RE-05 이후)

## Phase 7a — Candidate Discovery ✅ v1 완료

> "어떤 종목을 Stock Research Agent의 분석 대상으로 올릴 것인가"만 담당하는 constraint-based discovery. 투자 매력도 scoring/ranking(Phase 7)과는 분리했다 — 투자 판단이 아니라 순수 필터링이기 때문이다.

- [x] Kiwoom REST API 실측 조사 (ka10099/ka10019/ka10101 API/필드/파라미터 확인)
- [x] Stock Universe definition (`ka10099` 기반, KOSPI/KOSDAQ 전체 종목)
- [x] `DiscoveryFilter` 구조화 (market/sector_terms/size_terms/exclude_owned)
- [x] sector/size closed set grounding (실측된 값에서만 매칭, 재시도 → `FilterIntentError`)
- [x] Exclusion / constraint handling (exclude_owned, 사용자 문장 기반)
- [x] 후보 과다 시 정책 (`MAX_STOCK_RESEARCH_FANOUT`, 임의 narrowing 없이 0건 실행)
- [x] Candidate 모델 (score 없음, matched_filters로 추적)
- [x] Supervisor `candidate_discovery` intent + `portfolio_strategy` discovery 분기 연결
- [x] 실제 E2E Demo (성공/후보 과다/personalized discovery/exclude_owned true·false 전부)
- [x] **UX-01(Semantic Industry + Grounded Theme)**: `ka90001`/`ka90002` 실연동, `DiscoveryFilter.theme_requests` 신설(concept + grounding된 실제 테마명), Industry는 `upName` 재사용(ka10101이 upName보다 세분화되지 않음을 실측 확인), Theme catalog `KiwoomService` 24h TTL 캐시, 지원하지 않는 concept은 `DiscoveryError`로 명시적 실패 — 자세한 내용은 위 "Candidate Discovery" 섹션과 dev-log 참고
- [ ] UX-05(Classification Coverage Gap: AI/HBM/데이터센터 부재, LG에너지솔루션 등 theme 누락) — 별도 known issue로 기록, 코드 보정하지 않음(v1 범위 밖)

## Phase 8 — Portfolio Strategy Agent ✅ v1 완료

> Recommendation Engine(Phase 7)보다 먼저 구현했다. 이유는 위 "Current Status" 참고 — v1은 `RecommendationResult` 없이 보유 종목 + 명시적으로 분석 요청된 종목만으로 동작한다.

- [x] Portfolio data model
- [x] Investor profile model
- [x] Strategy result model
- [x] Account Tool integration (Kiwoom 계좌 → `PortfolioAdapter` → `PortfolioContext`)
- [ ] RecommendationResult integration (Recommendation Engine 완성 후 v2)
- [x] Position / P&L analysis (deterministic fact: 비중, 집중도, 평가손익률)
- [x] Portfolio risk analysis (LLM 제안 + fact-id grounding)
- [x] Personalized strategy generation (symbol/fact-id/action 3중 grounding, target_weight 항상 null)
- [x] StrategyResult generation
- [x] 실제 E2E demo (`scripts/portfolio_strategy_demo.py`, 실제 계좌 전체)

## Phase 9 — Supervisor / Router ✅ v1 완료

> Recommendation Engine(Phase 7)보다 먼저 구현했다 — 세 Agent(Market/Stock Research/Portfolio Strategy)가 모두 갖춰져 실제 사용자 요청 하나를 end-to-end로 연결하는 것을 우선했다.

- [x] User Request routing (LLM 기반 closed enum 분류, Python이 강제)
- [x] Agent orchestration (intent별 고정 실행 단계)
- [ ] Recommendation request routing (Recommendation Engine 완성 후 v2)
- [x] Cross-Agent result aggregation (`SupervisorResult` 결정론적 조립, 별도 LLM synthesis 없음)
- [ ] Cross-Agent consistency validation (별도 설계 필요, v2+)
- [x] Evidence tracking (각 Agent의 evidence를 그대로 보존)
- [x] Final response generation (부분 실패 시에도 확보한 결과는 보존)
- [x] 종목명 해석 (OpenDART 정확 일치, 추측 없음)
- [x] 위치별 부분 실패 정책 (root 실패=전체 실패 / fan-out 개별 실패=skip / sink 실패=부분 결과)
- [x] 실제 E2E demo (`scripts/supervisor_demo.py`, market_only/stock_research/portfolio_strategy 전체·특정종목 4개 시나리오)

## Phase 9a — REST API v1 ✅ 완료

> 새로운 투자 로직을 추가하는 게 아니라, 완성된 `SupervisorOrchestrator`를 외부 client에서 호출할 수 있는 최소 API boundary를 만드는 것이 목적이다.

- [x] `app/api/main.py` — FastAPI 앱, lifespan에서 의존성 그래프 1회 생성
- [x] `app/api/routes.py` — `AnalysisRequest` DTO, `GET /health`, `POST /analysis`
- [x] `SupervisorResult`를 별도 response model 없이 그대로 반환
- [x] Core exception → HTTP status 매핑 (400/502/500, 502의 의미를 API 정책으로 문서화)
- [x] 미분류 예외 원문 미노출 (ECOS/OpenDART API key가 URL에 포함되는 문제 회귀 테스트 포함)
- [x] `GET /health`는 외부 API 미호출
- [x] 실제 E2E (`GET /health`, `POST /analysis` MARKET_ONLY/STOCK_RESEARCH)
- [x] `POST /analysis?view=detail|summary` — `app/api/presentation.py`(순수 함수) + `PresentationResult`, 기존 `SupervisorResult`는 완전 불변
- [ ] DB / login·auth / history / Redis·Celery / background job / WebSocket / multi-worker (v1 범위 밖, 의도적으로 보류)
- [ ] `view=both` (v2+ — Phase 9b로 summary caching 자체는 해결됨, both는 여전히 별도 검토 대상)

## Phase 9b — Analysis Snapshot Lifecycle (UX-04) ✅ 완료

> `view=summary`/`view=detail`을 각각 별도 요청하면 Supervisor pipeline이 매번 독립 재실행되어, LLM reasoning의 비결정성 때문에 동일 질문의 두 응답이 서로 다른 분석을 가리킬 수 있는 문제(§13.5 관측)를 해결한다. 목표는 한 번 실행된 `SupervisorResult`에 `analysis_id`를 부여해 이후 조회가 동일 snapshot을 공유하게 하는 것.

- [x] `app/api/snapshot_store.py` — `AnalysisSnapshotStore`(in-memory TTL store, 기본 30분, `uuid4()` 기반 id)
- [x] `put()`/`get()` 모두 lazy TTL eviction, `asyncio.Lock` 없음(await 지점 없는 순수 dict 연산이라 race 발생 지점 자체가 없음)
- [x] `POST /analysis` 응답에 `X-Analysis-ID` header 추가, body shape은 기존과 완전히 동일하게 유지
- [x] `GET /analysis/{analysis_id}?view=detail|summary` 신규 — snapshot 조회 전용, `Supervisor.run()`/LLM/Kiwoom/OpenDART/ECOS 재호출 없음
- [x] 없거나 만료된 id → 404(고정 메시지 `"Analysis snapshot not found or expired."`, 410 미사용)
- [x] `analysis_id`를 `UserRequest`/`SupervisorResult`/`PresentationResult` 등 Core model에 추가하지 않음(API/lifecycle metadata로만 유지)
- [x] 신규 테스트 18건(`test_snapshot_store.py` 10 + `test_api.py` +8) — GET이 Supervisor.run() 호출 횟수를 늘리지 않음을 call count로 직접 검증
- [x] 실제 E2E (`stock_research`/`portfolio_strategy`) — POST(수 분, 실제 실행) vs GET(수 ms, 재실행 없음) latency 차이 확인, detail/summary 간 recommendation 개수·필드 완전 일치로 §13.5 불일치(6건 vs 10건) 재현 안 됨을 확인
- [ ] DB/Redis 기반 영속 store, multi-worker 공유 store, tombstone 기반 410 (v1 범위 밖, 의도적으로 보류)

## Phase 10 — Expansion

- [ ] Additional ECOS indicators
- [ ] News integration
- [ ] Additional market data
- [ ] Investment history
- [ ] Strategy history
- [ ] Recommendation history
- [ ] Recommendation performance tracking
- [ ] Advanced backtesting
- [ ] Report generation
- [ ] Additional MCP servers

---

# ⚠️ Disclaimer

이 프로젝트는 개인적인 학습 및 투자 의사결정 지원을 목적으로 개발한다.

생성된 분석 및 종목 추천 결과는 투자 수익을 보장하지 않으며 최종 투자 판단과 책임은 사용자에게 있다.
# Personal Investment Multi-Agent System

개인의 실제 투자 의사결정을 지원하기 위한 **Multi-Agent 기반 개인화 투자 분석 시스템**.

단순한 종목 추천이나 자동매매 시스템이 아니라, 여러 독립적인 데이터 소스를 수집·분석하고 사용자의 실제 포트폴리오와 기존 투자 전략을 함께 고려하여 **일관되고 근거를 추적할 수 있는 투자 전략과 신규 투자 후보를 생성하는 것**을 목표로 한다.

> **Current Status:** ECOS / OpenDART / Kiwoom integration + Stock Research Agent v1 + Market Agent v1 + Portfolio Strategy Agent v1 + Supervisor / Router v1 + Candidate Discovery v1 + REST API v1 (FastAPI, `POST /analysis`) completed  
> **Next:** Recommendation Engine (scoring/ranking)

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
- OpenDART `get_key_financials` — 매출/영업이익/순이익, 자산/부채/자본총계

`PortfolioContext`는 의도적으로 사용하지 않는다. 종목 자체의 분석(재사용 가능)과 사용자별 투자 판단(Portfolio Strategy Agent의 역할)을 분리하기 위함이다.

v1의 핵심 정책:

- **Evidence-grounded**: LLM은 `analysis.py`가 만든 deterministic facts만 근거로 사용하고, 뉴스·공시·산업 동향 등 제공되지 않은 정보를 추측하지 않는다.
- **평가 없는 raw fact**: PER/PBR/ROE 등 비교 기준이 없는 지표는 수치 사실만 제공하고 "고평가/저평가/양호" 같은 판단을 하지 않는다.
- **target_price / probability 미생성**: v1에는 목표주가 산정 근거가 없으므로 항상 `null`이며, Python이 파싱 후 구조적으로 강제한다.
- **catalyst 엄격 정의**: 향후 주가·실적·기업가치에 영향을 줄 구체적 이벤트만 catalyst로 인정하고, 단순 재무 규모 재진술은 catalyst로 취급하지 않는다.
- **risk_level 고정(MEDIUM)**: 단일연도 재무 데이터만으로는 LOW/HIGH를 판단할 근거가 부족해 v1은 중립값을 사용하며, LLM은 이 값을 변경할 수 없다.
- **confidence 상한**: `analysis.py`가 데이터 완전성에 따라 계산한 상한과 LLM이 제안한 값 중 더 낮은 쪽을 최종 `confidence`로 사용한다(v1은 HIGH를 반환하지 않는다).
- `catalysts` / `risks` / `scenarios`는 근거가 없으면 빈 리스트를 정상 출력으로 허용한다.

주요 출력:

```text
StockAnalysis
├── symbol
├── name
├── price
├── financials
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

## 5. Candidate Discovery — ✅ v1 구현 완료

"어떤 종목을 Stock Research Agent의 분석 대상으로 올릴 것인가"만 담당한다. 종목 자체의 매력도(Stock Research Agent)나 사용자별 BUY/AVOID 판단(Portfolio Strategy Agent)에는 관여하지 않는다 — 아래 전체 범위의 Recommendation Engine(scoring/ranking)과는 다른, 더 좁은 v1 기능이다.

Agent가 아니라 Supervisor와 동일한 얇은 2단 구조로 구현했다 — "투자 판단을 내리는 reasoning" 단계가 없기 때문이다(LLM은 자유 텍스트를 구조화하는 역할만 한다).

```text
app/discovery/
├── filter_intent.py   # LLM이 질문 → DiscoveryFilter로 구조화 (closed set 검증 + 재시도)
└── orchestrator.py     # universe 조회, 필터 적용, 후보 과다 시 정책, Candidate[] 조립
```

v1이 실제로 사용하는 데이터: Kiwoom `ka10099`(종목정보 리스트, 실제 API 호출로 검증). KOSPI/KOSDAQ 각각 단일 호출로 전체 종목(2026-08 기준 KOSPI 2,481종목)과 함께 종목코드/종목명/시장구분/업종명(`upName`)/규모구분(`upSizeName`)/상장주식수/최근가/감리구분/투자유의여부를 확보한다. ETF/ETN(`mrkt_tp` 8/60 등)은 애초에 조회 대상에 넣지 않아 구조적으로 제외된다.

v1의 핵심 정책:

- **LLM은 조건만 구조화하고 절대 종목을 고르지 않는다**: `DiscoveryFilter`(market/sector_terms/size_terms/exclude_owned)만 제안하고, 실제 종목 선택은 Python이 실제 universe 데이터로 수행한다.
- **sector_terms/size_terms는 실제 관측된 값만 허용한다**: 매 요청마다 universe를 먼저 조회해 실제 존재하는 업종명/규모구분 집합을 만들고, 이 집합을 LLM 프롬프트에 제공해 그 안에서만 고르게 한 뒤 Python이 다시 한번 검증한다(재시도 → 최종 실패 시 `FilterIntentError`). 실제 확인 결과 `upName`은 세분화된 업종(예: "반도체")이 아니라 27개의 굵직한 KRX 대분류(전기/전자, 제약, 통신 등)라, "반도체 종목 찾아줘" 같은 요청은 매칭되는 값이 없어 정상적으로 실패 처리된다 — 근거 없이 유사한 값으로 대체하지 않는다.
- **exclude_owned은 개인화 여부와 별개로, 사용자 문장 자체에서만 결정한다**: Portfolio Strategy Agent 경로를 탄다는 사실만으로 보유종목을 자동으로 제외하지 않는다. "내 포트폴리오에 없는", "미보유" 등 실제 제외 의도가 문장에 있을 때만 `exclude_owned=true`로 grounding한다(실제 E2E로 True/False 두 표현이 정확히 구분됨을 확인).
- **후보 과다 시 subset을 고르지 않는다**: `MAX_STOCK_RESEARCH_FANOUT`(투자 threshold가 아니라 Stock Research fan-out의 실행/비용 안전 한도)을 초과하면 일부를 임의로 골라내는 대신 Stock Research를 0건 실행하고 조건을 더 좁혀달라고 요청한다. 사용자가 개수를 지정해도 순서 기준이 없으면 "어떤 N개"를 고를지 자체가 임의적이므로, 한도 이하로 들어오면 전체를 그대로 통과시키고 초과하면 통과시키지 않는 이분법만 사용한다 — momentum/거래량 기반 랭킹은 암묵적 투자 전략 편향을 시스템 기본값으로 주입하는 것이라 v1에서 배제했다.
- **관리종목/투자유의/거래정지는 filter 조건으로 쓰지 않는다**: `auditInfo`/`orderWarning` 필드는 확인했지만 실제 flagged 값을 관측하지 못해, 해석하지 않고 raw fact로만 `Candidate`에 실어 보낸다.

Supervisor 연결: 새 intent `candidate_discovery`(후보만 반환) 추가. `portfolio_strategy`는 기존 "특정 종목 우선 → 보유종목 전체" 2단 분기에 "discovery 조건 있으면 그 후보로" 분기를 하나 추가해 확장했다(새 intent 아님, 기존 실행 로직 재사용).

주요 출력:

```text
Candidate
├── symbol / name
├── market
├── sector
└── matched_filters   # {"sector": "통신", "size": "대형주", ...} — 점수/매력도 없음
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
├── main.py     # FastAPI 앱, lifespan(의존성 그래프 1회 생성), 예외 핸들러
└── routes.py   # AnalysisRequest DTO, GET /health, POST /analysis
```

## Endpoint

v1은 **`POST /analysis` 단일 endpoint**로 Supervisor의 모든 intent(`market_only`/`stock_research`/`candidate_discovery`/`portfolio_strategy`)를 처리한다. Market/Stock/Portfolio/Discovery별로 endpoint를 나누지 않는다 — Supervisor 자체가 이미 "어떤 종류의 요청인가"를 안전하게 판단하는 역할을 하므로, endpoint를 나누면 client와 Supervisor가 이 판단을 각자 따로 내리게 되어 서로 어긋날 위험이 생긴다.

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

향후 필요에 따라 추가할 수 있다.

- 시장 뉴스
- 증권사 리포트
- 산업 자료
- 해외 시장 데이터
- 추가 경제 지표
- 기업 IR 자료

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
│   │   └── routes.py                # AnalysisRequest DTO, GET /health, POST /analysis
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
│   ├── discovery/                  # Candidate Discovery — v1 구현 완료
│   │   ├── filter_intent.py        # LLM → DiscoveryFilter (closed set 검증 + 재시도)
│   │   └── orchestrator.py         # universe 조회, 필터 적용, 후보 과다 정책
│   │
│   ├── recommendation/             # Recommendation Engine (planned)
│   │   └── engine.py               # Recommendation logic (planned)
│   │
│   ├── mcp/
│   │   ├── ecos_tools.py           # ECOS Domain Tools (기준금리/환율/KOSPI/KOSDAQ)
│   │   ├── opendart_tools.py       # OpenDART Domain Tools (find_stock_code_by_name 포함)
│   │   ├── kiwoom_tools.py         # Kiwoom Domain Tools (get_kospi/kosdaq_stock_list 포함)
│   │   └── server.py               # MCP Server / Tool exposure
│   │
│   ├── services/
│   │   ├── ecos.py                 # ECOS Service
│   │   ├── opendart.py             # OpenDART Service
│   │   ├── kiwoom.py               # Kiwoom Service (get_stock_list/ka10099 포함)
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

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/analysis \
  -H "Content-Type: application/json" \
  -d '{"question": "요즘 시장 상황 어때?"}'
```

`--host 127.0.0.1`(기본값)로 로컬 머신 밖에서 접근할 수 없게 하는 것이 v1의 실질적인 보안 경계다 — 아직 인증 시스템은 없다.

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

ECOS, OpenDART, Kiwoom 각 Service/Domain Tool을 `httpx.MockTransport` 또는 `AsyncMock` 기반으로 검증한다(URL/parameter 구성, HTTP 오류 처리, 응답 정규화, Kiwoom continuation 처리 등). 일부는 실제 외부 API를 호출하는 real-path 테스트(`test_real_*`)도 함께 포함한다.

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
└── risk_level 고정 (v1은 항상 MEDIUM)

test_stock_research_reasoning.py
├── LLM 응답 구조화 검증 + 최소 재시도 (mock, 실제 OpenAI 미호출)
├── target_price / probability는 항상 null로 강제
├── scenarios=[] 정상 허용
├── catalyst 엄격 정의(정적 규모 재진술은 catalyst 아님) 프롬프트 반영
└── catalysts / risks 빈 리스트 허용

test_stock_research_orchestrator.py
├── KiwoomTools / OpenDartTools / LLMService 전부 mock/fake 주입
├── confidence = min(LLM 제안값, analysis 상한)
├── risk_level은 analysis 결과만 사용 (LLM이 변경 불가)
├── evidence는 deterministic facts + 실제 tool 호출 출처로만 구성
└── ReasoningError 발생 시 fallback 없이 예외 전파
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
└── exclude_owned은 LLM이 문장에서 판단한 값을 그대로 신뢰(구조 검증 대상 아님, 의미 판단은 프롬프트 책임)

test_discovery_orchestrator.py
├── KiwoomTools fake로 KOSPI/KOSDAQ universe 주입
├── 조건 없음(모든 필드 기본값) → None 반환
├── market/sector/size 필터 적용, matched_filters에 매칭 근거 기록
├── exclude_owned=True/False에 따라 보유종목 제외 여부가 실제로 달라짐
├── 후보가 MAX_STOCK_RESEARCH_FANOUT 초과 시 DiscoveryError, 이하면 일부를 고르지 않고 전체 통과
└── symbol/name이 비어있는 항목은 제외
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
└── 실제 httpx.HTTPStatusError(URL에 가짜 ECOS API key 포함) → 500 + key가 응답 바디에 없음
```

## MCP End-to-End Test

`tests/test_mcp_server.py`에서 실제 MCP Client로 9개 Tool 전체를 실제 외부 API까지 end-to-end로 검증한다.

현재 전체 테스트 결과:

```text
238 passed
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

Recommendation Engine(scoring/ranking 기반 신규 투자 후보 평가)은 프로젝트 공식 범위에 포함되어 있으며 다음 구현 대상이다.

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
    └── 실제 E2E (health/MARKET_ONLY/STOCK_RESEARCH)               ✓
    │
    ▼
Recommendation Engine               ← NEXT (scoring/ranking)
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

## Phase 7 — Recommendation Engine (scoring/ranking)

> Stock Universe 확보와 조건 기반 후보 탐색은 Phase 7a(Candidate Discovery)로 먼저 구현했다. 이 Phase는 그 위에 얹는 scoring/ranking 기반 전체 Recommendation Engine이다 — 아직 미착수.

- [ ] Recommendation data models (RecommendedStock/RecommendationResult)
- [ ] Fundamental Score
- [ ] Earnings Momentum Score
- [ ] Valuation Score
- [ ] Price Momentum Score
- [ ] Foreign / Institution Flow Score
- [ ] Catalyst Score
- [ ] Risk Penalty
- [ ] Portfolio Fit Score
- [ ] Quantitative scoring engine
- [ ] Top-N recommendation (scoring 기반)
- [ ] Recommendation evidence tracking
- [ ] RecommendationResult generation
- [ ] Agent-based qualitative evaluation
- [ ] Hybrid recommendation
- [ ] Backtesting / scoring validation

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
- [ ] DB / login·auth / history / Redis·Celery / background job / WebSocket / multi-worker (v1 범위 밖, 의도적으로 보류)

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
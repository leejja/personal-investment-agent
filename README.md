# Personal Investment Multi-Agent System

개인의 실제 투자 의사결정을 지원하기 위한 **Multi-Agent 기반 개인화 투자 분석 시스템**.

단순한 종목 추천이나 자동매매 시스템이 아니라, 여러 독립적인 데이터 소스를 수집·분석하고 사용자의 실제 포트폴리오와 기존 투자 전략을 함께 고려하여 **일관되고 근거를 추적할 수 있는 투자 전략과 신규 투자 후보를 생성하는 것**을 목표로 한다.

> **Current Status:** ECOS / OpenDART / Kiwoom integration + Stock Research Agent v1 + Market Agent v1 (ECOS 확장: 환율/KOSPI/KOSDAQ, fact-grounded regime/risk_level) completed  
> **Next:** Recommendation Engine

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
│                    Supervisor / Router                       │
│                                                              │
│  • User Request 분석                                         │
│  • Agent routing / orchestration                            │
│  • Recommendation request routing                           │
│  • Agent 결과 종합                                           │
│  • Cross-Agent consistency 확인                             │
│  • Final response composition                               │
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

즉, MCP Client/Server 경로는 프로세스 경계를 넘는 외부 연동이 필요할 때 사용하고, 같은 프로세스 안의 Agent → Domain Tool 호출에는 사용하지 않는다. Portfolio Strategy Agent 등 향후 Agent도 Stock Research Agent·Market Agent와 동일한 패턴을 따를 예정이다.

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

## 1. Supervisor / Router Agent

사용자의 질문과 투자 상황을 분석하고 필요한 Agent와 분석 경로를 선택한다.

주요 역할:

- User Request 분석
- 필요한 Agent 결정
- Recommendation 요청 판단
- Agent 호출 순서 결정
- Agent 결과 수집
- 분석 결과 간 충돌 확인
- Cross-Agent consistency 확인
- 최종 응답 구성
- 판단 근거 및 데이터 출처 연결

Supervisor는 개별 시장·종목 분석을 직접 수행하기보다 각 Agent와 Engine을 조정하고 전체 분석 흐름을 관리한다.

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

## 4. Portfolio Strategy Agent

Market Agent와 Stock Research Agent의 결과, Recommendation Engine 결과를 사용자의 실제 투자 상황과 결합한다.

주요 입력:

```text
MarketAnalysis
StockAnalysis[]
RecommendationResult
PortfolioContext
InvestorProfile
```

주요 고려 요소:

- 보유 종목
- 보유 수량
- 평균 매입가
- 현재 평가금액
- 종목별 비중
- 섹터별 비중
- 손익
- 투자 목표
- 투자 기간
- 기존 투자 전략
- Risk tolerance
- 제약 조건
- 과거 매매
- 신규 추천 후보

이를 기반으로 단순 BUY / SELL 판단이 아니라 다음 전략을 생성한다.

- 신규 매수
- 비중 확대
- 유지
- 비중 축소
- 매도
- 신규 진입 회피
- 단계적 매수
- 단계적 매도
- 리밸런싱
- 목표가격 기반 대응
- 조건 기반 대응
- Risk 관리

주요 출력:

```text
StrategyResult
├── summary
├── recommendations[]
├── portfolio_risk
├── confidence
└── evidence[]
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
├── OAuth Access Token 발급
├── 공통 request() (cont-yn / next-key 연속조회 포함)
├── 주식 기본정보 조회
└── 계좌평가잔고 조회
```

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
│   ├── agents/                     # AI Agent Layer
│   │   ├── market/                 # Market Agent — v1 구현 완료
│   │   │   ├── analysis.py         # Deterministic 분석 (raw facts, 20/60일 변화율, confidence 상한)
│   │   │   ├── reasoning.py        # LLM reasoning (fact-id grounding 검증 포함)
│   │   │   └── orchestrator.py     # MarketAnalysis 조립
│   │   ├── stock_research/         # Stock Research Agent — v1 구현 완료
│   │   │   ├── analysis.py         # Deterministic 분석 (facts, confidence 상한, risk_level)
│   │   │   ├── reasoning.py        # LLM reasoning
│   │   │   └── orchestrator.py     # StockAnalysis 조립
│   │   └── portfolio/              # Portfolio Strategy Agent (planned)
│   │
│   ├── recommendation/             # Recommendation Engine (planned)
│   │   └── engine.py               # Recommendation logic (planned)
│   │
│   ├── mcp/
│   │   ├── ecos_tools.py           # ECOS Domain Tools (기준금리/환율/KOSPI/KOSDAQ)
│   │   ├── opendart_tools.py       # OpenDART Domain Tools
│   │   ├── kiwoom_tools.py         # Kiwoom Domain Tools
│   │   └── server.py               # MCP Server / Tool exposure
│   │
│   ├── services/
│   │   ├── ecos.py                 # ECOS Service
│   │   ├── opendart.py             # OpenDART Service
│   │   ├── kiwoom.py               # Kiwoom Service
│   │   ├── portfolio_adapter.py    # Kiwoom → PortfolioContext 변환
│   │   └── llm.py                  # LLM Service (Stock Research Agent / Market Agent 전용)
│   │
│   ├── models/
│   │   ├── common.py
│   │   ├── market.py
│   │   ├── stock.py
│   │   ├── portfolio.py
│   │   └── strategy.py
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
│   └── test_mcp_server.py
│
├── scripts/
│   ├── demo.py
│   ├── kiwoom_stock_info_demo.py
│   ├── stock_research_demo.py      # Stock Research Agent v1 실제 E2E 데모
│   └── market_agent_demo.py        # Market Agent v1 실제 E2E 데모
├── docs/
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

> `app/recommendation/`, `app/agents/portfolio/`와 관련 모델은 프로젝트의 공식 설계에 포함되었지만 아직 구현되지 않았다.

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

Development:
pytest
ruff
```

- `httpx`: 외부 REST API async HTTP client
- `mcp`: Model Context Protocol Server / Client
- `pydantic`: 구조화된 Data Model 및 validation
- `pydantic-settings`: 환경변수 및 API Key 관리
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

---

# 🧪 Testing

현재 Model Layer, ECOS / OpenDART / Kiwoom integration, LLMService, Stock Research Agent v1, Market Agent v1 전체 경로에 대한 테스트를 구현했다.

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

## MCP End-to-End Test

`tests/test_mcp_server.py`에서 실제 MCP Client로 9개 Tool 전체를 실제 외부 API까지 end-to-end로 검증한다.

현재 전체 테스트 결과:

```text
132 passed
```

전체 lint 결과:

```text
All checks passed!
```

---

# 🚧 Current Status

현재 프로젝트는 **Foundation, Model Layer v1, ECOS / OpenDART / Kiwoom 외부 데이터 Integration을 완료하고, Stock Research Agent v1과 Market Agent v1 두 Agent까지 구현·실제 E2E 검증을 마친 단계**다.

Market Agent보다 Stock Research Agent를 먼저 구현했다. Kiwoom/OpenDART로 이미 종목 단위 데이터(가격, 재무)가 충분히 확보된 반면, 시장 전체 데이터는 기준금리뿐이었기 때문이다. Market Agent v1을 구현하며 ECOS를 환율/KOSPI/KOSDAQ까지 확장했고, regime/risk_level 판단은 Stock Research Agent의 `risk_level`처럼 Python 상수로 고정할 수 없어 대신 fact-id grounding(존재하지 않거나 비어 있는 참조는 검증 실패 → 재시도 → `ReasoningError`)으로 구조적으로 통제했다.

Recommendation Engine은 프로젝트 공식 범위에 포함되어 있으며 다음 구현 대상이다.

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
Recommendation Engine               ← NEXT
    │
    ▼
Portfolio Strategy Agent
    │
    ▼
Supervisor / Router
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

## Phase 7 — Recommendation Engine

- [ ] Stock Universe definition
- [ ] Recommendation data models
- [ ] Fundamental Score
- [ ] Earnings Momentum Score
- [ ] Valuation Score
- [ ] Price Momentum Score
- [ ] Foreign / Institution Flow Score
- [ ] Catalyst Score
- [ ] Risk Penalty
- [ ] Portfolio Fit Score
- [ ] Quantitative scoring engine
- [ ] Top-N recommendation
- [ ] Exclusion / constraint handling
- [ ] Recommendation evidence tracking
- [ ] RecommendationResult generation
- [ ] Agent-based qualitative evaluation
- [ ] Hybrid recommendation
- [ ] Backtesting / scoring validation

## Phase 8 — Portfolio Strategy Agent

- [x] Portfolio data model
- [x] Investor profile model
- [x] Strategy result model
- [ ] Account Tool integration
- [ ] RecommendationResult integration
- [ ] Position / P&L analysis
- [ ] Portfolio risk analysis
- [ ] Personalized strategy generation
- [ ] StrategyResult generation

## Phase 9 — Supervisor / Router

- [ ] User Request routing
- [ ] Agent orchestration
- [ ] Recommendation request routing
- [ ] Cross-Agent result aggregation
- [ ] Cross-Agent consistency validation
- [ ] Evidence tracking
- [ ] Final response generation

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
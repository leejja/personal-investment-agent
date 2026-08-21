# Personal Investment Multi-Agent System

개인의 실제 투자 의사결정을 지원하기 위한 **Multi-Agent 기반 개인화 투자 분석 시스템**.

단순한 종목 추천이나 자동매매 시스템이 아니라, 여러 독립적인 데이터 소스를 수집·분석하고 사용자의 실제 포트폴리오와 기존 투자 전략을 함께 고려하여 **일관되고 근거를 추적할 수 있는 투자 전략과 신규 투자 후보를 생성하는 것**을 목표로 한다.

> **Current Status:** Model Layer v1 + ECOS Service / Domain Tool / MCP integration completed  
> **Next:** OpenDART API integration

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
          │     Market Agent     │
          │                      │
          │ • Market reasoning   │
          │ • MCP Client 역할    │
          └──────────┬───────────┘
                     │
                     │
                     │ MCP Protocol
                     │ Tool Calls
                     │
          ┌──────────▼───────────┐
          │ Stock Research Agent │
          │                      │
          │ • Stock reasoning    │
          │ • MCP Client 역할    │
          └──────────┬───────────┘
                     │
                     │
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
          │ • get_disclosure        (future) │
          │ • get_stock_price       (future) │
          │ • get_positions         (future) │
          │ • ...                            │
          └────────────────┬─────────────────┘
                           │
                           │ Python calls
                           ▼


======================== DOMAIN TOOL LAYER ======================


        ┌──────────────────┐
        │    EcosTools     │
        │                  │
        │ get_base_rate()  │
        └────────┬─────────┘
                 │
                 │
        ┌────────┴─────────┐
        │ OpenDartTools    │
        │    (future)      │
        └────────┬─────────┘
                 │
                 │
        ┌────────┴─────────┐
        │   KiwoomTools    │
        │    (future)      │
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
        │ ← NEXT                 │
        └────────────┬───────────┘
                     │

        ┌────────────────────────┐
        │     KiwoomService      │
        │                        │
        │ future                 │
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
          │ • PortfolioContext          │
          │ • InvestorProfile           │
          │ • StrategyResult            │
          └─────────────────────────────┘

          ┌─────────────────────────────┐
          │     Integration Models      │
          │                             │
          │ • EcosStatisticPoint        │
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
        │ exposes:
        │ get_base_rate
        ▼
app/mcp/ecos_tools.py
        │
        │ Domain Tool
        ▼
app/services/ecos.py
        │
        │ Service
        ▼
한국은행 ECOS API
```

현재는 실제 Agent가 아직 구현되지 않았기 때문에 `tests/test_mcp_server.py`의 MCP Client가 Agent Runtime의 역할을 대신하여 end-to-end 경로를 검증한다.

## Future

향후에는 다음 구조가 된다.

```text
Market Agent
Stock Research Agent
        │
        │ MCP Client
        │
        │ MCP Protocol
        ▼
MCP Server
        │
        ├── get_base_rate
        ├── get_disclosure
        ├── get_stock_price
        ├── get_positions
        └── ...
```

즉,

```text
현재

Test MCP Client
       ↓
MCP Server


향후

Agent Runtime
       │
       │ MCP Client
       ▼
MCP Server
```

형태로 확장한다.

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

외부 API integration에서도 구조화된 데이터 모델을 사용한다.

현재 ECOS:

```text
EcosStatisticPoint
├── statistic_code
├── statistic_name
├── item_code1
├── item_name1
├── unit
├── time
└── value: float
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

## 2. Market Agent

전체 시장 환경을 분석한다.

주요 분석 대상:

- 한국 / 미국 증시
- 주요 지수
- 금리
- 환율
- 거시경제 지표
- 경기 선행지표
- 업종 상대강도
- 외국인 / 기관 수급
- 시장 뉴스
- Risk-On / Risk-Off 환경

향후 MCP Client를 통해 Market Tool을 호출한다.

```text
Market Agent
    │
    ├── get_base_rate
    ├── get_exchange_rate
    ├── get_market_index
    └── ...
```

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

---

## 3. Stock Research Agent

개별 종목을 심층 분석한다.

주요 분석 대상:

- 주가
- 거래량
- 기술적 흐름
- 외국인 / 기관 수급
- 실적
- 밸류에이션
- OpenDART 공시
- 증권사 리포트
- 산업 자료
- 기업 뉴스
- 산업 뉴스
- Catalyst
- Risk

향후 다음 MCP Tool들을 사용할 수 있다.

```text
Stock Research Agent
        │
        ├── OpenDART Tools
        ├── Kiwoom Market Tools
        └── News Tools
```

필요한 경우 다음 Scenario 분석을 수행한다.

```text
Bull Scenario
Base Scenario
Bear Scenario
```

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
└── get_base_rate
```

MCP Client에서는 다음 작업을 수행할 수 있다.

```text
Tool Discovery
      │
      │ list_tools()
      ▼
get_base_rate 발견

      ↓

Tool Invocation
      │
      │ call_tool()
      ▼
get_base_rate 실행
```

현재 `tests/test_mcp_server.py`에서 실제 MCP Client를 사용하여 이 경로를 검증한다.

향후 Agent Runtime이 이 MCP Client 역할을 담당한다.

---

# 📊 Data Sources

초기 단계에서는 다음 API를 사용한다.

| Data Source | Purpose | Status |
| --- | --- | --- |
| OpenAI API | Agent reasoning 및 자연어 분석 | Planned |
| Kiwoom REST API | 계좌 / 주가 / 거래 / 수급 데이터 | Planned |
| 한국은행 ECOS API | 금리 / 환율 / 거시경제 데이터 | **Service + Tool + MCP Integrated** |
| OpenDART API | 기업 공시 / 재무 데이터 | **Next** |

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
│   │   ├── market/                 # Market Agent (planned)
│   │   ├── stock_research/         # Stock Research Agent (planned)
│   │   └── portfolio/              # Portfolio Strategy Agent (planned)
│   │
│   ├── recommendation/             # Recommendation Engine (planned)
│   │   └── engine.py               # Recommendation logic (planned)
│   │
│   ├── mcp/
│   │   ├── ecos_tools.py           # ECOS Domain Tools
│   │   └── server.py               # MCP Server / Tool exposure
│   │
│   ├── services/
│   │   └── ecos.py                 # ECOS Service
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
│   ├── test_ecos_service.py
│   ├── test_ecos_tools.py
│   └── test_mcp_server.py
│
├── scripts/
├── docs/
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

> `app/recommendation/`과 Recommendation 관련 모델은 프로젝트의 공식 설계에 포함되었지만 아직 구현되지 않았다.

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

현재 Model Layer와 ECOS 전체 integration path에 대한 테스트를 구현했다.

```text
tests/
├── test_models.py
├── test_ecos_service.py
├── test_ecos_tools.py
└── test_mcp_server.py
```

## Model Tests

```text
Valid Input
├── UserRequest
├── MarketAnalysis
├── StockScenario
├── PortfolioPosition
├── InvestorProfile
└── StrategyResult

Invalid Input
├── empty question
├── probability > 1
├── portfolio weight > 1
└── negative quantity
```

## ECOS Service Tests

```text
URL Construction
├── item_code1 only
└── multiple item codes

HTTP / Response Handling
├── successful response
├── HTTP error
└── unexpected ECOS response
```

## ECOS Domain Tool Test

```text
EcosTools.get_base_rate()
        │
        ▼
Correct ECOS statistic mapping
```

## MCP End-to-End Test

```text
MCP Client
    │
    ├── list_tools()
    │
    ▼
MCP Server
    │
    ├── get_base_rate 발견
    │
    ├── call_tool()
    │
    ▼
EcosTools
    │
    ▼
EcosService
    │
    ▼
Real ECOS API
    │
    ▼
structured_content
    │
    └── value = 2.75
```

현재 전체 테스트 결과:

```text
17 passed
```

전체 lint 결과:

```text
All checks passed!
```

---

# 🚧 Current Status

현재 프로젝트는 **Foundation과 Model Layer v1을 완료하고 외부 데이터 Integration을 구축하는 단계**다.

첫 번째 데이터 소스인 **한국은행 ECOS는 Service → Domain Tool → MCP Server까지 end-to-end integration을 완료**했다.

Recommendation Engine은 프로젝트 공식 범위에 추가되었으며 OpenDART / Kiwoom 및 주요 분석 기반이 구축된 이후 구현할 예정이다.

```text
Foundation
    │
    │ completed
    ▼
Model Layer v1
    │
    │ completed
    ▼
ECOS Integration
    │
    ├── Service            ✓
    ├── Domain Tool        ✓
    ├── MCP Server         ✓
    ├── MCP Tool           ✓
    └── End-to-End Test    ✓
    │
    ▼
OpenDART Integration      ← NEXT
    │
    ▼
Kiwoom Integration
    │
    ▼
Market Agent
    │
    ▼
Stock Research Agent
    │
    ▼
Recommendation Engine
    │
    ▼
Portfolio Strategy Agent
    │
    ▼
Supervisor / Router
```

다음 구현 대상:

```text
app/services/opendart.py
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

- [ ] OpenDART Service
- [ ] OpenDART response normalization
- [ ] OpenDART Service tests
- [ ] OpenDART Domain Tools
- [ ] OpenDART MCP Tools
- [ ] OpenDART MCP end-to-end tests

## Phase 4 — Kiwoom Integration

- [ ] Kiwoom market data integration
- [ ] Kiwoom account integration
- [ ] Position / P&L data
- [ ] Trade history
- [ ] Kiwoom Domain Tools
- [ ] Kiwoom MCP Tools
- [ ] Kiwoom MCP end-to-end tests

## Phase 5 — Market Agent

- [ ] MCP Client integration
- [ ] Market Tool invocation
- [ ] Market data collection
- [ ] Market indicator normalization
- [ ] Market regime analysis
- [ ] Risk-On / Risk-Off analysis
- [ ] Market Agent implementation
- [ ] MarketAnalysis generation

## Phase 6 — Stock Research Agent

- [ ] MCP Client integration
- [ ] OpenDART Tool invocation
- [ ] Kiwoom Tool invocation
- [ ] Fundamental analysis
- [ ] Stock Research Agent implementation
- [ ] Bull / Base / Bear scenarios
- [ ] StockAnalysis generation

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
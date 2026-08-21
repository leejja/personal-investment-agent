# Personal Investment Multi-Agent System

개인의 실제 투자 의사결정을 지원하기 위한 **Multi-Agent 기반 개인화 투자 분석 시스템**.

단순한 종목 추천이나 자동매매 시스템이 아니라, 여러 독립적인 데이터 소스를 수집·분석하고 사용자의 실제 포트폴리오와 기존 투자 전략을 함께 고려하여 **일관되고 근거를 추적할 수 있는 투자 전략을 생성하는 것**을 목표로 한다.

> **Current Status:** Model Layer v1 + ECOS Service / Tool / MCP integration completed  
> **Next:** Service Layer — OpenDART API integration

---

# 🎯 Project Goal

최종적으로 다음과 같은 구조의 개인 투자 의사결정 지원 시스템을 구축한다.

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
                          ▼
              Portfolio Strategy Agent
                          │
                          ▼
                    StrategyResult
```

시스템은 단순히 현재 시장 상황이나 특정 종목을 분석하는 데 그치지 않고,

```text
시장 환경
    ↓
개별 종목 분석
    ↓
실제 포트폴리오 영향
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
- 최종 Portfolio Strategy

---

# 🏗 Architecture

전체 시스템은 **Agent Layer**, **Model Layer**, **MCP / Tool Layer**, **Service Layer**, **External Data Sources**로 구성한다.

각 Layer는 가능한 한 명확한 책임을 가지며, Agent의 투자 판단 로직과 외부 데이터 접근 로직을 분리하는 것을 기본 원칙으로 한다.

현재 ECOS 연동을 통해 다음 경로를 실제로 구현하고 검증했다.

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
한국은행 ECOS API
```

## Overall Architecture

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
              │   Market reasoning   │
              └──────────┬───────────┘
                         │
                         │ MarketAnalysis
                         │
              ┌──────────┴───────────────┐
              │                          │
              │              ┌───────────▼──────────┐
              │              │ Stock Research Agent │
              │              │                      │
              │              │   Stock reasoning    │
              │              └───────────┬──────────┘
              │                          │
              │                          │ StockAnalysis[]
              └──────────────┬───────────┘
                             │
                    PortfolioContext
                    InvestorProfile
                             │
                             ▼
                ┌──────────────────────────┐
                │ Portfolio Strategy Agent │
                │                          │
                │   Portfolio reasoning    │
                └─────────────┬────────────┘
                              │
                              │ StrategyResult
                              ▼
                     Investment Strategy


=========================== MODEL LAYER =========================

             Agent 간 명시적인 Pydantic Data Contract

┌────────────────────────┐       ┌────────────────────────┐
│ Common Models          │       │ Analysis Models        │
│                        │       │                        │
│ • UserRequest          │       │ • MarketAnalysis       │
│ • Evidence             │       │ • StockAnalysis        │
│ • RiskLevel            │       │ • PortfolioContext     │
│ • AnalysisConfidence   │       │ • InvestorProfile      │
│                        │       │ • StrategyResult       │
└────────────────────────┘       └────────────────────────┘

Model Layer는 특정 외부 API에 의존하지 않는다.

Agent와 Service 사이에서 사용하는 데이터 구조와
Agent 간 Input / Output 계약을 명시적으로 정의한다.


======================== MCP / TOOL LAYER =======================

                Agent-accessible Tool Interfaces

                    ┌─────────────────┐
                    │   MCP Server    │
                    │                 │
                    │ Tool discovery  │
                    │ Tool invocation │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   Domain Tools  │
                    │                 │
                    │   EcosTools     │
                    └────────┬────────┘
                             │
                             │
                             ▼


========================== SERVICE LAYER ========================

                External Data Access / Normalization

       ┌─────────────────────────┐
       │       EcosService       │  ✓ v1 Completed
       │                         │
       │ • Async API request     │
       │ • HTTP error handling   │
       │ • JSON parsing          │
       │ • Response validation   │
       │ • Data normalization    │
       └─────────────────────────┘

       ┌─────────────────────────┐
       │     OpenDartService     │  ← Next
       │                         │
       │ • API request           │
       │ • Parsing               │
       │ • Conversion            │
       └─────────────────────────┘

       ┌─────────────────────────┐
       │      KiwoomService      │
       │                         │
       │ • Market data           │
       │ • Account data          │
       │ • Trade data            │
       └─────────────────────────┘


====================== EXTERNAL DATA SOURCES ====================

       ┌────────────────┐
       │    ECOS API    │
       │                │
       │ 금리 / 환율 /  │
       │ 거시경제 지표  │
       └────────────────┘

       ┌────────────────┐
       │  OpenDART API  │
       │                │
       │ 공시 / 재무    │
       │ 기업 데이터    │
       └────────────────┘

       ┌────────────────┐
       │ Kiwoom REST API│
       │                │
       │ 주가 / 계좌 /  │
       │ 거래 / 수급    │
       └────────────────┘
```

## Layer Responsibilities

| Layer | Responsibility |
| --- | --- |
| **Supervisor / Router** | User Request 분석, Agent routing, orchestration, 결과 종합 |
| **Agent Layer** | 시장·종목·포트폴리오 reasoning 및 투자 판단 |
| **Model Layer** | Agent 및 Service 사이의 명시적인 데이터 계약 |
| **MCP / Tool Layer** | Agent 또는 MCP Client가 사용할 수 있는 의미 기반 Tool Interface 제공 |
| **Service Layer** | 외부 API 호출, 오류 처리, parsing, normalization, 데이터 변환 |
| **External Data Sources** | 실제 시장·기업·계좌 데이터 제공 |

핵심적인 책임 분리는 다음과 같다.

```text
Agent
→ reasoning / investment decision

Model
→ data contract

MCP / Tool
→ agent-accessible domain interface

Service
→ external data access / parsing / normalization

External API
→ raw data provider
```

## Data Access Flow

Agent가 외부 API의 내부 구현 세부사항을 직접 알지 않도록 한다.

기본적인 데이터 접근 흐름은 다음과 같다.

```text
Agent / MCP Client
        │
        ▼
MCP Tool Interface
        │
        ▼
Domain Tool
        │
        ▼
Service Layer
        │
        ▼
External API
```

Service Layer는 외부 API의 구조를 알고 데이터를 가져오며, Domain Tool은 이를 Agent가 이해하기 쉬운 의미 기반 인터페이스로 변환한다.

예를 들어 Agent가 한국은행 기준금리를 조회할 때 ECOS 내부의 통계코드를 직접 알 필요가 없다.

```text
Agent / MCP Client

        ↓

get_base_rate(
    start_date,
    end_date
)

        ↓

EcosTools

        ↓

EcosService.get_statistic(
    statistic_code="722Y001",
    item_code1="0101000",
    ...
)

        ↓

ECOS API
```

`722Y001`, `0101000`과 같은 ECOS 내부 식별자는 Tool / Service 계층에서 관리한다.

이를 통해 Agent reasoning을 특정 외부 API의 구현 세부사항으로부터 분리한다.

---

## ECOS End-to-End Flow

현재 ECOS 연동은 MCP Client부터 실제 한국은행 API까지 end-to-end로 연결되어 있다.

```text
MCP Client
    │
    │ list_tools()
    ▼
MCP Server
    │
    │ get_base_rate
    ▼
EcosTools
    │
    │ semantic domain operation
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

그리고 MCP Tool 호출 결과에서는 structured content로 전달된다.

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

실제 MCP end-to-end 테스트를 통해 한국은행 기준금리 데이터가 정상적으로 반환되는 것을 확인했다.

---

## Model Flow

현재 구현된 Model Layer v1을 기준으로 주요 데이터 흐름은 다음과 같다.

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
     │              ▼
     └──────► Portfolio Strategy Agent
                    │
                    ▼
               StrategyResult
```

`MarketAnalysis`, `StockAnalysis[]`, `PortfolioContext`, `InvestorProfile`은 `Portfolio Strategy Agent`의 주요 입력으로 사용한다.

이를 통해 동일한 시장 및 종목 분석 결과라도 사용자의 실제 보유 포지션, 투자 성향, 투자 기간 및 제약 조건에 따라 서로 다른 개인화 투자 전략을 생성할 수 있다.

---

## Current Development Position

현재 개발 진행 위치는 다음과 같다.

```text
Foundation
    │
    │ COMPLETED
    ▼
Model Layer v1
    │
    │ COMPLETED
    ▼
ECOS Integration
    │
    ├── EcosService          ✓ COMPLETED
    ├── EcosTools            ✓ COMPLETED
    ├── MCP Tool             ✓ COMPLETED
    └── End-to-End Test      ✓ COMPLETED
    │
    ▼
Service Layer
    │
    ├── OpenDartService      ← NEXT
    └── KiwoomService
    │
    ▼
Additional MCP Tools
    │
    ▼
Agent Implementation
    │
    ▼
Supervisor / Router
```

현재 다음 구현 대상은:

```text
app/services/opendart.py
```

이다.

ECOS에서 검증한 다음 패턴을 OpenDART에도 적용한다.

```text
External API
    ↓
Service
    ↓
Domain Tool
    ↓
MCP Tool
```

---

# 🤖 Agents

## 1. Supervisor / Router Agent

사용자의 질문과 투자 상황을 분석하고 필요한 Agent를 선택한다.

주요 역할:

- User Request 분석
- 필요한 Agent 결정
- Agent 호출 순서 결정
- Agent 결과 수집
- 분석 결과 간 충돌 확인
- Cross-Agent consistency 확인
- Portfolio Strategy 결과를 포함한 최종 응답 구성
- 판단 근거 및 데이터 출처 연결

Supervisor는 개별 시장·종목 분석이나 포트폴리오 전략 자체를 직접 수행하기보다는 각 Agent를 조정하고 전체 분석 흐름을 관리하는 역할을 담당한다.

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

Market Agent의 분석 결과는 개별 종목 및 포트폴리오 전략의 **시장 Context**로 사용한다.

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

필요한 경우 다음과 같은 Scenario 분석을 수행한다.

```text
Bull Scenario
Base Scenario
Bear Scenario
```

각 Scenario는 확률과 목표가격 및 핵심 투자 논리를 구조화하여 표현한다.

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

각 분석 결과에는 가능한 한 데이터 출처와 Confidence를 함께 제공한다.

---

## 4. Portfolio Strategy Agent

Market Agent와 Stock Research Agent의 결과를 사용자의 실제 투자 상황과 결합한다.

주요 입력:

```text
MarketAnalysis
StockAnalysis[]
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
- 과거 투자 의사결정

이를 기반으로 단순한 BUY / SELL 판단이 아니라 다음과 같은 전략을 생성한다.

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

# 🔄 Agent Data Flow

Agent 간에는 가능한 한 명시적인 Pydantic 데이터 모델을 사용한다.

핵심 데이터 흐름:

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
     │              ▼
     └──────► Portfolio Strategy Agent
                    │
                    ▼
               StrategyResult
```

예를 들어 사용자가 다음 질문을 한다고 가정한다.

```text
"삼성전자 비중을 줄여야 할까?"
```

시스템 내부에서는 다음과 같은 흐름으로 분석한다.

```text
UserRequest
     │
     ▼
Supervisor
     │
     ├── Market Agent
     │      └── MarketAnalysis
     │
     ├── Stock Research Agent
     │      └── StockAnalysis
     │
     ├── PortfolioContext
     │      └── 보유수량 / 평단 / 비중 / 손익
     │
     └── InvestorProfile
            └── 투자성향 / 투자기간 / 목표 / 제약조건
                    │
                    ▼
           Portfolio Strategy Agent
                    │
                    ▼
               StrategyResult
```

---

# 📊 Data Sources

초기 단계에서는 다음 API를 사용한다.

| Data Source | Purpose | Status |
| --- | --- | --- |
| OpenAI API | Agent reasoning 및 자연어 분석 | Planned |
| Kiwoom REST API | 계좌 / 주가 / 거래 / 수급 관련 데이터 | Planned |
| 한국은행 ECOS API | 금리 / 환율 / 거시경제 데이터 | **Service + MCP Integrated** |
| OpenDART API | 기업 공시 / 재무 관련 데이터 | **Next** |

향후 필요에 따라 다음 데이터 소스를 추가할 수 있다.

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

최종 전략이 **어떤 데이터와 어떤 Agent의 판단에서 만들어졌는지 추적 가능**하도록 설계한다.

이를 위해 공통 `Evidence` 데이터 모델을 사용한다.

```text
Evidence
├── source
├── description
├── reference
└── timestamp
```

`reference`는 원본 데이터의 식별자를 추적하는 데 사용한다.

예:

```text
OpenDART 공시번호
ECOS 통계코드
뉴스 URL
기타 외부 데이터 reference
```

## Personalized

일반적인 투자 의견이 아니라 사용자의 실제 포트폴리오와 기존 투자 전략을 반영한다.

계좌의 객관적인 상태인 `PortfolioContext`와 투자자의 성향 및 제약조건인 `InvestorProfile`을 분리하여 관리한다.

## Consistent

동일한 상황에서 판단 기준이 임의로 변경되지 않도록 명시적인 데이터 모델과 투자 판단 기준을 사용한다.

## Risk Aware

상승 가능성뿐만 아니라 하락 위험과 포트폴리오 전체 Risk를 함께 고려한다.

## Layered

외부 API 접근, Tool Interface, Agent reasoning의 책임을 분리한다.

```text
External API
    ↓
Service
    ↓
Domain Tool
    ↓
MCP Tool
    ↓
Agent
```

이를 통해 특정 외부 API의 변경이 Agent reasoning에 직접 영향을 미치지 않도록 한다.

## Human-in-the-Loop

시스템의 목적은 완전 자동매매가 아니다.

최종 투자 판단과 주문 실행은 사용자가 결정하며 시스템은 **의사결정을 지원하는 역할**을 한다.

---

# 🧩 Model Layer

Agent 사이의 데이터 계약은 Pydantic 모델로 명시적으로 정의한다.

현재 Model Layer v1은 다음과 같다.

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

## Core Concepts

`MarketRegime`은 현재 시장 환경을 표현한다.

```text
RISK_ON
NEUTRAL
RISK_OFF
```

`RiskLevel`은 분석 대상의 위험 수준을 표현한다.

```text
LOW
MEDIUM
HIGH
```

`MarketRegime`과 `RiskLevel`은 서로 다른 개념으로 유지한다.

예를 들어 다음과 같은 상태도 표현할 수 있다.

```text
regime      = RISK_ON
risk_level  = HIGH
```

개별 종목 분석은 Bull / Base / Bear Scenario를 지원한다.

```text
StockScenario
├── scenario
├── thesis
├── target_price
└── probability
```

포트폴리오 전략은 단순 BUY / SELL이 아니라 현재 비중과 목표 비중 및 전략 변경 조건을 표현한다.

```text
PositionRecommendation
├── symbol
├── name
├── action
├── current_weight
├── target_weight
├── rationale
└── conditions[]
```

---

# 🔌 Service Layer

Service Layer는 외부 API 접근과 응답 정규화를 담당한다.

현재 첫 번째 Service인 `EcosService` v1이 구현되어 있다.

## EcosService

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

현재 구현된 `EcosStatisticPoint`:

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

ECOS의 문자열 기반 수치 데이터는 Service Layer에서 애플리케이션이 사용하기 적합한 타입으로 변환한다.

---

# 🛠 MCP / Tool Layer

외부 API의 저수준 인터페이스를 Agent에게 직접 노출하지 않는다.

Domain Tool을 통해 의미 기반 인터페이스를 제공하고 이를 MCP Tool로 노출한다.

현재 구현된 ECOS Tool:

```text
EcosTools
└── get_base_rate(
        start_date,
        end_date
    )
```

내부 구현:

```text
get_base_rate()
      │
      ▼
EcosTools
      │
      ▼
EcosService.get_statistic()
      │
      ▼
ECOS StatisticSearch API
```

Agent 또는 MCP Client는 다음 ECOS 내부 코드를 알 필요가 없다.

```text
STAT_CODE  = 722Y001
ITEM_CODE1 = 0101000
```

이러한 API-specific detail은 Tool / Service 계층에서 관리한다.

## MCP Server

현재 MCP Server는 다음 Tool을 노출한다.

```text
personal-investment-agent
└── get_base_rate
```

MCP Client에서 Tool discovery와 invocation을 수행할 수 있다.

```text
client.list_tools()
        │
        ▼
get_base_rate
        │
        ▼
client.call_tool(...)
```

실제 MCP Client를 사용한 end-to-end 테스트를 통해 ECOS 기준금리가 structured content로 전달되는 것을 확인했다.

---

# 🗂 Project Structure

현재 프로젝트 구조:

```text
personal-investment-agent/
│
├── app/
│   ├── agents/                     # AI agent layer
│   │   ├── market/                 # Market environment analysis
│   │   ├── stock_research/         # Individual stock research
│   │   └── portfolio/              # Portfolio-aware strategy generation
│   │
│   ├── mcp/                        # MCP servers and tool interfaces
│   │   ├── ecos_tools.py           # ECOS domain tools
│   │   └── server.py               # MCP server and tool exposure
│   │
│   ├── services/                   # External API and data access layer
│   │   └── ecos.py                 # ECOS API service and normalization
│   │
│   ├── models/                     # Agent input/output data contracts
│   │   ├── common.py               # Shared enums, evidence, request models
│   │   ├── market.py               # Market analysis models
│   │   ├── stock.py                # Stock research models
│   │   ├── portfolio.py            # Portfolio context models
│   │   └── strategy.py             # Investment strategy models
│   │
│   ├── config.py                   # Application configuration
│   ├── main.py                     # Application entry point
│   └── __init__.py
│
├── tests/
│   ├── test_models.py              # Model validation tests
│   ├── test_ecos_service.py        # ECOS Service unit tests
│   ├── test_ecos_tools.py          # ECOS Domain Tool tests
│   └── test_mcp_server.py          # MCP end-to-end tests
│
├── scripts/                        # Development and utility scripts
├── docs/                           # Architecture notes and development logs
│
├── .env                            # Local secrets (not committed)
├── .env.example                    # Environment variable template
├── .gitignore                      # Git ignore rules
├── pyproject.toml                  # Project metadata and dependencies
└── README.md                       # Project overview and documentation
```

향후 구현이 진행되면서 `agents/`, `services/`, `mcp/`, `tests/` 아래에 각 기능별 모듈이 추가될 예정이다.

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
Test     : pytest
Lint     : Ruff
```

프로젝트는 WSL2 Ubuntu filesystem에서 관리한다.

```text
~/project/personal-investment-agent
```

Windows VS Code에서 WSL 프로젝트를 직접 열어 개발할 수 있다.

```bash
cd ~/project/personal-investment-agent
code .
```

Python 가상환경을 사용한다.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

프로젝트 및 개발 의존성 설치:

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

- `httpx`: 외부 REST API에 대한 async HTTP client
- `mcp`: Model Context Protocol Server / Client 구현
- `pydantic`: Agent 및 Service 데이터 모델 정의와 validation
- `pydantic-settings`: 환경변수 및 API Key 설정 관리
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

애플리케이션에서는 `.env`를 직접 읽지 않고 다음 구조를 사용한다.

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

현재 `pydantic-settings` 기반 설정 로딩까지 구현되어 있다.

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

이후 `.env`에 자신의 API Key를 입력한다.

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

API Key가 정상적으로 설정되어 있다면 모두 `True`가 출력된다.

테스트 실행:

```bash
pytest
```

Lint 확인:

```bash
ruff check .
```

---

# 🧪 Testing

현재 Model Layer, ECOS Service, ECOS Domain Tool 및 MCP end-to-end 경로에 대한 테스트를 구현했다.

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

## ECOS Tool Test

```text
EcosTools.get_base_rate()
        │
        ▼
correct ECOS statistic mapping
```

## MCP End-to-End Test

```text
MCP Client
    │
    ├── Tool discovery
    │
    ▼
get_base_rate
    │
    ├── Tool invocation
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

현재 프로젝트는 **Foundation과 Model Layer v1을 완료하고 외부 데이터 Service / Tool / MCP integration을 구현하는 단계**다.

첫 번째 데이터 소스인 **한국은행 ECOS는 Service부터 MCP까지 end-to-end 연결을 완료**했다.

완료된 주요 작업:

- [x] WSL2 Ubuntu 개발환경 구성
- [x] VS Code WSL integration
- [x] Python virtual environment 구성
- [x] Git / GitHub repository 구성
- [x] 기본 프로젝트 directory 구성
- [x] `pyproject.toml` 구성
- [x] pytest / Ruff 개발환경 구성
- [x] Pydantic 도입
- [x] `.env` / `.env.example` 분리
- [x] `pydantic-settings` 기반 `app/config.py` 구성
- [x] OpenAI / Kiwoom / ECOS / OpenDART API Key 설정 확인
- [x] Model Layer v1 구현
- [x] Model validation tests
- [x] `httpx` dependency 추가
- [x] `EcosService` v1 구현
- [x] ECOS `StatisticSearch` API integration
- [x] Async HTTP request
- [x] HTTP error handling
- [x] ECOS JSON parsing
- [x] `EcosStatisticPoint` response model
- [x] ECOS data normalization
- [x] ECOS Service unit tests
- [x] `EcosTools` 구현
- [x] `get_base_rate` Domain Tool 구현
- [x] MCP Python SDK 도입
- [x] MCP Server 구현
- [x] `get_base_rate` MCP Tool 노출
- [x] MCP Tool discovery 검증
- [x] MCP Tool invocation 검증
- [x] 실제 ECOS API MCP end-to-end 검증
- [x] 전체 test suite — 17 passed
- [x] Ruff — All checks passed

현재 진행 단계:

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
    ├── MCP Tool           ✓
    └── End-to-End Test    ✓
    │
    ▼
OpenDART Integration      ← NEXT
    │
    ├── Service
    ├── Domain Tool
    ├── MCP Tool
    └── End-to-End Test
    │
    ▼
Kiwoom Integration
    │
    ▼
Agent Implementation
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
- [x] Basic validation test framework
- [x] Initial Service interface pattern

## Phase 2 — ECOS Integration

- [x] ECOS API integration
- [x] ECOS Service
- [x] ECOS response normalization
- [x] ECOS Service tests
- [x] ECOS Domain Tool
- [x] `get_base_rate` Tool
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

- [ ] Market data collection expansion
- [ ] Market indicator normalization
- [ ] Market regime analysis
- [ ] Risk-On / Risk-Off analysis
- [ ] Market Agent implementation
- [ ] MarketAnalysis generation

## Phase 6 — Stock Research Agent

- [ ] Fundamental analysis
- [ ] Market data analysis
- [ ] OpenDART analysis
- [ ] Stock Research Agent implementation
- [ ] Bull / Base / Bear scenarios
- [ ] StockAnalysis generation

## Phase 7 — Portfolio Strategy Agent

- [x] Portfolio data model
- [x] Investor profile model
- [x] Strategy result model
- [ ] Position / P&L analysis
- [ ] Portfolio risk analysis
- [ ] Personalized strategy generation
- [ ] StrategyResult generation

## Phase 8 — Supervisor / Router

- [ ] User Request routing
- [ ] Agent orchestration
- [ ] Cross-Agent result aggregation
- [ ] Cross-Agent consistency validation
- [ ] Evidence tracking
- [ ] Final response generation

## Phase 9 — Expansion

- [ ] News integration
- [ ] Additional market data
- [ ] Investment history
- [ ] Strategy history
- [ ] Report generation
- [ ] Additional MCP servers

---

# ⚠️ Disclaimer

이 프로젝트는 개인적인 학습 및 투자 의사결정 지원을 목적으로 개발한다.

생성된 분석 결과는 투자 수익을 보장하지 않으며 최종 투자 판단과 책임은 사용자에게 있다.
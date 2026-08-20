# Personal Investment Multi-Agent System

개인의 실제 투자 의사결정을 지원하기 위한 **Multi-Agent 기반 개인화 투자 분석 시스템**.

단순한 종목 추천이나 자동매매 시스템이 아니라, 여러 독립적인 데이터 소스를 수집·분석하고 사용자의 실제 포트폴리오와 기존 투자 전략을 함께 고려하여 **일관되고 근거를 추적할 수 있는 투자 전략을 생성하는 것**을 목표로 한다.

---

## 🎯 Project Goal

최종적으로 다음과 같은 구조의 개인 투자 의사결정 지원 시스템을 구축한다.

```text
User
│
▼
Supervisor / Router
│
┌─────────────────┼─────────────────┐
▼                 ▼                 ▼
Market Agent     Stock Research     Portfolio Strategy
Agent               Agent
│                 │                  │
└─────────────────┼──────────────────┘
▼
Investment Strategy
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

    * 데이터 출처
    * 분석 근거
    * Agent별 분석 결과
    * 판단 과정
    * Confidence
    * Risk
    * Bull / Base / Bear Scenario
    * 최종 Portfolio Strategy

    ---

# 🏗 Architecture

    전체 시스템은 크게 다음 계층으로 구성한다.

    ```text
┌──────────────────────────────────────────────┐
│                    User                      │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│             Supervisor / Router              │
│                                              │
│  User Request 분석                           │
│  필요한 Agent 선택                           │
│  Agent 결과 종합                             │
└──────────────┬───────────────┬───────────────┘
               │               │
       ┌───────▼──────┐ ┌──────▼──────────┐
       │ Market Agent │ │ Stock Research   │
       │              │ │ Agent            │
       └───────┬──────┘ └──────┬──────────┘
               │               │
               └───────┬───────┘
                       │
              ┌────────▼─────────────┐
              │ Portfolio Strategy   │
              │ Agent                │
              │                      │
              │ + PortfolioContext   │
              │ + InvestorProfile    │
              └────────┬─────────────┘
                       │
                       ▼
              Investment Strategy
    ```
    `Market Agent`와 `Stock Research Agent`의 분석 결과는 사용자의 실제
    `PortfolioContext` 및 `InvestorProfile`과 함께 `Portfolio Strategy Agent`의
    입력으로 사용된다.

    이를 통해 동일한 시장 및 종목 분석 결과라도 사용자의 실제 보유 포지션,
    투자 성향, 투자 기간 및 제약 조건에 따라 서로 다른 개인화 투자 전략을
    생성할 수 있다.

    Agent가 외부 API에 직접 강하게 의존하지 않도록 데이터 접근 계층을 분리한다.

    ```text
    Agent
    │
    ▼
    Service
    │
    ▼
    MCP / External API
    │
    ├── Kiwoom REST API
    ├── ECOS API
    ├── OpenDART API
    └── Other Data Sources
    ```

    이를 통해 Agent 로직과 외부 데이터 접근 로직을 분리하고 테스트 및 확장이 쉽도록 구성한다.

    ---

# 🤖 Agents

## 1. Supervisor / Router Agent

    사용자의 질문과 투자 상황을 분석하고 필요한 Agent를 선택한다.

    주요 역할:

    * User Request 분석
    * 필요한 Agent 결정
    * Agent 호출 순서 결정
    * Agent 결과 수집
    * 분석 결과 간 충돌 확인
    * 최종 투자 전략 생성
    * 판단 근거 및 데이터 출처 연결

    ---

## 2. Market Agent

    전체 시장 환경을 분석한다.

    주요 분석 대상:

    * 한국 / 미국 증시
    * 주요 지수
    * 금리
    * 환율
    * 거시경제 지표
    * 경기 선행지표
    * 업종 상대강도
    * 외국인 / 기관 수급
    * 시장 뉴스
    * Risk-On / Risk-Off 환경

    Market Agent의 분석 결과는 개별 종목 및 포트폴리오 전략의 **시장 Context**로 사용한다.

    ---

## 3. Stock Research Agent

    개별 종목을 심층 분석한다.

    주요 분석 대상:

    * 주가
    * 거래량
    * 기술적 흐름
    * 외국인 / 기관 수급
    * 실적
    * 밸류에이션
    * OpenDART 공시
    * 증권사 리포트
    * 산업 자료
    * 기업 뉴스
    * 산업 뉴스
    * Catalyst
    * Risk

    필요한 경우 다음과 같은 Scenario 분석을 수행한다.

    ```text
    Bull Scenario
    Base Scenario
    Bear Scenario
    ```

    각 분석 결과에는 가능한 한 데이터 출처와 Confidence를 함께 제공한다.

    ---

## 4. Portfolio Strategy Agent

    Market Agent와 Stock Research Agent의 결과를 사용자의 실제 투자 상황과 결합한다.

    주요 고려 요소:

    * 보유 종목
    * 보유 수량
    * 평균 매입가
    * 현재 평가금액
    * 종목별 비중
    * 섹터별 비중
    * 손익
    * 투자 목표
    * 기존 투자 전략
    * Risk 수준
    * 과거 매매
    * 과거 투자 의사결정

    이를 기반으로 단순한 BUY / SELL 판단이 아니라 다음과 같은 전략을 생성한다.

    * 유지
    * 비중 확대
    * 비중 축소
    * 단계적 매수
    * 단계적 매도
    * 리밸런싱
    * 목표가격 기반 대응
    * 조건 기반 대응
    * Risk 관리

    ---

# 🔄 Agent Data Flow

    Agent 간에는 가능한 한 명시적인 데이터 모델을 사용한다.

    초기 핵심 모델:

    ```text
    UserRequest
    │
    ▼
    Supervisor
    │
    ├──────────────► MarketAnalysis
    │
    ├──────────────► StockAnalysis[]
    │
    └──────────────► PortfolioContext
    │
    ▼
    StrategyResult
    ```

    예를 들어 사용자가 다음 질문을 한다고 가정한다.

    ```text
    "삼성전자 비중을 줄여야 할까?"
    ```

    시스템 내부 흐름은 다음과 같다.

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
    └── Portfolio Context
    └── 보유수량 / 평단 / 비중 / 손익
    │
    ▼
    Portfolio Strategy
    │
    ▼
    StrategyResult
    ```

    ---

# 📊 Data Sources

    초기 단계에서는 다음 API를 사용한다.

    | Data Source     | Purpose                  |
    | --------------- | ------------------------ |
    | OpenAI API      | Agent reasoning 및 자연어 분석 |
    | Kiwoom REST API | 계좌 / 주가 / 거래 / 수급 관련 데이터 |
    | 한국은행 ECOS API   | 금리 / 환율 / 거시경제 데이터       |
    | OpenDART API    | 기업 공시 / 재무 관련 데이터        |

    향후 필요에 따라 다음 데이터 소스를 추가할 수 있다.

    * 시장 뉴스
    * 증권사 리포트
    * 산업 자료
    * 해외 시장 데이터
    * 경제 지표
    * 기업 IR 자료

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
    └── timestamp
    ```

## Personalized

    일반적인 투자 의견이 아니라 사용자의 실제 포트폴리오와 기존 투자 전략을 반영한다.

## Consistent

    동일한 상황에서 판단 기준이 임의로 변경되지 않도록 명시적인 데이터 모델과 투자 판단 기준을 사용한다.

## Risk Aware

    상승 가능성뿐만 아니라 하락 위험과 포트폴리오 전체 Risk를 함께 고려한다.

## Human-in-the-Loop

    시스템의 목적은 완전 자동매매가 아니다.

    최종 투자 판단과 주문 실행은 사용자가 결정하며 시스템은 **의사결정을 지원하는 역할**을 한다.

    ---

# 🗂 Project Structure

    현재 기본 구조:

    ```text
    personal-investment-agent/
    │
    ├── app/                          # Application source code
    │   │
    │   ├── agents/                   # AI agents and reasoning logic
    │   │   ├── market/               # Market environment analysis
    │   │   ├── stock_research/       # Individual stock research
    │   │   └── portfolio/            # Portfolio analysis and strategy
    │   │
    │   ├── mcp/                      # MCP servers and tool interfaces
    │   ├── services/                 # External API and data access layer
    │   │
    │   ├── models/                   # Shared Pydantic data models
    │   │   └── common.py             # Common enums, requests, and evidence models
    │   │
    │   ├── config.py                 # Environment variables and application settings
    │   ├── main.py                   # Application entry point
    │   └── __init__.py
    │
    ├── tests/                         # Automated tests
    ├── scripts/                       # Development and utility scripts
    ├── docs/                          # Architecture notes and development logs
    │
├── .env                           # Local secrets (not committed)
    ├── .env.example                   # Environment variable template
    ├── .gitignore                     # Git ignore rules
    ├── pyproject.toml                 # Project metadata and dependencies
    └── README.md                      # Project overview and documentation
    ```

    구현이 진행되면서 다음과 같은 구조로 확장할 예정이다.

    ```text
    app/
    │
    ├── agents/                        # AI agent layer
    │   ├── supervisor/                # Request routing and agent orchestration
    │   ├── market/                    # Market environment analysis
    │   ├── stock_research/            # Individual stock research
    │   └── portfolio/                 # Portfolio-aware strategy generation
    │
    ├── models/                        # Agent input/output data contracts
    │   ├── common.py                  # Shared enums, evidence, and request models
    │   ├── market.py                  # Market analysis models
    │   ├── stock.py                   # Stock research models
    │   ├── portfolio.py               # Portfolio context models
    │   └── strategy.py                # Final investment strategy models
    │
    ├── services/                      # External data access and business services
    ├── mcp/                           # MCP servers and tool interfaces
    │
    ├── config.py                      # Application configuration
    └── main.py                        # Application entry point

    ```

    ---

# ⚙️ Development Environment

    현재 개발 환경:

    ```text
    OS       : Windows + WSL2 Ubuntu
    Python   : >= 3.12
    Package  : pip / pyproject.toml
    Test     : pytest
    Lint     : Ruff
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
    pydantic
    pydantic-settings
    pytest
    ruff
    ```

    `pydantic`은 Agent 간 데이터 모델 정의에 사용하고, `pydantic-settings`는 환경변수 및 API Key 설정 관리에 사용한다.

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
    git clone <repository-url>
    cd personal-investment-agent
    ```

    가상환경 생성:

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

    dependency 설치:

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

    ---

# 🚧 Current Status

    현재 프로젝트는 **초기 Architecture / Data Model 구현 단계**이다.

    완료된 작업:

    * [x] WSL2 Ubuntu 개발환경 구성
    * [x] Python virtual environment 구성
    * [x] Git / GitHub repository 구성
    * [x] 기본 프로젝트 directory 구성
    * [x] `pyproject.toml` 구성
    * [x] pytest / Ruff 개발환경 구성
    * [x] Pydantic 도입
    * [x] `.env` / `.env.example` 분리
    * [x] `pydantic-settings` 기반 `app/config.py` 구성
    * [x] OpenAI / Kiwoom / ECOS / OpenDART API Key 설정 확인

    현재 진행 단계:

    ```text
    Agent Input / Output Data Model 설계
    ```

    다음 구현 대상:

    ```text
    app/models/common.py
    │
    ├── UserRequest
    ├── Evidence
    ├── RiskLevel
    └── AnalysisConfidence
    │
    ▼
    MarketAnalysis
    │
    ▼
    StockAnalysis
    │
    ▼
    PortfolioContext
    │
    ▼
    StrategyResult
    ```

    그 이후 실제 외부 API를 연결한다.

    ```text
    Data Model
    ↓
    Service Layer
    ↓
    External API
    ↓
    Agent
    ↓
    Supervisor / Router
    ```

    ---

# 🗺 Roadmap

## Phase 1 — Foundation

    * [x] Development environment
    * [x] Project structure
    * [x] Environment configuration
    * [ ] Agent data models
    * [ ] Service interfaces
    * [ ] Basic test framework

## Phase 2 — Market Agent

    * [ ] ECOS API integration
    * [ ] Market data collection
    * [ ] Market regime analysis
    * [ ] Market Agent implementation

## Phase 3 — Stock Research Agent

    * [ ] Kiwoom market data integration
    * [ ] OpenDART integration
    * [ ] Fundamental analysis
    * [ ] Stock Research Agent implementation
    * [ ] Bull / Base / Bear scenarios

## Phase 4 — Portfolio Strategy Agent

    * [ ] Kiwoom account integration
    * [ ] Portfolio data model
    * [ ] Position / P&L analysis
    * [ ] Risk analysis
    * [ ] Personalized strategy generation

## Phase 5 — Supervisor / Router

    * [ ] User Request routing
    * [ ] Agent orchestration
    * [ ] Cross-Agent result aggregation
    * [ ] Evidence tracking
    * [ ] Final Strategy generation

## Phase 6 — Expansion

    * [ ] News integration
    * [ ] Additional market data
    * [ ] Investment history
    * [ ] Strategy history
    * [ ] Report generation
    * [ ] Additional MCP servers

    ---

# ⚠️ Disclaimer

    이 프로젝트는 개인적인 학습 및 투자 의사결정 지원을 목적으로 개발한다.

    생성된 분석 결과는 투자 수익을 보장하지 않으며 최종 투자 판단과 책임은 사용자에게 있다.


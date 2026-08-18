# Personal Investment Multi-Agent System

개인의 실제 투자 의사결정을 지원하기 위한 **Multi-Agent 기반 개인화 투자 분석 시스템**.

단순한 종목 추천이나 자동매매 시스템이 아니라, 여러 독립적인 데이터 소스를 수집·분석하고 사용자의 실제 포트폴리오와 투자 전략을 함께 고려하여 **일관되고 근거를 추적할 수 있는 투자 전략을 생성하는 것**을 목표로 한다.

## 🎯 Final Goal

최종 목표는 다음과 같은 흐름의 개인 투자 의사결정 시스템을 구축하는 것이다.

```text
                         User
                          │
                          ▼
                 Supervisor / Router
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
     Market Agent    Stock Research    Portfolio
                         Agent        Strategy Agent
          │               │               │
          └───────────────┼───────────────┘
                          ▼
                Investment Strategy
```

시스템은 단순히 현재 시장 상황을 설명하는 데 그치지 않고,

**시장 환경 → 개별 종목 분석 → 실제 포트폴리오 영향 → 투자 전략**

까지 연결하여 분석한다.

최종 결과에는 가능한 한 **데이터 출처, 분석 근거, 판단 과정, 리스크 및 시나리오**가 포함되도록 한다.

---

## 🤖 Agents

### 1. Supervisor / Router Agent

사용자의 질문과 투자 상황을 파악하고 필요한 Agent를 선택·조정한다.

여러 Agent의 분석 결과를 종합하여 최종 투자 전략을 생성한다.

---

### 2. Market Agent

전체 시장 환경을 분석한다.

주요 분석 대상:

* 한국 / 미국 증시
* 주요 지수
* 금리
* 환율
* 거시경제 지표
* 업종 상대강도
* 외국인 / 기관 수급
* 시장 뉴스
* 시장 Risk-On / Risk-Off 환경

---

### 3. Stock Research Agent

개별 종목을 심층 분석한다.

주요 분석 대상:

* 주가 / 거래량
* 기술적 흐름
* 외국인 / 기관 수급
* 실적
* 밸류에이션
* OpenDART 공시
* 증권사 리포트
* 산업 자료
* 기업 및 산업 뉴스
* Catalyst
* Risk

필요한 경우 다음과 같은 시나리오 분석을 수행한다.

* Bull Scenario
* Base Scenario
* Bear Scenario

---

### 4. Portfolio Strategy Agent

Market Agent와 Stock Research Agent의 분석을 사용자의 실제 투자 상황과 결합한다.

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
* 과거 매매 및 의사결정

이를 기반으로 단순한 BUY / SELL 판단이 아니라 다음과 같은 **포트폴리오 전략**을 생성한다.

* 유지
* 비중 확대
* 비중 축소
* 단계적 매수 / 매도
* 리밸런싱
* 목표가격 및 조건별 대응
* Risk 관리

---

## 📊 Data Sources

초기 단계에서는 다음 API 및 데이터 소스를 활용한다.

* OpenAI API
* 키움증권 REST API
* 한국은행 ECOS API
* OpenDART API

향후 필요에 따라 시장 데이터, 뉴스, 증권사 리포트 및 기타 데이터 소스를 추가한다.

---

## 🧠 Design Principles

### Evidence Based

가능한 모든 투자 판단에는 데이터와 분석 근거를 제공한다.

### Traceable

최종 전략이 **어떤 데이터와 어떤 Agent의 판단에서 만들어졌는지 추적 가능**하도록 설계한다.

### Personalized

일반적인 투자 의견이 아니라 사용자의 실제 포트폴리오와 기존 전략을 반영한다.

### Consistent

동일한 상황에서 분석 기준이 임의로 바뀌지 않도록 명시적인 투자 판단 기준과 데이터 모델을 사용한다.

### Risk Aware

수익 가능성뿐만 아니라 하락 위험과 포트폴리오 전체 Risk를 함께 고려한다.

### Human-in-the-Loop

시스템의 목적은 완전 자동매매가 아니라 **사용자의 최종 투자 의사결정을 지원하는 것**이다.

---

## 🔐 Security

API Key와 계좌 관련 민감정보는 Git Repository에 저장하지 않는다.

```text
.env             # 실제 API Key 및 민감정보 (Git 제외)
.env.example     # 환경변수 템플릿
```

각 사용자는 자신의 API Key를 별도로 설정하여 시스템을 실행한다.

---

## 🗂 Project Structure

```text
personal-investment-agent/
├── app/
│   ├── agents/
│   │   ├── market/
│   │   ├── stock_research/
│   │   └── portfolio/
│   ├── mcp/
│   ├── services/
│   ├── models/
│   └── main.py
│
├── tests/
├── scripts/
├── docs/
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

---

## 🚧 Current Status

Initial development.

현재 개발환경 및 프로젝트 기본 구조를 구성하고 있으며, 다음 단계에서는 **Supervisor / Router와 각 Agent 사이에서 사용될 입력·출력 데이터 모델 및 전체 시스템 아키텍처**를 설계한다.


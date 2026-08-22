# Automated Trading Roadmap

## 1. 장기 목표

Personal Investment Multi-Agent System을 단순 투자 분석 도구에서
장기적으로 다음 구조를 가진 개인 AI Portfolio Manager로 확장한다.

Market / Company / Portfolio Data
        ↓
Multi-Agent Analysis
        ↓
Strategy Engine
        ↓
Risk Engine
        ↓
Execution Engine
        ↓
Kiwoom REST API
        ↓
실제 주문

자동매매 기능은 프로젝트의 최종 단계에서 추가한다.

---

## 2. 핵심 원칙

자동매매 시스템의 목표를 "AI가 자동으로 수익을 만든다"로 정의하지 않는다.

목표는 다음과 같다.

- 검증된 투자 전략의 일관된 실행
- 감정적 투자 판단 최소화
- 데이터 기반 의사결정
- 포트폴리오 위험 통제
- 투자 판단 근거 추적
- 전략 성과의 지속적인 측정 및 개선

Agent가 많거나 LLM이 고성능이라는 사실 자체가 투자 수익을 보장하지 않는다.

실제 수익 가능성을 결정하는 핵심은 투자 전략에 지속적인
예측력(edge)이 존재하는지 여부이다.

---

## 3. 자동매매 Architecture

LLM이 직접 주문을 실행하지 않는다.

권장 구조:

Agents
   ↓
Investment Analysis
   ↓
Strategy Engine
   ↓
OrderProposal
   ↓
Risk Engine
   ↓
Execution Engine
   ↓
Kiwoom REST API

각 계층의 역할을 명확하게 분리한다.

### Agent Layer

담당:

- 시장 상황 해석
- 기업 분석
- 공시 분석
- 뉴스 분석
- 포트폴리오 상황 분석
- Catalyst / Risk 분석

### Strategy Engine

담당:

- 정량적 매수/매도 조건
- 모멘텀
- 밸류에이션
- 실적 변화
- 수급
- 변동성
- 포지션 사이징

### Risk Engine

Agent의 판단과 실제 주문 사이에 반드시 위치한다.

검증 항목 예:

- 종목 최대 비중
- 섹터 최대 비중
- 1회 최대 주문금액
- 일일 최대 주문금액
- 일일 최대 거래횟수
- 일일 최대 손실
- 중복 주문 방지
- 비정상 가격 감지
- 데이터 오류 감지
- API 오류 감지
- AI 이상 출력 방어
- Kill Switch

### Execution Engine

Risk Engine을 통과한 주문만 실제 증권사 API로 전달한다.

담당:

- 매수
- 매도
- 정정
- 취소
- 체결 확인
- 미체결 관리
- 주문 상태 추적

---

## 4. 자동화 단계

처음부터 완전 자동매매를 사용하지 않는다.

### Phase 1 — Recommendation

Agent가 분석 및 매수/매도 제안만 생성한다.

실제 주문 없음.

### Phase 2 — Human Approval

Agent가 주문안을 생성한다.

예:

삼성전자
매도 10주
제안가격 280,000원

사용자가 승인한 경우에만 주문한다.

### Phase 3 — Limited Automation

사전에 정의된 일부 전략만 자동 실행한다.

낮은 금액과 강한 Risk Limit을 사용한다.

### Phase 4 — Automated Portfolio Management

충분한 백테스트 및 실전 검증을 거친 전략에 대해서만
자동매매를 허용한다.

---

## 5. Backtesting Layer

자동매매 구현 전에 반드시 Backtesting Layer를 구축한다.

평가 지표:

- CAGR
- Benchmark 대비 초과수익
- MDD
- Sharpe Ratio
- Sortino Ratio
- 승률
- 평균 이익
- 평균 손실
- Profit Factor
- 거래 횟수
- Turnover
- 거래비용
- 세금
- Slippage

승률만으로 전략을 평가하지 않는다.

예:

승률 70%

평균 이익 +1%
평균 손실 -5%

이라면 높은 승률에도 좋은 전략이라고 할 수 없다.

---

## 6. Strategy Validation

과최적화를 방지하기 위해 다음 검증 절차를 고려한다.

Historical Data
      ↓
Training / Development Period
      ↓
Backtest
      ↓
Out-of-Sample Test
      ↓
Walk-Forward Validation
      ↓
Kiwoom Mock / Paper Trading
      ↓
소액 실계좌
      ↓
실전 성과 분석
      ↓
검증된 경우에만 투자 규모 확대

---

## 7. Hybrid AI + Quant Architecture

장기적으로 모든 투자판단을 LLM에 맡기지 않는다.

LLM과 정량 알고리즘을 결합한다.

LLM / Agents
├─ 뉴스 해석
├─ 공시 해석
├─ 시장 상황
├─ 기업 분석
└─ Catalyst / Risk
        ↓
Quant Strategy Engine
├─ Momentum
├─ Valuation
├─ Earnings
├─ Flow
└─ Volatility
        ↓
Portfolio Optimizer
        ↓
Risk Engine
        ↓
Execution Engine
        ↓
Kiwoom

LLM은 비정형 정보의 해석과 종합 판단을 담당하고,
수치화 가능한 조건과 위험관리는 deterministic logic을 적극 활용한다.

---

## 8. Evidence / Audit Trail

모든 투자판단은 가능한 한 근거를 추적할 수 있어야 한다.

예:

Order #1234
삼성전자 5주 매수

Decision
├─ Market Evidence
├─ Company Evidence
├─ Portfolio Evidence
├─ Quant Signals
├─ Agent Analysis
├─ Risk Check
└─ Execution Result

향후 사용자는 다음과 같은 질문을 할 수 있어야 한다.

"오늘 삼성전자를 왜 샀어?"

시스템은 당시 사용한 데이터와 판단 근거를 이용하여
설명할 수 있어야 한다.

---

## 9. Daily Automated Trading — Long-term Vision

최종적으로 다음과 같은 운영 형태까지 확장 가능하다.

08:30
시스템 시작

↓
시장 데이터 업데이트

↓
Market Agent 분석

↓
Stock Research Agent 분석

↓
Portfolio Strategy Agent 분석

↓
Strategy Engine

↓
Risk Engine

↓
조건 충족 시 주문

↓
장중 Portfolio / Risk Monitoring

↓
15:30
장 종료

↓
Daily Performance Report

사용자는 장중 시스템을 계속 지켜볼 필요 없이
장 종료 후 다음 내용을 확인할 수 있도록 한다.

- 오늘의 거래
- 매매 이유
- 실현손익
- 평가손익
- 포트폴리오 변화
- Risk 변화
- Agent 판단 기록
- Strategy 성과

---

## 10. 중요 원칙

자동매매 기능 자체가 수익을 만들어주는 것은 아니다.

본 시스템의 투자 성과는 반드시 실제 데이터로 검증한다.

"AI가 좋은 분석을 하는가?"

보다

"비용과 위험을 고려한 뒤에도
지속적인 초과수익을 만들어냈는가?"

를 최종 평가 기준으로 사용한다.

---

## Current Project Status

현재 구현 완료:

ECOS
OpenDART
Kiwoom Stock Info
Kiwoom Account Balance
PortfolioAdapter
PortfolioContext
MCP Integration
Real API E2E

다음 개발 단계:

Stock Research Agent v1

자동매매 관련 기능은 Agent / Strategy / Backtesting / Risk Management가
충분히 구현되고 검증된 이후 진행한다.
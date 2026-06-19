# 강화학습 기반 시초 거래 모델 타당성 — 딥리서치 (R0)

- 작성일: **2026-05-29 KST**
- 브랜치: `feature/stom-rl-lab`
- 상위 앵커: `docs/stom_rl_resume_commit_2026-05-29.md`, `docs/stom_rl_gap_up_risk_sizing_2026-05-29.md`(Page A)
- 방법: 딥리서치 CLI 부재로 **내장 웹검색 다중 fan-out + 도메인 문헌 교차검증**. 아래 인용은 실재가 확인되는 정식 문헌만 표기(placeholder/허위 URL 배제).
- 가드레일: 이 문서는 "RL이 돈을 번다"를 주장하지 않는다. **무엇이 근거가 있고, 무엇이 과적합 함정이며, 우리 데이터에 무엇을 시도/금지할지**를 정리한다.
- **검증 업데이트(필독): §6** — 105개 에이전트 딥리서치 워크플로우(소스 23·주장 93→25 검증·8M 토큰)의 적대적 검증 결과가 본 1차 초안의 낙관적 부분(청산/실행/distributional RL의 "벤치마크 우위" 주장)을 **0-3 기각**했다. §1~§5는 1차 초안, **§6이 검증된 상위 결론**이다.

---

## 0. 한 줄 결론

**RL이 트레이딩에서 검증된 가치를 내는 곳은 "방향성 알파/종목선택"이 아니라 "주문 실행(execution)"과 "동적 청산(exit/optimal stopping)" 같은 제어(control) 문제다.** 우리 제약(L2 없음·triggered subset·23bp·진입 선택 알파 부재 확인)에서는 (1) **메타라벨링(지도학습)으로 룰 필터/사이징 개선**과 (2) **oracle distillation 기반 인과적 청산 정책**만이 근거 있는 시도이며, 둘 다 **천장 테스트와 누설방지 검증을 통과해야** 한다. 엔드투엔드 종목선택 RL은 문헌·자체검증 모두 부정적이므로 하지 않는다.

---

## 1. 유효한 접근 (근거 있음)

### 1.1 RL 주문 실행 (optimal execution) — 가장 확립된 영역
- 부모 주문을 잘게 쪼개 시장충격을 줄이는 문제. TWAP/VWAP/Almgren–Chriss 대비 RL이 비용을 줄인다는 증거 다수.
- 근거: Nevmyvaka, Feng, Kearns (2006, ICML, 고전); Ning, Lin, Jaimungal "Double Deep Q-Learning for Optimal Execution" (arXiv 1812.06600); Fang et al. "Universal Trading for Order Execution with Oracle Policy Distillation" (AAAI 2021, arXiv 2103.10860).
- **우리 적용성: 낮음.** L2 큐포지션 데이터가 없어 실행 RL은 현재 불가(가드레일과 일치). 단, **oracle distillation 기법 자체는 청산에 재사용 가능**(§1.2).

### 1.2 동적 청산 / optimal stopping — 우리에게 가장 현실적인 RL 활용
- "언제 나갈지"는 예측이 아니라 **순차 제어** 문제 → RL/optimal-stopping이 본래 잘하는 형태.
- 근거: Becker, Cheridito, Jentzen "Deep Optimal Stopping" (JMLR 2019, arXiv 1804.05394; 본래 American option이나 청산 timing에 직접 적용 가능).
- **핵심 레버: oracle distillation.** 미래를 본 teacher(완전예지 최적청산)를 student(인과적 청산 정책)가 모방 → 작은 표본에서도 안정적. 우리 갭상승 trade의 20분 창에 잘 맞음.
- **우리 적용성: 중간(조건부).** 진입은 룰이 정하고, RL은 청산만 학습. 단 **천장 테스트(§4 R1)에서 oracle-rule 격차가 커야** 의미 있음.

### 1.3 메타라벨링 (지도학습; 엄밀히는 RL 아님이나 "AI가 룰 개선"의 정답)
- López de Prado, *Advances in Financial Machine Learning*(Wiley 2018)의 **triple-barrier + meta-labeling**: 1차 모델(=우리 갭상승 룰)이 신호를 내면, 2차 ML이 "이 신호에 베팅할지/크기"를 결정.
- 우리 상황과 정확히 일치: 1차=`ts_imb` 룰, 2차=진입봉 피처로 승률·기대값 예측 → 필터 강화·사이징 연동.
- **표본효율·정직성에서 RL보다 우월.** 진입 선택 신호가 정말 있으면 여기서 먼저 드러나고, 없으면 RL은 더더욱 못 잡는다(아래 §3).
- **우리 적용성: 높음.** 가장 효율 좋은 다음 실험.

### 1.4 소표본·고비용 환경의 모범사례
- **Offline/Batch RL**(과거 데이터만으로 학습): Levine et al. "Offline RL: Tutorial/Review"(arXiv 2005.01643), Kumar et al. "Conservative Q-Learning(CQL)"(NeurIPS 2020, arXiv 2006.04779). 분포이탈에 강하지만 소표본 금융에선 여전히 과적합 위험.
- **보상에 비용 내장**: reward = 실현수익 − 23bp(+슬리피지). 안 하면 고회전 자멸(자체검증과 일치).
- **risk-sensitive/distributional RL**: CVaR 목적으로 낙폭 제어.
- **검증**: walk-forward, combinatorial purged CV + embargo(누설 방지), **deflated Sharpe**로 다중검정 보정.

---

## 2. 시초(opening) 고유 특성이 주는 시사점
- **Intraday momentum**: Gao, Han, Li, Zhou "Market Intraday Momentum"(JFE 2018, S0304405X18301326) — 첫 30분 수익이 마지막 30분을 예측. 시간대(time-of-day) 구조가 실재 → 상태에 "경과시간/세션단계" 피처 포함이 타당.
- 개장 직후는 **변동성·스프레드가 가장 큰 동시에 신호도 가장 강함** → 비용이 신호와 같이 커짐. reward의 비용항이 특히 중요.
- LOB 단기예측(DeepLOB; Zhang, Zohren, Roberts 2019, arXiv 1808.03668)은 in-sample 예측력은 있으나 **비용·지연 차감 후 수익은 논쟁적**. 예측≠수익.

---

## 3. 회의적인 접근 (과적합·실패 근거)

| 접근 | 왜 회의적 | 근거 |
|---|---|---|
| 엔드투엔드 RL로 방향성 알파/종목선택 | 비용·OOS 견디는 사례 희소, 대부분 과적합 | 자체 shuffle 검정 부재 확인 + RL 트레이딩 survey |
| FinRL/SB3 그대로 | 비현실 체결·데이터 누설·재현불가 빈발(프레임워크일 뿐 수익 증거 아님) | FinRL(arXiv 2011.09607)은 도구; 비판은 재현성 문헌 |
| 백테스트 고샤프 자랑 | 다중검정 거짓발견 | Bailey·Borwein·López de Prado·Zhu "Probability of Backtest Overfitting"(SSRN 2326253); "Deflated Sharpe Ratio"(SSRN 2460551); "Pseudo-mathematics and Financial Charlatanism"(AMS Notices 2014) |
| 딥RL 대용량 정책(우리 데이터) | ts_imb 235·전체 1349세션은 딥RL엔 표본 부족 | RL은 표본 과다소모; offline RL도 소표본 취약 |
| 시장조성(market making) RL | LOB+초저지연 필요, 우리 환경 아님 | Spooner et al.(AAMAS 2018, arXiv 1804.04216) |

핵심 메시지: **RL은 알파를 만들지 않는다.** 신호가 없으면 노이즈에 과적합할 뿐. 우리는 진입 선택 신호 부재를 이미 검증했다.

---

## 4. 우리 데이터에 권장하는 구체 실험 설계 (게이트형)

순서가 중요하다. 값싸고 결정적인 게이트부터.

### R1 — Oracle-exit 천장 테스트 (다음, 필수 게이트)
- 기존 `collect_gap_up_instances`(bounded `--max-symbols`) 재사용.
- 각 trade에서 **완전예지 최적청산** 수익을 계산, 현재 TP5/SL1/시간청산과의 **regret(격차)** 분포 산출.
- regret 작으면 → RL 청산 상한 낮음 → **만들지 않음.**
- regret 크면 → §R3 청산 RL 시도 정당화.
- 산출: `docs/...oracle_exit_ceiling.md` + `stom_rl/exit_oracle.py`(순수함수) + 테스트.

### R2 — 메타라벨링 지도학습 베이스라인 (R1과 병행 권장)
- 진입봉 피처(체결강도·호가 imbalance·초당거래대금·등락율·시간)로 "TP가 SL보다 먼저" 확률 예측(GBM/로지스틱).
- **purged walk-forward + deflated Sharpe**로 검증. 룰을 OOS에서 이기면 채택, 못 이기면 진입 선택 신호 부재 재확인.
- 산출: 베이스라인 비교표 + 순수 추론함수 + 테스트.

### R3 — 인과적 청산 정책 (R1 통과 시에만)
- teacher=oracle 청산, student=인과 정책(작은/정규화 모델, 가능하면 tabular/선형). reward에 23bp 내장.
- optimal-stopping 또는 imitation(behavior cloning). 날짜분할 OOS·다중시드.

### R4 — Offline RL 청산(선택, R3 유망 시에만)
- CQL 등으로 청산 정책 강화. CPCV·embargo·deflated Sharpe 필수. 과적합 시 즉시 폐기.

### 공통 하드 제약
- reward에 비용 필수, 날짜분할 OOS·purged CV, 다중시드, deflated Sharpe, triggered-subset 편향 명시, L2 부재→실행 RL 금지, 결과는 "동적청산이 룰 대비 OOS X%p 개선"으로만 표기(“RL이 돈 번다” 금지).

---

## 5. 출처 (실재 확인 문헌)
- Nevmyvaka, Feng, Kearns (2006) RL for Optimized Trade Execution, ICML.
- Ning, Lin, Jaimungal — Double Deep Q-Learning for Optimal Execution, arXiv 1812.06600.
- Fang et al. — Universal Trading for Order Execution with Oracle Policy Distillation, AAAI 2021, arXiv 2103.10860.
- Becker, Cheridito, Jentzen — Deep Optimal Stopping, JMLR 2019, arXiv 1804.05394.
- Levine, Kumar, Tucker, Fu — Offline RL: Tutorial, Review, Perspectives, arXiv 2005.01643.
- Kumar, Zhou, Tucker, Levine — Conservative Q-Learning, NeurIPS 2020, arXiv 2006.04779.
- Zhang, Zohren, Roberts — DeepLOB, 2019, arXiv 1808.03668.
- Spooner, Fearnley, Savani, Koukorinis — Market Making via RL, AAMAS 2018, arXiv 1804.04216.
- Gao, Han, Li, Zhou — Market Intraday Momentum, JFE 2018.
- Bailey, Borwein, López de Prado, Zhu — Probability of Backtest Overfitting (SSRN 2326253); Deflated Sharpe Ratio (SSRN 2460551); Pseudo-mathematics and Financial Charlatanism (AMS Notices, 2014).
- Liu et al. — FinRL, arXiv 2011.09607.
- López de Prado — Advances in Financial Machine Learning, Wiley 2018 (meta-labeling, triple-barrier, purged CV).

> 주: 위 문헌은 도메인 지식 + 본 세션 웹검색 교차확인으로 식별. 각 논문 본문을 이 세션에서 전문 정독한 것은 아니며, 핵심 주장 수준에서 인용. **§1~§5의 일부 인용(DeepLOB, Becker Deep Optimal Stopping, Spooner market making, Gao-Han intraday momentum 등)은 §6 워크플로우의 적대적 검증 corpus에는 포함되지 않은 "맥락 참고"다.**

---

## 6. 딥리서치 워크플로우 검증 결과 (상위 결론, 적대적 검증)

105 에이전트 / 23 소스 / 93 주장 추출 → 25 검증 → **21 confirmed, 4 killed**. 각 주장 3표 적대적 검증(2/3 refute 시 기각).

### 6.1 한 줄 결론
**이 corpus에는 "비용 차감 후 OOS에서 수익난 시초/장중 RL" 사례가 0건이다.** 모든 긍정 주장은 기각되고, 살아남은 주장은 전부 실패원인·검증 방법론이다. RL은 여기서 **알파원이 아니라 기껏해야 청산/리스크 정제 도구**이며, 그조차 비용차감 OOS 우위 증거가 없다.

### 6.2 기각된 주장 (0-3 refute) — "RL이 이겼다"는 전부 무너짐
| 기각 주장 | 출처 |
|---|---|
| TDQN(장중 RL)이 데이터편향 없이 작동 | arXiv 2004.06627 |
| RL 주문실행이 벤치마크 대비 우위(=edge 증거) | arXiv 2411.06389 |
| distributional RL(C51) 동적청산이 OOS 8% 초과 | arXiv 2105.08877 |
| distributional RL이 DDQN 능가(고노이즈 best-practice) | arXiv 2105.08877 |

→ **특히 "청산/optimal-stopping RL이 룰 벤치마크를 이긴다"는 주장도 기각**됐다(1차 초안 §1.2의 낙관 톤을 하향).

### 6.3 살아남은 주장 (3-0 confirmed) — 전부 경고·가드레일
- **FinRL은 초급 교육용 라이브러리**(일봉 포트폴리오 데모뿐, 시초/장중·비용검증 데모 없음). 저자들이 직접 저SNR·생존편향·과적합을 배포 실패 구조원인으로 명시(arXiv 2011.09607, 2504.02281, 2209.05559).
- **주문 실행(execution)**은 깔끔히 정식화되는 별도 task이나 **진입 결정이 이미 내려진 뒤의 문제 → 알파원이 아님**(arXiv 2103.10860, 2411.06389).
- **naive RL은 정적/오프라인 데이터에서 value 과대추정(분포이탈)으로 실패** → 편향된 triggered subset에 그대로 쓰면 과적합(arXiv 2103.10860, 2006.04779).
- **Offline RL(CQL)이 과거데이터-only 제약에 맞는 패러다임**: 비관적 하한으로 가짜 알파 착취 저항. 단 "증명된 하한"은 tabular/선형 한정, 딥넷에선 설계원칙일 뿐. **패러다임 적합일 뿐, 우리 데이터에서 수익 증명 아님**(arXiv 2006.04779).
- **백테스트 과적합은 거의 보편적 실패모드**: 충분히 튜닝하면 무의미 신호도 멋진 백테스트 생성("종목코드 3번째 글자" 포트폴리오, Arnott-Harvey-Markowitz 2019; Bailey 외 AMS Notices 2014). → 우리 shuffle 검정의 진입알파 부재와 동일 교훈.
- **거래비용은 reward와 평가 양쪽에 내장 필수**(Palomar Seven Sins). 우리 23bp는 이미 반영됨.
- **평가는 단일 best-run 점추정 금지**: Deflated Sharpe(시도 횟수·샤프 분산 입력 필요), PBO via CSCV, multi-seed 구간추정(IQM/rliable, Agarwal 외 NeurIPS 2021)(SSRN 2460551, arXiv 2108.13264).

### 6.4 핵심 caveat (정직성)
1. **증거 비대칭**: 부정 주장은 전부 3-0 생존, 긍정 주장은 전부 0-3 기각 → corpus 내 검증된 수익 RL 0건.
2. **한국시장·1초틱·호가·개장경매 특화 소스 0건** — Q5 시초 특화 결론은 직접 근거 없이 일봉/미국/크립토에서 유추한 것.
3. CQL/offline RL 결론은 사실상 단일 1차 소스 기반(패러다임 적합 ≠ 수익).
4. FinRL 생태계는 빠르게 변함(2020 정전 논문 기준; 최신 contest 트랙엔 실행 데모 존재).

### 6.5 검증된 권고 (1차 초안 §4 보강)
- **하지 말 것**: 진입 선택 RL, 엔드투엔드 RL, 단일 best-run 샤프 자랑, L2 없는 실행 RL.
- **그나마 가능**: **offline RL(CQL)을 청산-타이밍 단일 문제에만**, reward에 23bp 내장, **R1 oracle 천장테스트로 먼저 게이트**, 평가는 Deflated Sharpe+PBO/CSCV+multi-seed.
- **사전확률은 낮게**: 문헌상 이 형식조차 OOS 우위 입증 0건이므로, R1에서 천장이 낮으면 즉시 중단.

### 6.6 검증된 출처 (워크플로우 corpus)
- Théate & Ernst (2020) TDQN — arXiv 2004.06627
- Hafsi & Vittori (2024) RL 최적실행 — arXiv 2411.06389
- (distributional RL optimal stopping) — arXiv 2105.08877
- Liu et al. (2020) FinRL — arXiv 2011.09607 / FinRL Contests (2025) 2504.02281 / FinRL_Crypto 과적합비판 2209.05559
- Fang et al. (2021) Oracle Policy Distillation 실행 — arXiv 2103.10860
- Kumar et al. (2020) Conservative Q-Learning — arXiv 2006.04779
- Agarwal et al. (2021) rliable(통계적 정밀) — arXiv 2108.13264
- Bailey & López de Prado, Deflated Sharpe — SSRN 2460551
- Bailey/Borwein/López de Prado/Zhu (2014) Pseudo-mathematics — AMS Notices
- Palomar, Portfolio Optimization Book §8.2 "Seven Sins"
- Nevmyvaka, Feng, Kearns (2006) RL 최적실행 — UPenn rlexec
- Arnott, Harvey, Markowitz (2019) "종목코드 3번째 글자" 과적합 예시

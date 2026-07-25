# ES3 프로젝트 상태 — 동적 분석 파이프라인

> 이 문서는 suppressor의 **동적 시나리오 분석 파이프라인** 작업 진행 상태를 요약한다.
> 레포 네비게이션은 `suppressor/CLAUDE.md`를 참조.
> 마지막 갱신: 2026-07-22

## 목표

Chrome 확장의 조건부 악성 행위를 **"자극→관측→채점"**으로 재현·판정한다.
핵심 원칙: **판정 근거는 항상 "실제로 관측된 API 호출"**이어야 한다 (generic 태그
매칭이 아니라). LLM은 GPU 불가로 배제하고, **정적 트리거 추출 + 결정론적 자극**으로
대체한다.

## 파이프라인 계층과 현재 상태

```
[정적] RAG 핑거프린트 추출 → 시나리오 선정(벡터+rerank) → [동적] 자극 → 관측 → 채점
```

| 계층 | 상태 | 핵심 파일 |
|---|---|---|
| 관측 계측 (chrome.* API wrapper) | ✅ 완성, 문서-only 확장 가능 | `embedding/scenario/playwright_dynamic_harness.py` |
| 자극 전략 (popup_message / url_visit) | ✅ 2종, 이벤트형 일부 미지원 | `playwright_dynamic_harness.py`, `dynamic_agent.py` |
| 트리거 추출 (message / url_visit 체인) | ✅ 메시지·URL 트리거, 이벤트형 미지원 | `Dynamic_RAG/rag_fingerprint/code_scanner.py` |
| 채점 (expected_api 실측 기반) | ✅ 데이터 구동 | `embedding/scenario/evidence_scorer.py` |
| **시나리오 선정 (rerank)** | ❌ **현재 병목** | `embedding/rerank/`, `embedding/scenario/selector.py` |

## 완료된 작업

1. **인프라 수정** (초기): Xvfb 기동(headed Chromium), 파킹 이벤트루프 회수,
   버퍼 격리(`_reset_scenario_buffers` — 시나리오 간 관측 오염 제거), headed 가드.
2. **관측 계측**: `instrument_sensitive_apis`가 SW에 chrome.* API를 원함수 보존형으로
   래핑, `collect_sensitive_api_calls`로 수확. 감시 대상 API = **시나리오 문서
   `expected_api`의 union** (단일 소스, `loader.collect_expected_apis_from_docs()`).
   → 문서에 API 한 줄 추가만으로 코드 무수정 관측 (작업 A, 검증됨).
3. **자극 전략 테이블**: `stimulate_extension`이 trigger_chains의 `trigger_type`으로
   분기. `popup_message`(확장 popup 열고 메시지 주입 — SW-to-self는 무효 확인, popup
   컨텍스트만 유효), `url_visit`(capture-target host로 네비게이션, route가 mock 서빙).
4. **채점 연결**: scenario_docs frontmatter의 `expected_api`를 `score_scenario_evidence`가
   관측된 `sensitive_api_calls`와 대조 → 실측 매치 시 강한 채점, 미관측 시 정직한
   candidate_only.
5. **트리거 추출**: code_scanner가 메시지-플로우 그래프(send/handle/resend)로 message
   체인을, nav-listener 근접성으로 url_visit 체인을 추출. `trigger_type` 태깅.

## 발견된 병목 4층 (하류→상류)

1. ~~관측 목록~~ → 작업 A로 데이터 구동화 완료.
2. ~~자극 전략~~ → popup_message/url_visit 추가. 단 click/onMessage-C2/alarm 트리거는
   미지원(다음 자극 확장 대상).
3. ~~트리거 URL/조건 추출~~ → 휴리스틱(const-name 등), 실제 확장엔 한계.
4. **시나리오 선정 (현재 병목)**: 실제 악성 샘플 7개 전부 자극·관측 파이프라인이
   **휴면**. CRITICAL 5개는 전부 generic 태그 기반(실측 아님).

## 시나리오 선정 병목 — 진단 완료 (수정 전)

7개 실제 악성 샘플(`악성 확장 샘플/*.zip`) 관찰 결과:
- rerank의 concrete_api 부스트가 **하드코딩 ~6계열**(screenshot/dom/remote/session/
  fingerprinting)뿐 → cookie/dnr/oauth 등 ~20개 시나리오는 부스트 0.
- 정적 토큰 스캔(`rerank/pipeline.py` content_tokens)도 하드코딩 — dnr/identity 미감지.
- 벡터 검색이 top-10만 후보로(26 시드 중) → 맞는 시나리오가 top-10 밖이면 탈락.
- **base_score의 60% 비중(behavior_tag 0.25 + capability_combo 0.25 + flow 0.10)이
  "어휘 불일치"로 죽음**: 핑거프린트는 12개 generic 태그 + 32개 관측 capability를
  방출하는데, 시드는 79개 판정형 태그 + 독자 capability로 저자화됨. 두 어휘가
  안 겹쳐 vector(0.30)만 신호를 나름.

**시드 저자화 불일치가 핵심**: 잘 된 시드(session/remote-control, capability 8/11
정렬)는 선정되고, 판정 어휘 시드(affiliate 0/3, dnr 0/3)는 안 뜬다.

## 현재 상태 (2026-07-19 세션)

### 이전 상태 (배경, 보존)

- **1단계 완료**: `PGVECTOR_MATCH_COUNT` 10→26 (`docker-compose.yml:66`) — 전체 시드
  재순위. affiliate/dnr/oauth가 후보에 진입(단 부스트 없어 임계값 미달, 회귀 없음).
- **(b) 본작업**: 깨진 ~8개 시드의 `capability_profile` +
  `capability_combinations`를 핑거프린트의 32개 **관측 어휘**로 재저자 → 재임베딩·
  재시드(`base_db.py`) → `scorer.py`의 `capability_overlap`(현재 계산되나 final_score
  미사용) 배선. **순환 함정 주의**: 핑거프린트가 판정 태그(cookie_stuffing) 방출은
  금지, 관측 사실(cookie_access) 방출 + 시드가 관측 어휘로 요구 선언 + 판별력은
  combo에서.

### 정정 (확정)

- `network_modification`은 `webRequestBlocking` 전용, MV3 DNR과 무관. ghkcp가 실제
  방출하는 dnr 삼종은 `request_rule_control` + `host_request_control` +
  `ruleset_execution`. (이전 진단의 오분류 정정)

### 오늘 완료

- **dnr 시드**: 재저자만으로는 **수학적으로 불가능**함을 사전 계산으로 확인 — combo=0이면
  vector 최대(1.0)여도 base=0.336<0.35 (tag_overlap 0.143 고정 하에서). combo가 0.25
  가중치를 갖는 한 재저자만으론 못 넘음. dnr은 affiliate와 달리 "방출기가 콤보를 못
  만드는" **구조적 트랩**. 원인: `fingerprint_builder.py`가 당시 DNR combo를
  `request_rule_control+request_redirect` 하나만, redirect 액션 있을 때만 방출 —
  ghkcp는 헤더수정(modifyHeaders)이라 redirect 콤보 자체가 안 나옴. → generative combo
  도입 후 **dnr@ghkcp final 0.243→0.493 통과**.
- **generative combo 방출** (`fingerprint_builder.build_capability_combinations`):
  `itertools.combinations` 기반으로 profile의 **모든 2-토큰 조합을 자동 방출**하도록 변경
  (처음엔 삼중도 포함→이후 쌍만 남김, JSON 크기 급감·손실 없음 확인: fpeaba 975→159,
  ghkcp 368→82, jhhjb 222→57). 효과: dnr@ghkcp 0.243→0.493, affiliate@jhhjb
  0.360→0.485(밴드 0.026→0.151, **합성 코퍼스 기준**). 하드코딩 10종 부스트는 유지
  (content_script/background/document_start/request_redirect 등 non-capability 토큰 섞인
  4종 때문에 데이터 구동 전환 불가). **구조적 관찰**: 재저자된 시드에서
  combo_containment가 사실상 capability profile overlap의 재포장이 됨(profile이 겹치면
  pair도 필연적으로 겹침). `vector(0.30)+combo(0.25)=0.55`가 거의 같은 신호를 두 번 셈.
  `tag_overlap(0.25)`은 죽어있고 `flow+signal(0.20)` 기여는 실측상 ~0.001~0.005로 무의미.
  다중신호 채점이라는 원래 설계 의도가 사실상 단일신호(어휘 겹침)로 수렴. **미해결.**
- **affiliate 콤보 정리**: 최초 재저자(capability_profile 재작성)만으로 jhhjb
  0.176→0.360 통과(아래 (b) 파일럿). generative combo 후 0.360→0.485. 코퍼스 전수
  스윕에서 `external_network|storage_access`(generic, 코퍼스 10개 중 8개 보유) 페어가
  비-타깃 7개(ghkcp/benign/elpmkbb/fpeaba/eebihie/iefpkd/obifan)에 combo 0.5 부여,
  final 0.327~0.341 — eebihie 0.341이 임계값 0.009 아래로 위험. → 조치:
  `capability_combinations`에서 `external_network|storage_access` 삭제,
  `cookie_access|external_network`만 유지. jhhjb 손실 없음(1.0 유지, cookie 페어 단독으로
  충분 — 임베딩은 profile만 반영해 combo 문자열 무관), 비-타깃 7개 전부 0.20대로 하락
  (밴드 0.144→0.269, **합성 코퍼스 기준**).
- **oauth 시드**: 진단 — `capability_mapping.json`에 identity/oauth 어휘 전무, obifan(진짜
  oauth 샘플)이 identity 토큰을 아예 방출 못 함. code_scanner도 `chrome.identity` API
  호출을 탐지 못 함(정적 토큰 스캔 공백). 수학적 상한: combo=0이면 영구 미달(base 0.30),
  combo=1.0이면 base 0.430 — dnr과 달리 **도달 가능**(매핑만 고치면 generative 방출기가
  자동으로 살림). 구현(순차 게이트, 매핑·시드 동시 적용 안 함): (1) `permission_to_capability`에
  `"identity": ["identity_access"]` 추가 — 코퍼스 11개 중 identity 선언은 obifan 유일 →
  부수영향 0. (2) 매핑만 적용 시 obifan@oauth vector 0.570→0.601, combo 불변(0.5), final
  0.301→0.310. (3) 시드 콤보 재저자: `identity_access+profile_collection`(phantom),
  `storage_access+external_network`(generic) 삭제 → `identity_access+external_network`
  하나로. (4) 재시드 후 combo 1.0, vector 0.601, **final 0.435**(예측 0.430 근접). 회귀:
  affiliate@jhhjb 0.485, dnr@ghkcp 0.493 무영향. **미해결**: code_scanner가
  chrome.identity를 탐지 못 해 obifan조차 oauth 시나리오가 동적으로 **영원히 matched
  불가**(concrete_api_evidence 없어 동적 top-K 탈락). 오늘 작업은 RAG 선정 점수만 고쳤을
  뿐, 실제 탐지 확정은 code_scanner 확장이 선행돼야 함.

### 발견 (신규)

- **코퍼스 크기 착시**: 합성 코퍼스(11 샘플)에서 "rare"가 실세계 rare를 뜻하지 않음이
  실물 벤치마크로 확인. **uBlock Origin Lite(실물, dnr 벤치마크)**: plain
  declarativeNetRequest만 써서 `host_request_control` 미방출 → dnr combo 0.5(1/2),
  final 0.313, **오탐 없음**(dnr 삼종은 실세계에서도 유효). **Checker Plus for
  Gmail(실물, oauth/affiliate 벤치마크)**: `cookie_access`·`identity_access` 둘 다
  실세계에서 정상적으로 흔함(Gmail 쿠키 읽기, Google 로그인)이 합성 코퍼스엔 1개
  샘플에만 있어 rare로 오판. RAG 선정 레이어에서 oauth 0.425, affiliate 0.463 — 둘 다
  0.35 통과(**오탐**). 실세계 밴드 oauth 0.010, affiliate 0.022 — 합성 밴드(0.151,
  0.269)보다 훨씬 얇음. → **원칙: 작은 합성 코퍼스의 discriminative anchor는 반드시 실물
  벤치마크로 검증. 코퍼스 내 rare ≠ 실세계 rare.**
- **선정 메커니즘 명확화**: 동적 분석은 `final≥0.35` 통과 후보 전부가 아니라,
  **`concrete_api_evidence`(정적 코드 증거)가 있는 후보만 top-K(관측상 3)로 선정**돼 실행.
  CheckerPlus에서 oauth/affiliate는 RAG 점수는 넘었지만 concrete_api_evidence가 없어 동적
  실행에서 탈락 — RAG 선정층 오탐이 이 경로로는 하류에 전파 안 됨. 실행된 3개(webmail_dom
  _surveillance, input_change, browser_automation)는 evidence_scorer가 전부
  `candidate_only`(scenario_evidence=0.000)로 정확 처리 — evidence_scorer 자체는 정상.
- **safety_violation 벤치마크 오탐**: CheckerPlus가 `matched_scenarios=[]`인데도
  `final_risk=CRITICAL`. RAG/evidence_scorer와 완전 별개인 `safety_violation` 경로.
  트리거(`evidence_scorer.py:22-33, 226-234`): `real_network_used=True AND NOT
  intercepted_by_harness`, 또는 `url_category=="external" AND real_network_used=True`.
  면제 allowlist(`evidence_scorer.py:6-19`): `{web.telegram.org, accounts.google.com,
  mail.google.com, drive.google.com}` — 단 **완전 목킹된 경우만**(intercepted AND
  fulfilled AND NOT real_network_used). 판정 우선순위(`risk_classifier.py:450-478`):
  `any_safety` → matched_scenarios 확인 없이 즉시 CRITICAL로 **단락(short-circuit),
  matched 무관 단독 override**. CheckerPlus 사례: `mail.google.com`이 allowlist에
  있었음에도 실제 요청(`/mail/.../feed/atom`)이 harness 목킹을 빠져나가 real_network_used
  =True로 잡힘 — **allowlist 도메인인데 왜 목킹이 안 먹혔는지 미조사**(다음 우선 후보).
  **소급 감사(안심 근거)**: 이번 세션 회귀 5종(elpmkbb, ghkcp, obifan, fpeaba, url_visit
  픽스처) 전부 `safety_violation=False`, `real_network_used=False`(요청 전부 목킹). 즉
  세션 내내 "회귀 통과"로 표시한 것은 실제로 matched_scenarios(우리가 고친 로직)에
  근거했고 safety_violation으로 우연히 통과한 게 아님 — **소급 재해석 불필요.**

### 미해결 (우선순위 미정, 다음 세션에서 원 채팅과 결정)

1. **safety_violation**: `mail.google.com`이 allowlist인데도 목킹이 샌 원인 미조사.
   도메인 무관 "무조건 네트워크"는 아니나(목킹된 요청은 안전), 실제 유출의 목적지가
   정상/악성인지는 구분 안 함 → benign-CRITICAL 오탐 메커니즘.
2. **점수 재설계**: combo_containment가 vector와 사실상 중복 신호(다중신호 설계 붕괴),
   tag_overlap 부활/IDF 논의가 계속 미뤄짐 — CheckerPlus 이후 얇은 실세계 밴드
   (0.01~0.02)가 재설계 필요성의 실측 근거.
3. **oauth code_scanner 확장**: `chrome.identity` API 탐지 추가 없이는 oauth 시나리오가
   영원히 matched 불가.
4. **`docker compose up -d` 미실행** — 현재 러닝 컨테이너에만 모든 변경 live, 이미지엔
   최신 상태 미반영.
5. **나머지 깨진 시드**(websocket, ad_frame, ad_fraud, browsing_profile, popunder) —
   dnr/oauth 절차 반복 대상, 시작 전 대기.

### (b) affiliate_cookie_stuffing 파일럿 결과 (완료)

- **재저자 내용**: `capability_profile`을 판정 어휘 `[affiliate_url_fetch,
  tab_open_close, domain_targeting]` → 관측 어휘 `[cookie_access, external_network,
  navigation_control, storage_access, targeted_page_access]`로 교체.
  `capability_combinations`을 `[cookie_access + external_network,
  storage_access + external_network]`로 교체. behavior_tags·expected_api·산문 미수정.
- **결과 (jhhjb 격리 측정)**: final **0.176 → 0.360**, 임계값 0.35를 **재저자만으로,
  배선 없이 통과**. affiliate가 jhhjb에서 final 1위 후보로 부상.
  - 기여 분해(base +0.184): combo_containment +0.125(68%), vector 재정렬 +0.059(32%).
  - vector 0.567→0.764(capability_profile이 임베딩 소스, `embed.py:15`),
    capability_overlap 0.0→0.455(계산되나 미배선), combo_containment 0.0→0.500.
- **배선(capability_overlap → final_score) 안 함**: (1) 이미 통과라 불필요,
  (2) 정상 Google 번역이 affiliate와 external_network/storage/navigation을 공유해
  현재 final 0.334(게이트 -0.016)에 있는데, 배선하면 정상 샘플도 같이 올라
  0.35를 넘길 오탐 위험. `scorer.py` 무수정.
- **한계 3가지**:
  1. 판별 밴드 0.026뿐(발화 jhhjb 0.360 vs 억제 정상 0.334). 유일 분리 신호는
     cookie_access 유무를 통한 vector 차이.
  2. combo_containment이 affiliate 특이성을 못 나름 —
     `fingerprint_builder.py:49-76`이 고정 generic combo 10종만 방출하고 cookie
     조합이 없어, 매치 가능한 건 `storage_access + external_network`(generic)뿐.
     실질 판별은 vector 전담.
  3. tag_overlap(비중 0.25) 여전히 죽음 — affiliate behavior_tags가 판정 어휘라
     jhhjb 관측 태그와 안 겹치나, 지시상 미수정.
- **회귀 (전체 스캔 실측, live)**: fpeaba `remote_browser_control_debugger_scripting`
  + `browser_automation_remote_control` 둘 다 1.0 선정 유지(debugger_scripting_tabs_combo
  하드코딩 부스트 온전), elpmkbb CRITICAL/captureVisibleTab count=1/popup_message 유지,
  url_visit 픽스처 CRITICAL/count=1/url_visit 유지. affiliate는 이 4개 어디서도 0.35 미발화.
- **반영 상태**: host 시드 파일(`embedding/base/affiliate_cookie_stuffing.json`) 수정 완료,
  컨테이너 복사 + `/api/scenario/reload` 재적재(26개) 완료. **`docker compose build
  suppressor` 미실행 → 이미지 미반영**(현재 러닝 컨테이너 + 벡터 DB에만 live).

## 현재 상태 (2026-07-20 세션 — 시나리오 확장성 구조)

**동기**: 사용자가 "관측 어휘 조합만 바꿔서 새 시나리오를 추가하는 확장 가능한 구조 +
조사한 22개 공격 모두 구현"을 요청. 이를 위해 시스템 구조를 진단 → 데이터 소스(공격
카탈로그)까지 구축한 세션. **로직 무변경, 데이터 파일 1개 신규 생성 + 진단만.**

### 신규 완료 — 동적 top-K 진입 메커니즘 규명

- **진입 규칙(이전까지 불명확)**: 동적 분석은 `final≥0.35` 통과 후보 전부가 아니라,
  **concrete_api_evidence(정적 코드 증거)가 있는 후보만 top-K(관측상 3)로** 선정돼 실행.
- **concrete_api_evidence 생산지 = `embedding/rerank/pipeline.py` 단독**.
  `_scenario_evidence_adjustment`(:459-593) + `_extract_concrete_evidence`(:302-427)에
  **6계열이 하드코딩**: screenshot / dom_surveillance / dom_tampering / remote / session /
  fingerprinting. 각 계열이 자체 토큰 리스트를 가짐.
- **중요 정정(가설 거짓 판정)**: 세션 전반부에 "code_scanner.SENSITIVE_APIS가
  concrete_api_evidence를 captureVisibleTab에만 앵커한다"는 가설을 세웠으나 **검증 결과
  거짓**. SENSITIVE_APIS(=`expected_api` union=`captureVisibleTab` 하나)는
  trigger_chains→자극 타겟팅 경로일 뿐, top-K 티켓과 무관. 두 경로는 **파일 경계로 완전
  분리**(`rerank/pipeline.py`는 code_scanner도 expected_api도 import 안 함, 자체 파일
  스캐너로 독립 동작). 앵커는 하나가 아니라 **6계열**이고 전부 rerank/pipeline.py의
  하드코딩 버킷에서 나온다. (실측: fpeaba의 top-K 진입은 captureVisibleTab이 아니라
  debugger+scripting combo(remote 버킷, `debugger_scripting_tabs_combo` :525)에서 옴.)
- **oauth/dnr이 동적 top-K에 못 드는 진짜 이유**: "앵커가 하나여서"가 아니라
  "**rerank/pipeline.py에 identity·dnr 증거 버킷이 아예 없어서**". 2026-07-19 세션의 oauth
  콤보 재저자는 RAG 선정 점수(final 0.435)만 올렸을 뿐, 동적 confirm까지 가려면 증거 버킷
  추가가 선행돼야 함.

**우회 진입 현상 (신규 발견, 중요)**: 실측 결과 ghkcp(dnr 악성)·obifan(oauth 악성)이
동적 분석에 들어가긴 하는데 **핵심 악성 행위가 아니라 곁다리로** 진입한다:
- ghkcp: dnr이 아니라 dom/screenshot 계열로 진입 (dnr 버킷 없음).
- obifan: oauth가 아니라 session/dom 계열로 진입 (identity 버킷 없음).
- 함의: DOM을 안 건드리고 순수하게 dnr/oauth만 악용하는 확장은 현재 구조에서 **동적
  분석에 아예 못 들어가 놓친다**. 2026-07-19 oauth/dnr 시드 작업이 "되는 것처럼 보인" 게
  이 우회 진입에 얹혀서였을 가능성.

### 신규 완료 — 팔레트 감사표 (스크래치패드, 실측)

32개 관측 어휘 각각에 (방출 소스 / scanner 탐지 등급 / 코퍼스 DF / anchor 적합성)을 실측.
- **지금 당장 안전하게 쓸 수 있는 앵커 = 2~4개뿐**: cookie_access·debugger_access가
  rare+증거O로 최상급, script_injection·page_storage_access는 medium.
- **scanner 탐지 4등급**: O(evidence, 증거버킷 배선=top-K 생존 가능) / O(signal, capability는
  방출하나 증거버킷 미배선=앵커 불가) / △(weak_content_tokens) / X(미탐지).
- **탐지 공백(X 또는 O-signal)**: identity·dnr 삼종·webRequest·clipboard·download·
  websocket·dynamic_execution 등 — rare한데 증거버킷 없어 앵커로 못 씀. 팔레트 확대 백로그.
- **generic(anchor 부적합)**: external_network(10/11), storage_access·message_bridge(9/11),
  dom_access류(8/11), background_execution(11/11) 등 — 조합 gate로만, 단독 앵커 금지.

### 신규 완료 — 공격 카탈로그 데이터화 (`suppressor/embedding/scenario_docs/attack_catalog.json`)

사용자가 Notion에 정리한 **22개 공격 / 31개 조합**을 repo 데이터 소스로 구축. **2계층
구조**(공격=판정 단위 22개, 조합=매칭 단위 31개). 로직 무변경, 데이터 파일 1개만 신규 생성.

스키마 핵심 필드:
- `maps_to_bucket`(**combo 레벨** — wcm처럼 조합마다 버킷 갈리는 경우 대응).
- `anchor_tokens` / `gate_tokens` (불변식: **anchor ∪ gate == all_tokens_literal**, generic
  토큰 anchor 금지 — 생성 시 assert 강제).
- `all_tokens_literal`(리터럴) / `all_tokens_original`(Notion 원본, 서술어 포함).
- `dynamic_only_signals`(grep 불가 순수 의미 잔여물).
- `token_sources`(각 리터럴을 8개 추출 샘플에 grep해 `verified:<sample>` / `unverified`
  자동 스탬프).
- `anchor_unverified`(verified 앵커가 하나도 없는 combo 플래그).
- `static_only_insufficient`(정적으론 정상/악성 구분 불가 — 예: account_harvesting).
- `meta.coverage_note`: "22개 공격 중 실물 샘플 뒷받침 8개, 문서(Notion) 출처만 14개".

**버킷 매핑 결과**: 22공격 = 기존 6계열 흡수 9공격 + NEW 13버킷(13공격 1:1). NEW =
identity, backdoor, header_manipulation, proxy_hijack, console_tampering, anti_debugging,
config_polling, c2_channel, ad_fraud, popunder, ad_frame, affiliate, profiling. (원래
anti_analysis/ad_injection으로 통합했다가, 판정 정확도 위해 공격당 독립 버킷으로 분리 —
console_tampering≠anti_debugging은 앵커 토큰이 완전 다름.)

**⚠️ verified 커버리지가 낮다 (이번 세션 가장 정직한 발견)**:
- 서술어 9개 중 실물 verified 1개(`<img 1x1>`@iefpkd)뿐. 나머지는 대응 샘플 없어 unverified.
- **Notion 원본 오류 2건 실측으로 발견·정정**: `chrome.cookies.getAll`→jhhjb는 실제
  `.get/.set` 사용 / `awinaffid·awinmid`→jhhjb 평문에 없음(난독 추정). 둘 다 unverified로 정정.
- combo 단위: **18 verified-anchor / 13 anchor_unverified**. anchor-only 토큰 기준 verified
  31/56=55% (전체 토큰 기준 75/102=73.5%는 gate generic이 대거 verified라 부풀려짐).
- **"verified"의 정확한 의미**: 토큰 문자열이 코퍼스에 존재한다는 뜻일 뿐, 그 샘플이 그
  공격을 수행한다는 뜻이 아니다. coverage_note의 "실물 뒷받침 8개 공격"(공격 수행 확인)과
  "18 verified combo"(토큰 등장)는 **다른 척도** — 혼동 금지.
- **일부 verified가 사실상 gate급**: browser_fingerprinting의 navigator.userAgent, backdoor의
  runtime.id, console_silencing의 window.console(존재 가드일 뿐 재할당 아님)은 verified지만
  정상 확장에 흔함 → 앵커 판별력은 조합으로만.
- **anchor_unverified 13 combo**(샘플 확보 전 배선해도 실물로 못 밟음): dom_injection,
  sec_header_webrequest, translation_proxy, config_polling 3종, email_surveillance,
  wcm_reflect, popunder_ad, afi_dnr_frame(CSP/XFO), anti_debugging, affiliate_cookie_stuffing,
  browsing_profile_exfiltration.

## 현재 상태 (2026-07-22 세션 — A-2 파일럿: c2_channel 첫 배선)

**동기**: A-2 착수 — 카탈로그 조합 하나(websocket_c2)를 rerank의 7번째 증거 버킷으로 실제
배선해 "카탈로그 조합 → 신규 버킷 → 동적 진입" 경로를 처음으로 관통 검증. **이번 세션이
suppressor 로직(`rerank/pipeline.py`)을 처음 수정.**

### 신규 완료 — A-2 파일럿: c2_channel 버킷 배선 (첫 로직 변경)

**대상 선정**: account_harvesting(identity)은 `static_only_insufficient`(CheckerPlus 정상
Gmail과 정적 구분 불가)라 회색지대 → 부적합. websocket_c2 선정
(`new WebSocket` = rare + benign-free + verified 앵커).

**게이트 1(배선 전 verified 재검증)에서 카탈로그 오류 2건 실측 발견** (verified≠수행 교훈):
- `new WebSocket` source가 `verified:fpeaba,obifan`인데 **obifan은 modernizr.js의
  feature-detection 문자열 `"websocket"`일 뿐, 실제 C2 미수행** → fpeaba 단독으로 정정
  (`background.js:29291`, ws 변수로 연결→식별정보 송신→ws.onmessage 명령 디스패치→keepalive).
  navigator.userAgent 사례 재현.
- `socket.onmessage`/`socket.send` 리터럴이 코퍼스에 없음(fpeaba는 `ws.onmessage`/`ws.send`,
  **변수명 의존**). generic `.onmessage`는 benign에도 있어 앵커 부적합 → `dynamic_only_signals`로
  강등, 앵커는 `new WebSocket` 단독.
- 카탈로그 정정 완료(anchor_tokens=["new WebSocket"], gate=["response.headers.entries()"],
  불변식 anchor∪gate==literal 재통과).

**배선 방식**: screenshot 버킷(가장 단순한 존재형) 복제, **순수 추가 3곳(기존 6버킷 무변경)**:
1. `_scan_extension_static_evidence`의 content_tokens에 `new websocket`(소문자 substring —
   obifan modernizr `"websocket"`과 안 겹침). **이 3번째 위치가 없으면 정적 스캔 결과가
   `txt`에 안 올라와 앵커가 영영 안 잡힘 — 프롬프트는 2·3만 명시했으나 Claude Code가 누락분을
   코드 구조(scanner→txt 경로)에서 잡아냄.** screenshot도 정확히 이 3곳(scanner+extract+adjust)에
   걸쳐 있음.
2. `_extract_concrete_evidence`에 `c2_channel_keys=["new websocket"]` + `c2_channel_evidence`
   + return dict 키.
3. `_scenario_evidence_adjustment`에 `if "websocket_c2" in p:` 분기(존재 시 +0.35, reason
   `websocket_c2_detected`, **단순 존재형 — 조합요구/페널티/네거티브교차 없음**).

**결과**: fpeaba의 websocket_c2 evidence가 기준선 ~0.19 → **0.642**. **오직 fpeaba만** c2
evidence 획득(reason=websocket_c2_detected, ev=['new websocket']). 경로가 rerank/evidence
층에서 관통.

**⚠️ 한계 — fpeaba는 c2로 동적 top-K 미진입 (K=3 포화)**:
- fpeaba의 다른 행위(browser_automation/remote_browser_control_debugger/screenshot)가 전부
  1.0 만점이라 **top-K=3을 포화**. c2(0.642)는 7위로 밀림. selected_candidates에 c2 없음.
- **새 구조적 발견: top-K 고정 K=3이 병목.** 다재다능한 악성은 핵심 행위 버킷을 새로
  배선해도 다른 만점 행위에 밀려 그 버킷으로 동적 진입 못 함. "우회 진입"(핵심 버킷 없어
  곁다리 진입, 2026-07-20 항목)의 **반대 얼굴 — 핵심 버킷이 생겨도 밀려남**. 둘 다 K=3
  고정이 원인. **앞으로 배선할 모든 verified combo에 영향.**

**회귀(jq 실측)**: 기존 6버킷 무영향(elpmkbb/url_visit/fpeaba/ghkcp/obifan/benign 3종 전부
기존 선정·매치·CRITICAL 유지), **c2 오탐 0**. 특히 **obifan이 modernizr `"websocket"`으로
안 걸림(0.186)** = 앵커 리터럴 정정의 실효성 실측 확인. 공통 health 정상(전 샘플
extension_context_launched=true, launch_fail/sync_in_async 없음).
- **운영 주의(자기 회수한 사고)**: 배선 반영 위해 `docker restart es3-suppressor-1` 했더니
  stale `/tmp/.X99-lock`(이전 세션 잔존)이 새 Xvfb 기동을 막아 **첫 실행은 전 샘플
  `context_launch_failed`**. 락 제거+재기동으로 복구 후 재실행이 유효 측정. DB 26 vectors
  intact(ensure_knowledge_base_seeded는 count>0이면 skip이라 재시드 안 됨).

### 신규 완료 — 순수 C2 픽스처 (`websocket_c2_fixture.zip`)

K=3 포화로 fpeaba에서 못 밟은 "곁다리 아닌 c2 동적 진입"을 실물로 밟기 위해 WebSocket C2만
하는 순수 픽스처 생성(url_visit 픽스처 방식).
- 구성: `permissions=[]`(WebSocket은 권한 불필요), 유일 행위=`new WebSocket("wss://c2-fixture.test/ws")`
  +hello send+재연결. **다른 27개 버킷 토큰 전부 0(순수성 실측)**. 무해(비라우팅 test 호스트,
  실제 exfil 없음, safety_violation=False/real_net=False). 최초 버전은 "no captureVisibleTab"
  식 **부인 주석이 스캔 텍스트에 토큰을 오염**(scanner는 주석 포함 raw 텍스트 검사) → 주석에서
  API명 제거로 해결.
- **핵심 성과**: 순수 픽스처가 websocket_c2로 top-3 **#1 진입**(0.646). launched=true, 동적
  harness 도달. **fpeaba의 K=3 포화 공백을 닫음 — "카탈로그 조합 → c2_channel 버킷 → 동적
  진입"이 순수 샘플에서 완전 관통.** A-2 파일럿의 선정-레이어 목표 100% 달성.
- WebSocket 자극 전략은 **미구현 확인**(stim=None, 전략 테이블에 WebSocket 없음) — 진입까지
  확인, 실제 자극·관측은 별도 작업.

### 신규 발견 (중대) — ambient 허위 매치: 관측 레이어의 근본 약점

순수 C2 픽스처가 예상 못 한 결함을 드러냄. 픽스처가 CRITICAL/matched로 나왔으나:
- `matched_evidence` = [content_script_execution, input_change_event, message_passing_bridge,
  storage_access] — **이 픽스처가 하지 않는 행위들.** 순수 WebSocket 확장인데 content
  script·입력·메시지·스토리지가 매치됨.
- 출처: harness **mock 페이지의 주변(ambient) 관측**(observation_totals: storage_events=18,
  dom_events=36, runtime_messages=18, mock_target_used=true)을 generic evidence scorer가
  websocket_c2 시나리오에 오귀속. `Generic scorer (dynamic-only): matched 4 of 6`.
- 진짜 C2 신호(external_communication=WebSocket 연결, periodic_execution=재연결)는 `missing`.
- 에이전트 자체 판정: `agent_result.final_assessment.scenario_matched=false, confidence=0.0`.
→ **이 CRITICAL은 허위 양성.** WebSocket 실제 관측이 아니라 mock 환경 배경 잡음을 긁어모은 것.

**함의 (다음 세션 최우선 후보)**:
- §최상위 원칙 "판정 근거는 관측된 실제 호출" 위반이 실측으로 잡힘. generic evidence
  scorer가 ambient 신호를 시나리오에 오귀속하는 구조적 약점.
- **소급 의심 필요**: 지금까지 모든 CRITICAL(elpmkbb/ghkcp/obifan 등)이 얼마나 실제 관측이고
  얼마나 mock ambient인지 미검증. 순수 픽스처는 "아무것도 안 하는데 CRITICAL이면 그건 다
  가짜"라 결함이 눈에 띄었지만, 다행위 샘플은 ambient가 진짜 행위와 섞여 안 보였을 것.
- **새 도구 확보**: 순수 C2 픽스처 = "ambient 허위매치 탐지용 그라운드 트루스". 앞으로 다른
  버킷 검증 시 "이 매치가 진짜냐 mock 잡음이냐"의 리트머스로 재사용.
- 후속 두 갈래: (a) WebSocket 자극·관측 계측 추가(진짜 C2 관측), (b) generic 스코어러의
  ambient-신호 오귀속 억제.

### A단계 진행 상황 (확장성 구조 구축 계획)

사용자 승인 하에 A단계 진행 중. 구조: **하드코딩 6계열은 유지하되, 새 공격 계열 추가가
"카탈로그 조합 하나 + 시드 md 하나"로 끝나게** 만드는 게 목표. 공격은 한 번에 전부가
아니라 하나씩 격리 검증하며 채운다.
- **A-1 (완료)**: 공격 카탈로그 데이터화 (위).
- **A-2 (완료 — 선정-레이어 관통 성공)**: websocket_c2를 rerank 7번째 증거 버킷으로 배선.
  카탈로그 정정 2건(게이트 1) → 배선 3곳 → fpeaba c2 evidence 0.642(단 K=3 포화로 동적
  미진입) → 순수 C2 픽스처로 top-3 #1 진입 실물 확인. **"카탈로그 조합→버킷→동적 진입"
  핵심 경로가 순수 샘플에서 증명됨.** 단 A-2가 **두 새 병목**을 드러냄: (1) top-K 고정 K=3
  (다행위 악성이 새 버킷 밀어냄), (2) ambient 허위매치(관측 레이어가 mock 잡음 오귀속). 둘 다
  "다음 verified combo 배선"보다 선행 검토 대상일 수 있음.
- **A-2 이후 (반복)**: verified-anchor 18 combo부터 하나씩 배선. unverified 13개는 대응
  확장 샘플 확보 후로 미룸.

### 미해결 (2026-07-22 갱신, 우선순위 재정렬 필요)

1. **⚠️ git 커밋 보류 상태 (최우선 경고)** — 2026-07-19/20/22 세션 전체가 **uncommitted**
   (사용자가 커밋 보류 지시). 누적 목록: affiliate/dnr/oauth 콤보, generative combo, 매핑
   `identity` 추가, `attack_catalog.json`(+websocket_c2 정정), **`rerank/pipeline.py`
   c2_channel 배선 3곳**, **`websocket_c2_fixture.zip`(신규)**, 이 CLAUDE.md까지. 다음 세션
   시작 시 이 상태 인지 필수 — **모르고 뭔가 건드리면 누적 작업이 유실될 수 있음**. 뭔가
   수정 전 커밋 여부 재확인.
2. **⚠️ ambient 허위매치 (신규, 중대)**: generic evidence scorer가 harness mock 페이지의
   주변(ambient) 관측(content_script_execution/input_change/storage 등)을 시나리오에 오귀속
   → 아무 행위 안 하는 순수 C2 픽스처가 CRITICAL/matched. §최상위 원칙("관측된 실제 호출")
   위반. **기존 CRITICAL들(elpmkbb/ghkcp/obifan)의 소급 감사 필요.** 순수 픽스처가 탐지 도구.
3. **top-K 고정 K=3 병목 (신규)**: 다행위 악성이 새로 배선한 핵심 버킷을 다른 만점 행위로
   밀어냄(fpeaba의 c2가 7위). 우회 진입의 반대 얼굴. 모든 후속 combo 배선에 영향.
4. **safety_violation 목킹 갭**: mail.google.com이 allowlist인데도 목킹이 새어 CheckerPlus
   (정상)가 CRITICAL. 원인 미조사. (2026-07-19 항목 유지)
5. **점수 재설계**: combo_containment가 vector와 사실상 중복 신호(다중신호 설계 붕괴).
   CheckerPlus 실세계 밴드 0.01~0.02가 재설계 필요성 실측 근거. tag_overlap 부활/IDF 계속
   미룸 — 단, **저자 도구용 IDF(어휘 희소도 표시)는 템플릿 시스템과도 연결**.
6. **oauth code_scanner 확장**: chrome.identity 미탐지로 obifan조차 oauth로는 영원히
   matched 불가. (2026-07-19 항목 유지)
7. **`docker compose up -d`/`build` 미실행**: 모든 변경이 러닝 컨테이너에만 live(c2_channel
   배선 pipeline.py도 docker-cp로만 반영), 이미지 미반영.
8. **실물 샘플 확보 (A단계 후반 병목)**: unverified 13 combo는 대응 확장 샘플이 코퍼스에
   없음. Notion에도 "테스트할 확장앱 확보 못 함" 기록. **WebSocket 자극 전략 미구현도 여기
   연결**(진입은 되나 실제 자극·관측 없음). 샘플 확보가 병목.

## 현재 상태 (2026-07-24 세션 — ambient 허위매치 근본 진단 + Fix A/B + 관측 표면 전수)

이번 세션은 코드 수정을 최소로 하고(evidence_scorer._score_generic만) 관측 레이어를
전수 진단했다. 아래는 전부 실측·코드 위치 기반 사실이다(해석·전망 배제).

### 1. 코퍼스 라벨 정정 (전 세션 라벨 오류 실측 확인)
- **hmkcid = 악성**(무해 아님). `thanks.html`에 `<iframe src="https://xuix.top/ad-editor">`
  (광고 iframe). Adobe 편집기(fabric.js)는 미끼. 동적 top-K 진입함(dom_surveillance 버킷,
  concrete_api=`document.queryselector`/`textcontent`, rerank 0.424). 정적 grep(JS만)으로
  "inert" 오판했던 것 — HTML iframe 누락이 원인.
- **fpeaba·ghkcpc = SOLID 아님.** `/app/results_json/{fpeaba,ghkcp}*/*dynamic*.json` 전
  세션(1.0/1.0.0/freshA~E/auditA) 통틀어 capture 시나리오 **sev=0.2, matched=[]**
  = captureVisibleTab **동적 미관측**. 파일 내 "captureVisibleTab" 문자열은 전부 rerank
  정적 concrete_api_evidence(코드 존재)일 뿐. 이들의 수정 전 CRITICAL은 generic 시나리오의
  ambient 매치에 얹혀 있던 것(ambient-propped).

### 2. ambient 4항목 + floor + Fix A/B + 10샘플 검증표
- **ambient 4항목**(harness/mock 유래, 확장 무관): `input_change_event`
  (`simulate_dom_input_events` playwright_dynamic_harness.py:2266) / `storage_access`·
  `message_passing_bridge`(mock 로그인폼 더미-POST 추론 :1117-1126, mock HTML
  `build_mock_page_html:235-249`) / `content_script_execution`(앞 둘에서 추론
  evidence_scorer.py:139). **append-site 전수**: dom/storage/runtime 3리스트는 위
  지점에서만 채워짐. `collect_*`는 no-op(:2705-2726).
- **ambient floor = 4/6 = 0.667 ≥ 0.6** → pipeline.py:92 override → risk_classifier:626
  confirmed_dynamic_flow → CRITICAL. 진짜 행위 0이어도 도달.
- **Fix A**(evidence_scorer._score_generic external_communication 체크): per-request
  `is_target_url_emulation=False` 요구 + `external_request_attempted` fallback 제거,
  `external_request_blocked`만 유지(harness:1155가 타깃-emul 제외 내장 :1151).
- **Fix B**(동 함수): matched가 ambient 4개뿐이면 `matched_evidence=[]`로 매치 차단
  (`_AMBIENT_ONLY_EVIDENCE` 상수). 점수는 진단용 유지.
- **10샘플 검증(Fix 후)**: obifan/jhhjba/hmkcid/urlvisit/elpmkbb = CRITICAL 유지(진짜
  비타깃 external 또는 capVis 실관측). eebihi/iefpkd/wsc2/fpeaba/ghkcpc = **HIGH(0.7)로
  하락**(CRITICAL 이탈). benign_external(신규 무해 픽스처) = **CRITICAL(오탐, Fix B를
  5/6로 우회)**. 회귀 무손실 확인: Fix A는 진짜 신호 안 지움(fpeaba/ghkcpc는 external
  전무라 Fix A 무관, Fix B가 하락시킴).

### 3. 현재 실제 판별자는 2개뿐
- (a) **expected_api 실관측**(captureVisibleTab), (b) **비타깃 external 요청**
  (`is_target_url_emulation=False`). 그 외 matched_evidence는 전부 ambient거나 generic.

### 4. 동적 관측되는 확장 chrome API = captureVisibleTab 1개
- 래핑 대상 = `_build_wrap_targets`(playwright_dynamic_harness.py:2312)가
  `self._sensitive_api_targets`를 dotted→{owner_path,method}로 변환. 입력 체인:
  main.py:857 `collect_expected_apis_from_docs()` → harness 생성자(main.py:858) →
  :333 → :2316. **합집합 = expected_api 선언 문서 2개(page_screenshot,
  tabs_capture) = {chrome.tabs.captureVisibleTab} 뿐.**
- 래퍼 JS(`_SENSITIVE_API_WRAP_JS` :47)는 **범용** — 임의 chrome.* 경로 래핑 가능,
  화이트리스트 없음. `orig.apply(this,args)` 반환(원함수 보존, 반환/예외/Promise 통과).
  주입 컨텍스트 = **service worker**(`instrument_sensitive_apis` :2402가
  `service_workers`에 `w.evaluate`). → cookies/identity/declarativeNetRequest/debugger/
  tabs.create/history는 SW 도달 가능 → **"선언 누락"(문서 expected_api에 추가만 하면
  관측 열림)**, WebSocket·DOM과는 다른 계급.
- 설치 vs 호출 구분 가능: `sensitive_api_wrapped`(설치 라벨) vs `sensitive_api_calls`
  (실호출) + 래퍼의 `existing_calls_at_install`(래핑 전 호출 감지).

### 5. _score_generic은 21 generic에 동일 6체크 재탕
- 시나리오 특화 판별력 0. hmkcid(악성)와 benign_external(무해)의 matched_evidence가
  **완전 동일**(content_script/input_change/external/message_bridge/storage). 시나리오
  이름(dom_surveillance 등)과 실측 증거가 분리. obifan의 진짜 탐지는 오직 session
  스코어러(`_score_session_exfiltration`)에서 나옴.

### 6. rerank dom 앵커 과광범
- benign_external 실측: `webmail_dom_surveillance_collection`(final 0.607)과
  `input_change_event_collection`(final 0.431) **둘 다** concrete_api=
  `[document.queryselector, textcontent]`로 진입. 정상 제목 읽기(querySelector+textContent)
  코드 하나가 두 악성 시나리오 동시 발화. `expected_api: []`라 generic 라우팅.

### 7. harness는 WebSocket 미기록
- `grep -ric websocket playwright_dynamic_harness.py` = **0**. `context.on("websocket")`
  미등록. wsc2 픽스처 실측: `new WebSocket` 호출하나 `net_requests=2, ext_attempted=False`
  = WS가 network_requests에 안 잡힘. → **c2_channel 버킷은 정적 top-K 진입만, 동적 확정
  불가**(관측 코드 부재). DOM 접근 후크도 없음(MutationObserver/CDP DOM 도메인 없음;
  CDP는 `Runtime.executionContextCreated` :2168 isolated-world 탐지용, DOM 접근 관측 아님).

### 8. 오탐 가드 픽스처 2종
- `websocket_c2_fixture.zip`: 기대=CRITICAL 아님, 실측=HIGH(0.7) → **통과**.
- `benign_external_fixture.zip`(신규, repo 루트): content script가 querySelector+textContent로
  제목 읽기 + 비타깃 호스트 fetch 1회(GET, body 없음). storage/cookies/message/timer/
  capVis 전무. 기대=CRITICAL 아님, 실측=**CRITICAL(0.9)** → **실패**(Fix B를 5/6로 우회).

### 임베딩 안전성 (문서 수정 시)
- `build_embedding_text`(base_db.py:99)는 vector_fingerprint를 dump, 임베딩 소스는
  `capability_profile`(embed.py:15)만. **scenario_docs/*.md frontmatter는 임베딩·rerank에
  미포함** → expected_api 추가는 벡터/선정 불변, 영향은 (1) 래핑 대상(main.py:857 합집합),
  (2) 스코어러 라우팅(`if expected_api:` evidence_scorer:249, 비면 무조건 _score_expected_api)
  뿐. multi-API 채점은 **OR**(하나라도 관측 시 sev=1.0, evidence_scorer:176; 미관측 시 sev=0.2
  candidate_only :188).

## 원칙과 함정

| 원칙 / 함정 | 근거 · 사례 |
|---|---|
| 시드는 판정 어휘가 아니라 **핑거프린트 관측 어휘**(32종)로 재저자한다. 판정 태그 방출 금지, 판별력은 combo에서. | affiliate/dnr/oauth 재저자 |
| 콤보 페어는 **최소 하나가 rare 토큰이면 유효** — 나머지가 generic이어도 rare 토큰이 페어 전체를 gate한다. (최초 "둘 다 non-generic이어야"는 과잉 제한, 철회) | affiliate `cookie_access+external_network`, oauth `identity_access+external_network` |
| **작은 합성 코퍼스에서 rare한 토큰 ≠ 실세계에서 rare.** 발견한 discriminative anchor는 반드시 실물 벤치마크로 검증. | uBOL(dnr 유효), CheckerPlus(cookie/identity 실세계 흔함 → 오탐) |
| 재저자만으로 통과 가능한지 **사전 수학 계산**(combo·vector·tag 상한)으로 확인 후 착수. combo=0 구조적 트랩이면 방출기/매핑부터. | dnr(트랩), oauth(도달 가능) |
| 매핑·시드 변경은 **한 번에 하나씩** 적용·측정(동시 적용 시 원인 분리 불가). | oauth 순차 게이트 |
| CRITICAL 판정은 matched_scenarios 뿐 아니라 **safety_violation 단독으로도** 발생(우선 override). 회귀 "통과" 판단 시 근거가 matched인지 safety_violation인지 구분할 것. | CheckerPlus(safety_violation-only CRITICAL) |
| 임베딩 소스는 `capability_profile`만(`embed.py:15`). `capability_combinations` 변경은 vector에 무영향, rerank combo_containment에만 영향. | affiliate/oauth 콤보 변경 시 vector 불변 |
| **코퍼스 내 토큰 존재 ≠ 판별력 ≠ 공격 수행.** verified 스탬프는 존재만 보증한다. | attack_catalog `token_sources` (userAgent/runtime.id/window.console는 verified지만 gate급) |
| **동적 top-K 진입 티켓은 `rerank/pipeline.py`의 하드코딩 버킷(2026-07-22 기준 7개: 기존 6 + c2_channel)에서만 나온다.** RAG 선정 점수를 올려도 대응 증거 버킷이 없으면 곁다리로 우회 진입하거나 못 들어간다. 단 버킷이 있어도 K=3 포화면 밀려남(반대 얼굴). | oauth/dnr 우회 진입 (ghkcp→dom/screenshot, obifan→session/dom); c2 배선 후 fpeaba c2 7위로 밀림 |
| **Notion 등 외부 정리 문서의 토큰도 반드시 실물 코드로 검증.** 원본 오류가 실측으로 드러난다. | `chrome.cookies.getAll`(실제 .get/.set), `awinaffid`(jhhjb 평문에 없음) |
| **순수 픽스처(단일 행위)는 허위매치 탐지 도구다** — 아무 행위 안 하는 샘플이 특정 시나리오에 매치되면 그건 mock ambient 오귀속. | url_visit·websocket_c2 픽스처(순수 C2가 CRITICAL → ambient 결함 노출) |
| **top-K 진입(선정 레이어 성공)과 정직한 동적 확정(관측 레이어)은 별개.** 전자가 돼도 후자가 ambient 허위일 수 있다. | websocket_c2 픽스처(top-3 #1 진입 + 허위 CRITICAL) |
| **게이트 1(배선 전 실물 verified 재확인)이 카탈로그 오류의 자동 정정 메커니즘.** 모든 combo 배선 시 필수. | websocket에서 2건(obifan false-verified, socket.* 리터럴 부재) 잡음 |
| **동적 관측되는 확장 chrome API는 captureVisibleTab 1개뿐** — `_build_wrap_targets`(:2312)가 문서 expected_api 합집합(선언 문서 2개)만 래핑. 래퍼는 범용(SW 컨텍스트, 임의 chrome.* 가능) → cookies/identity/dnr/debugger 등은 "선언 누락"(문서 추가로 열림), WebSocket·DOM은 "관측공백"(계측 코드 부재). | main.py:857, harness:2312/2402, `_SENSITIVE_API_WRAP_JS`:47 |
| **`_score_generic`은 21 generic에 동일 6체크 재탕, 시나리오 판별력 0.** 정상 확장(DOM 읽기+external 1건)도 5/6으로 CRITICAL. 오탐 가드 픽스처로만 노출됨. | benign_external(무해)=hmkcid(악성) matched_evidence 동일 |
| **scenario_docs frontmatter는 임베딩·rerank에 미포함**(임베딩=capability_profile만). expected_api 추가는 벡터/선정 불변, 래핑 대상+스코어러 라우팅만 바꿈. 문서 수정이 벡터 기준선을 안 흔든다. | embed.py:15, base_db.py:99, evidence_scorer:249 |
| **하니스 관측 표면은 좁다**: 확장 귀속·판별 가능 신호 = captureVisibleTab + 비타깃 external뿐. dom/storage/message/timer는 전부 ambient(harness/mock 유래). DOM 접근·WebSocket 후크 없음. | 관측 표면 전수(2026-07-24) |

## 검증 자산

- `elpmkbbdldhoiggkjfpgibmjioncklbn` (captureVisibleTab, popup_message 트리거) — 회귀 대조군.
- `url_visit_capture_fixture.zip` (무해 픽스처, url_visit 트리거) — url_visit 검증.
- `websocket_c2_fixture.zip` (무해 순수 C2 픽스처, `new WebSocket`만) — c2_channel 동적 진입
  검증 + **ambient 허위매치 탐지 그라운드 트루스**. permissions=[], 다른 27개 버킷 토큰 0.
  현재 컨테이너 `/tmp/samples`에만 있음(호스트는 스크래치패드, git 미커밋).
  **Fix A/B 후 기대=CRITICAL 아님, 실측=HIGH(0.7) 통과.**
- `benign_external_fixture.zip` (repo 루트, 무해, git 미커밋) — content script querySelector+
  textContent 제목 읽기 + 비타깃 fetch 1회. **오탐 가드: 기대=CRITICAL 아님, 실측=CRITICAL(0.9)
  실패** — Fix B(순수 ambient 4/4만 억제)를 5/6로 우회하는 오탐의 그라운드 트루스.
- `악성 확장 샘플/*.zip` (7개 실제 악성) — 코퍼스 커버리지 측정. **hmkcid=악성(광고 iframe
  xuix.top; 전 세션 무해 라벨 오류 정정). fpeaba·ghkcpc=capVis 동적 미관측(SOLID 아님).**
- **실물 벤치마크(오탐 검증용)**: uBlock Origin Lite(`ddkjiahejlhfcafbddmgiahcphecmpfh`,
  plain declarativeNetRequest — dnr 오탐 없음 확인), Checker Plus for Gmail
  (`oeopbcgkkoapgobdbedcemjljbihmemj`, identity+oauth2 — oauth/affiliate 선정층 오탐 +
  safety_violation CRITICAL 사례). 웹스토어 CRX로 획득.
- 임계값 `DEFAULT_MIN_FINAL_SCORE = 0.35` (`embedding/scenario/config.py`).

## 운영 메모

- 스캔: 컨테이너 내부에서 `POST /file_scan` (호스트 미노출). 확장 ZIP 업로드.
- 임베딩 모델 `bge-m3`는 최초 1회 `docker compose exec ollama ollama pull bge-m3` 필요.
- 코드 변경은 `docker compose build suppressor` 재빌드, env 변경은 `up -d` 재생성으로 반영.

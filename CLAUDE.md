# ES3 프로젝트 상태 — 동적 분석 파이프라인

> 이 문서는 suppressor의 **동적 시나리오 분석 파이프라인** 작업 진행 상태를 요약한다.
> 레포 네비게이션은 `suppressor/CLAUDE.md`를 참조.
> 마지막 갱신: 2026-07-19

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

## 검증 자산

- `elpmkbbdldhoiggkjfpgibmjioncklbn` (captureVisibleTab, popup_message 트리거) — 회귀 대조군.
- `url_visit_capture_fixture.zip` (무해 픽스처, url_visit 트리거) — url_visit 검증.
- `악성 확장 샘플/*.zip` (7개 실제 악성) — 코퍼스 커버리지 측정.
- **실물 벤치마크(오탐 검증용)**: uBlock Origin Lite(`ddkjiahejlhfcafbddmgiahcphecmpfh`,
  plain declarativeNetRequest — dnr 오탐 없음 확인), Checker Plus for Gmail
  (`oeopbcgkkoapgobdbedcemjljbihmemj`, identity+oauth2 — oauth/affiliate 선정층 오탐 +
  safety_violation CRITICAL 사례). 웹스토어 CRX로 획득.
- 임계값 `DEFAULT_MIN_FINAL_SCORE = 0.35` (`embedding/scenario/config.py`).

## 운영 메모

- 스캔: 컨테이너 내부에서 `POST /file_scan` (호스트 미노출). 확장 ZIP 업로드.
- 임베딩 모델 `bge-m3`는 최초 1회 `docker compose exec ollama ollama pull bge-m3` 필요.
- 코드 변경은 `docker compose build suppressor` 재빌드, env 변경은 `up -d` 재생성으로 반영.

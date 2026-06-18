# backend/ai_judgment

suppressor의 1차 분석 결과를 받아 로컬 LLM(Ollama)으로 2차 AI 판단을 수행하는 모듈입니다.
`recevie_result.py`가 suppressor 결과를 수신한 직후 백그라운드 태스크로 비동기 실행됩니다.

---

## 활성화 조건

환경변수 `ENABLE_AI_JUDGMENT=true` (기본값)일 때만 동작합니다.
`false`로 설정하면 AI 판단 없이 suppressor 결과만 저장합니다.

```python
# recevie_result.py
if os.getenv("ENABLE_AI_JUDGMENT", "true").lower() != "true":
    return
```

---

## 파일 구성

### judge.py

LLM 호출과 응답 파싱을 담당하는 핵심 파일입니다.

**`run_judgment(web_payload) → dict`**

1. `extractor.extract_for_llm(web_payload)` — 분석 결과에서 LLM 입력값 추출
2. `prompts.build_user_prompt(ext_data)` — 프롬프트 조립
3. Ollama API(`/api/chat`) POST 요청
4. 응답 JSON 파싱 (` ```json ``` ` 블록, `{...}` 추출 등 3단계 폴백)
5. 파싱 실패 또는 타임아웃 시 `_fallback()` 구조 반환 (항상 결과를 보장)

**반환 구조**

```json
{
  "judgment_id": "JDG-xxxx-1234567890",
  "extension_id": "abcdef...",
  "extension_name": "Example Extension",
  "analyzed_at": "2026-06-17T12:00:00",
  "ai_model": "qwen2.5:1.5b-instruct-q4_K_M",
  "input_risk_level": "HIGH",
  "input_risk_score": 0.72,
  "score_breakdown": {
    "dynamic":     {"score": 0.80, "level": "HIGH",   "weight": 0.65},
    "static":      {"score": 0.60, "level": "MEDIUM", "weight": 0.20},
    "obfuscation": {"score": 0.50, "level": "MEDIUM", "weight": 0.15}
  },
  "verdict": {
    "recommendation": "escalate",
    "confidence": "high",
    "summary": "외부 C2 서버와 통신하는 패턴이 감지됨",
    "key_reason": "fetch() + eval(atob()) 조합 탐지"
  },
  "risk_groups": {
    "permission": {"level": "high",   "key_items": [...], "note": "..."},
    "code":       {"level": "medium", "key_items": [...], "note": "..."},
    "behavior":   {"level": "high",   "key_items": [...], "note": "..."},
    "pattern":    {"level": "medium", "key_items": [...], "note": "..."}
  },
  "ambiguous": [{"issue": "...", "check": "..."}],
  "checklist": ["정적 분석 결과 직접 확인", ...]
}
```

**주요 환경변수**

| 변수명                   | 기본값                            | 설명                         |
| ------------------------ | --------------------------------- | ---------------------------- |
| `LOCAL_LLM_URL`          | `http://localhost:11434/api/chat` | Ollama API 엔드포인트        |
| `LOCAL_LLM_MODEL`        | `qwen2.5:1.5b-instruct-q4_K_M`    | 사용할 모델명                |
| `AI_JUDGMENT_MAX_TOKENS` | `1024`                            | 최대 응답 토큰 수            |
| `LLM_TIMEOUT`            | `300`                             | LLM 응답 대기 타임아웃(초)   |
| `LLM_TEMPERATURE`        | `0.1`                             | 판단 일관성을 위해 낮게 유지 |
| `OLLAMA_KEEP_ALIVE`      | `5m`                              | Ollama 모델 메모리 유지 시간 |

---

### extractor.py

`web_payload`에서 LLM 프롬프트에 필요한 핵심 필드만 추출합니다.

**추출 항목 (4개 위험 그룹 기준)**

| 그룹        | 추출 항목                                                                           |
| ----------- | ----------------------------------------------------------------------------------- |
| 권한/접근   | `permissions`, `suspicious_apis`, `external_domains`                                |
| 코드/난독화 | `static_findings` (`[심각도] 내용` 형태로 변환), `obf_indicators`, `obf_files`      |
| 동적 행동   | `runtime` (네트워크·스토리지·메시지 이벤트 수), `matched_scenarios`, `observations` |
| 유사 패턴   | `top_patterns` (RAG 매칭 상위 패턴)                                                 |

각 항목은 최대 개수와 글자 수를 제한(`_trim()`)해 프롬프트 크기를 조절합니다.

---

### prompts.py

LLM에 전달하는 시스템 프롬프트와 유저 프롬프트를 정의합니다.

- **`SYSTEM_PROMPT`** — AI 판단 역할 및 출력 JSON 스키마 정의
- **`build_user_prompt(ext_data)`** — `extractor`가 추출한 데이터를 프롬프트 텍스트로 조립

LLM은 반드시 아래 키를 포함한 JSON만 반환해야 합니다:
`verdict`, `risk_groups`, `ambiguous`, `checklist`

---

### slack.py

AI 판단 결과를 Slack Block Kit 메시지로 포맷해 웹훅으로 전송합니다.

suppressor의 기본 Slack 알림(`slack/main.py`)과 별개로, AI 요약 전용 채널로 추가 전송합니다.

**메시지 구성**

1. 헤더 — 확장명, 위험도, 점수
2. AI 판단 요약 — recommendation, confidence, summary, key_reason
3. 점수 분해 — dynamic/static/obfuscation 3개 컴포넌트
4. 위험 그룹 분석 — 권한/코드/동적/패턴 4개 그룹 (2열 레이아웃)
5. 불명확 항목 — 수동 확인이 필요한 항목 목록
6. 체크리스트 — 담당자 확인 사항
7. 대시보드 링크 버튼

**주요 환경변수**

| 변수명               | 설명                                                         |
| -------------------- | ------------------------------------------------------------ |
| `SLACK_WEBHOOK_URL`  | Slack 인커밍 웹훅 URL. 미설정 시 전송 건너뜀 (오류 아님)     |
| `DASHBOARD_BASE_URL` | 대시보드 버튼에 연결할 URL (기본값: `http://localhost:8000`) |

---

## 전체 실행 흐름

```
recevie_result.py
  └── BackgroundTasks.add_task(_run_ai_judgment, web_payload, target_dir)
        │
        ├── extractor.extract_for_llm(web_payload)
        │     └── web_payload에서 4개 그룹 핵심 필드 추출
        │
        ├── prompts.build_user_prompt(ext_data)
        │     └── 추출된 데이터 → 프롬프트 텍스트 조립
        │
        ├── judge.run_judgment(web_payload)
        │     ├── Ollama API POST → JSON 파싱
        │     └── 실패 시 _fallback() 반환 (항상 결과 보장)
        │
        ├── target_dir / "judgment.json" 저장
        │     └── analysis_result/{decision}/{browser}/{name}/{version}/{id}/judgment.json
        │
        └── slack.send_to_slack(judgment, web_payload)
              └── SLACK_WEBHOOK_URL 설정 시 Block Kit 메시지 전송
```

---

## Ollama 사전 준비

```bash
ollama pull qwen2.5:1.5b-instruct-q4_K_M
```

모델이 없거나 Ollama가 실행 중이지 않으면 LLM 판단이 스킵되고 `_fallback()` 결과가 저장됩니다.
앱 동작 자체에는 영향을 주지 않습니다.

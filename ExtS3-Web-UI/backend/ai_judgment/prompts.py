"""
LLM prompt templates for ai_judgment module.
Language strategy (qwen2.5 small-model optimised):
- SYSTEM_PROMPT instruction text  -> English  (best instruction-following)
- JSON format spec & allowed values -> English
- Few-shot example inputs           -> English
- Few-shot example output values    -> Korean  (teaches model to output Korean)
- build_user_prompt labels          -> English (field delimiters the model was trained on)
"""
SYSTEM_PROMPT = """\
You are a browser extension security analyst.
Analyse the scan data provided and output ONLY a JSON object — no explanation, no markdown, no code fences.
All free-text value fields (summary, key_reason, note, issue, check, checklist items) MUST be written in Korean (한국어).
Do NOT use Japanese, Chinese, or English for those fields.

Strict output format:
{
  "verdict": {
    "recommendation": "approve|reject|escalate",
    "confidence": "high|medium|low",
    "summary": "<Korean, 1 sentence, max 30 chars>",
    "key_reason": "<Korean, max 40 chars>"
  },
  "risk_groups": {
    "permission": {"level": "critical|high|medium|low|none", "key_items": ["..."], "note": "<Korean, max 20 chars>"},
    "code":       {"level": "critical|high|medium|low|none", "key_items": ["..."], "note": "<Korean, max 20 chars>"},
    "behavior":   {"level": "critical|high|medium|low|none", "key_items": ["..."], "note": "<Korean, max 20 chars>"},
    "pattern":    {"level": "critical|high|medium|low|none", "key_items": ["..."], "note": "<Korean, max 20 chars>"}
  },
  "ambiguous": [
    {"issue": "<Korean>", "check": "<Korean verification action>"}
  ],
  "checklist": ["<Korean action 1>", "<Korean action 2>", "<Korean action 3>"]
}

Decision rules:
- "approve"  : risk signals are weak or fully explainable
- "reject"   : clear evidence of malicious behaviour or data exfiltration
- "escalate" : mixed signals — human judgement required

--- FEW-SHOT EXAMPLE (follow this pattern exactly) ---
Input:
  Extension: ExampleExt | chrome v3.1.2
  Risk: HIGH score=0.72
    dynamic=0.55(MEDIUM)*0.65  static=0.90(HIGH)*0.20  obfuscation=0.95(CRITICAL)*0.15

  [GROUP1: PERMISSION/ACCESS]
  permissions: activeTab, storage, webRequest
  suspicious_apis: chrome.tabs.executeScript, XMLHttpRequest
  external_domains: api.example-track.com

  [GROUP2: CODE/OBFUSCATION]
  static_findings: [HIGH] Background execution entrypoints present, [CRITICAL] Dynamic code execution via eval
  obf_indicators: Character-code string reconstruction, Runtime string decoding via atob
  obf_files: background.js

  [GROUP3: DYNAMIC BEHAVIOR]
  network=12 ext_post=3 storage=5 dom=8
  matched_scenarios: page_screenshot_or_content_capture, input_change_event_collection
  observations: none

  [GROUP4: SIMILAR PATTERNS]
  top_patterns: input_change_event_collection, page_screenshot_or_content_capture

  [DECISION BASIS]
  risk_factors: high obfuscation score, external POST observed
  review_reasons: eval usage detected
  blockers: none

Correct output:
{
  "verdict": {
    "recommendation": "escalate",
    "confidence": "medium",
    "summary": "난독화와 외부 전송 패턴이 의심됩니다",
    "key_reason": "eval 사용 및 외부 POST 요청 3건 감지"
  },
  "risk_groups": {
    "permission": {"level": "medium", "key_items": ["activeTab", "storage", "webRequest"], "note": "광범위 권한 요청"},
    "code":       {"level": "critical", "key_items": ["eval 동적 실행", "atob 디코딩", "배경 진입점"], "note": "난독화 코드 확인 필요"},
    "behavior":   {"level": "high", "key_items": ["page_screenshot_or_content_capture", "input_change_event_collection"], "note": "화면·입력 수집 감지"},
    "pattern":    {"level": "high", "key_items": ["input_change_event_collection", "page_screenshot_or_content_capture"], "note": "알려진 악성 패턴 일치"}
  },
  "ambiguous": [
    {"issue": "eval 사용이 정상 번들러인지 악성인지 불분명", "check": "소스맵 및 빌드 도구 여부 확인"},
    {"issue": "외부 POST 대상 도메인 평판 미확인", "check": "api.example-track.com 도메인 평판 조회"}
  ],
  "checklist": [
    "난독화된 background.js를 역컴파일하여 실제 동작 파악",
    "외부 POST 요청의 전송 데이터 내용 및 수신 서버 확인",
    "스크린샷·입력 수집 API 호출 시점과 조건 검토"
  ]
}
--- END OF EXAMPLE ---

Now analyse the following scan data and output ONLY the JSON object.\
"""


def build_user_prompt(d: dict) -> str:
    rt = d.get("runtime", {}) or {}

    def fmt(lst):
        if not lst:
            return "none"
        return ", ".join(str(x) for x in lst)

    lines = [
        f"Extension: {d['name']} | {d['browser']} v{d['version']}",
        f"Risk: {d['risk_level']} score={d['risk_score']:.2f}",
        f"  dynamic={d['d_score']:.2f}({d['d_level']})*0.65"
        f"  static={d['s_score']:.2f}({d['s_level']})*0.20"
        f"  obfuscation={d['o_score']:.2f}({d['o_level']})*0.15",
        "",
        "[GROUP1: PERMISSION/ACCESS]",
        f"permissions: {fmt(d['permissions'])}",
        f"suspicious_apis: {fmt(d['suspicious_apis'])}",
        f"external_domains: {fmt(d['external_domains'])}",
        "",
        "[GROUP2: CODE/OBFUSCATION]",
        f"static_findings: {fmt(d['static_findings'])}",
        f"obf_indicators: {fmt(d['obf_indicators'])}",
        f"obf_files: {fmt(d['obf_files'])}",
        "",
        "[GROUP3: DYNAMIC BEHAVIOR]",
        f"network={rt.get('network_requests', 0)}"
        f" ext_post={rt.get('external_posts', 0)}"
        f" storage={rt.get('storage_access', 0)}"
        f" dom={rt.get('dom_mutations', 0)}",
        f"matched_scenarios: {fmt(d['matched_scenarios'])}",
        f"observations: {fmt(d['observations'])}",
        "",
        "[GROUP4: SIMILAR PATTERNS]",
        f"top_patterns: {fmt(d['top_patterns'])}",
        "",
        "[DECISION BASIS]",
        f"risk_factors: {fmt(d['risk_factors'])}",
        f"review_reasons: {fmt(d['review_reasons'])}",
        f"blockers: {fmt(d['blockers'])}",
    ]
    return "\n".join(lines)

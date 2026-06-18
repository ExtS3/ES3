"""Code body / Secret 정규식 룰.

Code: C-003, C-004, C-006, C-007, C-009, C-010, C-011
Secret: X-001, X-002, X-003
Tier1은 정규식만 사용 (AST 금지).
"""

from collections import Counter
from typing import Any, Dict, List, Tuple

try:
    from backend.scanners.common import add_finding
    from backend.vscode_analysis import rules
except ModuleNotFoundError:  # pragma: no cover - import shim
    from scanners.common import add_finding
    from vscode_analysis import rules


def _emit(findings, counts, rule_id, evidence):
    severity, category, title, recommendation = rules.RULE_META[rule_id]
    add_finding(findings, counts, severity, category, rule_id, title, evidence, recommendation)


def _snippet(text: str, idx: int, width: int = 40) -> str:
    start = max(0, idx - width)
    end = min(len(text), idx + width)
    return text[start:end]


def _is_vendored(file_name: str) -> bool:
    """vendored 의존성 경로 여부 (bundler 미포함 third-party 코드)."""
    return "node_modules/" in file_name.replace("\\", "/")


def _c003_match_is_exempt(content: str, m) -> bool:
    """C-003 매치 1건이 무해한 번들러 보일러플레이트인지 (좁은 예외).

    매치 시작 위치에서 면제 패턴이 정확히 시작되는지로 판정한다.
    - new Function("return this") / Function("return this") : globalThis 폴리필
    - eval("require('...')[.member]")                       : CommonJS require shim
    둘 다 문자열 리터럴 인자만 허용하므로, 동적/연결 입력은 절대 면제되지 않는다.
    """
    start = m.start()
    for pat in (rules.C003_EXEMPT_RETURN_THIS, rules.C003_EXEMPT_EVAL_REQUIRE):
        em = pat.match(content, start)
        if em:
            return True
    return False


def _c007_endpoint_exempt(content: str, endpoint: str) -> bool:
    """C-007: 메타데이터 IP/호스트 접근이 *무해한 VM 탐지 텔레메트리*인지 판정.

    면제 조건 (모두 충족해야만):
      1. 파일 어디에도 토큰/자격증명 경로가 없다 (C007_CREDENTIAL_PATHS 미매치).
      2. 접근이 인스턴스-메타데이터 정상 경로(/metadata/instance ...)로 나타난다.
    → instance/compute = VM 탐지(정상), identity/oauth2/token = 자격증명 탈취(위험).

    자격증명 경로가 보이면 무조건 발화(면제 금지). 정상 경로 맥락 없이 메타데이터 IP만
    단독으로 등장하는 exfil 의심 케이스도 면제하지 않는다.
    """
    if rules.C007_CREDENTIAL_PATHS.search(content):
        return False
    return bool(rules.C007_INSTANCE_METADATA_PATHS.search(content))


def _c003_first_unexempt(content: str):
    """C-003: 면제 대상이 아닌 첫 eval/Function/vm.run* 매치를 반환 (없으면 None).

    면제(globalThis 폴리필 / require shim)만 있는 파일은 None → 발화 안 함.
    그 외 동적·비자명 eval/Function/vm 호출이 섞여 있으면 그 매치로 Critical 발화.
    """
    for m in rules.C003_EVAL.finditer(content):
        if not _c003_match_is_exempt(content, m):
            return m
    return None


def scan_source_file(
    file_name: str,
    content: str,
    publisher_whitelisted: bool = False,
) -> Tuple[List[Dict[str, Any]], Counter]:
    """단일 소스파일 텍스트를 받아 code+secret 룰 findings + counts 반환.

    publisher_whitelisted: M-002(manifest)에서만 쓰는 화이트리스트 신호. 코드룰(C 룰)
        발화에는 영향 없음 — 침해된 신뢰 publisher 위협모델을 통과시키지 않기 위함.
        (호환 위해 파라미터는 유지하나 여기서는 사용하지 않는다.)
    """
    findings: List[Dict[str, Any]] = []
    counts: Counter = Counter()

    if not isinstance(content, str) or not content:
        return findings, counts

    # vendored(node_modules) 제외는 FP가 실제 우려되는 룰에만 한정한다 (카탈로그):
    #   C-003(eval) — python 번들 vendored lib FP
    #   C-011(native .node) — 정상 native dep 다수 매치
    # 나머지 Critical/상수 룰(C-004/006/007/009/010)은 양성 FP 0이므로 vendored에서도 발화.
    # publisher 화이트리스트는 코드룰 스킵에 일절 관여하지 않는다 (C1 보안 수정).
    vendored = _is_vendored(file_name)

    # --- Code body ---
    # C-003: eval / new Function / vm.runIn* (vendored면 면제)
    # 추가로, 무해한 번들러 보일러플레이트(globalThis 폴리필 / require shim)만 있는
    # 파일은 면제. 동적·비자명 eval/Function/vm 호출이 하나라도 있으면 Critical 발화.
    if not vendored:
        m = _c003_first_unexempt(content)
        if m:
            _emit(findings, counts, "C-003", {"file": file_name, "match": m.group(0)})

    # C-004: 비가시 Unicode 5자+ 연속
    m = rules.C004_INVISIBLE.search(content)
    if m:
        _emit(findings, counts, "C-004",
              {"file": file_name, "length": len(m.group(0)),
               "codepoints": [hex(ord(c)) for c in m.group(0)[:8]]})

    # C-006: 알려진 C2 IP 상수
    for ip in rules.KNOWN_C2_IPS:
        if ip in content:
            _emit(findings, counts, "C-006", {"file": file_name, "ip": ip})

    # C-007: 클라우드 메타데이터 엔드포인트
    # 보안-인지 정제: instance/compute류 정상 텔레메트리(VM 탐지)만 좁게 면제하고,
    # identity/oauth2/token 등 자격증명 탈취 경로는 무조건 Critical 유지.
    for endpoint in rules.CLOUD_METADATA_ENDPOINTS:
        if endpoint in content and not _c007_endpoint_exempt(content, endpoint):
            _emit(findings, counts, "C-007", {"file": file_name, "endpoint": endpoint})

    # C-009: GitHub Search dead-drop
    m = rules.C009_GITHUB_SEARCH.search(content)
    if m:
        _emit(findings, counts, "C-009", {"file": file_name, "match": m.group(0)})

    # C-010: Blockchain/Calendar 백업 채널
    m = rules.C010_BACKUP_CHANNEL.search(content)
    if m:
        _emit(findings, counts, "C-010", {"file": file_name, "match": m.group(0)})

    # C-011: native .node 모듈 로딩 (vendored면 면제)
    if not vendored:
        m = rules.C011_NATIVE_NODE.search(content)
        if m:
            _emit(findings, counts, "C-011", {"file": file_name, "match": m.group(0)})

    # --- Secret (vendored 포함 전체 대상 — 카탈로그 X 룰) ---

    # X-001: PAT (52자 base32) ∧ 동일 파일에 vsce/marketplace/ovsx 맥락
    if rules.X001_CONTEXT.search(content):
        m = rules.X001_PAT.search(content)
        if m:
            _emit(findings, counts, "X-001",
                  {"file": file_name, "match": m.group(0)[:6] + "..." })

    # X-002: LLM/클라우드 API 키 — EXAMPLE/PLACEHOLDER/xxx 마스킹 라인 제외
    for m in rules.X002_SECRETS.finditer(content):
        line_start = content.rfind("\n", 0, m.start()) + 1
        line_end = content.find("\n", m.end())
        if line_end == -1:
            line_end = len(content)
        line = content[line_start:line_end].upper()
        if any(tok in line for tok in rules.SECRET_MASK_TOKENS):
            continue
        _emit(findings, counts, "X-002",
              {"file": file_name, "match": m.group(0)[:8] + "..."})
        break  # 파일당 1건으로 충분 (noise 억제)

    # X-003: GCP service account private key
    m = rules.X003_GCP_KEY.search(content)
    if m:
        _emit(findings, counts, "X-003", {"file": file_name})

    return findings, counts


def scan_sources(
    source_files: List[Dict[str, Any]],
    publisher_whitelisted: bool = False,
) -> Tuple[List[Dict[str, Any]], Counter]:
    """[{file_name, content}, ...] 목록을 받아 전체 code+secret findings + counts 반환."""
    findings: List[Dict[str, Any]] = []
    counts: Counter = Counter()
    for entry in source_files:
        file_name = str(entry.get("file_name", "unknown"))
        content = entry.get("content")
        f, c = scan_source_file(file_name, content, publisher_whitelisted=publisher_whitelisted)
        findings.extend(f)
        counts.update(c)
    return findings, counts

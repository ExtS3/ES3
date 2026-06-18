"""VSCode Tier1 룰 정의 + 화이트리스트 + IOC 상수.

패턴 출처: dev/notes/vscode_rule_catalog.md 의 Pattern 열을 그대로 사용.
대상 룰: M-001,002,004,005,006 / C-003,004,006,007,009,010,011 / X-001,002,003 (총 15개)
"""

import re

# M-002 면제용 publisher 화이트리스트 (설계 §7)
PUBLISHER_WHITELIST = {
    "ms-vscode",
    "ms-python",
    "ms-toolsai",
    "github",
    "vscode",
    "microsoft",
}

# C-006 알려진 C2 IP 상수 (카탈로그 C-006/Appendix B GlassWorm+Anivia)
KNOWN_C2_IPS = [
    "199.247.10.166",
    "199.247.13.106",
    "217.69.3.218",
    "158.94.210.76",
    "51.178.245.127",
    "91.206.169.80",
    "51.38.250.193",
    "178.16.55.109",
    "158.94.210.52",
]

# C-007 클라우드 메타데이터 엔드포인트 (카탈로그 C-007)
CLOUD_METADATA_ENDPOINTS = [
    "169.254.169.254",
    "169.254.170.2",
    "metadata.google.internal",
    "metadata.azure.com",
]

# C-007 보안-인지 정제 (자격증명 탈취는 절대 면제 금지).
# 토큰/자격증명(identity) 엔드포인트는 무조건 Critical 유지 — 이게 보이면 예외 적용 안 함.
#   instance/compute = VM 탐지(정상 텔레메트리), identity/token = 자격증명 탈취(위험).
# AWS IMDS: /iam/security-credentials, /latest/meta-data/iam, token PUT(IMDSv2)
# Azure: /metadata/identity, oauth2/token
# GCP: /computeMetadata/.../token, service-accounts/.../token
C007_CREDENTIAL_PATHS = re.compile(
    r"/metadata/identity"          # Azure managed identity 토큰
    r"|oauth2/token"               # Azure/GCP OAuth 토큰
    r"|/iam/security-credentials"  # AWS 인스턴스 역할 자격증명
    r"|/computeMetadata/"          # GCP 메타데이터(토큰 포함 경로)
    r"|service-accounts/[^/]+/token"  # GCP SA 토큰
    r"|/latest/meta-data/iam"      # AWS IAM 메타데이터
    r"|/api/token",                # IMDSv2 token 엔드포인트류
    re.IGNORECASE,
)
# 면제 가능한 *정상* 인스턴스 메타데이터 경로 (VM 탐지/텔레메트리). 토큰 경로 없을 때만 의미.
#   Azure App Insights: /metadata/instance/compute?api-version=...
C007_INSTANCE_METADATA_PATHS = re.compile(
    r"/metadata/instance",  # Azure instance metadata (compute/network 등 비자격증명)
    re.IGNORECASE,
)

# X-002 마스킹/예시 컨텍스트 — 이 토큰이 같은 줄에 있으면 면제 (설계 §7)
SECRET_MASK_TOKENS = ("EXAMPLE", "PLACEHOLDER", "XXX")


# --- Code body 정규식 (카탈로그 Pattern 열 그대로) ---

# C-003: eval / new Function / vm.runIn*
C003_EVAL = re.compile(
    r"\beval\s*\(|new\s+Function\s*\(|vm\.runIn(NewContext|ThisContext|Context)\s*\("
)

# C-003 좁은 정상-맥락 예외 (번들러 보일러플레이트만 면제, 그 외 전부 Critical 유지).
# 안전성 근거: 두 패턴 모두 *문자열 리터럴 인자*만 허용 — 동적/연결 입력은 절대 매치 안 됨.
#   (1) globalThis 폴리필: new Function("return this") / Function("return this")
#       인자가 정확히 리터럴 "return this" 일 때만. 그 외 new Function(x)/(...+x)는 발화.
C003_EXEMPT_RETURN_THIS = re.compile(
    r"""(?:new\s+)?Function\s*\(\s*(['"])return this\1\s*\)"""
)
#   (2) CommonJS require shim: eval("require('...')[.member]")
#       eval 인자가 리터럴이고 그 내용이 require('mod') 또는 require('mod').member 형태일 때만.
#       eval(변수), eval("a"+b), eval("악성코드") 등 비자명/동적 입력은 매치 안 됨 → 발화.
C003_EXEMPT_EVAL_REQUIRE = re.compile(
    r"""\beval\s*\(\s*(['"])\s*require\(\s*['"][^'"]+['"]\s*\)(?:\.[A-Za-z_$][\w$]*)*\s*\1\s*\)"""
)

# C-004: 비가시 Unicode 5자+ 연속
# 카탈로그 Pattern: [\u{E0000}-\u{E007F}\u{2060}-\u{2064}\u{200B}-\u{200F}]{5,}
C004_INVISIBLE = re.compile(
    "[󠀀-󠁿⁠-⁤​-‏]{5,}"
)

# C-009: GitHub Search dead-drop
C009_GITHUB_SEARCH = re.compile(r"api\.github\.com/search/commits\?q=")

# C-010: Blockchain / Calendar C2 백업 채널
C010_BACKUP_CHANNEL = re.compile(
    r"api\.mainnet-beta\.solana\.com|api\.devnet\.solana\.com|calendar\.google\.com/calendar/ical/.*ical"
)

# C-011: native .node 모듈 로딩
C011_NATIVE_NODE = re.compile(r"""require\(['"][^'"]*\.node['"]\)""")


# --- Secret 정규식 (카탈로그 X 룰 Pattern 열 그대로) ---

# X-001: Azure DevOps PAT (52자 base32) — 맥락 키워드 동시 매칭 필수
X001_PAT = re.compile(r"\b[a-z2-7]{52}\b")
X001_CONTEXT = re.compile(r"vsce|marketplace\.visualstudio\.com|ovsx", re.IGNORECASE)

# X-002: LLM/클라우드 API 키 (OR 결합)
X002_SECRETS = re.compile(
    r"sk-(?:proj-)?[A-Za-z0-9_-]{40,}"          # OpenAI
    r"|sk-ant-(?:api03-)?[A-Za-z0-9_-]{90,}"    # Anthropic
    r"|AKIA[0-9A-Z]{16}"                          # AWS Access Key
    r"|gh[pousr]_[A-Za-z0-9]{36,}"               # GitHub PAT
    r"|hf_[A-Za-z0-9]{34}"                        # HuggingFace
    r"|AIza[0-9A-Za-z_-]{35}"                     # GCP API
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"             # Slack
)

# X-003: GCP Service Account private key
X003_GCP_KEY = re.compile(r'"private_key"\s*:\s*"-----BEGIN PRIVATE KEY-----')


# 룰 메타데이터 (severity / category / title / recommendation)
RULE_META = {
    "M-001": ("high", "manifest", "Eager activation (*)",
              "activationEvents에 와일드카드(*) 단독 사용을 제거하고 구체적 트리거를 지정하세요."),
    "M-002": ("high", "manifest", "Proposed API 사용 (publisher 미허용)",
              "미허용 publisher의 enabledApiProposals 사용입니다. stable 빌드 정책 위반 여부를 검토하세요."),
    "M-004": ("medium", "manifest", "extensionKind 누락 또는 workspace 실행",
              "extensionKind 설정을 검토해 원격(workspace) 실행 위험을 평가하세요."),
    "M-005": ("medium", "manifest", "install script 존재",
              "postinstall/preinstall 스크립트가 존재합니다. 설치 시 실행 코드를 검토하세요."),
    "M-006": ("medium", "manifest", "extensionPack 강제 묶음 설치",
              "extensionPack 멤버 확장도 함께 분석 큐에 추가해 검토하세요."),
    "C-003": ("critical", "code", "eval / new Function / vm.runIn*",
              "동적 코드 실행 호출이 발견되었습니다. 인자 흐름을 검토하세요."),
    "C-004": ("critical", "code", "비가시 Unicode 문자열 (5자+ 연속)",
              "비가시 유니코드 페이로드(GlassWorm 패턴)가 의심됩니다. 즉시 격리 검토하세요."),
    "C-006": ("critical", "code", "알려진 C2 IP 상수",
              "알려진 C2 인프라 IP가 코드 상수로 발견되었습니다. 즉시 차단/격리하세요."),
    "C-007": ("critical", "code", "클라우드 메타데이터 엔드포인트 접근",
              "클라우드 IMDS/메타데이터 접근(자격증명 수집 의심)이 발견되었습니다."),
    "C-009": ("high", "code", "GitHub Search dead-drop",
              "GitHub Search commits 엔드포인트(dead-drop C2 패턴) 사용을 검토하세요."),
    "C-010": ("high", "code", "Blockchain/Calendar C2 백업 채널",
              "Solana RPC / Google Calendar ical 백업 채널 패턴을 검토하세요."),
    "C-011": ("medium", "code", "Native .node 모듈 로딩",
              "native(.node) 모듈 로딩이 있습니다. 정상 의존성인지 확인하세요."),
    "X-001": ("critical", "secret", "Marketplace publisher PAT 노출",
              "Azure DevOps/Marketplace PAT 노출이 의심됩니다. 즉시 토큰을 회수하세요."),
    "X-002": ("high", "secret", "LLM/클라우드 API 키 노출",
              "API 키가 노출되었습니다. 키를 회수하고 재발급하세요."),
    "X-003": ("high", "secret", "GCP 서비스계정 private key 노출",
              "GCP 서비스계정 private key 노출이 의심됩니다. 즉시 키를 회수하세요."),
}

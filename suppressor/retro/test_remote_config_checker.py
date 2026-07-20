"""RemoteConfigChecker 단위 테스트.

BadBlocker(island.io, 2026-06) 시나리오 대응:
- 확장 코드/버전은 그대로, 원격 config 서버 응답만 바뀌어 임의 JS가 배포되는 공격
- retro가 코드에서 endpoint를 추출해 응답 변화를 감시하는지 검증

실행: pytest retro/test_remote_config_checker.py
"""

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from retro_monitor import (
    RemoteConfigChecker,
    Settings,
    extract_remote_config_endpoints,
    looks_executable,
    normalize_for_hash,
)


def _settings() -> Settings:
    return Settings(
        nexus_base_url="http://localhost:8081",
        nexus_repository="test",
        nexus_username="u",
        nexus_password="p",
    )


def _zip_with(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class _FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class _FakeSession:
    def __init__(self, responses: dict):
        self.responses = responses

    def get(self, url, timeout=None):
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        return _FakeResp(value)


def _checker(responses: dict) -> RemoteConfigChecker:
    checker = RemoteConfigChecker(_settings())
    checker.session = _FakeSession(responses)
    return checker


# --- endpoint 추출 ---

def test_extract_endpoints_from_fetch_and_xhr():
    zip_bytes = _zip_with({
        "background.js": (
            "fetch('https://api.adblock-for-youtube.com/api/v2/rules?version=7.2.1');"
            "xhr.open('GET', 'https://update.example.com/config');"
        ),
        "styles.css": "fetch('https://not-js.example.com/x');",
    })
    endpoints = extract_remote_config_endpoints(zip_bytes)
    assert "https://api.adblock-for-youtube.com/api/v2/rules?version=7.2.1" in endpoints
    assert "https://update.example.com/config" in endpoints
    assert "https://not-js.example.com/x" not in endpoints  # .js만 대상


def test_extract_dedupes():
    zip_bytes = _zip_with({
        "a.js": "fetch('https://api.example.com/r');",
        "b.js": "fetch('https://api.example.com/r');",
    })
    assert extract_remote_config_endpoints(zip_bytes) == ["https://api.example.com/r"]


# --- 정규화 / 실행성 판정 ---

def test_normalize_ignores_timestamp_churn():
    a = '{"rules": [], "generated_at": 1719900000}'
    b = '{"rules": [],  "generated_at": 1719986400}'
    assert normalize_for_hash(a) == normalize_for_hash(b)


def test_looks_executable():
    assert looks_executable('{"scripletsRules": [{"name": "set-constant"}]}')
    assert looks_executable("var f = function (input) { return input; }")
    assert not looks_executable('{"cssSelectors": ["#ad-banner", ".promo"]}')


# --- checker 알림 로직 ---

URL = "https://api.example.com/rules"


def test_first_seen_executable_alerts_once_then_silent():
    body = '{"scripletsRules": [{"name": "x"}]}'
    checker = _checker({URL: body})

    state, alerts = checker.check([URL], None)
    assert len(alerts) == 1
    assert alerts[0]["reason"] == "remote_config_executable_content"

    # 같은 응답이면 두 번째 사이클엔 조용해야 함
    _, alerts2 = checker.check([URL], state)
    assert alerts2 == []


def test_changed_executable_body_alerts():
    checker = _checker({URL: '{"scripletsRules": []}'})
    state, _ = checker.check([URL], None)

    checker.session = _FakeSession({URL: '{"scripletsRules": [{"name": "inject-evil"}]}'})
    _, alerts = checker.check([URL], state)
    assert len(alerts) == 1
    assert alerts[0]["reason"] == "remote_config_changed_with_executable_content"
    assert alerts[0]["changed"] is True


def test_non_executable_change_is_silent():
    checker = _checker({URL: '{"cssSelectors": ["#ad"]}'})
    state, alerts = checker.check([URL], None)
    assert alerts == []

    checker.session = _FakeSession({URL: '{"cssSelectors": ["#ad", ".banner-x"]}'})
    _, alerts2 = checker.check([URL], state)
    assert alerts2 == []


def test_network_error_preserves_baseline():
    body = '{"scripletsRules": [{"name": "x"}]}'
    checker = _checker({URL: body})
    state, _ = checker.check([URL], None)
    old_sha = state[URL]["sha256"]

    checker.session = _FakeSession({URL: ConnectionError("boom")})
    state2, alerts = checker.check([URL], state)
    assert alerts == []
    assert state2[URL]["sha256"] == old_sha  # 장애가 baseline을 초기화하지 않음

    # 복구 후 동일 응답이면 여전히 조용해야 함 (장애 → 오탐 없음)
    checker.session = _FakeSession({URL: body})
    _, alerts3 = checker.check([URL], state2)
    assert alerts3 == []

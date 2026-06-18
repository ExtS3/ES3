(() => {
  const TYPE_SELECT = document.getElementById('policy-type');
  const DESC = document.getElementById('policy-description');
  const NAME_HINT = document.getElementById('policy-name-hint');
  const PAYLOAD = document.getElementById('policy-payload');
  const OUTPUT = document.getElementById('script-output');
  const STATUS = document.getElementById('status-message');
  const BTN_PREVIEW = document.getElementById('btn-preview');
  const BTN_DOWNLOAD = document.getElementById('btn-download');
  const BTN_RESET = document.getElementById('btn-reset-example');

  let types = [];

  // Auth는 HttpOnly cookie(exts3_auth)로 처리. credentials:'same-origin'이면 자동 포함.
  // localStorage 토큰은 옛 컨테이너 secret으로 발급됐을 가능성 있어 안 쓴다.
  function authHeaders() {
    return {};
  }

  function showStatus(message, isError = false) {
    STATUS.textContent = message;
    STATUS.classList.remove('hidden', 'bg-error-container', 'text-error', 'bg-indigo-50', 'text-indigo-700');
    if (isError) {
      STATUS.classList.add('bg-error-container', 'text-error');
    } else {
      STATUS.classList.add('bg-indigo-50', 'text-indigo-700');
    }
    if (!isError) {
      setTimeout(() => STATUS.classList.add('hidden'), 2500);
    }
  }

  function currentType() {
    return types.find((t) => t.type === TYPE_SELECT.value);
  }

  function fillExample() {
    const t = currentType();
    if (!t) return;
    PAYLOAD.value = JSON.stringify(t.example, null, 2);
    DESC.textContent = t.description;
    NAME_HINT.textContent = `이 정책은 ${t.policy_name} 키로 등록됩니다.`;
    OUTPUT.textContent = '미리보기 버튼을 누르면 결과가 여기에 표시됩니다.';
  }

  function parsePayload() {
    try {
      return JSON.parse(PAYLOAD.value);
    } catch (e) {
      showStatus(`JSON 파싱 오류: ${e.message}`, true);
      return null;
    }
  }

  async function callApi(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
        ...(options.headers || {}),
      },
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      } catch (_) {}
      throw new Error(detail);
    }
    return res;
  }

  async function loadTypes() {
    try {
      const res = await callApi('/api/install-helper/policy-catalog/types');
      const body = await res.json();
      types = body.types || [];
      TYPE_SELECT.innerHTML = types
        .map((t) => `<option value="${t.type}">${t.title}</option>`)
        .join('');
      fillExample();
    } catch (e) {
      showStatus(`정책 타입 목록을 불러올 수 없습니다: ${e.message}`, true);
    }
  }

  async function preview() {
    const payload = parsePayload();
    if (payload === null) return;
    try {
      const res = await callApi('/api/install-helper/policy-catalog/render', {
        method: 'POST',
        body: JSON.stringify({ policy_type: TYPE_SELECT.value, payload }),
      });
      const body = await res.json();
      OUTPUT.textContent = body.script;
      showStatus('미리보기 생성 완료');
    } catch (e) {
      showStatus(`미리보기 실패: ${e.message}`, true);
    }
  }

  async function download() {
    const payload = parsePayload();
    if (payload === null) return;
    try {
      const res = await callApi('/api/install-helper/policy-catalog/download', {
        method: 'POST',
        body: JSON.stringify({ policy_type: TYPE_SELECT.value, payload }),
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chrome_policy_${TYPE_SELECT.value}.bat`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showStatus('.bat 다운로드 시작');
    } catch (e) {
      showStatus(`다운로드 실패: ${e.message}`, true);
    }
  }

  TYPE_SELECT.addEventListener('change', fillExample);
  BTN_PREVIEW.addEventListener('click', preview);
  BTN_DOWNLOAD.addEventListener('click', download);
  BTN_RESET.addEventListener('click', fillExample);

  loadTypes();
})();

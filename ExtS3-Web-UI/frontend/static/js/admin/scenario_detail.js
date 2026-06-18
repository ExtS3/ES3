const API = '/api/admin/scenario'
const SCENARIO_ID = window.__SCENARIO_ID__ || ''

document.addEventListener('DOMContentLoaded', () => {
  loadDetail()
})

// ── 상세 조회 ──────────────────────────────────────────────────────────────────
async function loadDetail() {
  const loading = document.getElementById('detail-loading')
  const errorEl = document.getElementById('detail-error')
  const content = document.getElementById('detail-content')

  try {
    const res = await fetch(`${API}/detail/${SCENARIO_ID}`)
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || `${res.status} ${res.statusText}`)

    renderDetail(data)
    loading.classList.add('hidden')
    content.classList.remove('hidden')
  } catch (err) {
    loading.classList.add('hidden')
    errorEl.classList.remove('hidden')
    errorEl.textContent = `시나리오를 불러올 수 없습니다: ${err.message}`
  }
}

// ── 렌더링 ─────────────────────────────────────────────────────────────────────
function renderDetail(data) {
  const scenario = data.scenario || {}
  const fingerprint =
    scenario.vector_fingerprint && typeof scenario.vector_fingerprint === 'object'
      ? scenario.vector_fingerprint
      : scenario

  // 헤더
  document.getElementById('d-pattern-name').textContent =
    data.pattern_name || SCENARIO_ID
  document.getElementById('d-scenario-id').textContent = data.id || SCENARIO_ID

  if (data.builtin) {
    document.getElementById('d-builtin-badge').classList.remove('hidden')
  } else {
    const delBtn = document.getElementById('delete-btn')
    delBtn.classList.remove('hidden')
    delBtn.addEventListener('click', () => confirmDelete(data.id, data.pattern_name))
  }

  // 태그
  const tags = data.behavior_tags || fingerprint.behavior_tags || []
  document.getElementById('d-tags').innerHTML = tags
    .map(
      (t) =>
        `<span class="text-xs px-2.5 py-1 bg-primary-container text-on-primary-container rounded-full font-medium">${escapeHtml(t)}</span>`,
    )
    .join('')

  // 핑거프린트 요약
  renderFingerprint(fingerprint)

  // 문서
  const docSection = document.getElementById('d-doc-section')
  if (data.doc) {
    document.getElementById('d-doc').innerHTML = renderMarkdown(data.doc)
  } else {
    docSection.querySelector('#d-doc').innerHTML =
      '<p class="text-on-surface-variant">등록된 문서가 없습니다.</p>'
  }

  // 원본 JSON
  document.getElementById('d-raw').textContent = JSON.stringify(scenario, null, 2)

  // ID 복사
  document.getElementById('copy-id-btn').addEventListener('click', () => {
    navigator.clipboard
      .writeText(data.id || SCENARIO_ID)
      .then(() => showToast('시나리오 ID를 복사했습니다.', 'success'))
      .catch(() => showToast('복사에 실패했습니다.', 'error'))
  })
}

// ── 핑거프린트 카드들 ──────────────────────────────────────────────────────────
function renderFingerprint(fp) {
  const container = document.getElementById('d-fingerprint')
  const sections = [
    ['manifest_profile', '매니페스트 프로파일'],
    ['capability_profile', '권한/기능 프로파일'],
    ['static_code_signals', '정적 코드 시그널'],
    ['predicted_flows', '예측 동작 흐름'],
  ]

  container.innerHTML = sections
    .filter(([key]) => fp[key] !== undefined)
    .map(([key, label]) => {
      return `
        <div class="border border-outline-variant/20 rounded-xl overflow-hidden">
          <div class="bg-surface-container-low px-4 py-2.5 text-sm font-bold text-on-surface">${label}</div>
          <div class="p-4">${renderValue(fp[key])}</div>
        </div>`
    })
    .join('')
}

function renderValue(value) {
  if (Array.isArray(value)) {
    if (value.length === 0) return '<span class="text-on-surface-variant text-sm">(없음)</span>'
    if (value.every((v) => typeof v !== 'object')) {
      return `<div class="flex flex-wrap gap-1.5">${value
        .map(
          (v) =>
            `<span class="text-xs px-2 py-0.5 bg-surface-container text-on-surface rounded-full font-mono">${escapeHtml(String(v))}</span>`,
        )
        .join('')}</div>`
    }
    return `<div class="space-y-2">${value
      .map((v) => `<div class="bg-surface-container-low rounded-lg p-3">${renderValue(v)}</div>`)
      .join('')}</div>`
  }

  if (value && typeof value === 'object') {
    return `<dl class="space-y-1.5">${Object.entries(value)
      .map(
        ([k, v]) =>
          `<div class="grid grid-cols-[180px_1fr] gap-3 items-start text-sm">
             <dt class="font-medium text-on-surface-variant font-mono text-xs pt-0.5">${escapeHtml(k)}</dt>
             <dd class="text-on-surface">${renderValue(v)}</dd>
           </div>`,
      )
      .join('')}</dl>`
  }

  if (typeof value === 'boolean') {
    return value
      ? '<span class="text-xs px-2 py-0.5 bg-green-50 text-green-700 rounded-full font-medium">true</span>'
      : '<span class="text-xs px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full font-medium">false</span>'
  }

  return `<span class="text-sm text-on-surface break-all">${escapeHtml(String(value))}</span>`
}

// ── 삭제 ───────────────────────────────────────────────────────────────────────
async function confirmDelete(scenarioId, patternName) {
  const confirmed = await showConfirm(
    '시나리오 삭제',
    `'${patternName || scenarioId}' 시나리오를 삭제합니다.\nJSON 파일과 MD 문서가 함께 삭제되며, vectorDB 재적재가 필요합니다.`,
  )
  if (!confirmed) return

  try {
    const res = await fetch(`${API}/delete/${scenarioId}`, { method: 'DELETE' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '삭제 실패')
    showToast('삭제되었습니다. 목록으로 이동합니다.', 'success')
    setTimeout(() => {
      window.location.href = '/scenario'
    }, 900)
  } catch (err) {
    showToast(err.message, 'error')
  }
}

// ── 간단한 마크다운 렌더러 ─────────────────────────────────────────────────────
function renderMarkdown(md) {
  const lines = md.replace(/\r\n/g, '\n').split('\n')
  let html = ''
  let inCode = false
  let listType = null // 'ul' | 'ol'

  const closeList = () => {
    if (listType) {
      html += `</${listType}>`
      listType = null
    }
  }

  for (const raw of lines) {
    const line = raw

    // 코드 펜스
    if (line.trim().startsWith('```')) {
      if (inCode) {
        html += '</code></pre>'
        inCode = false
      } else {
        closeList()
        html += '<pre><code>'
        inCode = true
      }
      continue
    }
    if (inCode) {
      html += escapeHtml(line) + '\n'
      continue
    }

    // 빈 줄
    if (line.trim() === '') {
      closeList()
      continue
    }

    // 헤딩
    const h = line.match(/^(#{1,3})\s+(.*)$/)
    if (h) {
      closeList()
      const level = h[1].length
      html += `<h${level}>${inlineMd(h[2])}</h${level}>`
      continue
    }

    // 순서 목록
    const ol = line.match(/^\s*\d+\.\s+(.*)$/)
    if (ol) {
      if (listType !== 'ol') {
        closeList()
        html += '<ol>'
        listType = 'ol'
      }
      html += `<li>${inlineMd(ol[1])}</li>`
      continue
    }

    // 비순서 목록
    const ul = line.match(/^\s*[-*]\s+(.*)$/)
    if (ul) {
      if (listType !== 'ul') {
        closeList()
        html += '<ul>'
        listType = 'ul'
      }
      html += `<li>${inlineMd(ul[1])}</li>`
      continue
    }

    // 일반 문단
    closeList()
    html += `<p>${inlineMd(line)}</p>`
  }

  if (inCode) html += '</code></pre>'
  closeList()
  return html
}

function inlineMd(text) {
  let s = escapeHtml(text)
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  return s
}

// ── 유틸 ───────────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// ── 공통 확인 다이얼로그 ───────────────────────────────────────────────────────
function showConfirm(title, message) {
  return new Promise((resolve) => {
    document.getElementById('confirm-title').textContent = title
    document.getElementById('confirm-message').textContent = message
    const modal = document.getElementById('confirm-modal')
    modal.classList.remove('hidden')

    const confirmBtn = document.getElementById('confirm-ok')
    const cancelBtn = document.getElementById('confirm-cancel')

    function cleanup(result) {
      modal.classList.add('hidden')
      confirmBtn.removeEventListener('click', onOk)
      cancelBtn.removeEventListener('click', onCancel)
      resolve(result)
    }
    function onOk() {
      cleanup(true)
    }
    function onCancel() {
      cleanup(false)
    }
    confirmBtn.addEventListener('click', onOk)
    cancelBtn.addEventListener('click', onCancel)
  })
}

// ── 토스트 ─────────────────────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container')
  const colors = {
    success: 'bg-green-50 border-green-200 text-green-800',
    error: 'bg-red-50 border-red-200 text-red-800',
    warn: 'bg-amber-50 border-amber-200 text-amber-800',
    info: 'bg-blue-50 border-blue-200 text-blue-800',
  }
  const icons = {
    success: 'check_circle',
    error: 'error',
    warn: 'warning',
    info: 'info',
  }
  const el = document.createElement('div')
  el.className = `flex items-start gap-3 px-4 py-3 rounded-xl border shadow-md text-sm font-medium transition-all ${colors[type] || colors.info}`
  el.innerHTML = `
    <span class="material-symbols-outlined text-base mt-0.5">${icons[type] || 'info'}</span>
    <span>${message}</span>
  `
  container.appendChild(el)
  setTimeout(() => el.remove(), 4000)
}

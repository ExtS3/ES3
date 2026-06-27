const API = '/api/admin/scenario'

// ── 상태 ───────────────────────────────────────────────────────────────────────
let allScenarios = []
let templatesLoaded = false

// ── 초기화 ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  fetchDbStatus()
  fetchScenarios()

  document
    .getElementById('reload-btn')
    .addEventListener('click', reloadVectorDB)
  document
    .getElementById('upload-form')
    .addEventListener('submit', handleUpload)
  document
    .getElementById('json-file-input')
    .addEventListener('change', onJsonFileChange)
  document.getElementById('search-input').addEventListener('input', (e) => {
    renderTable(filterScenarios(e.target.value))
  })

  document
    .getElementById('open-template-modal')
    .addEventListener('click', openTemplateModal)
  document
    .getElementById('template-modal-close')
    .addEventListener('click', closeTemplateModal)
  document
    .getElementById('template-modal-backdrop')
    .addEventListener('click', closeTemplateModal)
  document
    .getElementById('tpl-tab-json')
    .addEventListener('click', () => switchTemplateTab('json'))
  document
    .getElementById('tpl-tab-md')
    .addEventListener('click', () => switchTemplateTab('md'))
})

// ── vectorDB 상태 조회 ─────────────────────────────────────────────────────────
async function fetchDbStatus() {
  const el = document.getElementById('db-status')
  try {
    const res = await fetch(`${API}/db-status`)
    const data = await res.json()
    if (data.status === 'ok') {
      el.textContent = `vectorDB: ${data.vector_count}개 벡터 적재됨`
      el.className =
        'text-sm font-medium text-green-600 bg-green-50 px-3 py-1 rounded-full'
    } else {
      el.textContent = `vectorDB 연결 오류`
      el.className =
        'text-sm font-medium text-red-600 bg-red-50 px-3 py-1 rounded-full'
    }
  } catch {
    el.textContent = 'Suppressor 연결 불가'
    el.className =
      'text-sm font-medium text-red-600 bg-red-50 px-3 py-1 rounded-full'
  }
}

// ── 시나리오 목록 조회 ─────────────────────────────────────────────────────────
async function fetchScenarios() {
  const tbody = document.getElementById('scenario-tbody')
  tbody.innerHTML = `
    <tr>
      <td colspan="4" class="px-6 py-8 text-center text-sm text-on-surface-variant">
        불러오는 중...
      </td>
    </tr>`

  try {
    const res = await fetch(`${API}/list`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    const data = await res.json()
    allScenarios = data.scenarios || []
    document.getElementById('total-count').textContent =
      `총 ${allScenarios.length}개`
    renderTable(allScenarios)
  } catch (err) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" class="px-6 py-8 text-center text-sm text-red-500">
          ${err.message}
        </td>
      </tr>`
  }
}

// ── 테이블 렌더링 ──────────────────────────────────────────────────────────────
function renderTable(scenarios) {
  const tbody = document.getElementById('scenario-tbody')

  if (scenarios.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" class="px-6 py-8 text-center text-sm text-on-surface-variant">
          시나리오가 없습니다.
        </td>
      </tr>`
    return
  }

  tbody.innerHTML = scenarios
    .map(
      (s) => `
    <tr class="hover:bg-surface-container-low transition-colors cursor-pointer" onclick="openDetail('${s.id}')">
      <td class="px-6 py-4">
        <div class="flex items-center gap-2">
          <span class="font-mono text-sm font-medium text-on-surface">${s.id}</span>
          ${
            s.builtin
              ? `<span class="text-[10px] px-1.5 py-0.5 bg-primary-container text-on-primary-container rounded-full font-bold">기본</span>`
              : ''
          }
        </div>
        ${
          s.pattern_name
            ? `<div class="text-xs text-on-surface-variant mt-0.5">${s.pattern_name}</div>`
            : ''
        }
      </td>
      <td class="px-6 py-4">
        <div class="flex flex-wrap gap-1">
          ${(s.behavior_tags || [])
            .slice(0, 3)
            .map(
              (tag) =>
                `<span class="text-xs px-2 py-0.5 bg-primary-container text-on-primary-container rounded-full">${tag}</span>`,
            )
            .join('')}
          ${
            (s.behavior_tags || []).length > 3
              ? `<span class="text-xs px-2 py-0.5 bg-surface-container text-on-surface-variant rounded-full">+${s.behavior_tags.length - 3}</span>`
              : ''
          }
        </div>
      </td>
      <td class="px-6 py-4">
        ${
          s.has_doc
            ? `<span class="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 px-2 py-1 rounded-full">
               <span class="material-symbols-outlined text-sm">check_circle</span> 있음
             </span>`
            : `<span class="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded-full">
               <span class="material-symbols-outlined text-sm">warning</span> 없음
             </span>`
        }
      </td>
      <td class="px-6 py-4 text-right">
        <button
          onclick="event.stopPropagation(); openDetail('${s.id}')"
          class="text-xs px-3 py-1.5 bg-surface-container-high hover:bg-surface-container-highest rounded-lg font-medium transition-colors mr-2"
        >
          상세
        </button>
        ${
          s.builtin
            ? `<button
                 disabled
                 title="기본 제공 시나리오는 삭제할 수 없습니다"
                 class="text-xs px-3 py-1.5 bg-surface-container text-on-surface-variant/50 rounded-lg font-medium cursor-not-allowed"
               >
                 삭제
               </button>`
            : `<button
                 onclick="event.stopPropagation(); confirmDelete('${s.id}')"
                 class="text-xs px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg font-medium transition-colors"
               >
                 삭제
               </button>`
        }
      </td>
    </tr>
  `,
    )
    .join('')
}

// ── 상세 페이지로 이동 ─────────────────────────────────────────────────────────
function openDetail(scenarioId) {
  window.location.href = `/scenario/${scenarioId}`
}

// ── 검색 필터 ──────────────────────────────────────────────────────────────────
function filterScenarios(keyword) {
  const q = keyword.trim().toLowerCase()
  if (!q) return allScenarios
  return allScenarios.filter(
    (s) =>
      s.id.toLowerCase().includes(q) ||
      (s.pattern_name || '').toLowerCase().includes(q) ||
      (s.behavior_tags || []).some((t) => t.toLowerCase().includes(q)),
  )
}

// ── 파일 입력 변경 시 파일명 표시 ─────────────────────────────────────────────
function onJsonFileChange(e) {
  const file = e.target.files[0]
  const label = document.getElementById('json-file-label')
  label.textContent = file ? file.name : 'JSON 파일 선택'
}

// ── 시나리오 업로드 ────────────────────────────────────────────────────────────
async function handleUpload(e) {
  e.preventDefault()

  const jsonInput = document.getElementById('json-file-input')
  const mdInput = document.getElementById('md-file-input')
  const btn = document.getElementById('upload-btn')

  if (!jsonInput.files[0]) {
    showToast('JSON 파일을 선택해주세요.', 'error')
    return
  }

  if (!mdInput.files[0]) {
    showToast('MD 문서를 선택해주세요.', 'error')
    return
  }

  const formData = new FormData()
  formData.append('json_file', jsonInput.files[0])
  formData.append('md_file', mdInput.files[0])

  btn.disabled = true
  btn.textContent = '업로드 중...'

  try {
    const res = await fetch(`${API}/upload`, {
      method: 'POST',
      body: formData,
    })
    const data = await res.json()

    if (!res.ok) {
      throw new Error(data.detail || '업로드 실패')
    }

    showToast(data.message, 'success')
    if (data.reload_required) {
      showToast('변경사항을 반영하려면 vectorDB 재적재가 필요합니다.', 'warn')
    }
    jsonInput.value = ''
    mdInput.value = ''
    document.getElementById('json-file-label').textContent = 'JSON 파일 선택'
    fetchScenarios()
    fetchDbStatus()
  } catch (err) {
    showToast(err.message, 'error')
  } finally {
    btn.disabled = false
    btn.textContent = '업로드'
  }
}

// ── vectorDB 재적재 ────────────────────────────────────────────────────────────
async function reloadVectorDB() {
  const btn = document.getElementById('reload-btn')
  const confirmed = await showConfirm(
    'vectorDB 재적재',
    '기존 벡터를 모두 삭제하고 현재 시나리오 파일 전체를 다시 임베딩합니다.\n시간이 걸릴 수 있습니다. 진행할까요?',
  )
  if (!confirmed) return

  btn.disabled = true
  btn.innerHTML = `<span class="material-symbols-outlined text-sm animate-spin">refresh</span> 재적재 중...`

  try {
    const res = await fetch(`${API}/reload`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '재적재 실패')
    showToast(`재적재 완료 — ${data.vector_count}개 벡터`, 'success')
    fetchDbStatus()
  } catch (err) {
    showToast(err.message, 'error')
  } finally {
    btn.disabled = false
    btn.innerHTML = `<span class="material-symbols-outlined text-sm">refresh</span> vectorDB 재적재`
  }
}

// ── 삭제 확인 ──────────────────────────────────────────────────────────────────
async function confirmDelete(scenarioId) {
  const confirmed = await showConfirm(
    '시나리오 삭제',
    `'${scenarioId}' 시나리오를 삭제합니다.\nJSON 파일과 MD 문서가 함께 삭제되며, vectorDB 재적재가 필요합니다.`,
  )
  if (!confirmed) return

  try {
    const res = await fetch(`${API}/delete/${scenarioId}`, { method: 'DELETE' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '삭제 실패')
    showToast(data.message, 'success')
    if (data.reload_required) {
      showToast('변경사항을 반영하려면 vectorDB 재적재가 필요합니다.', 'warn')
    }
    fetchScenarios()
    fetchDbStatus()
  } catch (err) {
    showToast(err.message, 'error')
  }
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

// ── 양식(템플릿) 모달 ──────────────────────────────────────────────────────────
async function openTemplateModal() {
  document.getElementById('template-modal').classList.remove('hidden')
  if (templatesLoaded) return

  try {
    const [jsonRes, mdRes] = await Promise.all([
      fetch('/static/templates/scenario_template.json'),
      fetch('/static/templates/scenario_template.md'),
    ])
    if (!jsonRes.ok || !mdRes.ok) throw new Error('템플릿 로드 실패')

    document.getElementById('tpl-json-content').textContent =
      await jsonRes.text()
    document.getElementById('tpl-md-content').textContent =
      await mdRes.text()
    templatesLoaded = true
  } catch {
    const msg = '템플릿을 불러올 수 없습니다.'
    document.getElementById('tpl-json-content').textContent = msg
    document.getElementById('tpl-md-content').textContent = msg
  }
}

function closeTemplateModal() {
  document.getElementById('template-modal').classList.add('hidden')
}

function switchTemplateTab(tab) {
  const isJson = tab === 'json'
  document.getElementById('tpl-panel-json').classList.toggle('hidden', !isJson)
  document.getElementById('tpl-panel-md').classList.toggle('hidden', isJson)

  const jsonTab = document.getElementById('tpl-tab-json')
  const mdTab = document.getElementById('tpl-tab-md')
  jsonTab.classList.toggle('border-primary', isJson)
  jsonTab.classList.toggle('text-primary', isJson)
  jsonTab.classList.toggle('border-transparent', !isJson)
  jsonTab.classList.toggle('text-on-surface-variant', !isJson)
  mdTab.classList.toggle('border-primary', !isJson)
  mdTab.classList.toggle('text-primary', !isJson)
  mdTab.classList.toggle('border-transparent', isJson)
  mdTab.classList.toggle('text-on-surface-variant', isJson)
}

// ── 토스트 알림 ────────────────────────────────────────────────────────────────
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

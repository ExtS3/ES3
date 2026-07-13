const STAGE_LABELS = {
    queued: '대기 중',
    holding: '대기',
    started: '검사 시작',
    file_saved: '파일 저장',
    rag_fingerprint: 'RAG 지문 추출',
    embedding: '임베딩',
    vector_search: '벡터 검색',
    rerank: '후보 재정렬',
    dynamic_rag: '동적 분석',
    dynamic_complete: '동적 분석 완료',
    static_analysis: '정적 분석',
    obfuscation_analysis: '난독화 분석',
    risk_scoring: '위험도 산정',
    risk_complete: '위험도 산정 완료',
    nexus_upload: 'Nexus 업로드',
    web_forward: '결과 전달',
    vscode_static_analysis: 'VSCode 정적 분석',
    complete: '완료',
    error: '오류',
};

const STATUS_LABELS = {
    holding: '홀딩 / 대기 중',
    queued: '대기 중',
    running: '검사 진행 중',
    success: '완료',
    review: '검토 대기',
    safe: '승인 됨',
    reject: '거부',
    error: '실패',
};

let isAdmin = false;

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
    }[char]));
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function statusClass(status) {
    if (status === 'success' || status === 'safe') return 'bg-green-50 text-green-700 border-green-200';
    if (status === 'error' || status === 'reject') return 'bg-red-50 text-red-700 border-red-200';
    if (status === 'running') return 'bg-blue-50 text-blue-700 border-blue-200';
    if (status === 'review') return 'bg-amber-50 text-amber-700 border-amber-200';
    return 'bg-slate-50 text-slate-700 border-slate-200';
}

function timeAgo(isoString) {
    if (!isoString) return '-';
    const diffSec = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
    if (Number.isNaN(diffSec)) return '-';
    if (diffSec < 60) return '방금 전';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}분 전`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}시간 전`;
    return new Date(isoString).toLocaleString();
}

function renderJobs(jobs) {
    const tbody = document.getElementById('scan-status-body');
    if (!tbody) return;

    if (!jobs.length) {
        tbody.innerHTML = `
            <tr>
              <td colspan="${isAdmin ? 8 : 7}" class="px-5 py-14 text-center text-on-surface-variant">
                <div class="flex flex-col items-center gap-3">
                  <span class="material-symbols-outlined text-5xl text-on-surface-variant/40">manage_search</span>
                  <p class="text-sm font-medium">아직 등록된 검사 내역이 없습니다.</p>
                </div>
              </td>
            </tr>`;
        return;
    }

    tbody.innerHTML = jobs.map((job) => {
        const status = job.status || 'queued';
        const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
        const stageKey = job.current_stage || job.current_stage_label || 'queued';
        const stageLabel = STAGE_LABELS[stageKey] || STAGE_LABELS[job.current_stage_label] || job.current_stage_label || stageKey;
        const updatedAt = timeAgo(job.updated_at);
        const adminCell = isAdmin
            ? `
              <td class="px-5 py-4 text-right">
                <button type="button" data-delete-job="${escapeHtml(job.job_id)}" title="내역 삭제"
                        class="p-1.5 rounded-lg text-on-surface-variant hover:bg-red-50 hover:text-red-600 transition-colors">
                  <span class="material-symbols-outlined text-base pointer-events-none">delete</span>
                </button>
              </td>`
            : '';

        return `
            <tr class="hover:bg-surface-container-low/60 transition-colors">
              <td class="px-5 py-4">
                <div class="font-semibold text-on-surface">${escapeHtml(job.ext_name || job.ext_id || '-')}</div>
                <div class="text-xs text-on-surface-variant mt-1">${escapeHtml(job.filename || job.job_id || '')}</div>
              </td>
              <td class="px-5 py-4 text-sm">${escapeHtml(job.browser || '-')}</td>
              <td class="px-5 py-4 text-sm">${escapeHtml(job.version || '-')}</td>
              <td class="px-5 py-4">
                <span class="inline-flex items-center px-2.5 py-1 rounded-full border text-xs font-bold ${statusClass(status)}">
                  ${STATUS_LABELS[status] || escapeHtml(status)}
                </span>
              </td>
              <td class="px-5 py-4 text-sm">${escapeHtml(stageLabel)}</td>
              <td class="px-5 py-4 min-w-[180px]">
                <div class="flex items-center gap-3">
                  <div class="h-2 w-full bg-surface-container-high rounded-full overflow-hidden">
                    <div class="h-full bg-primary rounded-full transition-all duration-500" style="width:${progress}%"></div>
                  </div>
                  <span class="text-xs font-bold text-on-surface-variant tabular-nums w-9 text-right">${progress}%</span>
                </div>
              </td>
              <td class="px-5 py-4 text-xs text-on-surface-variant">${escapeHtml(updatedAt)}</td>${adminCell}
            </tr>`;
    }).join('');
}

async function deleteScanJob(jobId) {
    if (!window.confirm('이 검사 내역을 삭제할까요?')) return;
    const response = await fetch(`/api/admin/scan-status/${encodeURIComponent(jobId)}`, {
        method: 'DELETE',
        credentials: 'same-origin',
    });
    if (!response.ok) {
        alert('삭제에 실패했습니다.');
        return;
    }
    await loadScanStatus().catch(console.error);
}

async function loadScanStatus() {
    const response = await fetch('/api/scan-status', {credentials: 'same-origin'});
    if (!response.ok) throw new Error(`status ${response.status}`);
    applyScanStatusPayload(await response.json());
}

function applyScanStatusPayload(data) {
    const counts = data.counts || {};
    setText('scan-count-running', counts.running || 0);
    setText('scan-count-queued', counts.queued || 0);
    setText('scan-count-review', counts.review || 0);
    setText('scan-count-complete', counts.done || 0);
    setText('scan-count-error', counts.error || 0);
    renderJobs(Array.isArray(data.jobs) ? data.jobs : []);
}

function startRealtimeUpdates() {
    if (!window.EventSource) return false;

    const source = new EventSource('/api/scan-status/stream');
    let opened = false;
    source.onopen = () => {
        opened = true;
    };
    source.onmessage = (event) => {
        try {
            applyScanStatusPayload(JSON.parse(event.data));
        } catch (error) {
            console.error(error);
        }
    };
    source.onerror = () => {
        source.close();
        if (!opened) {
            loadScanStatus().catch(console.error);
        }
        window.setInterval(() => {
            loadScanStatus().catch(console.error);
        }, 2000);
    };
    return true;
}

(async function initScanStatusPage() {
    const session = await (window.exts3SessionPromise || Promise.resolve({authenticated: false, roles: ['guest']}));
    const roles = Array.isArray(session.roles) ? session.roles : [];
    isAdmin = roles.includes('admin');

    document.querySelectorAll('[data-admin-only]').forEach((element) => {
        element.classList.toggle('hidden', !isAdmin);
    });

    const badge = document.getElementById('scan-access-badge');
    if (badge) {
        badge.innerHTML = isAdmin
            ? '<span class="material-symbols-outlined text-sm">admin_panel_settings</span>관리자'
            : '<span class="material-symbols-outlined text-sm">visibility</span>읽기 전용';
        badge.className = isAdmin
            ? 'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary-container text-on-primary-container text-xs font-bold'
            : 'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-container-low border border-outline-variant text-xs font-bold text-on-surface-variant';
    }

    const refreshButton = document.getElementById('scan-refresh-btn');
    if (refreshButton) {
        refreshButton.addEventListener('click', () => loadScanStatus().catch(console.error));
    }

    const tbody = document.getElementById('scan-status-body');
    if (tbody) {
        tbody.addEventListener('click', (event) => {
            const button = event.target.closest('[data-delete-job]');
            if (button) deleteScanJob(button.dataset.deleteJob).catch(console.error);
        });
    }

    await loadScanStatus().catch(console.error);
    if (!startRealtimeUpdates()) {
        window.setInterval(() => {
            loadScanStatus().catch(console.error);
        }, 2000);
    }
})();

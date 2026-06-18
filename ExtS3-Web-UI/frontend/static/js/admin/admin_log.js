let currentSummaryJson = null;
let currentLogJson = null;
let currentLogRequest = null;
let currentSummaryFileName = 'summary.json';
let currentPdfFileName = 'analysis_report.pdf';

document.addEventListener('DOMContentLoaded', () => {
    fetchLogData();
});

async function fetchLogData() {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id');
    const appName = params.get('name');
    const appBrowser = params.get('browser');
    const version = params.get('version') || '1.0.0';
    const sourcePath = params.get('source_path') || '';

    if (!id || !appName || !appBrowser) {
        showError('URL 파라미터가 올바르지 않습니다. id, name, browser가 필요합니다.');
        return;
    }

    showLoading(true);

    try {
        currentLogRequest = {
            id,
            app_name: appName,
            app_browser: appBrowser,
            version,
            source_path: sourcePath
        };

        const response = await fetch('/api/admin/log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentLogRequest)
        });
        const result = await response.json();

        if (!response.ok) {
            showError(`서버 오류: ${result.detail || response.statusText}`);
            return;
        }

        if (!result.success || !result.data) {
            showError('분석 데이터를 불러오지 못했습니다.');
            return;
        }

        const logs = result.data;
        const summary = logs.summary || {};
        currentSummaryJson = summary;
        currentLogJson = logs;
        currentSummaryFileName = `${sanitizeFileName(id)}_${sanitizeFileName(version)}_summary.json`;
        currentPdfFileName = `${sanitizeFileName(id)}_${sanitizeFileName(version)}_analysis_report.pdf`;

        renderBasicInfo({ id, appName, appBrowser, version, summary });
        updateSecurityBadges(summary);
        renderAnalysisReport(summary);
        renderJson('json-summary', summary);
        setupDownloadButton();
        setupPdfExportButton();
    } catch (error) {
        console.error('로그 데이터 로드 실패:', error);
        showError(`네트워크 오류: ${error.message}`);
    } finally {
        showLoading(false);
    }
}

function renderBasicInfo({ id, appName, appBrowser, version, summary }) {
    setText('head-app_name', appName);
    setText('info-app_name', appName);
    setText('info-app_browser', appBrowser);
    setText('info-version', version);
    setText('info-id', id);

    const payload = getPayload(summary);
    const extension = payload.extension || {};
    setText('info-app_type', extension.program_type || summary.category || summary.app_type || 'Extension');
    setText('info-submmit_date', payload.generated_at || summary.submitted_at || summary.submit_date || 'N/A');
}

function renderAnalysisReport(summary) {
    const payload = getPayload(summary);
    const overall = payload.overall || summary.summary || summary.final_risk_summary || {};
    const finalRisk = summary.final_risk_summary || overall || {};
    const decision = finalRisk.recommended_decision || overall.recommended_decision || summary.decision || summary.judge || 'review';
    const riskLevel = finalRisk.risk_level || overall.risk_level || 'UNKNOWN';
    const riskScore = toNumber(finalRisk.risk_score ?? overall.risk_score);
    const reason = finalRisk.decision_reason || overall.decision_reason || overall.summary || '분석 결과 확인이 필요합니다.';

    setText('card-decision', decisionLabel(decision));
    setText('card-risk-level', String(riskLevel).toUpperCase());
    setText('card-risk-score', Number.isFinite(riskScore) ? `${riskScore.toFixed(2)} / 1.0` : '-');
    setText('card-action', actionLabel(decision));
    setText('summary-reason', reason);

    renderHumanRiskSummary(payload);
    renderVersionDiff(payload);
    renderStaticSection(payload.static_analysis || {});
    renderDynamicSection(payload.dynamic_analysis || {}, finalRisk.component_scores?.dynamic || {});
    renderObfuscationSection(payload.obfuscation_analysis || {}, finalRisk.component_scores?.obfuscation || {});
    renderRagSection(payload.rag_analysis || {});
    renderReviewChecklist(payload);
}

function renderHumanRiskSummary(payload) {
    const staticAnalysis = payload.static_analysis || {};
    const dynamicAnalysis = payload.dynamic_analysis || {};
    const ragAnalysis = payload.rag_analysis || {};
    const lines = [];

    const permissions = staticAnalysis.permissions || [];
    if (permissions.includes('<all_urls>')) {
        lines.push('이 확장 프로그램은 모든 사이트에 접근할 수 있는 <all_urls> 권한을 요청합니다.');
    }

    const networkFindings = (staticAnalysis.key_findings || []).filter((finding) => {
        const text = `${finding.title || ''} ${finding.description || ''} ${finding.evidence || ''}`.toLowerCase();
        return text.includes('fetch') || text.includes('xmlhttprequest') || text.includes('request') || text.includes('url');
    });
    if (networkFindings.length > 0) {
        const files = unique(networkFindings.map((finding) => finding.file || extractEvidenceValue(finding.evidence, 'file')).filter(Boolean));
        lines.push(`${files.length ? files.join(', ') : '확장 프로그램 코드'}에서 외부 통신 또는 URL 이동과 관련된 정적 신호가 발견되었습니다.`);
    }

    const staticRisk = staticAnalysis.risk_level || payload.overall?.component_scores?.static?.risk_level;
    if (!permissions.includes('<all_urls>') && networkFindings.length === 0 && staticRisk) {
        lines.push(`정적 분석 위험도는 ${staticRisk}이며, 코드와 매니페스트에서 검토할 항목이 발견되었습니다.`);
    }

    const evidence = dynamicAnalysis.runtime_evidence || {};
    const network = toNumber(evidence.network_requests, 0);
    const storage = toNumber(evidence.storage_access, 0);
    const messages = toNumber(evidence.message_events, 0);
    if (network === 0 && storage === 0 && messages === 0) {
        lines.push('다만 실제 실행 중 네트워크 요청, 스토리지 접근, 메시지 이벤트는 관측되지 않았습니다.');
    }

    const factors = payload.overall?.risk_factors || dynamicAnalysis.risk_factors || [];
    if (factors.includes('candidate_only_static_match')) {
        lines.push('candidate_only_static_match는 코드상으로 의심 패턴과 유사하지만, 실제 실행 중에는 확인되지 않았다는 의미입니다.');
    }

    const topPattern = first(ragAnalysis.top_patterns);
    if (topPattern) {
        lines.push(`RAG 분석에서는 ${topPattern.pattern_name} 패턴이 가장 유사한 후보로 잡혔습니다.`);
    }

    if (lines.length === 0) {
        lines.push('요약 가능한 위험 근거가 충분하지 않습니다. raw JSON과 원본 분석 결과를 함께 확인하세요.');
    }

    setHtml('human-risk-summary', lines.map((line) => `<p>${escapeHtml(line)}</p>`).join(''));
}

// manifest.json 변경과 그 외 코드 파일 변경을 분리해 집계한다.
function splitVersionDiff(versionDiff) {
    const diff = (versionDiff && versionDiff.diff) || {};
    const files = diff.files || {};
    const isManifest = (p) => p === 'manifest.json' || String(p).endsWith('/manifest.json');

    const filesAdded = files.added || [];
    const filesRemoved = files.removed || [];
    const filesModified = files.modified || [];

    const manifestFile = filesModified.find((m) => isManifest(m.path)) || null;
    const codeAdded = filesAdded.filter((p) => !isManifest(p));
    const codeRemoved = filesRemoved.filter((p) => !isManifest(p));
    const codeModified = filesModified.filter((m) => !isManifest(m.path));

    const perms = diff.permissions || { added: [], removed: [] };
    const host = diff.host_permissions || { added: [], removed: [] };
    const optional = diff.optional_permissions || { added: [], removed: [] };
    const manifestChanges = diff.manifest_changes || [];

    const permsAdded = (perms.added || []).length;
    const permsRemoved = (perms.removed || []).length;
    const hostAdded = (host.added || []).length;
    const hostRemoved = (host.removed || []).length;
    const optAdded = (optional.added || []).length;
    const optRemoved = (optional.removed || []).length;

    const manifestChangeCount =
        permsAdded + permsRemoved + hostAdded + hostRemoved + optAdded + optRemoved + manifestChanges.length;
    const codeChangeCount = codeAdded.length + codeRemoved.length + codeModified.length;

    return {
        perms, host, optional, manifestChanges, manifestFile,
        codeAdded, codeRemoved, codeModified,
        counts: {
            permsAdded, permsRemoved, hostAdded, hostRemoved, optAdded, optRemoved,
            manifestFields: manifestChanges.length,
            manifestChangeCount,
            codeAdded: codeAdded.length,
            codeRemoved: codeRemoved.length,
            codeModified: codeModified.length,
            codeChangeCount,
        },
    };
}

function renderVersionDiff(payload) {
    const section = document.getElementById('version-diff-section');
    if (!section) return;

    const versionDiff = payload.version_diff;
    if (!versionDiff || !versionDiff.has_previous) {
        // 최초 버전이거나 변경 이력이 없으면 박스를 숨긴다.
        section.classList.add('hidden');
        return;
    }

    const prev = versionDiff.previous_version || '-';
    const curr = versionDiff.current_version || '-';
    const { counts } = splitVersionDiff(versionDiff);

    const subBox = (title, accent, count, label, bodyHtml) => `
        <div class="rounded-lg border ${accent.border} ${accent.bg} p-4">
            <div class="flex items-center justify-between mb-2">
                <h4 class="text-sm font-black ${accent.text}">${escapeHtml(title)}</h4>
                <span class="rounded-full px-2.5 py-0.5 text-xs font-bold ${accent.chip}">${count} ${escapeHtml(label)}</span>
            </div>
            ${bodyHtml}
        </div>`;

    const manifestBody = `
        <ul class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-on-surface-variant">
            <li>권한 추가: <b>${counts.permsAdded}</b></li>
            <li>권한 제거: <b>${counts.permsRemoved}</b></li>
            <li>호스트 권한 추가: <b>${counts.hostAdded}</b></li>
            <li>호스트 권한 제거: <b>${counts.hostRemoved}</b></li>
            <li>선택 권한 추가: <b>${counts.optAdded}</b></li>
            <li>선택 권한 제거: <b>${counts.optRemoved}</b></li>
            <li>기타 필드 변경: <b>${counts.manifestFields}</b></li>
        </ul>`;

    const codeBody = `
        <ul class="grid grid-cols-3 gap-x-4 gap-y-1 text-xs text-on-surface-variant">
            <li>파일 추가: <b>${counts.codeAdded}</b></li>
            <li>파일 제거: <b>${counts.codeRemoved}</b></li>
            <li>파일 수정: <b>${counts.codeModified}</b></li>
        </ul>
        ${counts.codeChangeCount === 0 ? '<p class="mt-2 text-xs text-on-surface-variant">manifest.json 외 코드 변경 없음</p>' : ''}`;

    setHtml('version-diff-summary', `
        <p class="mb-3 text-on-surface-variant">
            <span class="font-bold">v${escapeHtml(prev)}</span>
            <span class="material-symbols-outlined align-middle text-sm">arrow_forward</span>
            <span class="font-bold">v${escapeHtml(curr)}</span>
            버전 간 변경 요약입니다.
        </p>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            ${subBox('매니페스트 변경 (manifest.json)',
                { border: 'border-purple-200', bg: 'bg-purple-50/60', text: 'text-purple-800', chip: 'bg-purple-100 text-purple-800' },
                counts.manifestChangeCount, '건', manifestBody)}
            ${subBox('코드 변경 (manifest.json 외)',
                { border: 'border-blue-200', bg: 'bg-blue-50/60', text: 'text-blue-800', chip: 'bg-blue-100 text-blue-800' },
                counts.codeChangeCount, '개 파일', codeBody)}
        </div>
    `);

    section.classList.remove('hidden');
    setupVersionDiffButton(versionDiff);
}

function setupVersionDiffButton(versionDiff) {
    const button = document.getElementById('view-version-diff');
    if (!button) return;

    const params = new URLSearchParams(window.location.search);
    const id = params.get('id') || '';
    const version = params.get('version') || '';
    const storageKey = `version_diff:${id}:${version}`;

    try {
        sessionStorage.setItem(storageKey, JSON.stringify(versionDiff));
    } catch (e) {
        console.warn('version_diff 저장 실패:', e);
    }

    button.onclick = () => {
        const target = new URLSearchParams({
            id,
            name: params.get('name') || '',
            browser: params.get('browser') || '',
            version,
        });
        window.location.href = `/admin/version-diff?${target.toString()}`;
    };
}

function renderStaticSection(staticAnalysis) {
    const findings = staticAnalysis.key_findings || [];
    const permissions = staticAnalysis.permissions || [];
    const domains = staticAnalysis.external_domains || [];
    const items = [];

    permissions.slice(0, 5).forEach((permission) => items.push(`${permission} 권한 사용`));
    findings.slice(0, 6).forEach((finding) => {
        const file = finding.file || extractEvidenceValue(finding.evidence, 'file');
        items.push(file ? `${finding.title} (${file})` : finding.title);
    });

    setHtml('static-section', `
        ${fieldRow('위험도', staticAnalysis.risk_level || riskFromCounts(staticAnalysis.severity_counts) || 'UNKNOWN')}
        ${fieldRow('요약', staticAnalysis.summary || '정적 분석 요약 없음')}
        ${listBlock('주요 문제', items.length ? items : ['표시할 주요 문제가 없습니다.'])}
        ${listBlock('권한 근거', permissions.length ? permissions : ['권한 위험 신호 없음'])}
        ${listBlock('외부 도메인 근거', domains.length ? domains.slice(0, 8) : ['외부 도메인 없음'])}
    `);
}

function renderDynamicSection(dynamicAnalysis, dynamicScore) {
    const evidence = dynamicAnalysis.runtime_evidence || {};
    const factors = dynamicAnalysis.risk_factors || [];
    const network = toNumber(evidence.network_requests, 0);
    const storage = toNumber(evidence.storage_access, 0);
    const messages = toNumber(evidence.message_events, 0);
    const conclusion = network === 0 && storage === 0 && messages === 0
        ? '의심 후보는 있으나 재현 증거는 부족합니다.'
        : '실행 중 관측된 행위가 있어 세부 로그 확인이 필요합니다.';

    setHtml('dynamic-section', `
        ${fieldRow('위험도', dynamicAnalysis.risk_level || dynamicScore.risk_level || 'UNKNOWN')}
        ${fieldRow('실제 관측된 네트워크 요청', `${network}건`)}
        ${fieldRow('실제 관측된 스토리지 접근', `${storage}건`)}
        ${fieldRow('실제 관측된 메시지 이벤트', `${messages}건`)}
        ${listBlock('위험 플래그 의미', explainRiskFactors(factors))}
        ${fieldRow('결론', conclusion)}
    `);
}

function renderObfuscationSection(obfuscationAnalysis, obfuscationScore) {
    const files = obfuscationAnalysis.obfuscated_files || [];
    const indicators = obfuscationAnalysis.key_indicators || [];
    const packed = Boolean(obfuscationAnalysis.packed_or_minified);
    const riskLevel = obfuscationAnalysis.risk_level && obfuscationAnalysis.risk_level !== 'UNKNOWN'
        ? obfuscationAnalysis.risk_level
        : obfuscationScore.risk_level || 'LOW';

    setHtml('obfuscation-section', `
        ${fieldRow('위험도', riskLevel)}
        ${fieldRow('난독화 파일', files.length ? `${files.length}개` : '없음')}
        ${fieldRow('패킹/압축 의심', packed ? '있음' : '없음')}
        ${listBlock('주요 지표', indicators.length ? indicators : ['표시할 난독화 지표가 없습니다.'])}
    `);
}

function renderRagSection(ragAnalysis) {
    const topPattern = first(ragAnalysis.top_patterns) || {};
    const score = toNumber(topPattern.score);
    const threshold = topPattern.threshold_passed === true ? '후보 기준 통과' : '후보 기준 미통과';
    const judgment = topPattern.pattern_name
        ? `${threshold}. 실제 행위 증거와 함께 재검토해야 합니다.`
        : '비교 가능한 유사 패턴이 없습니다.';

    setHtml('rag-section', `
        ${fieldRow('가장 유사한 패턴', topPattern.pattern_name || '없음')}
        ${fieldRow('유사도', Number.isFinite(score) ? score.toFixed(2) : '-')}
        ${fieldRow('판단', judgment)}
        ${listBlock('근거', topPattern.evidence?.length ? topPattern.evidence : ['표시할 근거 없음'])}
    `);
}

function renderReviewChecklist(payload) {
    const staticAnalysis = payload.static_analysis || {};
    const domains = staticAnalysis.external_domains || [];
    const findings = staticAnalysis.key_findings || [];
    const files = unique(findings.map((finding) => finding.file || extractEvidenceValue(finding.evidence, 'file')).filter(Boolean));
    const hasAllUrls = (staticAnalysis.permissions || []).includes('<all_urls>');
    const checklist = [];

    checklist.push(hasAllUrls ? '<all_urls> 권한이 반드시 필요한지 확인' : '요청 권한이 기능 범위에 비해 과도하지 않은지 확인');
    checklist.push(domains.length ? `${domains.slice(0, 4).join(', ')} 등 외부 도메인 통신 목적 확인` : '외부 도메인 통신 목적 및 필요성 확인');
    checklist.push(files.length ? `${files.slice(0, 4).join(', ')}의 네트워크/탭/팝업 로직 검토` : 'background 또는 content script의 네트워크 로직 검토');
    checklist.push('사용자 세션, 입력값, 개인정보 전송 여부 확인');
    checklist.push('동적 분석 환경에서 실제 사용자 입력 또는 로그인 시나리오 재실행');

    setHtml('review-checklist', checklist.map((item) => `<li>${escapeHtml(item)}</li>`).join(''));
}

function updateSecurityBadges(summary) {
    const counts = summary.final_risk_summary?.severity_counts
        || summary.web_payload?.overall?.severity_counts
        || summary.summary?.severity_counts
        || {};

    setText('count-critical', counts.critical || 0);
    setText('count-high', counts.high || 0);
    setText('count-medium', counts.medium || 0);
    setText('count-low', counts.low || 0);
}

function setupDownloadButton() {
    const button = document.getElementById('download-summary-json');
    if (!button || button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';
    button.addEventListener('click', () => {
        if (!currentSummaryJson) return;
        const blob = new Blob([JSON.stringify(currentSummaryJson, null, 2)], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = currentSummaryFileName;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    });
}

function setupPdfExportButton() {
    const button = document.getElementById('export-analysis-pdf');
    if (!button || button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';
    button.addEventListener('click', exportAnalysisPdf);
}

async function exportAnalysisPdf() {
    const target = document.getElementById('security-analysis-report-section');
    const jsPdf = window.jspdf?.jsPDF;

    if (!target) {
        showError('PDF로 내보낼 리포트 영역을 찾지 못했습니다.');
        return;
    }
    if (!window.html2canvas || !jsPdf) {
        showError('PDF 내보내기 라이브러리를 불러오지 못했습니다. 네트워크 연결을 확인하세요.');
        return;
    }

    const controls = target.querySelectorAll('button');
    controls.forEach((button) => button.classList.add('hidden'));
    showLoading(true);

    try {
        const canvas = await window.html2canvas(target, {
            scale: 2,
            backgroundColor: '#ffffff',
            useCORS: true,
            logging: false,
        });
        const imageData = canvas.toDataURL('image/png');
        const pdf = new jsPdf('p', 'mm', 'a4');
        const pageWidth = pdf.internal.pageSize.getWidth();
        const pageHeight = pdf.internal.pageSize.getHeight();
        const margin = 8;
        const imageWidth = pageWidth - margin * 2;
        const imageHeight = (canvas.height * imageWidth) / canvas.width;

        let y = margin;
        let remainingHeight = imageHeight;

        pdf.addImage(imageData, 'PNG', margin, y, imageWidth, imageHeight);
        remainingHeight -= pageHeight - margin * 2;

        while (remainingHeight > 0) {
            pdf.addPage();
            y = margin - (imageHeight - remainingHeight);
            pdf.addImage(imageData, 'PNG', margin, y, imageWidth, imageHeight);
            remainingHeight -= pageHeight - margin * 2;
        }

        pdf.save(currentPdfFileName);
    } catch (error) {
        console.error('PDF 다운로드 실패:', error);
        showError(`PDF 다운로드 실패: ${error.message}`);
    } finally {
        controls.forEach((button) => button.classList.remove('hidden'));
        showLoading(false);
    }
}

function renderJson(elementId, data) {
    const element = document.getElementById(elementId);
    if (!element) return;
    element.textContent = data && Object.keys(data).length
        ? JSON.stringify(data, null, 2)
        : '분석 데이터가 없습니다.';
}

function getPayload(summary) {
    return summary.web_payload || summary || {};
}

function decisionLabel(value) {
    const normalized = String(value || '').toLowerCase();
    if (normalized === 'approve') return '승인 가능';
    if (normalized === 'reject') return '반려 권장';
    return '검토 필요';
}

function actionLabel(value) {
    const normalized = String(value || '').toLowerCase();
    if (normalized === 'approve') return '승인 가능';
    if (normalized === 'reject') return '승인 보류 및 반려 검토';
    return '승인 전 사람이 검토';
}

function explainRiskFactors(factors) {
    const map = {
        candidate_only_static_match: '코드상으로는 의심 패턴과 유사하지만, 실제 실행 중에는 확인되지 않았다는 의미',
        zero_dynamic_evidence: '동적 실행 중 네트워크 요청, 스토리지 접근, 메시지 이벤트 같은 재현 증거가 없다는 의미'
    };
    const explanations = (factors || []).map((factor) => map[factor] || `${factor}: 추가 해석이 필요한 분석 플래그`);
    return explanations.length ? explanations : ['특이 위험 플래그 없음'];
}

function riskFromCounts(counts = {}) {
    if (counts.critical > 0) return 'CRITICAL';
    if (counts.high > 0) return 'HIGH';
    if (counts.medium > 0) return 'MEDIUM';
    if (counts.low > 0) return 'LOW';
    return null;
}

function fieldRow(label, value) {
    return `
        <div class="flex justify-between gap-4 border-b border-slate-100 py-2">
            <span class="font-bold text-on-surface">${escapeHtml(label)}</span>
            <span class="text-right break-words">${escapeHtml(value ?? '-')}</span>
        </div>
    `;
}

function listBlock(label, items) {
    return `
        <div class="pt-3">
            <p class="font-bold text-on-surface mb-2">${escapeHtml(label)}</p>
            <ul class="list-disc pl-5 space-y-1">
                ${(items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}
            </ul>
        </div>
    `;
}

function extractEvidenceValue(evidence, key) {
    if (!evidence || typeof evidence !== 'string') return '';
    const quoted = new RegExp(`['"]${key}['"]\\s*:\\s*['"]([^'"]+)['"]`).exec(evidence);
    return quoted ? quoted[1] : '';
}

function first(value) {
    return Array.isArray(value) && value.length ? value[0] : null;
}

function unique(items) {
    return [...new Set(items)];
}

function toNumber(value, fallback = NaN) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value ?? '';
}

function setHtml(id, value) {
    const element = document.getElementById(id);
    if (element) element.innerHTML = value;
}

function textOf(id) {
    const element = document.getElementById(id);
    return element ? element.textContent.trim() : '';
}

function sanitizePrintableHtml(html) {
    const template = document.createElement('template');
    template.innerHTML = html || '';
    template.content.querySelectorAll('script, style, button').forEach((node) => node.remove());
    template.content.querySelectorAll('*').forEach((node) => {
        [...node.attributes].forEach((attr) => {
            if (attr.name.startsWith('on')) {
                node.removeAttribute(attr.name);
            }
        });
    });
    return template.innerHTML;
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function sanitizeFileName(value) {
    return String(value || 'analysis').replace(/[\\/:*?"<>|]+/g, '_');
}

function showLoading(isLoading) {
    const overlay = document.getElementById('loading-overlay');
    if (!overlay) return;
    overlay.classList.toggle('hidden', !isLoading);
}

function showError(message) {
    let banner = document.getElementById('error-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'error-banner';
        banner.className = 'fixed top-16 left-0 w-full z-50 bg-red-100 border-b border-red-300 text-red-700 text-sm font-medium px-6 py-3 flex items-center gap-2';
        banner.innerHTML = '<span class="material-symbols-outlined text-base">error</span><span id="error-banner-msg"></span>';
        document.body.prepend(banner);
    }
    document.getElementById('error-banner-msg').textContent = message;
    banner.classList.remove('hidden');
}

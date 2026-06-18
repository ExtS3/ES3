document.addEventListener('DOMContentLoaded', () => {
    init();
});

async function init() {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id') || '';
    const name = params.get('name') || '';
    const browser = params.get('browser') || '';
    const version = params.get('version') || '';

    setText('head-app_name', name || id || 'N/A');

    const backHref = `/admin/log?${new URLSearchParams({ id, name, browser, version }).toString()}`;
    const backLink = document.getElementById('back-to-log');
    if (backLink) backLink.href = backHref;
    const backBtn = document.getElementById('back-btn');
    if (backBtn) backBtn.onclick = () => { window.location.href = backHref; };

    let versionDiff = readFromSession(id, version);
    if (!versionDiff) {
        versionDiff = await fetchVersionDiff({ id, name, browser, version });
    }

    if (!versionDiff || !versionDiff.has_previous || !versionDiff.diff) {
        showEmpty('표시할 버전 변경 내역이 없습니다. (최초 버전이거나 변경 사항 없음)');
        return;
    }

    render(versionDiff);
}

function readFromSession(id, version) {
    try {
        const raw = sessionStorage.getItem(`version_diff:${id}:${version}`);
        return raw ? JSON.parse(raw) : null;
    } catch (e) {
        return null;
    }
}

async function fetchVersionDiff({ id, name, browser, version }) {
    showLoading(true);
    try {
        const response = await fetch('/api/admin/log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, app_name: name, app_browser: browser, version, source_path: '' })
        });
        const result = await response.json();
        if (!response.ok || !result.success || !result.data) return null;
        const summary = result.data.summary || {};
        const payload = summary.web_payload || summary || {};
        return payload.version_diff || null;
    } catch (e) {
        console.error('version_diff 로드 실패:', e);
        return null;
    } finally {
        showLoading(false);
    }
}

function render(versionDiff) {
    const prev = versionDiff.previous_version || '-';
    const curr = versionDiff.current_version || '-';
    setText('head-version-range', `v${prev} → v${curr}`);

    const split = splitVersionDiff(versionDiff);
    renderSummary(split.counts, prev, curr);
    renderManifestSection(split);
    renderCodeSection(split);
}

// manifest.json 변경과 그 외 코드 파일 변경을 분리한다. (admin_log.js와 동일 규칙)
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

    const manifestChangeCount =
        (perms.added || []).length + (perms.removed || []).length +
        (host.added || []).length + (host.removed || []).length +
        (optional.added || []).length + (optional.removed || []).length +
        manifestChanges.length;
    const codeChangeCount = codeAdded.length + codeRemoved.length + codeModified.length;

    return {
        perms, host, optional, manifestChanges, manifestFile,
        codeAdded, codeRemoved, codeModified,
        counts: { manifestChangeCount, codeChangeCount },
    };
}

function renderSummary(counts, prev, curr) {
    const chip = (label, count, tone) => `
        <span class="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-bold ${tone}">
            ${escapeHtml(label)} <span class="font-black">${count}</span>
        </span>`;
    const manifestTone = counts.manifestChangeCount > 0 ? 'bg-purple-100 text-purple-800' : 'bg-slate-100 text-slate-500';
    const codeTone = counts.codeChangeCount > 0 ? 'bg-blue-100 text-blue-800' : 'bg-slate-100 text-slate-500';

    setHtml('diff-summary', `
        <p class="mb-3 text-sm text-on-surface-variant">
            <span class="font-bold text-on-surface">v${escapeHtml(prev)}</span>
            <span class="material-symbols-outlined align-middle text-sm">arrow_forward</span>
            <span class="font-bold text-on-surface">v${escapeHtml(curr)}</span>
            버전 간 전체 변경 내역입니다.
        </p>
        <div class="flex flex-wrap gap-2">
            ${chip('매니페스트 변경', counts.manifestChangeCount, manifestTone)}
            ${chip('코드 변경 파일', counts.codeChangeCount, codeTone)}
        </div>
    `);
}

function permissionBlock(title, group) {
    const added = (group && group.added) || [];
    const removed = (group && group.removed) || [];
    if (!added.length && !removed.length) return '';

    const pills = (items, tone, sign) => items.map((it) =>
        `<span class="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ${tone}">${sign} ${escapeHtml(String(it))}</span>`
    ).join('');

    return `
        <article class="bg-white rounded-xl border border-outline/10 p-5">
            <h4 class="text-sm font-black text-on-surface mb-3">${escapeHtml(title)}</h4>
            <div class="flex flex-wrap gap-2">
                ${pills(added, 'bg-green-100 text-green-800', '+')}
                ${pills(removed, 'bg-red-100 text-red-800', '−')}
            </div>
        </article>`;
}

function renderManifestSection(split) {
    const blocks = [];
    blocks.push(permissionBlock('권한 (permissions)', split.perms));
    blocks.push(permissionBlock('호스트 권한 (host_permissions)', split.host));
    blocks.push(permissionBlock('선택 권한 (optional_permissions)', split.optional));

    if (split.manifestChanges.length) {
        const rows = split.manifestChanges.map((c) => `
            <div class="border-b border-slate-100 py-2 text-sm">
                <p class="font-bold text-on-surface">${escapeHtml(c.field)}</p>
                <p class="text-xs text-red-700 break-all">- ${escapeHtml(formatValue(c.from))}</p>
                <p class="text-xs text-green-700 break-all">+ ${escapeHtml(formatValue(c.to))}</p>
            </div>`).join('');
        blocks.push(`
            <article class="bg-white rounded-xl border border-outline/10 p-5">
                <h4 class="text-sm font-black text-on-surface mb-3">기타 매니페스트 필드 변경</h4>
                ${rows}
            </article>`);
    }

    if (split.manifestFile) {
        blocks.push(fileCardForModified(split.manifestFile, 'manifest.json 원본 diff'));
    }

    const body = blocks.filter(Boolean);
    setHtml('manifest-changes', `
        <h3 class="text-base font-bold text-on-surface flex items-center gap-2 mb-1">
            <span class="material-symbols-outlined text-purple-600">description</span>
            매니페스트 변경 (manifest.json)
        </h3>
        ${body.length
            ? `<div class="space-y-4">${body.join('')}</div>`
            : `<div class="bg-surface-container-low rounded-xl p-6 text-center text-sm text-on-surface-variant">매니페스트 변경 사항이 없습니다.</div>`}
    `);
}

function renderCodeSection(split) {
    const parts = [];

    split.codeAdded.forEach((path) => {
        parts.push(fileCard(path, '추가됨', 'bg-green-100 text-green-800', `
            <div class="p-4 text-xs text-green-700 font-mono">새로 추가된 파일입니다.</div>`));
    });
    split.codeRemoved.forEach((path) => {
        parts.push(fileCard(path, '삭제됨', 'bg-red-100 text-red-800', `
            <div class="p-4 text-xs text-red-700 font-mono">삭제된 파일입니다.</div>`));
    });
    split.codeModified.forEach((entry) => {
        parts.push(fileCardForModified(entry));
    });

    setHtml('code-changes', `
        <h3 class="text-base font-bold text-on-surface flex items-center gap-2 mb-1">
            <span class="material-symbols-outlined text-blue-600">code</span>
            코드 변경 (manifest.json 외)
        </h3>
        ${parts.length
            ? `<div class="space-y-4">${parts.join('')}</div>`
            : `<div class="bg-surface-container-low rounded-xl p-6 text-center text-sm text-on-surface-variant">manifest.json 외 코드 변경 사항이 없습니다.</div>`}
    `);
}

function fileCardForModified(entry, titleOverride) {
    let body;
    if (entry.is_minified) {
        body = `<div class="p-4 text-xs text-on-surface-variant">난독화/압축된 파일이라 인라인 diff를 표시하지 않습니다.</div>`;
    } else if (entry.diff) {
        body = renderUnifiedDiff(entry.diff);
        if (entry.diff_truncated) {
            body += `<div class="px-4 py-2 text-xs text-amber-700 bg-amber-50">diff가 너무 길어 일부만 표시했습니다.</div>`;
        }
    } else {
        body = `<div class="p-4 text-xs text-on-surface-variant">이전 버전 원본을 찾을 수 없어 변경된 파일 정보만 표시합니다. (sha256: ${escapeHtml((entry.from_sha256 || '').slice(0, 12))} → ${escapeHtml((entry.to_sha256 || '').slice(0, 12))})</div>`;
    }
    return fileCard(titleOverride || entry.path, '수정됨', 'bg-blue-100 text-blue-800', body);
}

function fileCard(path, badge, badgeTone, bodyHtml) {
    return `
        <article class="bg-white rounded-xl border border-outline/10 overflow-hidden">
            <div class="flex items-center justify-between gap-3 px-4 py-2.5 bg-surface-container-low border-b border-outline/10">
                <span class="font-mono text-xs font-bold text-on-surface break-all">${escapeHtml(path)}</span>
                <span class="shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-bold ${badgeTone}">${escapeHtml(badge)}</span>
            </div>
            ${bodyHtml}
        </article>`;
}

function renderUnifiedDiff(diffText) {
    const lines = String(diffText).split('\n');
    let oldLn = 0;
    let newLn = 0;
    const rows = [];

    for (const line of lines) {
        if (line.startsWith('--- ') || line.startsWith('+++ ')) {
            continue;
        }
        if (line.startsWith('@@')) {
            const m = /@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
            if (m) {
                oldLn = parseInt(m[1], 10);
                newLn = parseInt(m[2], 10);
            }
            rows.push(`<tr class="diff-hunk"><td class="diff-ln"></td><td class="diff-ln"></td><td>${escapeHtml(line)}</td></tr>`);
            continue;
        }
        if (line.startsWith('+')) {
            rows.push(`<tr class="diff-add"><td class="diff-ln"></td><td class="diff-ln">${newLn}</td><td>${escapeHtml(line)}</td></tr>`);
            newLn++;
        } else if (line.startsWith('-')) {
            rows.push(`<tr class="diff-del"><td class="diff-ln">${oldLn}</td><td class="diff-ln"></td><td>${escapeHtml(line)}</td></tr>`);
            oldLn++;
        } else {
            rows.push(`<tr><td class="diff-ln">${oldLn}</td><td class="diff-ln">${newLn}</td><td>${escapeHtml(line)}</td></tr>`);
            oldLn++;
            newLn++;
        }
    }

    return `<div class="overflow-x-auto"><table class="diff-table w-full border-collapse"><tbody>${rows.join('')}</tbody></table></div>`;
}

function formatValue(value) {
    if (value === null || value === undefined) return '(없음)';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
}

function showEmpty(message) {
    const el = document.getElementById('diff-empty');
    if (!el) return;
    el.textContent = message;
    el.classList.remove('hidden');
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? '';
}

function setHtml(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = value;
}

function showLoading(isLoading) {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.toggle('hidden', !isLoading);
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

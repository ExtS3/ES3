function toNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
}

function formatBytes(bytes) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = Math.max(0, bytes);
    let unitIndex = 0;

    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }

    const digits = value >= 10 || unitIndex === 0 ? 0 : 2;
    return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[char]));
}

function getSafeItemMeta(item) {
    // Nexus path shape: {status}/{browser}/{name}/{version}/{id}.zip
    const pathParts = String(item.path ?? '').split('/');
    const fullFileName = pathParts[4] || '';

    return {
        browser: pathParts[1] || 'unknown',
        name: pathParts[2] || 'Unknown Name',
        version: pathParts[3] || '0.0.0',
        extId: fullFileName.split('.')[0] || 'Unknown ID',
    };
}

function formatBrowserLabel(browser) {
    const key = String(browser || '').toLowerCase();
    if (key === 'chrome') return 'Chrome';
    if (key === 'vscode') return 'VS Code';
    return browser || 'Unknown';
}

function formatBrowserBreakdown(items) {
    if (items.length === 0) return '';

    const counts = new Map();
    items.forEach((item) => {
        const label = formatBrowserLabel(getSafeItemMeta(item).browser);
        counts.set(label, (counts.get(label) || 0) + 1);
    });

    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    const top = sorted.slice(0, 3).map(([label, count]) => `${label} ${count}개`);
    const restCount = sorted.length - 3;
    if (restCount > 0) top.push(`외 ${restCount}종`);

    return top.join(' · ');
}

function buildClientSummary(items, safeItems) {
    return {
        totalStorageBytes: items.reduce((sum, item) => sum + toNumber(item.fileSize), 0),
        availableStorageBytes: null,
        storageLimitBytes: null,
        activeRepositoryCount: new Set(safeItems.map((item) => getSafeItemMeta(item).name)).size,
        safeAssetCount: safeItems.length,
        extensionActivityPercent: items.length > 0
            ? Math.round((safeItems.length / items.length) * 100)
            : 0,
    };
}

function updateDashboardStats(items, safeItems, summary = null) {
    const stats = summary || buildClientSummary(items, safeItems);
    const totalBytes = toNumber(stats.totalStorageBytes);
    const storageLimitBytes = stats.storageLimitBytes === null ? null : toNumber(stats.storageLimitBytes);
    const hasStorageLimit = storageLimitBytes > 0;
    const activeRepoCount = toNumber(stats.activeRepositoryCount);

    document.getElementById('storage-used-value').textContent = formatBytes(totalBytes);
    document.getElementById('storage-total-value').textContent = hasStorageLimit
        ? `/ ${formatBytes(storageLimitBytes)}`
        : '사용 중';
    document.getElementById('active-repo-count').textContent = activeRepoCount.toLocaleString();
    document.getElementById('storage-browser-breakdown').textContent = formatBrowserBreakdown(items);
}

async function downloadSafeAsset(button) {
    const nexusPath = button.dataset.nexusPath;
    if (!nexusPath) return;

    try {
        const response = await fetch(`/api/nexus/download?path=${encodeURIComponent(nexusPath)}`);
        if (!response.ok) {
            alert(response.status === 401 || response.status === 403
                ? '다운로드 권한이 없습니다.'
                : '다운로드에 실패했습니다.');
            return;
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = button.dataset.fileName || 'extension.zip';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    } catch (error) {
        console.error('다운로드 실패:', error);
        alert('다운로드 중 오류가 발생했습니다.');
    }
}

window.addEventListener('DOMContentLoaded', async () => {
    const repoContainer = document.getElementById('repo-list');

    try {
        const [response, session] = await Promise.all([
            fetch('/api/nexus/dashboard', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
            }),
            window.exts3SessionPromise || Promise.resolve({}),
        ]);

        if (!response.ok) {
            throw new Error(`Nexus dashboard request failed: ${response.status}`);
        }

        const result = await response.json();
        const items = Array.isArray(result.items) ? result.items : [];
        const safeItems = items.filter((item) => String(item.path ?? '').startsWith('safe/'));

        updateDashboardStats(items, safeItems, result.summary);
        repoContainer.innerHTML = '';

        if (safeItems.length === 0) {
            repoContainer.innerHTML = '<div class="es3-empty col-span-full"><span class="material-symbols-outlined">travel_explore</span><p>아직 검증된 확장 프로그램이 없습니다.</p><a href="/search" class="es3-btn">앱 탐색하기</a></div>';
            return;
        }

        // /detail은 로그인만 요구(require_authenticated_page), 다운로드는
        // /api/nexus/download의 install_extension 권한을 그대로 따른다.
        const permissions = Array.isArray(session?.permissions) ? session.permissions : [];
        const canViewDetail = Boolean(session?.authenticated);
        const canDownload = canViewDetail && permissions.includes('install_extension');

        safeItems.slice(0, 3).forEach((item) => {
            const { browser, name, version, extId } = getSafeItemMeta(item);
            const fileSizeMB = (toNumber(item.fileSize) / (1024 * 1024)).toFixed(2);
            const detailUrl = `/detail?extID=${encodeURIComponent(extId)}&browser=${encodeURIComponent(browser)}`;

            const cardHTML = `
            <div class="bg-surface-container-lowest p-5 rounded-xl transition-all hover:translate-y-[-4px] group border border-outline-variant/10">
                <div class="flex items-start justify-between mb-4">
                    <div class="flex items-center gap-3">
                        <div class="w-12 h-12 bg-indigo-50 rounded-xl flex items-center justify-center text-primary font-bold text-xl">
                            ${escapeHtml(name.charAt(0).toUpperCase())}
                        </div>
                        <div>
                            <h4 class="font-bold text-on-surface group-hover:text-primary transition-colors">${escapeHtml(name)}</h4>
                            <p class="text-xs text-on-surface-variant flex items-center gap-1">
                                <span class="material-symbols-outlined text-[14px]">public</span>
                                ${escapeHtml(formatBrowserLabel(browser))}
                            </p>
                        </div>
                    </div>
                    <span class="px-2 py-1 bg-green-100 text-green-700 text-[10px] font-bold rounded-md uppercase">Safe</span>
                </div>

                <div class="space-y-2 py-3">
                    <div class="flex justify-between text-xs">
                        <span class="text-on-surface-variant">ID</span>
                        <span class="font-mono text-slate-500">${escapeHtml(extId)}</span>
                    </div>
                    <div class="flex justify-between text-xs">
                        <span class="text-on-surface-variant">버전</span>
                        <span class="font-bold">${escapeHtml(version)}</span>
                    </div>
                    <div class="flex justify-between text-xs">
                        <span class="text-on-surface-variant">용량</span>
                        <span class="font-bold">${fileSizeMB} MB</span>
                    </div>
                </div>

                <div class="mt-4 pt-4 border-t border-slate-100 flex gap-2">
                    <button type="button" class="detail-btn flex-1 py-2 text-xs font-bold text-primary bg-primary-container rounded-lg hover:bg-primary hover:text-on-primary transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                            data-detail-url="${escapeHtml(detailUrl)}"
                            ${canViewDetail ? '' : 'disabled title="로그인이 필요합니다"'}>
                        상세 정보
                    </button>
                    <button type="button" class="download-btn p-2 text-on-surface-variant bg-surface-container hover:bg-surface-dim rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                            data-nexus-path="${escapeHtml(item.path ?? '')}"
                            data-file-name="${escapeHtml(extId)}.zip"
                            title="${canDownload ? '다운로드' : '다운로드 권한이 없습니다'}"
                            ${canDownload ? '' : 'disabled'}>
                        <span class="material-symbols-outlined text-sm">download</span>
                    </button>
                </div>
            </div>`;

            repoContainer.insertAdjacentHTML('beforeend', cardHTML);
        });

        repoContainer.querySelectorAll('.detail-btn').forEach((button) => {
            button.addEventListener('click', () => {
                window.location.href = button.dataset.detailUrl;
            });
        });

        repoContainer.querySelectorAll('.download-btn').forEach((button) => {
            button.addEventListener('click', () => downloadSafeAsset(button));
        });
    } catch (error) {
        console.error('데이터 로딩 실패:', error);
        updateDashboardStats([], []);
        repoContainer.innerHTML = '<p class="text-error text-center py-10">로그인 이후 이용 가능한 서비스입니다.</p>';
    }
});

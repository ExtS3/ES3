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
    const pathParts = String(item.path ?? '').split('/');
    const fullFileName = pathParts[3] || '';

    return {
        name: pathParts[1] || 'Unknown Name',
        version: pathParts[2] || '0.0.0',
        extId: fullFileName.split('.')[0] || 'Unknown ID',
    };
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
    const availableBytes = stats.availableStorageBytes === null ? null : toNumber(stats.availableStorageBytes);
    const storageLimitBytes = stats.storageLimitBytes === null ? null : toNumber(stats.storageLimitBytes);
    const hasStorageLimit = storageLimitBytes > 0;
    const remainingBytes = availableBytes !== null
        ? availableBytes
        : hasStorageLimit
            ? Math.max(storageLimitBytes - totalBytes, 0)
            : null;
    const usedPercent = hasStorageLimit
        ? Math.min(100, Math.round((totalBytes / storageLimitBytes) * 100))
        : 0;
    const activeRepoCount = toNumber(stats.activeRepositoryCount);
    const safeAssetCount = toNumber(stats.safeAssetCount);

    document.getElementById('storage-used-value').textContent = formatBytes(totalBytes);
    document.getElementById('storage-total-value').textContent = hasStorageLimit
        ? `/ ${formatBytes(storageLimitBytes)}`
        : '사용 중';
    document.getElementById('storage-progress-bar').style.width = `${usedPercent}%`;
    document.getElementById('active-repo-count').textContent = activeRepoCount.toLocaleString();
    document.getElementById('verified-item-count').textContent = safeAssetCount.toLocaleString();

    const storageProgressBar = document.getElementById('storage-progress-bar');
    const storageLabels = storageProgressBar
        ?.parentElement
        ?.nextElementSibling
        ?.querySelectorAll('span');
    const percentLabel = document.getElementById('storage-used-percent') || storageLabels?.[0];
    if (percentLabel) {
        percentLabel.textContent = hasStorageLimit ? `${usedPercent}% 사용 중` : 'Nexus blob store 합계';
    }

    const remainingLabel = document.getElementById('storage-remaining-value') || storageLabels?.[1];
    if (remainingLabel) {
        remainingLabel.textContent = remainingBytes !== null
            ? `남은 용량: ${formatBytes(remainingBytes)}`
            : '남은 용량 확인 불가';
    }
}

window.addEventListener('DOMContentLoaded', async () => {
    const repoContainer = document.getElementById('repo-list');

    try {
        const response = await fetch('/api/nexus/dashboard', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
        });

        if (!response.ok) {
            throw new Error(`Nexus dashboard request failed: ${response.status}`);
        }

        const result = await response.json();
        const items = Array.isArray(result.items) ? result.items : [];
        const safeItems = items.filter((item) => String(item.path ?? '').startsWith('safe/'));

        updateDashboardStats(items, safeItems, result.summary);
        repoContainer.innerHTML = '';

        if (safeItems.length === 0) {
            repoContainer.innerHTML = '<p class="text-on-surface-variant text-center py-10">안전 검사가 완료된 항목이 없습니다.</p>';
            return;
        }

        safeItems.slice(0, 3).forEach((item) => {
            const { name, version, extId } = getSafeItemMeta(item);
            const fileSizeMB = (toNumber(item.fileSize) / (1024 * 1024)).toFixed(2);
            const detailUrl = `/detail?name=${encodeURIComponent(name)}&version=${encodeURIComponent(version)}&id=${encodeURIComponent(extId)}`;

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
                                <span class="material-symbols-outlined text-[14px]">sell</span>
                                v${escapeHtml(version)}
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
                        <span class="text-on-surface-variant">용량</span>
                        <span class="font-bold">${fileSizeMB} MB</span>
                    </div>
                </div>

                <div class="mt-4 pt-4 border-t border-slate-100 flex gap-2">
                    <button onclick="location.href='${detailUrl}'"
                            class="flex-1 py-2 text-xs font-bold text-primary bg-primary-container rounded-lg hover:bg-primary hover:text-on-primary transition-all">
                        상세 정보
                    </button>
                    <button id="download-btn"
                            class="p-2 text-on-surface-variant bg-surface-container hover:bg-surface-dim rounded-lg transition-colors"
                            title="다운로드">
                        <span class="material-symbols-outlined text-sm">download</span>
                    </button>
                </div>
            </div>`;

            repoContainer.insertAdjacentHTML('beforeend', cardHTML);
        });
    } catch (error) {
        console.error('데이터 로딩 실패:', error);
        updateDashboardStats([], []);
        repoContainer.innerHTML = '<p class="text-red-500">데이터를 불러오는 중 에러가 발생했습니다.</p>';
    }
});

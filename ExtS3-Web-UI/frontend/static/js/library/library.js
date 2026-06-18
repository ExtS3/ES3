// Nexus library list with optional extension-name filtering.
window.addEventListener('DOMContentLoaded', async () => {
    let allSafeItems = [];
    let filteredSafeItems = [];
    let currentPage = 1;
    const itemsPerPage = 10;

    const listContainer = document.getElementById('nexus-item-list');
    const paginationContainer = document.getElementById('pagination-controls');
    const searchForm = document.getElementById('library-search-form');
    const searchInput = document.getElementById('library-search-input');
    const searchClear = document.getElementById('library-search-clear');
    const searchParams = new URLSearchParams(window.location.search);
    const extNameQuery = (searchParams.get('extName') || '').trim();

    if (searchInput) {
        searchInput.value = extNameQuery;
    }

    if (searchClear && extNameQuery) {
        searchClear.classList.remove('hidden');
        searchClear.classList.add('inline-flex');
    }

    if (searchForm) {
        searchForm.addEventListener('submit', event => {
            event.preventDefault();
            const value = (searchInput?.value || '').trim();
            if (!value) {
                window.location.href = '/library';
                return;
            }

            const params = new URLSearchParams();
            params.set('extName', value);
            window.location.href = `/library?${params.toString()}`;
        });
    }

    try {
        const response = await fetch('/api/nexus/list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });

        const result = await response.json();
        const rawData = Array.isArray(result) ? result : (result.items || []);

        allSafeItems = rawData.filter(item => {
            const itemPath = item.path || item.name || '';
            return itemPath.startsWith('safe/') || item.status === 'safe';
        });

        filteredSafeItems = filterItemsByExtName(allSafeItems, extNameQuery);
        updateStats(filteredSafeItems);
        renderList(currentPage);
    } catch (error) {
        console.error('Failed to load Nexus library data:', error);
        if (listContainer) {
            listContainer.innerHTML = '<p class="text-center py-10 text-red-500">Failed to load library data.</p>';
        }
    }

    function updateStats(items) {
        const totalCount = document.getElementById('stat-total-count');
        const updateCountEl = document.getElementById('stat-update-count');
        const pulse = document.getElementById('update-pulse');
        const updateCount = items.filter(item => item.update_available === true).length;

        if (totalCount) totalCount.innerText = items.length;
        if (updateCountEl) updateCountEl.innerText = updateCount;

        if (!pulse) return;
        if (updateCount > 0) {
            pulse.classList.remove('hidden');
        } else {
            pulse.classList.add('hidden');
        }
    }

    function renderList(page) {
        if (!listContainer) return;
        listContainer.innerHTML = '';

        const startIndex = (page - 1) * itemsPerPage;
        const endIndex = startIndex + itemsPerPage;
        const pageItems = filteredSafeItems.slice(startIndex, endIndex);

        if (pageItems.length === 0) {
            const message = extNameQuery
                ? `"${escapeHtml(extNameQuery)}" search results were not found in the safe library.`
                : 'No safe library items were found.';
            listContainer.innerHTML = `<p class="text-center py-10 text-on-surface-variant">${message}</p>`;
            if (paginationContainer) paginationContainer.innerHTML = '';
            return;
        }

        pageItems.forEach(item => {
            const parsed = parseSafeItem(item);
            const itemPath = item.path || item.name || '';
            const itemHtml = `
                <div class="flex items-center justify-between p-4 border-b border-surface-container-highest hover:bg-surface-container-low transition-colors">
                    <div class="flex items-center gap-4 min-w-0">
                        <div class="p-2 bg-secondary-container rounded-lg">
                            <span class="material-symbols-outlined text-secondary">deployed_code</span>
                        </div>
                        <div class="min-w-0">
                            <h4 class="font-medium text-on-surface truncate">${escapeHtml(parsed.appName)}</h4>
                            <p class="text-sm text-on-surface-variant">${escapeHtml(parsed.browser)} - ${escapeHtml(parsed.version)}</p>
                            <p class="text-[11px] text-on-surface-variant font-mono mt-1 break-all">${escapeHtml(parsed.extensionId)}</p>
                        </div>
                    </div>
                    <div class="flex items-center gap-3">
                        ${item.update_available ? '<span class="px-2 py-1 bg-error-container text-error text-xs rounded-full font-bold uppercase tracking-wider">Update</span>' : ''}
                        <span class="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full font-bold uppercase tracking-wider">Safe</span>
                        <div class="relative">
                            <button
                                type="button"
                                class="library-action-trigger inline-flex items-center gap-1.5 px-4 py-2 bg-primary text-on-primary rounded-lg text-sm font-bold hover:bg-primary-dim transition-colors"
                                data-extension-id="${escapeHtml(parsed.extensionId)}"
                                data-extension-name="${escapeHtml(parsed.appName)}"
                                data-nexus-path="${escapeHtml(itemPath)}"
                                aria-haspopup="menu"
                                aria-expanded="false">
                                <span class="material-symbols-outlined text-sm">download</span>
                                설치
                                <span class="material-symbols-outlined text-sm">expand_more</span>
                            </button>
                            <div class="library-action-menu hidden absolute right-0 top-11 z-20 w-48 overflow-hidden rounded-lg border border-outline-variant/30 bg-white shadow-xl">
                                <button type="button" class="library-menu-item crx-download-btn" data-extension-id="${escapeHtml(parsed.extensionId)}" data-extension-name="${escapeHtml(parsed.appName)}" data-nexus-path="${escapeHtml(itemPath)}">
                                    <span class="material-symbols-outlined text-base">inventory_2</span>
                                    CRX 수동 설치 파일
                                </button>
                                <button type="button" class="library-menu-item install-batch-btn" data-extension-id="${escapeHtml(parsed.extensionId)}" data-extension-name="${escapeHtml(parsed.appName)}">
                                    <span class="material-symbols-outlined text-base">settings</span>
                                    정책 설치 배치
                                </button>
                                <button type="button" class="library-menu-item uninstall-batch-btn" data-extension-id="${escapeHtml(parsed.extensionId)}" data-extension-name="${escapeHtml(parsed.appName)}">
                                    <span class="material-symbols-outlined text-base">delete</span>
                                    정책 해제 배치
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            listContainer.insertAdjacentHTML('beforeend', itemHtml);
        });

        bindActionMenus();
        renderPagination();
    }

    function parseSafeItem(item) {
        const pathParts = (item.path || item.name || '').split('/').filter(Boolean);
        const browser = safeDecode(pathParts[1] || item.browser || 'Unknown');
        const appName = safeDecode(pathParts[2] || item.extName || item.name || 'Unknown');
        const version = safeDecode(pathParts[3] || item.version || '0.0.0');
        const extensionId = safeDecode(pathParts[4] ? pathParts[4].replace('.zip', '') : (item.extension_id || item.extID || 'Unknown'));

        return { browser, appName, version, extensionId };
    }

    function safeDecode(value) {
        try {
            return decodeURIComponent(String(value || ''));
        } catch (_) {
            return String(value || '');
        }
    }

    function filterItemsByExtName(items, query) {
        const normalizedQuery = normalizeText(query);
        if (!normalizedQuery) return items;

        return items.filter(item => {
            const parsed = parseSafeItem(item);
            return normalizeText(parsed.appName).includes(normalizedQuery);
        });
    }

    function normalizeText(value) {
        return String(value || '').trim().toLowerCase();
    }

    function bindActionMenus() {
        document.querySelectorAll('.library-action-trigger').forEach(button => {
            button.addEventListener('click', event => {
                event.stopPropagation();
                const menu = button.nextElementSibling;
                const willOpen = menu.classList.contains('hidden');
                closeActionMenus();
                if (willOpen) {
                    menu.classList.remove('hidden');
                    button.setAttribute('aria-expanded', 'true');
                }
            });
        });

        document.querySelectorAll('.crx-download-btn').forEach(button => {
            button.addEventListener('click', () => downloadCrxFile(button));
        });

        document.querySelectorAll('.install-batch-btn').forEach(button => {
            button.addEventListener('click', () => downloadPolicyBatch(button, '/api/install-helper/batch'));
        });

        document.querySelectorAll('.uninstall-batch-btn').forEach(button => {
            button.addEventListener('click', () => downloadPolicyBatch(button, '/api/install-helper/uninstall-batch'));
        });
    }

    function closeActionMenus() {
        document.querySelectorAll('.library-action-menu').forEach(menu => {
            menu.classList.add('hidden');
        });
        document.querySelectorAll('.library-action-trigger').forEach(button => {
            button.setAttribute('aria-expanded', 'false');
        });
    }

    async function downloadCrxFile(button) {
        const nexusPath = button.dataset.nexusPath;
        closeActionMenus();
        if (!nexusPath) {
            alert('CRX 파일 경로를 찾을 수 없습니다.');
            return;
        }

        try {
            const response = await fetch(`/api/nexus/download?path=${encodeURIComponent(nexusPath)}`);
            if (!response.ok) {
                alert(await readErrorMessage(response, 'CRX 파일 다운로드에 실패했습니다.'));
                return;
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const downloadLink = document.createElement('a');
            downloadLink.href = url;
            downloadLink.download = nexusPath.split('/').pop() || 'extension.zip';
            document.body.appendChild(downloadLink);
            downloadLink.click();
            downloadLink.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Failed to download CRX file:', error);
            alert('CRX 파일 다운로드 중 오류가 발생했습니다.');
        }
    }

    async function downloadPolicyBatch(button, endpoint) {
        const extensionId = button.dataset.extensionId;
        const extensionName = button.dataset.extensionName || extensionId;
        closeActionMenus();
        if (!extensionId || extensionId === 'Unknown') {
            alert('Extension ID was not found.');
            return;
        }

        button.disabled = true;
        button.classList.add('opacity-60', 'cursor-not-allowed');

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    extension_id: extensionId,
                    extension_name: extensionName,
                }),
            });

            if (!response.ok) {
                alert(await readErrorMessage(response, 'Failed to create the install helper file.'));
                return;
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const helperLink = document.createElement('a');
            helperLink.href = url;
            helperLink.download = `${endpoint.includes('uninstall') ? 'uninstall' : 'install'}_${extensionId}.bat`;
            document.body.appendChild(helperLink);
            helperLink.click();
            helperLink.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Failed to download batch file:', error);
            alert('An error occurred while downloading the batch file.');
        } finally {
            button.disabled = false;
            button.classList.remove('opacity-60', 'cursor-not-allowed');
        }
    }

    async function readErrorMessage(response, fallback) {
        try {
            const data = await response.json();
            return data.detail || data.message || fallback;
        } catch (_) {
            return fallback;
        }
    }

    document.addEventListener('click', closeActionMenus);

    function renderPagination() {
        if (!paginationContainer) return;
        paginationContainer.innerHTML = '';
        const totalPages = Math.ceil(filteredSafeItems.length / itemsPerPage);
        if (totalPages <= 1) return;

        for (let i = 1; i <= totalPages; i++) {
            const btn = document.createElement('button');
            btn.innerText = i;
            btn.className = `px-3 py-1 rounded-md text-sm font-medium transition-all ${
                i === currentPage
                    ? 'bg-indigo-600 text-white shadow-md'
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`;
            btn.onclick = () => {
                currentPage = i;
                renderList(i);
                window.scrollTo({ top: 0, behavior: 'smooth' });
            };
            paginationContainer.appendChild(btn);
        }
    }

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, char => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[char]));
    }
});

document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(location.search);
    const extID = urlParams.get('extID');
    const extName = urlParams.get('extName');
    const browser = urlParams.get('browser');
    const searchValue = extID || extName;
    const pageSize = 8;
    let currentPage = 1;
    let currentSort = 'recommended';
    let results = [];

    ensureSortControls();
    updateTitle(searchValue, 0);

    if (!searchValue || !browser) {
        console.error('Missing search parameters.');
        renderResults([], browser, currentPage, pageSize);
        renderPagination(0, currentPage, pageSize);
        return;
    }

    try {
        const requestBody = { browser, limit: 50 };
        let endpoint = '';

        if (extID) {
            endpoint = '/api/search_id';
            requestBody.extension_id = extID;
        } else {
            endpoint = '/api/search_name';
            requestBody.extension_name = extName;
        }

        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
            throw new Error('Failed to fetch search results.');
        }

        const data = await response.json();
        if (data.success === false) {
            results = [];
        } else if (Array.isArray(data.data)) {
            results = data.data;
        } else if (data.data) {
            results = [data.data];
        } else if (Array.isArray(data)) {
            results = data;
        } else {
            results = [data];
        }

        results = results
            .map(item => (item && item.data ? item.data : item))
            .filter(item => item && item.name);

        updateTitle(searchValue, results.length);
        renderCurrentPage();
    } catch (error) {
        console.error('Fetch error:', error);
        results = [];
        renderCurrentPage();
        alert('검색 결과를 불러오지 못했습니다.');
    }

    function renderCurrentPage() {
        const sorted = sortResults(results, currentSort);
        renderResults(sorted, browser, currentPage, pageSize);
        renderPagination(sorted.length, currentPage, pageSize, page => {
            currentPage = page;
            renderCurrentPage();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    function ensureSortControls() {
        const existing = document.getElementById('search-sort-controls');
        if (existing) return existing;

        const resultsContainer = document.getElementById('results-container');
        if (!resultsContainer || !resultsContainer.parentElement) return null;

        const controls = document.createElement('section');
        controls.id = 'search-sort-controls';
        controls.className = 'flex flex-wrap items-center justify-between gap-3 rounded-lg bg-surface-container-lowest border border-outline-variant/60 px-4 py-3';
        controls.innerHTML = `
            <div class="flex items-center gap-2 text-sm font-semibold text-on-surface">
                <span class="material-symbols-outlined text-base">sort</span>
                <span>정렬</span>
            </div>
            <div class="flex flex-wrap items-center gap-2" role="group" aria-label="Sort search results">
                ${sortButtonHtml('recommended', '추천순', true)}
                ${sortButtonHtml('users', '사용자순')}
                ${sortButtonHtml('rating', '별점순')}
                ${sortButtonHtml('updated', '최신순')}
            </div>
        `;
        resultsContainer.parentElement.insertBefore(controls, resultsContainer);

        controls.querySelectorAll('[data-sort]').forEach(button => {
            button.addEventListener('click', () => {
                currentSort = button.dataset.sort;
                currentPage = 1;
                updateSortButtons(controls, currentSort);
                renderCurrentPage();
            });
        });

        return controls;
    }
});

function sortButtonHtml(sortKey, label, active = false) {
    const activeClass = 'bg-primary text-on-primary border-primary shadow-sm';
    const idleClass = 'bg-surface-container-lowest text-on-surface-variant border-outline-variant hover:bg-surface-container';
    return `
        <button
            type="button"
            class="h-9 rounded-lg border px-3 text-sm font-semibold transition-colors ${active ? activeClass : idleClass}"
            data-sort="${sortKey}">
            ${label}
        </button>
    `;
}

function updateSortButtons(container, activeSort) {
    container.querySelectorAll('[data-sort]').forEach(button => {
        const active = button.dataset.sort === activeSort;
        button.className = active
            ? 'h-9 rounded-lg border px-3 text-sm font-semibold transition-colors bg-primary text-on-primary border-primary shadow-sm'
            : 'h-9 rounded-lg border px-3 text-sm font-semibold transition-colors bg-surface-container-lowest text-on-surface-variant border-outline-variant hover:bg-surface-container';
    });
}

function sortResults(items, sortKey) {
    const sorted = [...items];
    const byNumber = key => item => Number(item[key] ?? 0);

    if (sortKey === 'users') {
        return sorted.sort((a, b) => byNumber('users_count')(b) - byNumber('users_count')(a));
    }

    if (sortKey === 'rating') {
        return sorted.sort((a, b) => {
            const ratingDiff = byNumber('rating_value')(b) - byNumber('rating_value')(a);
            if (ratingDiff !== 0) return ratingDiff;
            return byNumber('users_count')(b) - byNumber('users_count')(a);
        });
    }

    if (sortKey === 'updated') {
        return sorted.sort((a, b) => {
            const aDays = Number.isFinite(Number(a.updated_days)) ? Number(a.updated_days) : Number.MAX_SAFE_INTEGER;
            const bDays = Number.isFinite(Number(b.updated_days)) ? Number(b.updated_days) : Number.MAX_SAFE_INTEGER;
            return aDays - bDays;
        });
    }

    return sorted.sort((a, b) => byNumber('recommendation_score')(b) - byNumber('recommendation_score')(a));
}

function updateTitle(searchValue, count) {
    const resultTitle = document.querySelector('h1.text-3xl');
    if (!searchValue || !resultTitle) return;

    resultTitle.innerHTML = `'${escapeHtml(searchValue)}' 검색 결과 <span class="text-primary" id="result-count">${count}건</span>`;
}

function renderResults(results, browser, currentPage, pageSize) {
    const gridSection = document.getElementById('results-container') || document.querySelector('section.grid');
    if (!gridSection) return;

    gridSection.innerHTML = '';

    if (!results || results.length === 0) {
        gridSection.innerHTML = '<p class="col-span-full text-center py-10 text-slate-500">검색 결과가 없습니다.</p>';
        return;
    }

    const startIndex = (currentPage - 1) * pageSize;
    const pageItems = results.slice(startIndex, startIndex + pageSize);

    pageItems.forEach(item => {
        const ext = item && item.data ? item.data : item;
        const themeColor = getThemeColor(ext.category || 'Utility');
        const detailUrl = `/detail?extID=${encodeURIComponent(ext.id)}&browser=${encodeURIComponent(browser || '')}&extName=${encodeURIComponent(ext.name || '')}`;
        const users = formatUsers(ext.users_count, ext.users);
        const score = Number(ext.recommendation_score || 0).toFixed(0);

        const cardHtml = `
            <div class="relative z-10 group bg-surface-container-lowest rounded-xl p-5 hover:shadow-xl hover:shadow-primary/5 transition-all duration-300 flex flex-col h-full border border-transparent hover:border-primary/10">
                <div class="flex justify-between items-start mb-4">
                    <div class="w-14 h-14 ${themeColor.bg} rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform">
                        <img src="${escapeHtml(ext.logo_url || '')}" onerror="this.src='https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/extension/default/48px.svg'" class="w-10 h-10 object-contain" alt="">
                    </div>
                    <div class="flex flex-col items-end gap-1">
                        <span class="px-2 py-1 rounded-lg bg-surface-container-low text-[10px] font-bold text-on-surface-variant uppercase">${escapeHtml(browser || 'Browser')}</span>
                        <span class="px-2 py-1 rounded-lg bg-primary-container text-[10px] font-bold text-primary">추천 ${escapeHtml(score)}</span>
                    </div>
                </div>
                <div class="flex-1">
                    <h3 class="text-lg font-bold text-on-surface mb-1 group-hover:text-primary transition-colors">${escapeHtml(ext.name)}</h3>
                    <p class="text-sm text-on-surface-variant line-clamp-2 mb-4 leading-relaxed">${escapeHtml(ext.summary || ext.description || '설명이 없습니다.')}</p>
                    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3">
                        <span class="inline-flex items-center gap-1 text-sm font-bold text-on-surface">
                            <span class="material-symbols-outlined text-yellow-400 text-sm" style="font-variation-settings: 'FILL' 1;">star</span>
                            ${escapeHtml(ext.rating || '0.0')}
                        </span>
                        <span class="text-xs text-on-surface-variant">${escapeHtml(users)} users</span>
                    </div>
                    <p class="text-xs text-on-surface-variant mb-6">업데이트 ${escapeHtml(ext.updated || 'N/A')}</p>
                </div>
                <a class="relative z-20 block w-full py-2.5 rounded-lg bg-primary text-on-primary font-bold text-sm hover:brightness-110 transition-all text-center"
                   href="${detailUrl}">
                    View Detail
                </a>
            </div>
        `;
        gridSection.insertAdjacentHTML('beforeend', cardHtml);
    });
}

function renderPagination(totalItems, currentPage, pageSize, onPageChange) {
    const container = document.getElementById('search-pagination-controls');
    if (!container) return;

    container.innerHTML = '';
    const totalPages = Math.ceil(totalItems / pageSize);
    if (totalPages <= 1) return;

    const prev = createPageButton('Prev', currentPage > 1, () => onPageChange(currentPage - 1));
    container.appendChild(prev);

    for (let page = 1; page <= totalPages; page++) {
        const button = createPageButton(String(page), true, () => onPageChange(page));
        button.className = page === currentPage
            ? 'px-3 py-1 rounded-md text-sm font-medium bg-indigo-600 text-white shadow-md'
            : 'px-3 py-1 rounded-md text-sm font-medium bg-gray-200 text-gray-700 hover:bg-gray-300';
        container.appendChild(button);
    }

    const next = createPageButton('Next', currentPage < totalPages, () => onPageChange(currentPage + 1));
    container.appendChild(next);
}

function createPageButton(label, enabled, onClick) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.disabled = !enabled;
    button.className = enabled
        ? 'px-3 py-1 rounded-md text-sm font-medium bg-gray-200 text-gray-700 hover:bg-gray-300'
        : 'px-3 py-1 rounded-md text-sm font-medium bg-gray-100 text-gray-400 cursor-not-allowed';
    if (enabled) button.addEventListener('click', onClick);
    return button;
}

function getThemeColor(category) {
    const maps = {
        Productivity: { bg: 'bg-indigo-50', text: 'text-primary' },
        Utility: { bg: 'bg-sky-50', text: 'text-sky-600' },
        'Dev Tools': { bg: 'bg-purple-50', text: 'text-purple-600' },
        Security: { bg: 'bg-emerald-50', text: 'text-emerald-600' },
        Analytics: { bg: 'bg-orange-50', text: 'text-orange-600' },
    };
    return maps[category] || { bg: 'bg-slate-50', text: 'text-slate-600' };
}

function formatUsers(usersCount, fallback) {
    const count = Number(usersCount || 0);
    if (!count) return fallback || '0';
    return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(count);
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[char]));
}

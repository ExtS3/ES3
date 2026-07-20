// ES3 공통 셸(헤더/사이드바) 주입 + 세션·네비게이션.
// 마이그레이션된 템플릿은 <header id="es3-header"></header> / <aside id="es3-sidebar"></aside>
// 플레이스홀더만 두고, 이 파일이 마크업을 채운다(네비 단일 소스).
// 구형 템플릿(자체 aside 마크업 + #side-bottom)도 그대로 동작한다.

(function injectShell() {
    const NAV_ITEMS = [
        { href: '/', icon: 'home', label: '홈' },
        { href: '/search', icon: 'explore', label: '앱 탐색' },
        { href: '/library', icon: 'inventory_2', label: '라이브러리' },
        { href: '/admin/scan-status', icon: 'manage_search', label: '검사 내역' },
        { href: '/scenario', icon: 'dataset', label: '시나리오 관리' },
        {
            href: '/admin', icon: 'dashboard_customize', label: '관리자 대시보드',
            children: [
                { href: '/admin/permissions', icon: 'manage_accounts', label: '사용자 권한' },
                { href: '/admin/policy', icon: 'rule_settings', label: '정책 설정' },
            ],
        },
    ];

    function activeHref() {
        const p = window.location.pathname;
        if (p.startsWith('/admin/scan-status')) return '/admin/scan-status';
        if (p.startsWith('/admin')) return '/admin';
        if (p.startsWith('/scenario')) return '/scenario';
        if (p.startsWith('/library')) return '/library';
        if (p.startsWith('/search') || p.startsWith('/list') || p.startsWith('/detail') || p.startsWith('/no_result')) return '/search';
        return '/';
    }

    const aside = document.getElementById('es3-sidebar');
    if (aside) {
        const active = activeHref();
        aside.className = 'fixed left-0 top-0 h-screen w-60 z-30 hidden md:flex flex-col bg-surface-container-lowest border-r border-outline-variant';
        aside.innerHTML = `
<div class="pt-6 pb-6 flex justify-center">
    <a href="/"><img src="/static/img/logo.png" alt="ES3" class="h-12"></a>
</div>
<nav class="flex flex-col gap-1 px-3">
    ${NAV_ITEMS.map(item => {
        const isActive = item.href === active;
        // 하위 메뉴: 해당 섹션에 있으면 항상 펼침, 아니면 그룹 호버 시에만 노출.
        const children = item.children || [];
        return `
    <div class="group flex flex-col gap-1">
    <a href="${item.href}" class="relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${isActive
            ? 'bg-primary-container text-on-primary-container'
            : 'text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface'}">
        ${isActive ? '<span class="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-full es3-gradient-bg"></span>' : ''}
        <span class="material-symbols-outlined" data-icon="${item.icon}">${item.icon}</span>
        <span>${item.label}</span>
    </a>` + (children.length ? `
    <div class="${isActive ? 'flex' : 'hidden group-hover:flex group-focus-within:flex'} flex-col gap-1">` : '') + children.map(child => {
        const childActive = window.location.pathname === child.href;
        return `
    <a href="${child.href}" class="relative flex items-center gap-2 ml-6 px-3 py-2 rounded-lg text-sm transition-colors ${childActive
            ? 'bg-primary-container text-on-primary-container font-medium'
            : 'text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface'}">
        ${childActive ? '<span class="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-[3px] rounded-full es3-gradient-bg"></span>' : ''}
        <span class="material-symbols-outlined text-base" data-icon="${child.icon}">${child.icon}</span>
        <span>${child.label}</span>
    </a>`;
    }).join('') + (children.length ? '</div>' : '') + '</div>';
    }).join('')}
</nav>
<div id="side-bottom" class="mt-auto"></div>
`;
    }

    const header = document.getElementById('es3-header');
    if (header) {
        header.className = 'fixed top-0 right-0 left-0 md:left-60 h-14 z-40 bg-surface-container-lowest/80 backdrop-blur-md border-b border-outline-variant';
        header.innerHTML = `
<div class="flex justify-end items-center h-full px-6">
    <div class="flex items-center gap-4">
        <div class="relative hidden sm:block">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm">search</span>
            <input class="pl-10 pr-4 py-2 bg-surface-container-low border-none rounded-lg text-sm w-64 focus:ring-2 focus:ring-primary/30" placeholder="라이브러리에서 검색..." type="text"/>
        </div>
    </div>
</div>
`;
    }
})();

const sideBottom = document.getElementById('side-bottom');
if (sideBottom) {
    sideBottom.innerHTML = `
<div class="px-4 pb-2" id="slackConnectWrap" style="display:none">
    <button id="slackConnect" class="es3-btn w-full" style="background:#4A154B">
        <svg width="15" height="15" viewBox="0 0 122.8 122.8" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M25.8 77.6c0 7.1-5.8 12.9-12.9 12.9S0 84.7 0 77.6s5.8-12.9 12.9-12.9h12.9v12.9zm6.5 0c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9v32.3c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V77.6z" fill="#E01E5A"/>
            <path d="M45.2 25.8c-7.1 0-12.9-5.8-12.9-12.9S38.1 0 45.2 0s12.9 5.8 12.9 12.9v12.9H45.2zm0 6.5c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H12.9C5.8 58.1 0 52.3 0 45.2s5.8-12.9 12.9-12.9h32.3z" fill="#36C5F0"/>
            <path d="M97 45.2c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9-5.8 12.9-12.9 12.9H97V45.2zm-6.5 0c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V12.9C64.7 5.8 70.5 0 77.6 0s12.9 5.8 12.9 12.9v32.3z" fill="#2EB67D"/>
            <path d="M77.6 97c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9-12.9-5.8-12.9-12.9V97h12.9zm0-6.5c-7.1 0-12.9-5.8-12.9-12.9s5.8-12.9 12.9-12.9h32.3c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H77.6z" fill="#ECB22E"/>
        </svg>
        Slack 연동
    </button>
</div>
<div class="px-4 pb-3">
    <a id="moveBuild" href="/build" class="es3-btn w-full">
        <span class="material-symbols-outlined text-sm" data-icon="upload">upload</span>
        Upload
    </a>
</div>
<div class="px-4 pb-4 flex flex-col gap-1 border-t border-outline-variant pt-3">
    <a id="user" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-primary hover:bg-primary-container" href="/login">
        <span class="material-symbols-outlined" data-icon="login">login</span>
        <span>Login</span>
    </a>
</div>
`;
}

window.exts3SessionPromise = window.exts3SessionPromise || (async () => {
    const token = localStorage.getItem('exts3_auth_token');
    const cached = sessionStorage.getItem('exts3_session_cache');
    if (cached) {
        try {
            const parsed = JSON.parse(cached);
            const cachedSession = parsed.session || {};
            if (parsed.expiresAt > Date.now() && (!token || cachedSession.authenticated)) {
                return parsed.session;
            }
        } catch (_) {
            sessionStorage.removeItem('exts3_session_cache');
        }
    }

    const response = await fetch('/api/auth/session', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: 'same-origin',
    });
    if (!response.ok) {
        return {authenticated: false, role_label: 'Guest', roles: ['guest'], permissions: []};
    }
    const session = await response.json();
    sessionStorage.setItem('exts3_session_cache', JSON.stringify({
        session,
        expiresAt: Date.now() + 15000,
    }));
    return session;
})();

(async () => {
    let session = {authenticated: false, role_label: 'Guest', roles: ['guest']};
    try {
        session = await window.exts3SessionPromise;
    } catch (error) {
        session = {authenticated: false, role_label: 'Guest', roles: ['guest']};
    }

    const roleLabel = session.role_label || 'Guest';
    const roles = Array.isArray(session.roles) ? session.roles : ['guest'];
    const permissions = Array.isArray(session.permissions) ? session.permissions : [];
    const isAdmin = roles.includes('admin');
    const canUpload = permissions.includes('upload');
    const headerActions = document.querySelector('header .flex.items-center.gap-4');

    if (headerActions && !document.getElementById('sessionRoleBadge')) {
        const badge = document.createElement('div');
        badge.id = 'sessionRoleBadge';
        badge.className = 'hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary-container text-on-primary-container text-xs font-bold';
        badge.innerHTML = `
            <span class="material-symbols-outlined text-sm">${isAdmin ? 'admin_panel_settings' : session.authenticated ? 'person' : 'public'}</span>
            <span>${roleLabel}</span>
        `;
        headerActions.prepend(badge);
    }

    document.querySelectorAll('a[href="/admin"]').forEach(link => {
        if (!isAdmin) {
            link.style.display = 'none';
        }
    });

    document.querySelectorAll('a[href="/scenario"]').forEach(link => {
        if (!isAdmin) {
            link.style.display = 'none';
        }
    });

    const protectedLinks = ['/search', '/library', '/build', '/user_set', '/admin/scan-status'];
    document.querySelectorAll('a').forEach(link => {
        const href = link.getAttribute('href') || '#';
        const path = new URL(href, window.location.origin).pathname;
        if (!session.authenticated && protectedLinks.includes(path)) {
            link.style.display = 'none';
        }
    });

    document.querySelectorAll('a[href="/user_set"]').forEach(link => {
        link.href = '#';
        link.title = roleLabel;
        link.addEventListener('click', event => event.preventDefault());
    });

    const uploadButton = document.getElementById('moveBuild');
    if (uploadButton && (!session.authenticated || !canUpload)) {
        uploadButton.style.display = 'none';
    }

    const slackConnectWrap = document.getElementById('slackConnectWrap');
    if (slackConnectWrap && isAdmin) {
        slackConnectWrap.style.display = '';
        document.getElementById('slackConnect').addEventListener('click', openSlackModal);
    }

    const userLink = document.getElementById('user');
    if (userLink) {
        if (session.authenticated) {
            userLink.href = '#';
            // Logout은 중립 회색, 호버 시에만 위험 색 힌트
            userLink.className = 'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-on-surface-variant hover:bg-error-container hover:text-error-dim';
            userLink.innerHTML = `
                <span class="material-symbols-outlined" data-icon="logout">logout</span>
                <span>Logout</span>
            `;
            userLink.addEventListener('click', async event => {
                event.preventDefault();
                await fetch('/api/auth/logout', {method: 'POST'});
                localStorage.removeItem('exts3_auth_token');
                sessionStorage.removeItem('exts3_session_cache');
                window.location.href = '/';
            });
        } else {
            userLink.href = '/login';
            userLink.innerHTML = `
                <span class="material-symbols-outlined" data-icon="login">login</span>
                <span>Login</span>
            `;
        }
    }
})();

document.querySelectorAll('header input').forEach(input => {
    const params = new URLSearchParams(window.location.search);
    const currentExtName = params.get('extName');
    if (currentExtName && !input.value) {
        input.value = currentExtName;
    }

    input.setAttribute('type', 'search');
    input.setAttribute('name', 'extName');
    input.setAttribute('aria-label', 'Extension search');

    const runLibrarySearch = () => {
        const extName = input.value.trim();
        if (!extName) {
            window.location.href = '/library';
            return;
        }

        const nextParams = new URLSearchParams();
        nextParams.set('extName', extName);
        window.location.href = `/library?${nextParams.toString()}`;
    };

    input.addEventListener('keydown', event => {
        if (event.key !== 'Enter') return;

        event.preventDefault();
        runLibrarySearch();
    });

    const searchIcon = input.parentElement?.querySelector('.material-symbols-outlined');
    if (searchIcon) {
        searchIcon.classList.add('cursor-pointer');
        searchIcon.addEventListener('click', runLibrarySearch);
    }
});

// Slack 연동 모달 — 사이드바 "Slack 연동" 버튼(관리자 전용)에서 호출
async function openSlackModal() {
    let overlay = document.getElementById('slackModalOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'slackModalOverlay';
        overlay.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm';
        overlay.innerHTML = `
<div class="bg-surface-container-lowest rounded-xl shadow-xl w-full max-w-2xl mx-4 overflow-hidden" role="dialog" aria-modal="true" aria-labelledby="slackModalTitle">
    <div style="height:4px;background:linear-gradient(90deg,#36C5F0,#2EB67D,#ECB22E,#E01E5A)"></div>
    <div class="p-8">
    <div class="flex items-center gap-4 mb-6">
        <div class="w-12 h-12 rounded-lg flex items-center justify-center border border-outline-variant bg-white">
            <svg width="26" height="26" viewBox="0 0 122.8 122.8" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <path d="M25.8 77.6c0 7.1-5.8 12.9-12.9 12.9S0 84.7 0 77.6s5.8-12.9 12.9-12.9h12.9v12.9zm6.5 0c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9v32.3c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V77.6z" fill="#E01E5A"/>
                <path d="M45.2 25.8c-7.1 0-12.9-5.8-12.9-12.9S38.1 0 45.2 0s12.9 5.8 12.9 12.9v12.9H45.2zm0 6.5c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H12.9C5.8 58.1 0 52.3 0 45.2s5.8-12.9 12.9-12.9h32.3z" fill="#36C5F0"/>
                <path d="M97 45.2c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9-5.8 12.9-12.9 12.9H97V45.2zm-6.5 0c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V12.9C64.7 5.8 70.5 0 77.6 0s12.9 5.8 12.9 12.9v32.3z" fill="#2EB67D"/>
                <path d="M77.6 97c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9-12.9-5.8-12.9-12.9V97h12.9zm0-6.5c-7.1 0-12.9-5.8-12.9-12.9s5.8-12.9 12.9-12.9h32.3c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H77.6z" fill="#ECB22E"/>
            </svg>
        </div>
        <div>
            <h2 id="slackModalTitle" class="text-xl font-bold text-on-surface">Slack 연동</h2>
            <p id="slackModalStatus" class="text-sm text-on-surface-variant">상태 확인 중...</p>
        </div>
    </div>

    <div class="mb-5">
        <label class="block text-sm font-semibold text-on-surface mb-2">연동된 웹훅 URL</label>
        <div id="slackCurrentUrl" class="w-full bg-surface-container-low rounded-lg px-4 py-3 text-sm text-on-surface-variant font-mono break-all min-h-[44px]">
            -
        </div>
    </div>

    <div class="mb-2">
        <label for="slackWebhookInput" class="block text-sm font-semibold text-on-surface mb-2">새 웹훅 URL 입력</label>
        <p class="text-sm text-on-surface-variant mb-2">
            Slack 워크스페이스에서 Incoming Webhook을 생성한 뒤, 발급된 URL을 입력하세요.
            분석 알림이 해당 채널로 전송됩니다.
        </p>
        <input id="slackWebhookInput" type="url" placeholder="https://hooks.slack.com/services/..."
            class="w-full bg-surface-container-low rounded-lg px-4 py-3 text-sm text-on-surface border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary" />
    </div>
    <p id="slackModalError" class="text-xs text-error mb-2" style="display:none"></p>
    <p id="slackModalSuccess" class="text-xs mb-2" style="display:none;color:#2EB67D"></p>

    <div class="flex justify-end gap-2 mt-6">
        <button id="slackModalCancel" class="es3-btn es3-btn-ghost">닫기</button>
        <button id="slackModalSave" class="es3-btn" style="background:#4A154B">저장</button>
    </div>
    </div>
</div>
`;
        document.body.appendChild(overlay);

        const close = () => { overlay.style.display = 'none'; };
        overlay.addEventListener('click', event => {
            if (event.target === overlay) close();
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && overlay.style.display !== 'none') close();
        });
        overlay.querySelector('#slackModalCancel').addEventListener('click', close);

        overlay.querySelector('#slackModalSave').addEventListener('click', async () => {
            const input = overlay.querySelector('#slackWebhookInput');
            const errorEl = overlay.querySelector('#slackModalError');
            const successEl = overlay.querySelector('#slackModalSuccess');
            const saveBtn = overlay.querySelector('#slackModalSave');
            const url = input.value.trim();
            errorEl.style.display = 'none';
            successEl.style.display = 'none';

            if (!url.startsWith('https://hooks.slack.com/')) {
                errorEl.textContent = 'URL은 https://hooks.slack.com/ 으로 시작해야 합니다.';
                errorEl.style.display = '';
                return;
            }

            saveBtn.disabled = true;
            saveBtn.textContent = '저장 중...';
            try {
                const res = await fetch('/api/admin/settings/slack-webhook', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url}),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || '저장에 실패했습니다.');
                overlay.querySelector('#slackModalStatus').textContent = 'Slack 채널과 연동되어 있습니다.';
                overlay.querySelector('#slackCurrentUrl').textContent = data.url;
                input.value = '';
                successEl.textContent = '저장되었습니다. 이후 분석 알림이 이 웹훅으로 전송됩니다.';
                successEl.style.display = '';
            } catch (error) {
                errorEl.textContent = error.message;
                errorEl.style.display = '';
            } finally {
                saveBtn.disabled = false;
                saveBtn.textContent = '저장';
            }
        });
    }

    overlay.style.display = '';
    overlay.querySelector('#slackModalError').style.display = 'none';
    overlay.querySelector('#slackModalSuccess').style.display = 'none';

    const statusEl = overlay.querySelector('#slackModalStatus');
    const currentUrlEl = overlay.querySelector('#slackCurrentUrl');
    statusEl.textContent = '상태 확인 중...';
    try {
        const res = await fetch('/api/admin/settings/slack-webhook');
        const data = res.ok ? await res.json() : {configured: false};
        statusEl.textContent = data.configured
            ? 'Slack 채널과 연동되어 있습니다. 새 URL을 저장하면 교체됩니다.'
            : '아직 연동된 웹훅이 없습니다.';
        currentUrlEl.textContent = data.configured ? data.url : '아직 연동된 웹훅이 없습니다.';
    } catch (_) {
        statusEl.textContent = '상태를 확인할 수 없습니다.';
        currentUrlEl.textContent = '-';
    }

    overlay.querySelector('#slackWebhookInput').focus();
}

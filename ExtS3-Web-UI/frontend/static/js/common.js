// ES3 공통 셸(헤더/사이드바) 주입 + 세션·네비게이션.
// 마이그레이션된 템플릿은 <header id="es3-header"></header> / <aside id="es3-sidebar"></aside>
// 플레이스홀더만 두고, 이 파일이 마크업을 채운다(네비 단일 소스).
// 구형 템플릿(자체 aside 마크업 + #side-bottom)도 그대로 동작한다.

(function injectShell() {
    const NAV_ITEMS = [
        { href: '/', icon: 'home', label: '홈' },
        { href: '/search', icon: 'explore', label: '앱 탐색' },
        { href: '/library', icon: 'inventory_2', label: '라이브러리' },
        { href: '/scenario', icon: 'dataset', label: '시나리오 관리' },
        { href: '/admin', icon: 'dashboard_customize', label: '관리자 대시보드' },
    ];

    function activeHref() {
        const p = window.location.pathname;
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
        return `
    <a href="${item.href}" class="relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${isActive
            ? 'bg-primary-container text-on-primary-container'
            : 'text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface'}">
        ${isActive ? '<span class="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-full es3-gradient-bg"></span>' : ''}
        <span class="material-symbols-outlined" data-icon="${item.icon}">${item.icon}</span>
        <span>${item.label}</span>
    </a>`;
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
<div class="px-4 pb-3">
    <button id="moveBuild" class="es3-btn w-full">
        <span class="material-symbols-outlined text-sm" data-icon="upload">upload</span>
        Upload
    </button>
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

    const protectedLinks = ['/search', '/library', '/build', '/user_set'];
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

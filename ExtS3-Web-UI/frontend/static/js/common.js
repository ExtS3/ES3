const sideBottom = document.getElementById('side-bottom');
if (sideBottom) {
    sideBottom.innerHTML = `
<div class="mt-auto px-4 flex flex-col gap-4">
    <button id="moveBuild" class="w-full bg-indigo-600 text-white px-4 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 hover:bg-indigo-700 transition-all active:scale-95 shadow-lg shadow-indigo-200 dark:shadow-none">
        <span class="material-symbols-outlined text-sm" data-icon="upload">upload</span>
        Upload
    </button>
    <div class="flex flex-col gap-1 border-t border-slate-200 dark:border-slate-800 pt-4 pb-2">
        <a class="flex items-center gap-3 p-3 text-slate-600 dark:text-slate-400 hover:bg-slate-100 rounded-lg text-sm font-medium transition-all" href="#">
            <span class="material-symbols-outlined">help</span>
            Help
        </a>
        <a id="user" class="flex items-center gap-3 px-4 py-3 text-error dark:text-error-container hover:bg-error-container/10 rounded-lg mx-2 text-sm font-medium Inter transition-all hover:scale-[1.02]" href="/login">
            <span class="material-symbols-outlined" data-icon="login">login</span>
            <span>Login</span>
        </a>
    </div>
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
        badge.className = 'hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 text-xs font-bold';
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

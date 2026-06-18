let permissionList = [];
let roleList = [];

const permissionLabels = {
    upload: 'Upload',
    delete_user: 'Delete users',
    manage_extension_policy: 'Manage policy',
    request_extension: 'Request extension',
    bypass_holding: 'Bypass holding',
    install_extension: 'Install extension',
    approve_extension: 'Approve/reject extension',
    approve_signup: 'Approve signup',
};
const defaultSignupPermissions = ['request_extension', 'upload', 'install_extension'];
const visibleRoleNames = ['admin', 'user'];

async function api(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.detail || 'Request failed');
    }
    return data;
}

function permissionName(name) {
    return permissionLabels[name] || name;
}

function roleName(name) {
    return name.replace(/^department_/, '').replace(/_/g, ' ');
}

function checkboxControl({inputClass, value, checked, label, capitalize = false}) {
    return `
        <label class="flex items-center gap-3 bg-surface-container-low rounded-lg px-3 py-2 text-sm font-semibold ${capitalize ? 'capitalize' : ''}">
            <input type="checkbox" class="${inputClass} rounded" value="${value}" ${checked ? 'checked' : ''}>
            <span>${label}</span>
        </label>
    `;
}

function renderSignupRequests(requests) {
    const container = document.getElementById('signupRequests');
    const pending = requests.filter(item => item.status === 'pending');
    if (!pending.length) {
        container.innerHTML = '<p class="p-5 text-sm text-on-surface-variant">No pending signup requests.</p>';
        return;
    }

    container.innerHTML = pending.map(item => `
        <div class="p-5 border-b border-slate-100 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4" data-request-id="${item.id}">
            <div>
                <p class="font-bold">${item.user_id}</p>
                <p class="text-sm text-on-surface-variant">Requested roles: ${(item.requested_roles || []).join(', ') || 'user'}</p>
            </div>
            <div class="flex flex-wrap gap-3">
                ${permissionList.map(permission => `
                    <label class="inline-flex items-center gap-2 text-sm">
                        <input type="checkbox" class="signup-permission rounded" value="${permission.name}" ${defaultSignupPermissions.includes(permission.name) ? 'checked' : ''}>
                        ${permissionName(permission.name)}
                    </label>
                `).join('')}
            </div>
            <div class="flex gap-2">
                <button class="approve-signup px-3 py-2 rounded-lg bg-primary text-white text-sm font-bold">Approve</button>
                <button class="reject-signup px-3 py-2 rounded-lg bg-slate-200 text-slate-700 text-sm font-bold">Reject</button>
            </div>
        </div>
    `).join('');

    container.querySelectorAll('.approve-signup').forEach(button => {
        button.addEventListener('click', async event => {
            const row = event.target.closest('[data-request-id]');
            const permissions = [...row.querySelectorAll('.signup-permission:checked')].map(input => input.value);
            await api(`/api/admin/permissions/signup-requests/${row.dataset.requestId}/approve`, {
                method: 'POST',
                body: JSON.stringify({permissions}),
            });
            await loadAccess();
        });
    });

    container.querySelectorAll('.reject-signup').forEach(button => {
        button.addEventListener('click', async event => {
            const row = event.target.closest('[data-request-id]');
            await api(`/api/admin/permissions/signup-requests/${row.dataset.requestId}/reject`, {
                method: 'POST',
                body: JSON.stringify({}),
            });
            await loadAccess();
        });
    });
}

function renderUsers(users) {
    const container = document.getElementById('usersAccess');
    if (!users.length) {
        container.innerHTML = '<p class="text-sm text-on-surface-variant">No users.</p>';
        return;
    }

    container.innerHTML = users.map(user => `
        <article class="bg-white border border-slate-200 rounded-lg p-5" data-user-id="${user.id}">
            <div class="flex flex-col gap-5">
                <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                  <div>
                    <h3 class="font-black text-lg">${user.id}</h3>
                    <p class="text-sm text-on-surface-variant">Roles: ${(user.roles || []).join(', ') || 'none'}</p>
                  </div>
                  <button class="save-user-access px-4 py-2 rounded-lg bg-primary text-white text-sm font-bold">Save access</button>
                </div>

                <details class="rounded-lg border border-slate-200 bg-white">
                    <summary class="cursor-pointer list-none px-4 py-3 text-sm font-bold text-on-surface flex items-center justify-between">
                        <span>Roles & permissions</span>
                        <span class="material-symbols-outlined text-base">expand_more</span>
                    </summary>
                    <div class="border-t border-slate-100 p-4 space-y-5">
                        <div>
                            <p class="text-xs font-black uppercase tracking-wide text-on-surface-variant mb-2">Roles</p>
                            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                ${roleList
                                    .filter(role => visibleRoleNames.includes(role.name))
                                    .map(role => checkboxControl({
                                        inputClass: 'user-role',
                                        value: role.name,
                                        checked: (user.roles || []).includes(role.name),
                                        label: roleName(role.name),
                                        capitalize: true,
                                    })).join('')}
                            </div>
                        </div>

                        <div>
                            <p class="text-xs font-black uppercase tracking-wide text-on-surface-variant mb-2">Permissions</p>
                            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                            ${permissionList.map(permission => checkboxControl({
                                inputClass: 'user-permission',
                                value: permission.name,
                                checked: (user.permissions || []).includes(permission.name),
                                label: permissionName(permission.name),
                            })).join('')}
                            </div>
                        </div>
                    </div>
                </details>
            </div>
        </article>
    `).join('');

    container.querySelectorAll('.save-user-access').forEach(button => {
        button.addEventListener('click', async event => {
            const row = event.target.closest('[data-user-id]');
            const roles = [...row.querySelectorAll('.user-role:checked')].map(input => input.value);
            const permissions = [...row.querySelectorAll('.user-permission:checked')].map(input => input.value);
            await api(`/api/admin/permissions/users/${encodeURIComponent(row.dataset.userId)}/roles`, {
                method: 'PUT',
                body: JSON.stringify({roles}),
            });
            await api(`/api/admin/permissions/users/${encodeURIComponent(row.dataset.userId)}/permissions`, {
                method: 'PUT',
                body: JSON.stringify({permissions}),
            });
            await loadAccess();
        });
    });
}

async function loadAccess() {
    const [permissions, roles, users, signupRequests] = await Promise.all([
        api('/api/admin/permissions'),
        api('/api/admin/permissions/roles'),
        api('/api/admin/permissions/users'),
        api('/api/admin/permissions/signup-requests'),
    ]);
    permissionList = permissions.permissions || [];
    roleList = roles.roles || [];
    renderSignupRequests(signupRequests.requests || []);
    renderUsers(users.users || []);
}

document.getElementById('refreshAccess').addEventListener('click', loadAccess);
loadAccess().catch(error => {
    document.getElementById('usersAccess').innerHTML = `<p class="text-sm text-red-600">${error.message}</p>`;
});

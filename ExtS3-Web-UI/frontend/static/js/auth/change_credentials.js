(async () => {
    const message = document.getElementById('changeCredentialsMessage');
    try {
        const response = await fetch('/api/auth/me');
        if (response.ok) {
            const me = await response.json();
            document.getElementById('newUsername').value = me.id || '';
        }
    } catch (error) {
        message.textContent = 'Login is required.';
    }
})();

document.getElementById('changeCredentialsForm').addEventListener('submit', async event => {
    event.preventDefault();
    const message = document.getElementById('changeCredentialsMessage');
    message.textContent = 'Saving...';

    const response = await fetch('/api/auth/change-credentials', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            username: document.getElementById('newUsername').value.trim(),
            password: document.getElementById('newPassword').value,
        }),
    });
    const result = await response.json();
    if (!response.ok) {
        message.textContent = result.detail || 'Failed to change credentials.';
        return;
    }
    if (result.token) {
        localStorage.setItem('exts3_auth_token', result.token);
    }
    window.location.href = result.redirect || '/';
});

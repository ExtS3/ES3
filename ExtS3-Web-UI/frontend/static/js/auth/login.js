const loginForm = document.getElementById('login_form');
const loginButton = document.getElementById('login_btn');

loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const id = document.getElementById('id').value.trim();
    const pw = document.getElementById('pw').value;

    loginButton.disabled = true;
    loginButton.textContent = '로그인 중...';

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, pw }),
            credentials: 'same-origin',
        });

        const result = await response.json();

        if (!response.ok) {
            alert(result.detail || '로그인에 실패했습니다.');
            return;
        }

        if (result.token) {
            localStorage.setItem('exts3_auth_token', result.token);
        }
        sessionStorage.removeItem('exts3_session_cache');

        const sessionResponse = await fetch('/api/auth/session', {
            credentials: 'same-origin',
            headers: result.token ? { Authorization: `Bearer ${result.token}` } : {},
        });
        if (sessionResponse.ok) {
            const session = await sessionResponse.json();
            if (session.authenticated) {
                sessionStorage.setItem('exts3_session_cache', JSON.stringify({
                    session,
                    expiresAt: Date.now() + 15000,
                }));
            }
        }

        window.location.replace(result.redirect || '/');
    } catch (error) {
        console.error('Login failed:', error);
        alert('서버 연결에 실패했습니다.');
    } finally {
        loginButton.disabled = false;
        loginButton.textContent = '로그인';
    }
});

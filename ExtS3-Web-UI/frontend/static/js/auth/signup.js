document.getElementById('signupForm').addEventListener('submit', async event => {
    event.preventDefault();
    const message = document.getElementById('signupMessage');
    message.textContent = 'Submitting request...';

    const response = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: document.getElementById('signupId').value.trim(),
            password: document.getElementById('signupPassword').value,
        }),
    });
    const result = await response.json();
    if (!response.ok) {
        message.textContent = result.detail || 'Signup request failed.';
        return;
    }
    message.textContent = 'Signup request submitted. Wait for administrator approval.';
    event.target.reset();
});

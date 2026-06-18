let fields = {};

document.addEventListener('DOMContentLoaded', () => {
  fields = {
    criticalAutoRejectEnabled: document.getElementById('critical-auto-reject-enabled'),
    lowAutoApproveEnabled: document.getElementById('low-auto-approve-enabled'),
    saveButton: document.getElementById('save-policy'),
    statusMessage: document.getElementById('status-message')
  };

  loadPolicy();
  fields.saveButton.addEventListener('click', savePolicy);
});

async function loadPolicy() {
  try {
    const response = await fetch('/api/admin/policy');
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.detail || result.message || 'Failed to load policy.');
    }

    fillForm(result.data);
  } catch (error) {
    showStatus(error.message, 'error');
  }
}

async function savePolicy() {
  const payload = readForm();
  fields.saveButton.disabled = true;
  fields.saveButton.textContent = 'Saving';

  try {
    const response = await fetch('/api/admin/policy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.detail || result.message || 'Failed to save policy.');
    }

    fillForm(result.data);
    showStatus('Policy settings saved.', 'success');
  } catch (error) {
    showStatus(error.message, 'error');
  } finally {
    fields.saveButton.disabled = false;
    fields.saveButton.textContent = '저장';
  }
}

function fillForm(policy) {
  fields.criticalAutoRejectEnabled.checked = Boolean(policy.critical_auto_reject_enabled);
  fields.lowAutoApproveEnabled.checked = Boolean(policy.low_auto_approve_enabled);
}

function readForm() {
  return {
    critical_auto_reject_enabled: fields.criticalAutoRejectEnabled.checked,
    low_auto_approve_enabled: fields.lowAutoApproveEnabled.checked,
    fallback_decision: 'review'
  };
}

function showStatus(message, type) {
  fields.statusMessage.textContent = message;
  fields.statusMessage.classList.remove('hidden', 'bg-green-50', 'text-green-700', 'bg-red-50', 'text-red-700');
  if (type === 'success') {
    fields.statusMessage.classList.add('bg-green-50', 'text-green-700');
  } else {
    fields.statusMessage.classList.add('bg-red-50', 'text-red-700');
  }
}

async function readErrorMessage(response, fallback) {
    try {
        const data = await response.json();
        return data.detail || data.message || fallback;
    } catch (_) {
        return fallback;
    }
}

async function loadSession() {
    if (window.exts3SessionPromise) {
        return window.exts3SessionPromise;
    }
    try {
        const response = await fetch('/api/auth/session');
        if (!response.ok) return {authenticated: false, permissions: []};
        return await response.json();
    } catch (_) {
        return {authenticated: false, permissions: []};
    }
}

async function requestExtensionScan({extensionId, browser, extVersion, extName, bypassHolding}) {
    const nexusResponse = await fetch('/api/nexus/exists', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            extID: extensionId,
            browser,
            extVersion,
            extName,
        }),
    });

    if (!nexusResponse.ok) {
        alert(await readErrorMessage(nexusResponse, '라이브러리 목록을 불러오지 못했습니다.'));
        return;
    }

    const nexusStatus = await nexusResponse.json();
    const targetFile = nexusStatus.exists ? nexusStatus.item : null;

    if (targetFile) {
        const targetPath = targetFile.path || '';
        const topLevelPath = nexusStatus.top_level || targetPath.split('/').filter(Boolean)[0];

        if (topLevelPath === 'review') {
            alert('현재 검토 진행 중인 확장 프로그램입니다.');
            return;
        }

        if (topLevelPath === 'safe' || targetFile.status === 'safe') {
            alert('라이브러리에 존재하는 확장 프로그램입니다.');
            window.location.href = `/library?extName=${encodeURIComponent(extName)}`;
            return;
        }

        alert('현재 처리 중인 확장 프로그램입니다.');
        return;
    }

    if (bypassHolding) {
        const confirmed = confirm('홀딩 시간을 건너뛰고 즉시 보안 검사를 시작할까요?');
        if (!confirmed) return;
    }

    const downloadResponse = await fetch('/api/download_zip', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            browser,
            extension_id: extensionId,
            extVersion,
            extName,
            bypass_holding: bypassHolding,
        }),
    });

    if (downloadResponse.ok) {
        const result = await downloadResponse.json().catch(() => ({}));
        alert(result.message || (bypassHolding ? '즉시 보안 검사를 시작했습니다.' : '검토 요청을 등록했습니다.'));
        return;
    }

    alert(await readErrorMessage(downloadResponse, '요청 중 오류가 발생했습니다.'));
}

window.addEventListener('DOMContentLoaded', async () => {
    const params = new URLSearchParams(window.location.search);
    const extID = params.get('extID');
    const searchExtName = params.get('extName');
    const browser = params.get('browser');

    let response;

    try {
        if (extID) {
            response = await fetch('/api/search_id', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    extension_id: extID,
                    browser,
                }),
            });
        } else if (searchExtName) {
            response = await fetch('/api/search_name', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    extension_name: searchExtName,
                    browser,
                }),
            });
        }

        if (!response) return;

        const result = await response.json();
        const extInfo = result.data;
        if (!extInfo) return;

        const extensionId = extInfo.id;
        const extName = extInfo.name;
        const extVersion = extInfo.version;
        const extLastUpdated = extInfo.last_updated || extInfo.updated || 'N/A';
        const extSummary = extInfo.summary || extInfo.description || '설명이 없습니다.';
        const extLogo = extInfo.logo_url;

        document.getElementById('extName').textContent = extName;
        document.getElementById('extLogo').src = extLogo;
        document.getElementById('extVer').textContent = extVersion;
        document.getElementById('extUpd').textContent = extLastUpdated;
        document.getElementById('extSummary').textContent = extSummary;

        const session = await loadSession();
        const permissions = Array.isArray(session.permissions) ? session.permissions : [];
        const canBypassHolding = permissions.includes('bypass_holding');

        const requestButton = document.getElementById('download_btn');
        const bypassButton = document.getElementById('bypass_holding_btn');
        const requestPayload = {extensionId, browser, extVersion, extName};

        if (requestButton) {
            requestButton.addEventListener('click', () => {
                requestExtensionScan({...requestPayload, bypassHolding: false}).catch(error => {
                    console.error('Extension request failed:', error);
                    alert('서버 통신에 실패했습니다.');
                });
            });
        }

        if (bypassButton && canBypassHolding) {
            bypassButton.classList.remove('hidden');
            bypassButton.addEventListener('click', () => {
                requestExtensionScan({...requestPayload, bypassHolding: true}).catch(error => {
                    console.error('Immediate extension request failed:', error);
                    alert('서버 통신에 실패했습니다.');
                });
            });
        }
    } catch (error) {
        console.error('Search detail load failed:', error);
    }
});

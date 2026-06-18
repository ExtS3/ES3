let uploadFile = null
let uploadMode = 'first'  // 'first' | 'update'
let myExtensions = []     // 추가 업로드 시 불러온 내 확장 목록

document.querySelector('#selectBuildFile').addEventListener('click', () => {
    document.querySelector('#UploadFile').click();
});
document.querySelector('#UploadFile').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    document.getElementById('selectFile').textContent = file.name; // 선택한 파일 이름 표시
    
    uploadFile = file; // 선택 파일 전역 변수 저장

});




// ---- 업로드 모드 (첫 업로드 / 추가 업로드) ----
const modeFirstBtn = document.getElementById('mode-first');
const modeUpdateBtn = document.getElementById('mode-update');
const modeHint = document.getElementById('mode-hint');
const updateSelectWrap = document.getElementById('update-select-wrap');
const extSelect = document.getElementById('extSelect');
const extNameInput = document.getElementById('extName');
const versionInput = document.getElementById('version');
const browserSelect = document.getElementById('browser');
const extIDInput = document.getElementById('extID');

const ACTIVE_TAB = 'px-5 py-2 rounded-lg text-sm font-semibold transition-colors bg-primary text-on-primary';
const INACTIVE_TAB = 'px-5 py-2 rounded-lg text-sm font-semibold transition-colors text-on-surface-variant hover:bg-surface-container';

function setExtNameEditable(editable) {
    extNameInput.readOnly = !editable;
    extNameInput.classList.toggle('bg-surface-container', !editable);
    extNameInput.classList.toggle('text-on-surface-variant', !editable);
    extNameInput.classList.toggle('cursor-not-allowed', !editable);
    extNameInput.classList.toggle('bg-surface-container-low', editable);
}

async function applyMode(mode) {
    uploadMode = mode;
    modeFirstBtn.className = mode === 'first' ? ACTIVE_TAB : INACTIVE_TAB;
    modeUpdateBtn.className = mode === 'update' ? ACTIVE_TAB : INACTIVE_TAB;

    if (mode === 'first') {
        updateSelectWrap.classList.add('hidden');
        modeHint.textContent = '새로운 확장을 처음 업로드합니다. 버전은 자동으로 1.0.0으로 설정됩니다.';
        setExtNameEditable(true);
        extNameInput.value = '';
        versionInput.value = '1.0.0';
        browserSelect.disabled = false;
    } else {
        updateSelectWrap.classList.remove('hidden');
        modeHint.textContent = '이미 업로드한 확장을 선택하면 버전이 자동으로 1단계 올라갑니다.';
        setExtNameEditable(false);
        browserSelect.disabled = true;
        await loadMyExtensions();
    }
}

async function loadMyExtensions() {
    extSelect.innerHTML = '<option value="">불러오는 중...</option>';
    try {
        const res = await fetch('/api/uploads/mine');
        const data = await res.json();
        myExtensions = (data && data.extensions) || [];
    } catch (e) {
        myExtensions = [];
    }

    if (!myExtensions.length) {
        extSelect.innerHTML = '<option value="">업로드한 확장이 없습니다</option>';
        extNameInput.value = '';
        versionInput.value = '';
        return;
    }

    extSelect.innerHTML = '<option value="">확장을 선택하세요</option>' +
        myExtensions.map((x) =>
            `<option value="${x.ext_id}">${x.ext_name} (현재 v${x.latest_version} → v${x.next_version})</option>`
        ).join('');
}

extSelect.addEventListener('change', () => {
    const ext = myExtensions.find((x) => x.ext_id === extSelect.value);
    if (!ext) {
        extNameInput.value = '';
        versionInput.value = '';
        return;
    }
    extNameInput.value = ext.ext_name;
    versionInput.value = ext.next_version;
    if (ext.browser) browserSelect.value = ext.browser;
});

modeFirstBtn.addEventListener('click', () => applyMode('first'));
modeUpdateBtn.addEventListener('click', () => applyMode('update'));
applyMode('first');

document.getElementById('buildBtn').addEventListener('click', async () => {
    // 1. 파일 선택 여부 확인
    if (!uploadFile) {
        await showCustomConfirm({
            titleText: '파일 미선택',
            messageText: '업로드할 파일을 먼저 선택해주세요.',
            iconName: 'warning',
            type: 'danger' 
        });
        return;
    }

    // 2. 커스텀 모달로 업로드 의사 확인
    const isConfirmed = await showCustomConfirm({
        titleText: 'Nexus 서버 업로드',
        messageText: `[${uploadFile.name}] 파일을 서버로 전송하시겠습니까?`,
        iconName: 'cloud_upload',
        type: 'primary'
    });


    if (isConfirmed) {
        try {
            // 모드/이름/버전을 서버에서 확정받는다 (이름 중복·소유권 검증 포함)
            const resolveBody = uploadMode === 'update'
                ? { mode: 'update', ext_id: extSelect.value }
                : { mode: 'first', ext_name: extNameInput.value.trim(), browser: browserSelect.value };

            const resolveRes = await fetch('/api/uploads/resolve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(resolveBody)
            });
            if (!resolveRes.ok) {
                const msg = await readErrorMessage(resolveRes, '업로드 정보를 확인하지 못했습니다.');
                throw new Error(msg);
            }
            const resolved = await resolveRes.json();

            const version = resolved.version;
            const browser = browserSelect.value;
            const extName = resolved.ext_name;
            const extID = resolved.ext_id;

            // 화면에도 확정된 값 반영
            versionInput.value = version;
            extNameInput.value = extName;
            extIDInput.value = extID;

            const formData = new FormData();
            // 중요: pending 함수가 Form(...)으로 요구하는 변수명과 일치시켜야 함
            formData.append('plugin_name', extName);
            formData.append('browser', browser);
            formData.append('version', version);
            formData.append('mode', uploadMode);
            formData.append("extID", extID)
            formData.append('file', uploadFile);

            // 첫 번째 호출 (파일 저장용)
            const response = await fetch('/api/security_scan/file_save', {
                method: 'POST',
                body: formData // headers에 fileName 따로 안 넣어도 FormData에 담겨 감
            });

            // 두 번째 호출 (보안 스캔용 - 422 에러 나던 곳)
            const scan_file = await fetch('/api/send_suppressor', {
                method: 'POST',
                body: formData
            });

            if (!scan_file.ok) {
                const errorMsg = await readErrorMessage(scan_file, "보안 스캔 요청 중 오류가 발생했습니다.");
                console.error("스캔 요청 실패:", errorMsg);
                throw new Error(errorMsg);
            }
            
            // 1. 응답이 정상(200~299)인지 먼저 확인
            if (!response.ok) {
                // 서버가 에러를 뱉었을 때 (413 등)
                let errorMessage = `서버 에러가 발생했습니다. (상태 코드: ${response.status})`;
                
                try {
                    // 혹시 모르니 에러 내용을 텍스트로 읽어봅니다.
                    const errorDetail = await readErrorMessage(response, errorMessage);
                    console.error("서버에서 보낸 상세 에러:", errorDetail);
                    errorMessage = errorDetail;
                    
                    if (response.status === 413) {
                        errorMessage = "파일 용량이 너무 큽니다. 서버 설정(Nginx 등)을 확인해주세요.";
                    }
                } catch (e) {
                    // 텍스트조차 못 읽는 상황 대비
                }
                
                throw new Error(errorMessage);
            }

            // 2. 정상일 때만 JSON으로 변환
            const result = await response.json();

            if (result.success) {
                // 성공 시: 확인 버튼만 있는 모달 띄우기
                await showCustomConfirm({
                    titleText: '보안 검사 후 업로드 예정입니다.',
                    messageText: `저장 경로: ${result.save_path}`,
                    iconName: 'check_circle',
                    type: 'primary',
                    showCancel: false  // <-- 취소 버튼을 숨깁니다!
                }  
            );
            location.href ="/"
                
                // 모달 확인을 누른 후 실행할 로직이 있다면 여기에 작성 (예: 페이지 새로고침)
                // location.reload(); 
            } else {
                throw new Error(result.detail || '업로드에 실패했습니다.');
            }
        } catch (error) {
            // 실패 시 커스텀 모달 활용
            await showCustomConfirm({
                titleText: '업로드 오류',
                messageText: error.message,
                iconName: 'error',
                type: 'danger'
            });
        }
    }
});







///////////////// 예쁜>< 승인 버튼
// 버튼 클릭 함수도 미리 만들어두기 - 이거 내가 안 만듦! 쏘리. 근데 커스텀이라니까 예뻐서 안 쓸 수가 없었어요.

// 전역 변수로 모달 요소 저장
const confirmModal = document.getElementById('custom-confirm-modal');
const backdrop = document.getElementById('modal-backdrop');
const content = document.getElementById('modal-content');
const title = document.getElementById('modal-title');
const message = document.getElementById('modal-message');
const icon = document.getElementById('modal-icon');
const iconContainer = document.getElementById('modal-icon-container');
const confirmBtn = document.getElementById('modal-confirm-btn');
const cancelBtn = document.getElementById('modal-cancel-btn');

let resolvePromise; // 사용자의 선택을 기다리는 프로미스 저장용

// 커스텀 confirm 함수 정의
function showCustomConfirm({ titleText, messageText, iconName, type, showCancel = true }) {
  // 1. 모달 컨텐츠 설정
  title.textContent = titleText;
  message.textContent = messageText;
  icon.textContent = iconName;

  // 2. 취소 버튼 표시 여부 결정 (추가된 로직)
  if (showCancel) {
    cancelBtn.classList.remove('hidden');
  } else {
    cancelBtn.classList.add('hidden');
  }

  if (type === 'danger') {
    iconContainer.className = 'p-3 rounded-full bg-error/10 text-error';
    confirmBtn.className = 'flex-1 px-5 py-2.5 rounded-full text-sm font-semibold bg-error text-white hover:bg-error-hover transition-colors shadow-sm';
  } else {
    iconContainer.className = 'p-3 rounded-full bg-primary/10 text-primary';
    confirmBtn.className = 'flex-1 px-5 py-2.5 rounded-full text-sm font-semibold bg-primary text-white hover:bg-primary-hover transition-colors shadow-sm';
  }

  // 3. 모달 열기
  confirmModal.classList.remove('hidden');
  setTimeout(() => {
    backdrop.classList.add('opacity-100');
    content.classList.add('scale-100', 'opacity-100');
  }, 10);

  return new Promise((resolve) => {
    resolvePromise = resolve;
  });
}

async function readErrorMessage(response, fallback) {
    try {
        const data = await response.json();
        return data.detail || data.message || fallback;
    } catch (_) {
        return fallback;
    }
}

// 모달 닫기 함수
function closeModals() {
    backdrop.classList.remove('opacity-100');
    content.classList.remove('scale-100', 'opacity-100');
    
    // Promise를 반환하여 애니메이션이 끝날 때까지 기다릴 수 있게 함
    return new Promise((resolve) => {
        setTimeout(() => {
            confirmModal.classList.add('hidden');
            resolve(); // 0.3초 뒤에 완료 알림
        }, 300);
    });
}


// --- 버튼 클릭 이벤트 등록 ---

// 확인 버튼 클릭 시: 애니메이션이 완전히 끝날 때까지 기다린 후 true 반환
confirmBtn.addEventListener('click', async () => {
    const currentResolve = resolvePromise; // 현재 프로미스 저장
    await closeModals(); // 0.3초 애니메이션 대기
    if (currentResolve) currentResolve(true);
});

// 취소 버튼도 동일하게
cancelBtn.addEventListener('click', async () => {
    const currentResolve = resolvePromise;
    await closeModals();
    if (currentResolve) currentResolve(false);
});

// 배경 클릭도 동일하게
backdrop.addEventListener('click', async () => {
    const currentResolve = resolvePromise;
    await closeModals();
    if (currentResolve) currentResolve(false);
});

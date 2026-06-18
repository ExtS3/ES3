// 전역 상태 변수
let filteredApps = []; 
let currentPage = 1;
const itemsPerPage = 4; // 한 페이지에 보여줄 개수 (4개로 하려면 4로 수정)

async function fetchPendingApps() {
    const queueBody = document.getElementById('queue-body');
    if (!queueBody) return;

    try {
        const response = await fetch("/api/nexus/list", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });

        const result = await response.json();
        const allApps = Array.isArray(result) ? result : (result.data || []);

        // 1. review 경로 필터링 + 날짜 내림차순 정렬 (최신순)
        filteredApps = allApps
            .filter(app => app.path && app.path.includes('review/'))
            .sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified)); // 날짜 정렬 추가

        if (filteredApps.length === 0) {
            queueBody.innerHTML = '<tr><td colspan="4" class="text-center py-4">데이터가 없습니다.</td></tr>';
            return;
        }

        currentPage = 1;
        displayPage(currentPage);

    } catch (error) {
        console.error("데이터 로드 실패:", error);
    }
}

function displayPage(page) {
    const queueBody = document.getElementById('queue-body');
    queueBody.innerHTML = '';

    const start = (page - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const paginatedItems = filteredApps.slice(start, end);

    let lastDisplayedDate = ""; // 날짜 구분선을 위한 변수

    paginatedItems.forEach(app => {
        // 날짜 포맷팅 (YYYY-MM-DD)
        const dateObj = new Date(app.lastModified);
        const formattedDate = dateObj.toISOString().split('T')[0];

        // 2. 날짜가 바뀌면 구분선 행 추가 (선택 사항)
        if (formattedDate !== lastDisplayedDate) {
            const dateDivider = `
                <tr class="bg-surface-container-low/50">
                    <td colspan="4" class="py-2 px-4 text-xs font-bold text-primary border-b border-primary/10">
                        <span class="flex items-center gap-1">
                            <span class="material-symbols-outlined text-sm">calendar_today</span>
                            ${formattedDate}
                        </span>
                    </td>
                </tr>`;
            queueBody.insertAdjacentHTML('beforeend', dateDivider);
            lastDisplayedDate = formattedDate;
        }

        const pathParts = app.path.split('/').filter(Boolean);
        const browser = pathParts[1] || 'Unknown';
        const appName = pathParts[2] || 'Unknown';
        const version = pathParts[3] || '0.0.0';
        const id = pathParts[4] ? pathParts[4].replace('.zip', '') : 'Unknown';

        const row = `
            <tr class="border-b border-surface-variant/30 hover:bg-surface-container-low transition-colors cursor-pointer" 
                onmousedown="handleMouseDown(event)"
                onmouseup="handleRowClick(event, '${id}', '${encodeURIComponent(appName)}', '${encodeURIComponent(browser)}', '${version}', '${encodeURIComponent(app.path)}')">
                <td class="py-4 px-4 text-sm font-medium text-on-surface">
                    <div class="flex flex-col">
                        <span>${appName}</span>
                        <span class="text-[10px] text-on-surface-variant/70">${dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                    </div>
                </td>
                <td class="py-4 px-4 text-sm text-on-surface-variant">${browser}</td>
                <td class="py-4 px-4 text-sm text-on-surface-variant font-mono">${version}</td>
                <td class="px-6 py-4 text-right">
                    <div class="flex justify-end gap-2">
                        <button onmousedown="event.stopPropagation()" onmouseup="event.stopPropagation()" onclick="event.stopPropagation(); approveApp('${id}', '${encodeURIComponent(appName)}', '${encodeURIComponent(browser)}', '${version}', '${encodeURIComponent(app.path)}')" 
                                class="px-3 py-1 bg-primary/10 text-primary hover:bg-primary hover:text-white text-xs font-bold rounded-full border border-primary/20 transition-all">
                            승인
                        </button>
                        <button onmousedown="event.stopPropagation()" onmouseup="event.stopPropagation()" onclick="event.stopPropagation(); rejectApp('${id}', '${encodeURIComponent(appName)}', '${encodeURIComponent(browser)}', '${version}', '${encodeURIComponent(app.path)}')" 
                                class="px-3 py-1 bg-error/10 text-error hover:bg-error hover:text-white text-xs font-bold rounded-full border border-error/20 transition-all">
                            거부
                        </button>
                    </div>
                </td>
            </tr>
        `;
        queueBody.insertAdjacentHTML('beforeend', row);
    });

    updatePaginationControls();
}

// 페이지 번호 버튼 생성 함수
function updatePaginationControls() {
    const controls = document.getElementById('pagination-controls');
    if (!controls) return;
    controls.innerHTML = '';

    const totalPages = Math.ceil(filteredApps.length / itemsPerPage);
    if (totalPages <= 1) return; // 1페이지면 버튼 숨김

    for (let i = 1; i <= totalPages; i++) {
        const btn = document.createElement('button');
        btn.textContent = i;
        btn.className = `w-8 h-8 rounded-lg text-sm font-bold transition-all ${
            currentPage === i 
            ? 'bg-primary text-white shadow-sm' 
            : 'bg-surface-container-highest text-on-surface-variant hover:bg-primary/20'
        }`;
        
        btn.onclick = () => {
            currentPage = i;
            displayPage(i);
        };
        controls.appendChild(btn);
    }
}


// 로그 상세 페이지
function showLog(id, app_name, app_browser, version, source_path){
    location.href= `/admin/log?id=${id}&name=${app_name}&browser=${app_browser}&version=${version}&source_path=${source_path}`;
}

//////////////////////////////////////
// date부분이랑 클릭 부분에서 드래그를 했을 때 드래그가 아니라 클릭으로 인식해서 다음 페이지로 넘어가는 문제가 생기길래. 이런 것도 해봄
// html 에서 onmouse에 관한 함수들로 관리.

// 드래그 감지용 전역 변수
let startX, startY;

// 드래그 여부를 판단해서 showLog를 실행할지 결정하는 함수
function handleRowClick(event, id, name, browser, version, source_path) {
    if (event.target.closest('button')) {
        return;
    }

    // 뗐을 때의 좌표
    const diffX = Math.abs(event.pageX - startX);
    const diffY = Math.abs(event.pageY - startY);

    // 좌표 변화가 적으면(예: 5px 미만) 단순 클릭으로 간주
    if (diffX < 5 && diffY < 5) {
        showLog(id, name, browser, version, source_path);
    }
}

// 눌렀을 때 좌표 저장
function handleMouseDown(event) {
    startX = event.pageX;
    startY = event.pageY;
}
///////////////////////////////

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
function showCustomConfirm({ titleText, messageText, iconName, type }) {
  // 1. 모달 컨텐츠 설정 (타입에 따라 색상 변경)
  title.textContent = titleText;
  message.textContent = messageText;
  icon.textContent = iconName;

  if (type === 'danger') {
    iconContainer.className = 'p-3 rounded-full bg-error/10 text-error';
    confirmBtn.className = 'px-5 py-2.5 rounded-full text-sm font-semibold bg-error text-white hover:bg-error-hover transition-colors shadow-sm';
  } else {
    iconContainer.className = 'p-3 rounded-full bg-primary/10 text-primary';
    confirmBtn.className = 'px-5 py-2.5 rounded-full text-sm font-semibold bg-primary text-white hover:bg-primary-hover transition-colors shadow-sm';
  }

  // 2. 모달 열기 (애니메이션 적용)
  confirmModal.classList.remove('hidden');
  setTimeout(() => {
    backdrop.classList.add('opacity-100');
    content.classList.add('scale-100', 'opacity-100');
  }, 10);

  // 3. 사용자의 클릭을 기다리는 프로미스 반환
  return new Promise((resolve) => {
    resolvePromise = resolve; // 나중에 버튼 클릭 시 호출할 함수 저장
  });
}

// 모달 닫기 함수
function closeModals() {
  backdrop.classList.remove('opacity-100');
  content.classList.remove('scale-100', 'opacity-100');
  setTimeout(() => {
    confirmModal.classList.add('hidden');
  }, 300); // 애니메이션 시간 뒤에 hidden 처리
}

// 확인 버튼 클릭 시
confirmBtn.addEventListener('click', () => {
  resolvePromise(true); // 프로미스를 true로 완료
  closeModals();
});

// 취소 버튼 클릭 시 (배경 클릭 포함)
[cancelBtn, backdrop].forEach(el => {
  el.addEventListener('click', () => {
    resolvePromise(false); // 프로미스를 false로 완료
    closeModals();
  });
});




// 기존 함수를 async 함수로 변경
async function approveApp(id, app_name) {
  const isConfirmed = await showCustomConfirm({
    titleText: '승인하시겠습니까?',
    messageText: `${app_name}(ID: ${id})을 목록에 승인 상태로 등록합니다.`,
    iconName: 'check_circle', // 구글 아이콘 이름
    type: 'primary' // 승인은 파란색
  });

  if (isConfirmed) {
    console.log(`ID ${id} 승인 처리 시작 (서버 fetch)...`);
    // 여기에 실제 서버 fetch API 코드를 작성하세요.
    console.log(`ID ${id} 승인 처리 완료!!!`)
    alert("승인 처리가 완료되었습니다."); // 임시 알림
  }
}

async function rejectApp(id, app_name) {
  const isConfirmed = await showCustomConfirm({
    titleText: '거부하시겠습니까?',
    messageText: `거부 후에는 ${app_name}(ID: ${id})에 대해 더 이상 처리가 불가합니다.`,
    iconName: 'cancel', // 구글 아이콘 이름
    type: 'danger' // 거절은 빨간색
  });

  if (isConfirmed) {
    console.log(`ID ${id, app_name} 거부 처리 시작 (서버 fetch)...`);
    // 여기에 실제 서버 fetch API 코드를 작성하세요.
    alert("거부 처리가 완료되었습니다."); // 임시 알림
  }
}



console.log("스크립트 파일 로드됨");
async function sendDashboardDecision(url, payload, successMessage) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const result = await response.json();

  if (!response.ok || !result.success) {
    throw new Error(result.detail || result.message || '처리 중 오류가 발생했습니다.');
  }

  alert(successMessage);
  window.location.href = window.location.pathname + window.location.search;
}

async function approveApp(id, app_name, app_browser, version, source_path) {
  const decodedName = decodeURIComponent(app_name);
  const decodedBrowser = decodeURIComponent(app_browser);
  const decodedPath = decodeURIComponent(source_path).replace(/^\/+/, '');
  const isConfirmed = await showCustomConfirm({
    titleText: '승인하시겠습니까?',
    messageText: `${decodedName}(ID: ${id})을 승인 상태로 등록합니다.`,
    iconName: 'check_circle',
    type: 'primary'
  });

  if (!isConfirmed) return;

  try {
    await sendDashboardDecision('/api/decision/approve', {
      id,
      app_name: decodedName,
      browser: decodedBrowser,
      version,
      source_path: decodedPath
    }, '승인 처리되었습니다.');
  } catch (error) {
    console.error('Approve failed:', error);
    alert(error.message);
  }
}

async function rejectApp(id, app_name, app_browser, version, source_path) {
  const decodedName = decodeURIComponent(app_name);
  const decodedBrowser = decodeURIComponent(app_browser);
  const decodedPath = decodeURIComponent(source_path).replace(/^\/+/, '');
  const isConfirmed = await showCustomConfirm({
    titleText: '거부하시겠습니까?',
    messageText: `${decodedName}(ID: ${id})은 거부 목록에 기록되고 review에서 삭제됩니다.`,
    iconName: 'cancel',
    type: 'danger'
  });

  if (!isConfirmed) return;

  try {
    await sendDashboardDecision('/api/decision/reject', {
      id,
      app_name: decodedName,
      browser: decodedBrowser,
      version,
      source_path: decodedPath
    }, '거부 처리되었습니다.');
  } catch (error) {
    console.error('Reject failed:', error);
    alert(error.message);
  }
}

async function fetchRejectedApps() {
  const rejectList = ensureRejectListContainer();
  if (!rejectList) return;

  try {
    const response = await fetch('/api/decision/rejects');
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.detail || result.message || '거부 목록을 불러오지 못했습니다.');
    }

    const items = Array.isArray(result.items) ? result.items : [];
    if (items.length === 0) {
      rejectList.innerHTML = '<p class="text-sm text-on-surface-variant">거부된 프로그램이 없습니다.</p>';
      return;
    }

    rejectList.innerHTML = items.slice(0, 8).map((item) => {
      const rejectedAt = item.rejected_at ? new Date(item.rejected_at) : null;
      const rejectedText = rejectedAt && !Number.isNaN(rejectedAt.getTime())
        ? rejectedAt.toLocaleString()
        : '시간 정보 없음';

      return `
        <div class="flex gap-4">
          <div class="flex-shrink-0 mt-1">
            <div class="w-8 h-8 rounded-full bg-error/10 flex items-center justify-center">
              <span class="material-symbols-outlined text-error text-sm">block</span>
            </div>
          </div>
          <div class="min-w-0">
            <p class="text-sm text-on-surface font-medium truncate">${item.app_name || item.id || 'Unknown'}</p>
            <p class="text-xs text-on-surface-variant mt-0.5">${item.browser || 'Unknown'} · ${item.version || 'Unknown'} · ${rejectedText}</p>
            <p class="text-xs text-on-surface-variant/80 mt-1 font-mono truncate">${item.source_path || ''}</p>
          </div>
        </div>
      `;
    }).join('');
  } catch (error) {
    console.error('Rejected apps load failed:', error);
    rejectList.innerHTML = `<p class="text-sm text-error">${error.message}</p>`;
  }
}

function ensureRejectListContainer() {
  let rejectList = document.getElementById('reject-list');
  if (rejectList) return rejectList;

  const layout = document.querySelector('main .grid.grid-cols-1.lg\\:grid-cols-3');
  if (!layout) return null;

  const panel = document.createElement('div');
  panel.className = 'space-y-4';
  panel.innerHTML = `
    <h2 class="text-xl font-bold tracking-tight text-on-surface">거부 프로그램 목록</h2>
    <div class="bg-surface-container-low rounded-2xl p-6 border border-outline-variant/10">
      <div id="reject-list" class="space-y-6">
        <p class="text-sm text-on-surface-variant">거부된 프로그램을 불러오는 중입니다.</p>
      </div>
    </div>
  `;

  const oldSidePanel = layout.children[1];
  if (oldSidePanel) {
    oldSidePanel.replaceWith(panel);
  } else {
    layout.appendChild(panel);
  }

  return document.getElementById('reject-list');
}

function setupRejectReportDownload() {
  const reportButton = document.getElementById('report-download-btn');
  if (!reportButton) return;

  reportButton.addEventListener('click', () => {
    window.location.href = '/api/decision/rejects/report.pdf';
  });
}

fetchPendingApps();
fetchRejectedApps();
setupRejectReportDownload();

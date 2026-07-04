let selectBrow = "Chrome"; // 기본 선택 플랫폼 (search.html의 Chrome 칩이 기본 active)

//////////////////////// 플랫폼 선택 칩 /////////////////////////

const buttons = document.querySelectorAll('.browser-btn');

buttons.forEach(button => {
    button.addEventListener('click', () => {
        buttons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        selectBrow = button.getAttribute('data-name');
    });
});

//////////////////// 검색 타입 자동 판별 ////////////////////
// 토글 없이 입력값 형태로 ID/이름을 판별한다.
// - Chrome 확장 ID: a~p 32자 (예: mjokpjlgmbbdhooncpdlgcgpepecigdm)
// - VS Code 확장 ID: 게시자.이름 (예: ms-python.python)
function detectParamKey(value) {
    if (/^[a-p]{32}$/.test(value)) return 'extID';
    if (selectBrow === 'VSCode' && /^[\w-]+\.[\w-]+$/.test(value)) return 'extID';
    return 'extName';
}

//////////////////// 검색 실행 ////////////////////
document.getElementById('exploreBtn').addEventListener('click', () => {
    const searchValue = document.getElementById('searchInput').value.trim();

    if (!searchValue) {
        document.getElementById('searchInput').focus();
        return;
    }

    const paramKey = detectParamKey(searchValue);
    location.href = `/search_list?${paramKey}=${encodeURIComponent(searchValue)}&browser=${selectBrow}`;
});

//////////////////// 검색창 Enter 키로 검색 실행 ////////////////////
document.getElementById('searchInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        document.getElementById('exploreBtn').click();
    }
});

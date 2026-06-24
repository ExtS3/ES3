let selectBrow = ""; // 선택된 브라우저
let searchType = "id"; // 기본값 ID로 검색 설정 ('id' 또는 'name')

//////////////////////// 브라우저 선택 버튼 함수 /////////////////////////

const buttons = document.querySelectorAll('.browser-btn');

buttons.forEach(button => {
    button.addEventListener('click', () => {
        // 1. 모든 버튼에서 active 클래스 제거
        buttons.forEach(btn => btn.classList.remove('active'));

        // 2. 클릭된 버튼에 active 클래스 추가
        button.classList.add('active');

        // 3. 변수에 데이터 저장
        selectBrow = button.getAttribute('data-name');

        console.log("현재 선택된 브라우저:", selectBrow);
    });
});
////////////////////////////////////////////////////////////////////

//////////////////// 검색방법 선택 함수 (수정) ////////////////////
function toggleSearch(type) {
  const idBtn = document.getElementById('search-id');
  const nameBtn = document.getElementById('search-name');
  
  // 1. 각 버튼 안의 아이콘(svg 또는 i) 요소를 찾습니다.
  const idIcon = idBtn.querySelector('svg'); 
  const nameIcon = nameBtn.querySelector('svg');
  
  const idSpan = idBtn.querySelector('span');
  const nameSpan = nameBtn.querySelector('span');
  
  searchType = type;

  if (type === 'id') {
    // --- ID 활성화 ---
    idBtn.classList.replace('bg-white', 'bg-indigo-50');
    idBtn.classList.replace('border-slate-100', 'border-indigo-500');
    idSpan.classList.replace('text-slate-600', 'text-indigo-700');
    idSpan.classList.add('font-bold');
    
    // ID 아이콘 색상 변경 (무채색 -> 인디고)
    if(idIcon) idIcon.classList.replace('text-slate-400', 'text-indigo-600');

    // --- 이름 비활성화 ---
    nameBtn.classList.replace('bg-indigo-50', 'bg-white');
    nameBtn.classList.replace('border-indigo-500', 'border-slate-100');
    nameSpan.classList.replace('text-indigo-700', 'text-slate-600');
    nameSpan.classList.remove('font-bold');

    // 이름 아이콘 색상 원복 (인디고 -> 무채색)
    if(nameIcon) nameIcon.classList.replace('text-indigo-600', 'text-slate-400');

  } else {
    // --- 이름 활성화 ---
    nameBtn.classList.replace('bg-white', 'bg-indigo-50');
    nameBtn.classList.replace('border-slate-100', 'border-indigo-500');
    nameSpan.classList.replace('text-slate-600', 'text-indigo-700');
    nameSpan.classList.add('font-bold');

    // 이름 아이콘 색상 변경 (무채색 -> 인디고)
    if(nameIcon) nameIcon.classList.replace('text-slate-400', 'text-indigo-600');

    // --- ID 비활성화 ---
    idBtn.classList.replace('bg-indigo-50', 'bg-white');
    idBtn.classList.replace('border-indigo-500', 'border-slate-100');
    idSpan.classList.replace('text-indigo-700', 'text-slate-600');
    idSpan.classList.remove('font-bold');

    // ID 아이콘 색상 원복 (인디고 -> 무채색)
    if(idIcon) idIcon.classList.replace('text-indigo-600', 'text-slate-400');
  }
}

//////////////////// 검색 실행 함수 (수정) ////////////////////
document.getElementById('exploreBtn').addEventListener('click', async () => {
    const searchValue = document.getElementById('searchInput').value;
    
    if (!searchValue) {
        alert("검색어를 입력해주세요.");
        return;
    }
    if (!selectBrow) {
        alert('브라우저를 선택하세요.');
        return;
    }

    // [핵심] searchType에 따라 파라미터 키값을 다르게 설정
    // ID검색이면 extID, 이름검색이면 extName (원하시는 명칭으로 변경 가능)
    const paramKey = (searchType === 'id') ? 'extID' : 'extName';
    
    console.log(`요청 타입: ${searchType}, 값: ${searchValue}, 브라우저: ${selectBrow}`);

    // 최종 URL 생성
    location.href = `/search_list?${paramKey}=${encodeURIComponent(searchValue)}&browser=${selectBrow}`;
});

//////////////////// 검색창 Enter 키로 검색 실행 ////////////////////
document.getElementById('searchInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        document.getElementById('exploreBtn').click();
    }
});


# frontend/static/vendor

서드파티 라이브러리 파일 모음입니다.
CDN 대신 로컬에 직접 보관해 외부 네트워크 없이도 동작하도록 합니다.

---

## 파일 구성

### html2canvas.min.js

**버전**: 1.4.1
**참조 템플릿**: `frontend/templates/admin/log.html`
**사용 위치**: `frontend/static/js/admin/admin_log.js`

HTML DOM 영역을 Canvas로 캡처하는 라이브러리입니다.
`admin_log.js`의 `exportAnalysisPdf()`에서 분석 리포트 영역(`#security-analysis-report-section`)을 이미지로 변환할 때 사용합니다.

```javascript
// admin_log.js 사용 예시
const canvas = await window.html2canvas(target, {
  scale: 2,
  backgroundColor: '#ffffff',
  useCORS: true,
})
```

`window.html2canvas`로 전역 접근합니다. `jspdf.umd.min.js`와 함께 로드해야 PDF 내보내기가 정상 동작합니다.

---

### jspdf.umd.min.js

**버전**: 2.5.1
**참조 템플릿**: `frontend/templates/admin/log.html`
**사용 위치**: `frontend/static/js/admin/admin_log.js`

클라이언트 사이드 PDF 생성 라이브러리입니다.
`html2canvas`가 캡처한 Canvas 이미지를 A4 PDF로 변환해 다운로드합니다.

```javascript
// admin_log.js 사용 예시
const jsPdf = window.jspdf?.jsPDF
const pdf = new jsPdf('p', 'mm', 'a4')
pdf.addImage(imageData, 'PNG', margin, y, imageWidth, imageHeight)
pdf.save(currentPdfFileName)
```

`window.jspdf.jsPDF`로 접근합니다. `html2canvas.min.js`보다 나중에 로드되어야 합니다.

**로드 순서** (`log.html` 기준):

```html
<script src="/static/vendor/html2canvas.min.js"></script>
<script src="/static/vendor/jspdf.umd.min.js"></script>
```

---

### tailwindcss-forms-container-queries.js

**참조 템플릿**: 전체 페이지 공통 (`<head>` 태그 내)

Tailwind CSS 플러그인 2개를 번들한 파일입니다.

- **@tailwindcss/forms** — `input`, `select`, `textarea` 등 폼 요소의 기본 스타일을 Tailwind로 제어 가능하게 초기화
- **@tailwindcss/container-queries** — `@container` 기반 반응형 레이아웃 지원 (`container-type`, `@lg:` 등 컨테이너 쿼리 유틸리티)

Tailwind CDN 스크립트와 함께 로드해 플러그인으로 등록됩니다.

```html
<!-- 일반적인 로드 패턴 -->
<script>
  tailwind.config = {
    plugins: [tailwindForms, tailwindContainerQueries],
  }
</script>
```

---

## 업데이트 방법

각 라이브러리를 업데이트할 경우 아래 공식 배포처에서 minified 파일을 받아 교체합니다.

| 파일                                     | 배포처                                           |
| ---------------------------------------- | ------------------------------------------------ |
| `html2canvas.min.js`                     | https://github.com/niklasvh/html2canvas/releases |
| `jspdf.umd.min.js`                       | https://github.com/parallax/jsPDF/releases       |
| `tailwindcss-forms-container-queries.js` | Tailwind CDN 번들 또는 직접 빌드                 |

라이브러리 버전을 변경할 경우 이 README의 버전 정보도 함께 수정하세요.

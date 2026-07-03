// ES3 공유 Tailwind 테마 — 템플릿마다 복붙돼 있던 인라인 tailwind.config를 대체한다.
// 로드 순서: tailwindcss vendor 스크립트 → 이 파일. (Play CDN 방식은 나중 할당도 반영됨)
// 기존 M3 색 이름을 그대로 유지하고 값만 ES3 로고 팔레트로 재정의 → 기존 클래스가 전부 재도색된다.
// 원본 팔레트: /static/css/common/tokens.css
tailwind.config = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // 브랜드 (로고 로열블루-바이올렛)
        "primary": "#4A5BE0",
        "primary-dim": "#3B49C4",
        "primary-fixed": "#EEF1FE",
        "primary-fixed-dim": "#DDE3FC",
        "primary-container": "#EEF1FE",
        "on-primary": "#FFFFFF",
        "on-primary-container": "#3B49C4",
        "on-primary-fixed": "#2C358E",
        "on-primary-fixed-variant": "#3B49C4",
        "inverse-primary": "#AEB8F5",
        "surface-tint": "#4A5BE0",
        // 보조 (로고 바이올렛)
        "secondary": "#7C4DE0",
        "secondary-dim": "#6339BF",
        "secondary-fixed": "#F1EBFD",
        "secondary-fixed-dim": "#E4D9FA",
        "secondary-container": "#F1EBFD",
        "on-secondary": "#FFFFFF",
        "on-secondary-container": "#5B33B8",
        "on-secondary-fixed": "#45268F",
        "on-secondary-fixed-variant": "#5B33B8",
        // 3차 (로고 하늘색)
        "tertiary": "#1E96D6",
        "tertiary-dim": "#1273A8",
        "tertiary-fixed": "#E4F4FE",
        "tertiary-fixed-dim": "#CBEAFC",
        "tertiary-container": "#E4F4FE",
        "on-tertiary": "#FFFFFF",
        "on-tertiary-container": "#1273A8",
        "on-tertiary-fixed": "#0E5A83",
        "on-tertiary-fixed-variant": "#1273A8",
        // 표면/배경
        "background": "#F7F8FC",
        "on-background": "#1E2130",
        "surface": "#F7F8FC",
        "surface-bright": "#F7F8FC",
        "surface-dim": "#E6E8F0",
        "on-surface": "#1E2130",
        "on-surface-variant": "#64748B",
        "surface-container-lowest": "#FFFFFF",
        "surface-container-low": "#F1F3F9",
        "surface-container": "#EBEDF5",
        "surface-container-high": "#E6E8F0",
        "surface-container-highest": "#DDE0EA",
        "inverse-surface": "#1E2130",
        "inverse-on-surface": "#F1F3F9",
        "outline": "#8A93A6",
        "outline-variant": "#E6E8F0",
        // 위험
        "error": "#D9394F",
        "error-dim": "#B2293C",
        "error-container": "#FDECEF",
        "on-error": "#FFFFFF",
        "on-error-container": "#B2293C",
      },
      fontFamily: {
        "headline": ["Pretendard", "Inter", "sans-serif"],
        "body": ["Pretendard", "Inter", "sans-serif"],
        "label": ["Pretendard", "Inter", "sans-serif"],
      },
      borderRadius: { "DEFAULT": "0.375rem", "lg": "0.5rem", "xl": "0.75rem", "full": "9999px" },
    },
  },
};

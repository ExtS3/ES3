# frontend/templates/setting

## user_setting.html

**라우트**: `GET /user_set`
**인증**: 로그인 필요 (`require_authenticated_page`)

사용자 설정 페이지입니다.

**현재 상태**: 전용 JS 파일이 없습니다. 프로필 이미지, 이름, 소속 등의 UI 레이아웃만 정적으로 표시하며 실제 저장 기능이 구현되어 있지 않습니다. 향후 기능 추가 시 `frontend/static/js/` 하위에 `setting/user_setting.js`를 만들어 연결하면 됩니다.

> 프로필 이미지가 외부 URL(`lh3.googleusercontent.com`)을 직접 참조합니다. 네트워크 차단 환경에서는 이미지가 깨집니다. 실제 운영 시 사용자 프로필 이미지 업로드 기능과 함께 교체 필요합니다.

**로드 JS**: `common.js`, `upload.js`

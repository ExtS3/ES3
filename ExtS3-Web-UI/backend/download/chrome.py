import requests
import os
import re
from backend.search.browser.chrome_id import get_extension_info

def chrome_download(extID, save_path="downloads"):
    # 1. 경로 생성
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    
    # 2. 확장 프로그램 정보 획득
    result = get_extension_info(extID)
    extInfo = result.get('data', {})
    extName = extInfo.get("name", extID)
    
    # 파일명 특수문자 제거 (서버 환경에서는 필수)
    clean_name = re.sub(r'[\\/:*?"<>|]', '', extName).strip()
    filename = f"{clean_name}.zip"
    full_path = os.path.join(save_path, filename)

    # 3. 구글 다운로드 API 설정
    # prodversion을 최신(123.0)으로 올리고, params 방식을 사용합니다.
    url = "https://clients2.google.com/service/update2/crx"
    params = {
        "response": "redirect",
        "os": "win",
        "arch": "x86-64",
        "os_arch": "x86_64",
        "nacl_arch": "x86-64",
        "prod": "chromecrx",
        "prodversion": "123.0.0.0", # 버전 상향
        "lang": "ko",
        "acceptformat": "crx2,crx3",
        "x": f"id={extID.strip()}&installsource=ondemand&uc" # strip() 추가
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    }

    try:
        # stream=True와 allow_redirects=True 유지
        response = requests.get(url, headers=headers, params=params, stream=True, allow_redirects=True, timeout=30)

        if response.status_code == 200:
            with open(full_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(f"✅ 다운로드 성공: {full_path}")
            return full_path
        
        elif response.status_code == 204:
            print(f"❌ 실패(204): 구글 서버가 파일을 거부했습니다. (ID: {extID})")
            return None
        else:
            print(f"❌ 실패: 상태 코드 {response.status_code}")
            return None

    except Exception as e:
        print(f"⚠️ 에러 발생: {e}")
        return None
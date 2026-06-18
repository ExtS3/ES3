import os

import requests


API_BASE_URL = "https://open-vsx.org/api"


def vscode_download(ext_id, version, save_path="downloads"):
    if not version or version == "N/A":
        print(f"⚠️ VSCode 다운로드 스킵: 유효하지 않은 버전 ({version})")
        return None

    try:
        publisher, name = str(ext_id).split(".", 1)

        if not os.path.exists(save_path):
            os.makedirs(save_path)

        filename = f"{ext_id}-{version}.vsix"
        full_path = os.path.join(save_path, filename)

        url = (
            f"{API_BASE_URL}/{publisher}/{name}/{version}"
            f"/file/{publisher}.{name}-{version}.vsix"
        )

        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        with open(full_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print(f"✅ VSCode 다운로드 성공: {full_path}")
        return full_path

    except Exception as e:
        print(f"⚠️ VSCode 다운로드 에러: {e}")
        return None

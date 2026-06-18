"""VSCode (Open VSX) 배관 단위 테스트.

레포 루트에서 실행:
    python -m unittest tests.browser.test_vscode
"""

import unittest
from unittest.mock import patch, MagicMock, mock_open

from backend.search.browser.vscode_id import vscode_search_by_id
from backend.search.browser.vscode_name import vscode_search_by_name
from backend.download.vscode import vscode_download


CHROME_KEYS = {
    "id", "name", "logo_url", "version", "users", "users_count",
    "rating", "rating_value", "updated", "last_updated",
    "summary", "description", "url",
}

LATEST_PAYLOAD = {
    "files": {"icon": "https://open-vsx.org/.../eslint_icon.png",
              "download": "https://open-vsx.org/.../dbaeumer.vscode-eslint-3.0.24.vsix"},
    "name": "vscode-eslint",
    "namespace": "dbaeumer",
    "version": "3.0.24",
    "averageRating": 5.0,
    "downloadCount": 4399634,
    "timestamp": "2026-03-05T03:59:45.436054Z",
    "displayName": "ESLint",
    "description": "Integrates ESLint JavaScript into VS Code.",
}

SEARCH_PAYLOAD = {
    "extensions": [
        {"namespace": "ms-python", "name": "python"},
        {"namespace": "vscode", "name": "python"},
        {"name": "missing-namespace"},  # 누락 → 스킵되어야 함
    ]
}


def _mock_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class VscodeIdTest(unittest.TestCase):
    @patch("backend.search.browser.vscode_id.requests.get")
    def test_success_returns_dict_with_12_keys(self, mock_get):
        mock_get.return_value = _mock_response(LATEST_PAYLOAD)
        result = vscode_search_by_id("dbaeumer.vscode-eslint")

        self.assertIsInstance(result, dict)
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(set(data.keys()), CHROME_KEYS)

    @patch("backend.search.browser.vscode_id.requests.get")
    def test_normalization_mapping(self, mock_get):
        mock_get.return_value = _mock_response(LATEST_PAYLOAD)
        data = vscode_search_by_id("dbaeumer.vscode-eslint")["data"]

        self.assertEqual(data["name"], "ESLint")  # displayName
        self.assertEqual(data["users_count"], 4399634)  # downloadCount
        self.assertEqual(data["rating_value"], 5.0)  # averageRating
        self.assertEqual(data["updated"], "2026-03-05")  # timestamp 정규화
        self.assertEqual(data["last_updated"], "2026-03-05")
        self.assertEqual(data["version"], "3.0.24")
        self.assertTrue(data["logo_url"].endswith("eslint_icon.png"))  # files.icon
        self.assertIn("dbaeumer/vscode-eslint", data["url"])

    @patch("backend.search.browser.vscode_id.requests.get")
    def test_failure_returns_dict_not_none(self, mock_get):
        mock_get.side_effect = Exception("network down")
        result = vscode_search_by_id("dbaeumer.vscode-eslint")

        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_malformed_id_returns_dict_not_none(self):
        # '.' 없는 ID → split 실패 → 삼켜서 dict 반환
        result = vscode_search_by_id("no-dot-id")
        self.assertIsInstance(result, dict)
        self.assertFalse(result["success"])


class VscodeNameTest(unittest.TestCase):
    @patch("backend.search.browser.vscode_name.requests.get")
    def test_returns_list_of_id_strings(self, mock_get):
        mock_get.return_value = _mock_response(SEARCH_PAYLOAD)
        result = vscode_search_by_name("python")

        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(x, str) for x in result))
        self.assertEqual(result, ["ms-python.python", "vscode.python"])

    @patch("backend.search.browser.vscode_name.requests.get")
    def test_failure_returns_empty_list(self, mock_get):
        mock_get.side_effect = Exception("boom")
        result = vscode_search_by_name("python")
        self.assertEqual(result, [])


class VscodeDownloadTest(unittest.TestCase):
    @patch("backend.download.vscode.open", new_callable=mock_open)
    @patch("backend.download.vscode.os.makedirs")
    @patch("backend.download.vscode.os.path.exists", return_value=True)
    @patch("backend.download.vscode.requests.get")
    def test_success_path_and_filename_contract(
        self, mock_get, _mock_exists, _mock_makedirs, _mock_file
    ):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_get.return_value = resp

        result = vscode_download("dbaeumer.vscode-eslint", "3.0.24")

        # (a) 반환 경로가 {ext_id}-{version}.vsix 로 끝난다
        #     (download_zip.py:32 의 전송 파일명과 정합해야 하는 유일한 계약 접점)
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith("dbaeumer.vscode-eslint-3.0.24.vsix"))

        # (b) 호출된 Open VSX URL 포맷 검증
        called_url = mock_get.call_args[0][0]
        self.assertEqual(
            called_url,
            "https://open-vsx.org/api/dbaeumer/vscode-eslint/3.0.24"
            "/file/dbaeumer.vscode-eslint-3.0.24.vsix",
        )

    @patch("backend.download.vscode.requests.get")
    def test_falsy_version_returns_none_without_request(self, mock_get):
        result = vscode_download("dbaeumer.vscode-eslint", None)
        self.assertIsNone(result)
        mock_get.assert_not_called()

    @patch("backend.download.vscode.requests.get")
    def test_failure_returns_none(self, mock_get):
        mock_get.side_effect = Exception("404")
        result = vscode_download("dbaeumer.vscode-eslint", "3.0.24")
        self.assertIsNone(result)

    def test_malformed_id_returns_none(self):
        result = vscode_download("no-dot-id", "1.0.0")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

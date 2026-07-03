"""infra_cluster 단위 테스트.

BadBlocker(island.io, 2026-06) 시나리오: 같은 인프라 도메인을 공유하는 자매 확장 중
하나가 거부되면 나머지의 자동 승인이 차단되는지 검증.

실행: python -m unittest discover -s tests -p "test_*.py"
"""

import tempfile
import unittest
from pathlib import Path

from backend.admin.infra_cluster import (
    find_cluster_taint,
    normalize_domain,
    record_signals,
)

BADBLOCKER_ID = "cmedhionkhpnakcndndgjdbohmhepckk"
SISTER_ID = "onomjaelhagjjojbkcafidnepbfkpnee"  # Adblock for Chrome (malware 제거)
SHARED_DOMAIN = "https://api.adblock-for-youtube.com/api/v2/rules"


class NormalizeDomainTest(unittest.TestCase):
    def test_url_to_netloc(self):
        self.assertEqual(normalize_domain(SHARED_DOMAIN), "api.adblock-for-youtube.com")

    def test_bare_domain_lowercased(self):
        self.assertEqual(normalize_domain("Evil.Example.COM"), "evil.example.com")

    def test_benign_cdn_excluded(self):
        self.assertIsNone(normalize_domain("https://fonts.googleapis.com/css"))
        self.assertIsNone(normalize_domain("cdn.jsdelivr.net"))

    def test_garbage_excluded(self):
        self.assertIsNone(normalize_domain(""))
        self.assertIsNone(normalize_domain(None))
        self.assertIsNone(normalize_domain("not-a-domain"))


class ClusterTaintTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.infra_path = Path(self._tmp.name) / "extension_infra.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _record(self, ext_id, domains, name="ext"):
        record_signals(ext_id, "Chrome", name, domains, infra_path=self.infra_path)

    def test_shared_domain_with_rejected_sister_taints(self):
        # 자매 확장(제거 이력)이 같은 인프라 도메인을 사용
        self._record(SISTER_ID, [SHARED_DOMAIN], name="Adblock for Chrome")
        reject_records = [{"id": SISTER_ID, "app_name": "Adblock for Chrome"}]

        taint = find_cluster_taint(
            BADBLOCKER_ID, [SHARED_DOMAIN], reject_records, infra_path=self.infra_path
        )
        self.assertIsNotNone(taint)
        self.assertTrue(taint["tainted"])
        self.assertEqual(taint["matches"][0]["ext_id"], SISTER_ID)
        self.assertIn("api.adblock-for-youtube.com", taint["matches"][0]["shared_domains"])

    def test_no_taint_without_reject_history(self):
        self._record(SISTER_ID, [SHARED_DOMAIN])
        taint = find_cluster_taint(
            BADBLOCKER_ID, [SHARED_DOMAIN], [], infra_path=self.infra_path
        )
        self.assertIsNone(taint)

    def test_no_taint_when_domains_differ(self):
        self._record(SISTER_ID, ["https://other-infra.example.com/x"])
        reject_records = [{"id": SISTER_ID}]
        taint = find_cluster_taint(
            BADBLOCKER_ID, [SHARED_DOMAIN], reject_records, infra_path=self.infra_path
        )
        self.assertIsNone(taint)

    def test_self_rejection_does_not_taint_itself(self):
        self._record(BADBLOCKER_ID, [SHARED_DOMAIN])
        reject_records = [{"id": BADBLOCKER_ID}]
        taint = find_cluster_taint(
            BADBLOCKER_ID, [SHARED_DOMAIN], reject_records, infra_path=self.infra_path
        )
        self.assertIsNone(taint)

    def test_benign_shared_domain_does_not_taint(self):
        # 둘 다 googleapis를 쓰는 건 연관 근거가 아님
        self._record(SISTER_ID, ["https://fonts.googleapis.com/css"])
        reject_records = [{"id": SISTER_ID}]
        taint = find_cluster_taint(
            BADBLOCKER_ID,
            ["https://fonts.googleapis.com/css"],
            reject_records,
            infra_path=self.infra_path,
        )
        self.assertIsNone(taint)

    def test_record_signals_accumulates_across_versions(self):
        self._record(SISTER_ID, ["https://a.example.com/x"])
        self._record(SISTER_ID, ["https://b.example.com/y"])  # 새 버전, 도메인 교체
        reject_records = [{"id": SISTER_ID}]
        # 과거 버전 도메인과의 연관도 유지되어야 함
        taint = find_cluster_taint(
            BADBLOCKER_ID, ["a.example.com"], reject_records, infra_path=self.infra_path
        )
        self.assertIsNotNone(taint)


if __name__ == "__main__":
    unittest.main()
